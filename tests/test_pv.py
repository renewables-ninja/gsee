"""
Tests for the core-backed single-site `pv.run_model` wrapper.

Numerical behaviour is guarded by the reference regression tests and
the multi-site equivalence tests in test_api_multisite; this covers
the wrapper semantics: input validation, NaN propagation, output
container, and routing to the frozen legacy implementation.

"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from gsee import api, pv, synthetic

COORDS = (47.36, 8.55)

CONFIG = {"tilt": 30, "azim": 180, "tracking": 0, "capacity": 1000.0}


@pytest.fixture(scope="module")
def data():
    return synthetic.synthetic_weather(*COORDS, seed=99)


def test_run_model_matches_run_sites(data):
    dataset = xr.Dataset(
        {
            var: (("time", "site"), data[var].to_numpy()[:, None])
            for var in data.columns
        },
        coords={
            "time": data.index.tz_localize(None),
            "site": ["only"],
            "lat": ("site", [COORDS[0]]),
            "lon": ("site", [COORDS[1]]),
        },
    )
    from_sites = api.run_sites(dataset, **CONFIG)["pv"].to_numpy()[:, 0]
    from_model = pv.run_model(data, coords=COORDS, **CONFIG).to_numpy()
    np.testing.assert_array_equal(from_model, from_sites)


def test_precomputed_angles_match_computed(data):
    angles = api.sun_angles_frame(data.index, COORDS)
    with_angles = pv.run_model(data, coords=COORDS, angles=angles, **CONFIG)
    without = pv.run_model(data, coords=COORDS, **CONFIG)
    np.testing.assert_array_equal(with_angles.to_numpy(), without.to_numpy())


def test_nan_input_gives_nan_output(data):
    modified = data.copy()
    modified.iloc[100:110, modified.columns.get_loc("global_horizontal")] = np.nan
    result = pv.run_model(modified, coords=COORDS, **CONFIG)
    clean = pv.run_model(data, coords=COORDS, **CONFIG)
    assert result.iloc[100:110].isna().all()
    unaffected = np.ones(len(result), dtype=bool)
    unaffected[100:110] = False
    np.testing.assert_array_equal(
        result.to_numpy()[unaffected], clean.to_numpy()[unaffected]
    )


def test_output_is_series_with_input_index(data):
    result = pv.run_model(data, coords=COORDS, **CONFIG)
    assert isinstance(result, pd.Series)
    assert result.index.equals(data.index)


def test_include_raw_data_columns(data):
    result = pv.run_model(data, coords=COORDS, include_raw_data=True, **CONFIG)
    assert list(result.columns) == [
        "output",
        "direct",
        "diffuse",
        "temperature",
        "module_temperature",
        "relative_efficiency",
    ]
    np.testing.assert_array_equal(
        result["temperature"].to_numpy(), data["temperature"].to_numpy()
    )


def test_non_utc_index_raises(data):
    shifted = data.tz_convert("Europe/Zurich")
    with pytest.raises(ValueError, match="UTC"):
        pv.run_model(shifted, coords=COORDS, **CONFIG)


def test_angles_index_mismatch_raises(data):
    angles = api.sun_angles_frame(data.index, COORDS)
    with pytest.raises(ValueError, match="index"):
        pv.run_model(data.iloc[:-1], coords=COORDS, angles=angles, **CONFIG)


def test_invalid_system_loss_raises(data):
    with pytest.raises(ValueError, match="system_loss"):
        pv.run_model(data, coords=COORDS, system_loss=1.5, **CONFIG)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"legacy_solarposition": True},
        {"angles": "duration_frame"},
    ],
)
def test_routes_to_legacy_implementation(data, monkeypatch, kwargs):
    if kwargs.get("angles") == "duration_frame":
        kwargs["angles"] = pd.DataFrame({"duration": 60.0}, index=data.index)
    called = {}

    def fake_legacy(*args, **kw):
        called["legacy"] = True
        return pd.Series(0.0, index=data.index)

    monkeypatch.setattr(pv, "_run_model_legacy", fake_legacy)
    pv.run_model(data, coords=COORDS, **CONFIG, **kwargs)
    assert called
