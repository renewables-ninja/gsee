"""
Tolerance-based comparison of model results against reference data.

Two tolerance profiles:

- "exact": regression guard for the current implementation.
- "physical": a physically equivalent tolerance level for new implementations.

"""

from dataclasses import dataclass

import numpy as np


@dataclass
class Tolerances:
    # PV output, normalized by installed capacity where noted
    energy_rtol: float  # relative difference in total energy over the period
    rmse_frac: float  # per-step RMSE as fraction of capacity
    p995_frac: float  # 99.5th percentile abs per-step deviation, fraction of capacity
    aux_atol: float | None  # tight check on auxiliary columns (None to skip)
    # Solar angles
    elevation_deg: float  # max abs deviation where ref elevation > -1 deg
    azimuth_deg: float  # max abs deviation where ref elevation > 1 deg
    risen_fraction_p995: float  # 99.5th percentile abs deviation
    rise_set_seconds: float  # max abs sunrise/sunset deviation
    rise_set_nullity_days: int  # days where one side has a rise/set and other NaT


PROFILES = {
    "exact": Tolerances(
        energy_rtol=1e-7,
        rmse_frac=1e-6,
        p995_frac=1e-6,
        aux_atol=1e-4,
        elevation_deg=1e-5,
        azimuth_deg=1e-5,
        risen_fraction_p995=1e-5,
        rise_set_seconds=1e-3,
        rise_set_nullity_days=0,
    ),
    "physical": Tolerances(
        energy_rtol=0.005,
        rmse_frac=0.01,
        p995_frac=0.05,
        aux_atol=None,
        elevation_deg=0.05,
        azimuth_deg=0.1,
        risen_fraction_p995=0.05,
        rise_set_seconds=120.0,
        rise_set_nullity_days=3,
    ),
}


def output_metrics(new, ref, capacity):
    """Deviation metrics for a PV output series against its reference."""
    assert new.index.equals(ref.index), "Indices must match"
    assert not new.isna().any(), "New output contains NaNs"
    assert not ref.isna().any(), "Reference output contains NaNs"
    diff = (new - ref).to_numpy()
    ref_sum = ref.sum()
    return {
        "energy_rtol": abs(new.sum() - ref_sum) / max(ref_sum, 1e-12),
        "rmse_frac": float(np.sqrt(np.mean(diff**2))) / capacity,
        "p995_frac": float(np.quantile(np.abs(diff), 0.995)) / capacity,
        "max_frac": float(np.max(np.abs(diff))) / capacity,
    }


def angle_metrics(new, ref):
    """
    Deviation metrics for a sun angles frame (columns
    apparent_elevation, azimuth, risen_fraction in degrees/fractions,
    sunrise/sunset as datetimes) against its reference.

    """
    assert new.index.equals(ref.index), "Indices must match"

    near_horizon = ref["apparent_elevation"] > -1.0
    sun_up = ref["apparent_elevation"] > 1.0

    elev_diff = (new["apparent_elevation"] - ref["apparent_elevation"]).abs()
    azim_diff = (new["azimuth"] - ref["azimuth"] + 180.0) % 360.0 - 180.0
    risen_diff = (
        new["risen_fraction"].fillna(0) - ref["risen_fraction"].fillna(0)
    ).abs()

    metrics = {
        "elevation_deg": float(elev_diff[near_horizon].max()),
        "azimuth_deg": float(azim_diff.abs()[sun_up].max()),
        "risen_fraction_p995": float(np.quantile(risen_diff, 0.995)),
    }

    rise_set_seconds = 0.0
    nullity_days = 0
    for col in ("sunrise", "sunset"):
        both = new[col].notna() & ref[col].notna()
        nullity_days += int((new[col].notna() != ref[col].notna()).sum())
        if both.any():
            seconds = (new.loc[both, col] - ref.loc[both, col]).dt.total_seconds()
            rise_set_seconds = max(rise_set_seconds, float(seconds.abs().max()))
    metrics["rise_set_seconds"] = rise_set_seconds
    metrics["rise_set_nullity_days"] = nullity_days

    return metrics


def _evaluate(metrics, limits):
    """Returns (ok, lines) comparing each metric against its limit."""
    ok = True
    lines = []
    for key, limit in limits.items():
        value = metrics[key]
        passed = value <= limit
        ok = ok and passed
        lines.append(
            "  {} {}: {:.3e} (limit {:.3e})".format(
                "PASS" if passed else "FAIL", key, value, limit
            )
        )
    return ok, lines


def check_output(new, ref, capacity, profile):
    """
    Compare model output (and, for profiles with `aux_rtol`, auxiliary
    result columns) against the reference frame. Returns (ok, report).

    """
    tol = PROFILES[profile]
    metrics = output_metrics(new["output"], ref["output"], capacity)
    limits = {
        "energy_rtol": tol.energy_rtol,
        "rmse_frac": tol.rmse_frac,
        "p995_frac": tol.p995_frac,
    }
    ok, lines = _evaluate(metrics, limits)
    lines.append("  info max_frac: {:.3e}".format(metrics["max_frac"]))

    if tol.aux_atol is not None:
        for col in ref.columns:
            if col == "output" or col not in new.columns:
                continue
            close = np.allclose(
                new[col], ref[col], rtol=0.0, atol=tol.aux_atol, equal_nan=True
            )
            ok = ok and close
            lines.append("  {} aux column {}".format("PASS" if close else "FAIL", col))

    return ok, "profile={}\n{}".format(profile, "\n".join(lines))


def check_angles(new, ref, profile):
    """Compare sun angles against the reference frame. Returns (ok, report)."""
    tol = PROFILES[profile]
    metrics = angle_metrics(new, ref)
    limits = {
        "elevation_deg": tol.elevation_deg,
        "azimuth_deg": tol.azimuth_deg,
        "risen_fraction_p995": tol.risen_fraction_p995,
        "rise_set_seconds": tol.rise_set_seconds,
        "rise_set_nullity_days": tol.rise_set_nullity_days,
    }
    ok, lines = _evaluate(metrics, limits)
    return ok, "profile={}\n{}".format(profile, "\n".join(lines))
