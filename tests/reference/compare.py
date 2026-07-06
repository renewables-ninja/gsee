"""
Tolerance-based comparison of model results against reference data.

Two tolerance profiles:

- "exact": regression guard for the current implementation.
- "physical": a physically equivalent tolerance level for new implementations.

"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Tolerances:
    # PV output, normalized by installed capacity where noted
    energy_rtol: float  # relative difference in total energy over the period
    rmse_frac: float  # per-step RMSE as fraction of capacity
    p995_frac: float  # 99.5th percentile abs per-step deviation, fraction of capacity
    aux_atol: float | None  # tight check on auxiliary columns (None to skip)
    # Solar angles. Elevation/azimuth are compared on steps both sides
    # agree are fully sunlit; partial (sunrise/sunset) steps get their
    # own looser bound, since their midpoints legitimately move with
    # the rise/set times and the output-level metrics above hold the
    # line on what that does to energy.
    elevation_deg: float  # max abs deviation, full steps with ref elevation > -1
    elevation_partial_deg: float  # max abs deviation on partial steps
    azimuth_deg: float  # max abs deviation, full steps with ref elevation > 1
    # The risen-fraction and rise/set metrics are computed over
    # well-conditioned days only: days whose solar elevation clearly
    # brackets the horizon (max >= 3 deg and min <= -3 deg). On polar
    # grazing days the crossing is so shallow that rise/set timing is
    # ill-conditioned and legitimately differs by minutes between
    # methods; the energy consequence of those days is negligible and
    # remains covered by the output metrics, which include every day.
    risen_fraction_p995: float  # 99.5th percentile abs deviation
    rise_set_seconds_p99: float  # 99th pct abs deviation, matched events
    rise_set_unmatched: int  # events with no counterpart within 6 h
    # If True, the three metrics above are reported but not enforced
    # for sites polewards of POLAR_REFERENCE_LATITUDE: the reference
    # data's rise/set times come from the iterative SPA appendix
    # method, whose accuracy degrades to minutes at extreme latitudes
    # (verified by evaluating the true solar elevation at the disputed
    # event times — see the phase 2 notes in the plan). Output metrics
    # remain fully enforced at all latitudes.
    polar_informational: bool


PROFILES = {
    "exact": Tolerances(
        energy_rtol=1e-7,
        rmse_frac=1e-6,
        p995_frac=1e-6,
        aux_atol=1e-4,
        elevation_deg=1e-5,
        elevation_partial_deg=1e-5,
        azimuth_deg=1e-5,
        risen_fraction_p995=1e-5,
        rise_set_seconds_p99=1e-3,
        rise_set_unmatched=0,
        polar_informational=False,
    ),
    "physical": Tolerances(
        energy_rtol=0.005,
        rmse_frac=0.01,
        p995_frac=0.05,
        aux_atol=None,
        elevation_deg=0.05,
        elevation_partial_deg=0.5,
        azimuth_deg=0.1,
        risen_fraction_p995=0.05,
        # The reference's own rise/set times deviate from the true
        # -0.8333 deg crossing by up to ~2 min at mid-latitudes for
        # events far from 0h UT, so this cannot be tighter
        rise_set_seconds_p99=180.0,
        rise_set_unmatched=6,
        polar_informational=True,
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


_EVENT_MATCH_WINDOW = 6 * 3600.0  # seconds

#: Polewards of this latitude, rise/set and risen-fraction metrics are
#: informational in profiles with `polar_informational` set
POLAR_REFERENCE_LATITUDE = 70.0

#: Days count as well-conditioned for rise/set comparison when the
#: solar elevation clearly brackets the horizon
_CONDITIONING_ELEVATION = 3.0  # degrees


def _event_seconds(col, good_days):
    """Sunrise/sunset column to sorted unix seconds on well-conditioned days."""
    events = pd.DatetimeIndex(col.dropna())
    events = events[events.normalize().isin(good_days)]
    return np.sort(events.as_unit("ns").asi8) / 1e9


def _matched_event_diff(new_col, ref_col, good_days):
    """
    Match sunrise (or sunset) events between two frames by proximity —
    NOT by calendar day or timestep row, either of which misattributes
    events that drift across a UTC midnight or timestep boundary (e.g.
    Kathmandu's sunrises cross UTC midnight in April). Returns (sorted
    array of matched |diff| in seconds, count of unmatched events).

    """
    new_events = _event_seconds(new_col, good_days)
    ref_events = _event_seconds(ref_col, good_days)
    unmatched = 0
    diffs = np.array([])
    if len(new_events) == 0 or len(ref_events) == 0:
        return diffs, len(new_events) + len(ref_events)
    for a, b in ((new_events, ref_events), (ref_events, new_events)):
        nearest = np.searchsorted(b, a)
        candidates = np.stack(
            [b[np.clip(nearest - 1, 0, len(b) - 1)], b[np.clip(nearest, 0, len(b) - 1)]]
        )
        seconds = np.abs(candidates - a).min(axis=0)
        matched = seconds <= _EVENT_MATCH_WINDOW
        unmatched += int((~matched).sum())
        if a is new_events:
            diffs = np.sort(seconds[matched])
    return diffs, unmatched


def angle_metrics(new, ref):
    """
    Deviation metrics for a sun angles frame (columns
    apparent_elevation, azimuth, risen_fraction in degrees/fractions,
    sunrise/sunset as datetimes) against its reference.

    Sunrise/sunset events are matched by proximity (see
    `_matched_event_diff`), so an event drifting across a timestep or
    calendar-day boundary is measured as a small time difference
    rather than a spurious missing/extra event.

    """
    assert new.index.equals(ref.index), "Indices must match"

    ref_rf = ref["risen_fraction"].fillna(0)
    new_rf = new["risen_fraction"].fillna(0)
    full = (ref_rf >= 1) & (new_rf >= 1)
    partial = (ref_rf > 0) & (ref_rf < 1) & (new_rf > 0) & (new_rf < 1)
    near_horizon = ref["apparent_elevation"] > -1.0
    sun_up = ref["apparent_elevation"] > 1.0

    elev_diff = (new["apparent_elevation"] - ref["apparent_elevation"]).abs()
    azim_diff = ((new["azimuth"] - ref["azimuth"] + 180.0) % 360.0 - 180.0).abs()
    risen_diff = (new_rf - ref_rf).abs()

    def _masked_max(series, mask):
        return float(series[mask].max()) if mask.any() else 0.0

    daily_elevation = ref["apparent_elevation"].resample("1D")
    well_conditioned = (daily_elevation.max() >= _CONDITIONING_ELEVATION) & (
        daily_elevation.min() <= -_CONDITIONING_ELEVATION
    )
    good_days = well_conditioned.index[well_conditioned]
    good_steps = new.index.normalize().isin(good_days)

    metrics = {
        "elevation_deg": _masked_max(elev_diff, full & near_horizon),
        "elevation_partial_deg": _masked_max(elev_diff, partial),
        "azimuth_deg": _masked_max(azim_diff, full & sun_up),
        "risen_fraction_p995": (
            float(np.quantile(risen_diff[good_steps], 0.995))
            if good_steps.any()
            else 0.0
        ),
    }

    seconds_p99 = 0.0
    unmatched_total = 0
    for col in ("sunrise", "sunset"):
        diffs, unmatched = _matched_event_diff(new[col], ref[col], good_days)
        unmatched_total += unmatched
        if len(diffs) > 0:
            seconds_p99 = max(seconds_p99, float(np.quantile(diffs, 0.99)))
    metrics["rise_set_seconds_p99"] = seconds_p99
    metrics["rise_set_unmatched"] = unmatched_total

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


def check_angles(new, ref, profile, lat=None):
    """
    Compare sun angles against the reference frame. Returns (ok,
    report). Pass the site latitude to enable the polar-informational
    handling of rise/set metrics (see Tolerances).

    """
    tol = PROFILES[profile]
    metrics = angle_metrics(new, ref)
    limits = {
        "elevation_deg": tol.elevation_deg,
        "elevation_partial_deg": tol.elevation_partial_deg,
        "azimuth_deg": tol.azimuth_deg,
        "risen_fraction_p995": tol.risen_fraction_p995,
        "rise_set_seconds_p99": tol.rise_set_seconds_p99,
        "rise_set_unmatched": tol.rise_set_unmatched,
    }
    informational = []
    if (
        tol.polar_informational
        and lat is not None
        and abs(lat) > POLAR_REFERENCE_LATITUDE
    ):
        informational = [
            "risen_fraction_p995",
            "rise_set_seconds_p99",
            "rise_set_unmatched",
        ]
        for key in informational:
            del limits[key]
    ok, lines = _evaluate(metrics, limits)
    for key in informational:
        lines.append(
            "  info {}: {:.3e} (not enforced polewards of {} deg)".format(
                key, metrics[key], POLAR_REFERENCE_LATITUDE
            )
        )
    return ok, "profile={}\n{}".format(profile, "\n".join(lines))
