"""
Validation of the vectorized solar core (gsee.core.solarposition).

Three things to test:

1. Machine-precision equivalence of `solar_position` with per-site
   pvlib SPA. The time/site split must not change the numbers.
2. Broadcast consistency. Computing S sites at once must equal
   computing each site alone.
3. Physical equivalence against the committed reference data.
   Angles and the resulting PV output must stay
   within the "physical" tolerance limit.

"""

import numpy as np
import pandas as pd
import pvlib
import pytest

from gsee import api, pv
from gsee.core import solarposition
from tests.reference import cases, compare

CASES = cases.build_cases()

PRECISION_SITES = [
    (78.25, 15.5),
    (47.36, 8.55),
    (0.0, -78.5),
    (-45.9, 170.5),
    (-75.0, 123.0),
]


@pytest.fixture(scope="module")
def datetimes():
    return pd.date_range("2019-01-01", "2019-12-31 23:00", freq="1h", tz="UTC")


@pytest.mark.parametrize("site", PRECISION_SITES)
def test_solar_position_matches_pvlib(site, datetimes):
    lat, lon = site
    ref = pvlib.solarposition.get_solarposition(datetimes, lat, lon)
    new = solarposition.solar_position(datetimes, lat, lon)
    assert np.allclose(
        new["apparent_elevation"][:, 0], ref["apparent_elevation"], atol=1e-9, rtol=0
    )
    assert np.allclose(new["azimuth"][:, 0], ref["azimuth"], atol=1e-9, rtol=0)
    assert np.allclose(
        new["apparent_zenith"][:, 0], ref["apparent_zenith"], atol=1e-9, rtol=0
    )


def test_multi_site_equals_single_site(datetimes):
    lats = np.array([s[0] for s in PRECISION_SITES])
    lons = np.array([s[1] for s in PRECISION_SITES])
    combined = solarposition.sun_angles(datetimes, lats, lons)
    for i, (lat, lon) in enumerate(PRECISION_SITES):
        single = solarposition.sun_angles(datetimes, lat, lon)
        for key in ("apparent_elevation", "azimuth", "risen_fraction"):
            np.testing.assert_array_equal(combined[key][:, i], single[key][:, 0])
        for key in ("sunrise", "sunset"):
            np.testing.assert_array_equal(combined[key][:, i], single[key][:, 0])


def test_sun_rise_set_close_to_iterative_spa(datetimes):
    lat, lon = 47.36, 8.55
    days = pd.DatetimeIndex(np.asarray(datetimes.floor("D").unique()))
    ref = pvlib.solarposition.sun_rise_set_transit_spa(
        days.tz_localize("UTC") if days.tz is None else days, lat, lon
    )
    rise, set_, transit = solarposition.sun_rise_set(days.tz_localize(None), lat, lon)
    for new_col, ref_col in ((rise, "sunrise"), (set_, "sunset"), (transit, "transit")):
        new_values = pd.to_datetime(new_col[:, 0]).tz_localize("UTC")
        diff = (new_values - ref[ref_col]).dt.total_seconds().abs()
        assert diff.max() < 60, "{} differs by up to {}s".format(ref_col, diff.max())


def test_time_terms_cached():
    unixtime = np.arange(0.0, 86400.0, 3600.0) + 1.5e9
    first = solarposition.time_terms(unixtime)
    # Content-keyed: a copy of the same values hits the cache
    assert solarposition.time_terms(unixtime.copy()) is first
    assert solarposition.time_terms(unixtime, delta_t=68.0) is not first
    for i in range(2 * solarposition._TIME_TERMS_CACHE_SIZE):
        solarposition.time_terms(unixtime + (i + 1) * 60.0)
    assert len(solarposition._TIME_TERMS_CACHE) <= solarposition._TIME_TERMS_CACHE_SIZE


def test_risen_fraction_well_formed_at_polar_sites(datetimes):
    lats = np.array([78.25, 67.5, -75.0])
    lons = np.array([15.5, -21.0, 123.0])
    result = solarposition.sun_angles(datetimes, lats, lons)
    rf = result["risen_fraction"]
    assert not np.isnan(rf).any()
    assert rf.min() >= 0.0
    assert rf.max() <= 1.0
    # Sun up at (local) midday in midsummer, down at midwinter
    for i, month_up, month_down in ((0, 6, 12), (2, 12, 6)):
        up = rf[(datetimes.month == month_up), i]
        down = rf[(datetimes.month == month_down), i]
        assert up.mean() > 0.9
        assert down.max() == 0.0


@pytest.mark.reference
@pytest.mark.parametrize(
    "case_id", sorted(c for c in CASES if CASES[c]["store_angles"])
)
def test_core_angles_physically_equivalent(case_id):
    case = CASES[case_id]
    data = cases.read_frame(cases.input_path(case_id))
    angles = api.sun_angles_frame(data.index, (case["lat"], case["lon"]))
    ref = cases.read_frame(cases.angles_path(case_id))

    ok, report = compare.check_angles(angles, ref, "physical", lat=case["lat"])
    assert ok, "\n" + report


@pytest.mark.reference
@pytest.mark.parametrize(
    "case_id",
    sorted(c for c in CASES if "legacy" not in c),
)
def test_core_output_physically_equivalent(case_id):
    case = CASES[case_id]
    data = cases.read_frame(cases.input_path(case_id))
    angles = api.sun_angles_frame(data.index, (case["lat"], case["lon"]))
    result = pv.run_model(
        data,
        coords=(case["lat"], case["lon"]),
        include_raw_data=True,
        angles=angles,
        **case["params"],
    )
    ref = cases.read_frame(cases.output_path(case_id))
    capacity = case["params"]["capacity"]

    ok, report = compare.check_output(result, ref, capacity, "physical")
    assert ok, "\n" + report
