"""
Validation of the vectorized BRL model (gsee.core.diffuse).

Its `legacy_predictors=True` mode is compared against the unchanged
ephem-based implementation (gsee.legacy.brl_model), which is kept as
the legacy reference (test skipped when the optional ephem dependency
is missing). Bit-identical results are impossible, so the comparison
is tolerance-based, with the tolerances pinned from measured
behaviour. Deviations at the 1e-3 level are accepted except for the
handful of hours where the persistence branch flips.

The corrected default mode has no independent reference
implementation, so it is validated structurally. Its logit must differ
from the legacy mode's by exactly the two intended predictor
corrections (solar time radians -> hours, midnight radian altitude ->
hourly degree altitude). The resulting diffuse-fraction shift must
match the documented magnitude.

"""

import numpy as np
import pandas as pd
import pytest

from gsee.core import diffuse, solarposition

SITES = {"zurich": (47.36, 8.55), "cape_town": (-33.9, 18.4)}


def _synthetic_clearness(index, seed):
    rng = np.random.default_rng(seed)
    hour = index.hour.to_numpy()
    day_shape = np.sin(np.pi * (hour - 5) / 14)
    clearness = np.clip(
        0.45 + 0.3 * day_shape + 0.15 * rng.normal(size=len(index)), 0.02, 1.0
    )
    return np.where((hour >= 5) & (hour <= 19), clearness, np.nan)


@pytest.fixture(scope="module")
def clearness_index():
    return pd.date_range("2019-01-01", "2019-12-31 23:00", freq="1h")


@pytest.mark.parametrize("site", sorted(SITES))
def test_legacy_mode_matches_legacy_implementation(site, clearness_index):
    brl_model = pytest.importorskip("gsee.legacy.brl_model", exc_type=ImportError)
    lat, lon = SITES[site]
    clearness = _synthetic_clearness(clearness_index, seed=42)
    legacy = brl_model.run(pd.Series(clearness, index=clearness_index), (lat, lon))
    vectorized = diffuse.brl_diffuse_fraction(
        clearness[:, None], clearness_index, lat, lon, legacy_predictors=True
    )[:, 0]

    legacy_values = legacy.to_numpy()
    assert np.array_equal(np.isnan(vectorized), np.isnan(legacy_values))

    diff = np.abs(vectorized - legacy_values)
    valid = ~np.isnan(diff)
    # Measured 2026-07: mean <= 9.2e-5, p99 = 0.0; the only deviations
    # are persistence-branch flips on days where the two
    # sunrise/sunset sources disagree on the event hour (<= 0.034% of
    # hours, individually up to ~0.2)
    assert np.nanquantile(diff, 0.99) < 1e-4
    assert np.nanmean(diff) < 5e-4
    assert np.nanmax(diff) < 0.5
    assert (diff[valid] > 0.05).mean() < 0.002


@pytest.mark.parametrize("site", sorted(SITES))
def test_corrected_mode_applies_exactly_the_two_fixes(site, clearness_index):
    """
    The corrected and legacy logits must differ by exactly
    b1*(AST_hours - AST_radians) + b2*(alpha_hourly_deg - alpha_midnight_rad).

    """
    lat, lon = SITES[site]
    clearness = _synthetic_clearness(clearness_index, seed=42)
    corrected = diffuse.brl_diffuse_fraction(
        clearness[:, None], clearness_index, lat, lon
    )[:, 0]
    legacy = diffuse.brl_diffuse_fraction(
        clearness[:, None], clearness_index, lat, lon, legacy_predictors=True
    )[:, 0]

    unixtime = solarposition._to_unixtime(clearness_index)
    terms = solarposition.time_terms(unixtime)
    hour_angle = (terms["v"] + lon - terms["alpha"]) % 360.0
    delta_solar_time = (hour_angle / 15.0 + 12.0) % 24.0 - np.radians(
        (hour_angle + 180.0) % 360.0
    )
    hourly_altitude = solarposition.solar_position(clearness_index, lat, lon)[
        "apparent_elevation"
    ][:, 0]
    day_starts = (unixtime.reshape(-1, 24)[:, 0] * 1e9).astype("datetime64[ns]")
    midnight_altitude = np.repeat(
        np.radians(
            solarposition.solar_position(day_starts, lat, lon)["apparent_elevation"]
        )[:, 0],
        24,
    )

    params = diffuse.DEFAULT_PARAMS
    expected = params["b1"] * delta_solar_time + params["b2"] * (
        hourly_altitude - midnight_altitude
    )
    with np.errstate(invalid="ignore"):
        logit_difference = np.log(1 / corrected - 1) - np.log(1 / legacy - 1)
    valid = ~np.isnan(logit_difference)
    np.testing.assert_allclose(
        logit_difference[valid], expected[valid], rtol=1e-9, atol=1e-9
    )


def test_corrected_predictors_raise_diffuse_fraction(clearness_index):
    lat, lon = SITES["zurich"]
    clearness = _synthetic_clearness(clearness_index, seed=42)
    corrected = diffuse.brl_diffuse_fraction(
        clearness[:, None], clearness_index, lat, lon
    )
    legacy = diffuse.brl_diffuse_fraction(
        clearness[:, None], clearness_index, lat, lon, legacy_predictors=True
    )
    shift = np.nanmean(corrected - legacy)
    # The corrected predictor units raise the mean diffuse fraction by
    # ~+0.06 (see gsee.core.diffuse docstring)
    assert 0.03 < shift < 0.10


def test_brl_multi_site_equals_single(clearness_index):
    clearness = np.stack(
        [_synthetic_clearness(clearness_index, seed=s) for s in (1, 2)], axis=1
    )
    lats = np.array([SITES["zurich"][0], SITES["cape_town"][0]])
    lons = np.array([SITES["zurich"][1], SITES["cape_town"][1]])
    combined = diffuse.brl_diffuse_fraction(clearness, clearness_index, lats, lons)
    for i in range(2):
        single = diffuse.brl_diffuse_fraction(
            clearness[:, [i]], clearness_index, lats[i], lons[i]
        )
        # Not exactly equal: numpy reduction order in the daily mean
        # depends on array shape, giving 1-ulp differences
        np.testing.assert_allclose(combined[:, i], single[:, 0], rtol=1e-12, atol=1e-12)


def test_brl_rejects_non_hourly(clearness_index):
    half_hourly = pd.date_range("2019-01-01", periods=96, freq="30min")
    with pytest.raises(ValueError, match="hourly"):
        diffuse.brl_diffuse_fraction(np.zeros((96, 1)), half_hourly, 47.0, 8.0)
