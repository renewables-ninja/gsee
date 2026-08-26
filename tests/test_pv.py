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


def test_sub_hourly_input(data):
    # Sub-hourly resolutions are supported as long as the input provides
    # `diffuse_fraction` (the BRL model is hourly-only)
    quarterhourly = synthetic.synthetic_weather(*COORDS, seed=99, freq="15min")
    result = pv.run_model(quarterhourly, coords=COORDS, **CONFIG)
    assert result.index.equals(quarterhourly.index)
    assert np.isfinite(result).all()
    assert (result >= 0).all() and result.max() > 0
    # Output is mean power per timestep (W), so the annual mean must be
    # resolution-independent (same seed produces the same daily clearness)
    hourly = pv.run_model(data, coords=COORDS, **CONFIG)
    assert result.mean() == pytest.approx(hourly.mean(), rel=0.05)


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


@pytest.fixture
def cold_sunny_data():
    index = pd.date_range("2019-01-15", periods=24, freq="h", tz="UTC")
    return pd.DataFrame(
        {"global_horizontal": 400.0, "diffuse_fraction": 0.2, "temperature": -15.0},
        index=index,
    )


def test_cold_relative_efficiency_exceeds_one(cold_sunny_data):
    # Efficiency above 1.0 at cold module temperatures is physically
    # expected and must not be capped by default
    result = pv.run_model(
        cold_sunny_data, coords=COORDS, include_raw_data=True, **CONFIG
    )
    assert result["relative_efficiency"].max() > 1.0


def test_clip_high_efficiency_caps_at_one(cold_sunny_data):
    capped = pv.run_model(
        cold_sunny_data,
        coords=COORDS,
        include_raw_data=True,
        temperature_correction_method="clip_high_efficiency",
        **CONFIG,
    )
    assert capped["relative_efficiency"].max() == 1.0
    uncapped = pv.run_model(cold_sunny_data, coords=COORDS, **CONFIG)
    assert (capped["output"] <= uncapped + 1e-9).all()


def test_unknown_temperature_correction_method_raises(cold_sunny_data):
    with pytest.raises(ValueError, match="temperature_correction_method"):
        pv.run_model(
            cold_sunny_data,
            coords=COORDS,
            temperature_correction_method="clip_low_temperature",
            **CONFIG,
        )


def test_all_technologies_gain_efficiency_when_cold():
    from gsee.core import panel

    for technology in ["csi", "csi-new", "cis", "cdte", "cec-csi-median"]:
        efficiency = panel.relative_efficiency(
            np.array([1000.0]), np.array([-15.0]), technology
        )
        assert efficiency[0] > 1.0, technology


def test_non_utc_index_raises(data):
    shifted = data.tz_convert("Europe/Zurich")
    with pytest.raises(ValueError, match="UTC"):
        pv.run_model(shifted, coords=COORDS, **CONFIG)


def test_angles_index_mismatch_raises(data):
    angles = api.sun_angles_frame(data.index, COORDS)
    with pytest.raises(ValueError, match="index"):
        pv.run_model(data.iloc[:-1], coords=COORDS, angles=angles, **CONFIG)


def test_missing_diffuse_fraction_raises(data):
    with pytest.raises(ValueError, match="diffuse_fraction"):
        pv.run_model(data.drop(columns=["diffuse_fraction"]), coords=COORDS, **CONFIG)


def test_missing_global_horizontal_raises(data):
    with pytest.raises(ValueError, match="global_horizontal"):
        pv.run_model(data.drop(columns=["global_horizontal"]), coords=COORDS, **CONFIG)


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
    legacy = pytest.importorskip("gsee.legacy", exc_type=ImportError)
    if kwargs.get("angles") == "duration_frame":
        kwargs["angles"] = pd.DataFrame({"duration": 60.0}, index=data.index)
    called = {}

    def fake_legacy(*args, **kw):
        called["legacy"] = True
        return pd.Series(0.0, index=data.index)

    monkeypatch.setattr(legacy, "run_model", fake_legacy)
    with pytest.warns(DeprecationWarning, match="gsee.legacy.run_model"):
        pv.run_model(data, coords=COORDS, **CONFIG, **kwargs)
    assert called


def test_huld_coefficients_match_the_core():
    # `gsee.pv`'s panel classes are no longer on the compute path -- run_model
    # goes through gsee.core -- but they remain public API until 0.5.0. Guard
    # the two copies of the Huld coefficients against drifting apart.
    from gsee.core.panel import HULD_COEFFICIENTS

    for technology, coefficients in HULD_COEFFICIENTS.items():
        panel = pv._PANEL_TYPES[technology]()
        assert (
            panel.k_1,
            panel.k_2,
            panel.k_3,
            panel.k_4,
            panel.k_5,
            panel.k_6,
        ) == coefficients, "coefficients for {} have drifted".format(technology)


def test_legacy_technologies_match_the_frozen_implementation():
    # pv.run_model validates `technology` against this set before delegating
    # to the frozen legacy code, so it must mirror what legacy actually has.
    pytest.importorskip("ephem")
    from gsee.legacy.panel import _PANEL_TYPES as legacy_types

    assert pv._LEGACY_TECHNOLOGIES == frozenset(legacy_types)


def test_albedo_is_configurable(data):
    # Ground reflectance must move output monotonically
    low = pv.run_model(data, (47.36, 8.55), 30, 180, 0, 1000.0, albedo=0.0)
    default = pv.run_model(data, (47.36, 8.55), 30, 180, 0, 1000.0)
    high = pv.run_model(data, (47.36, 8.55), 30, 180, 0, 1000.0, albedo=0.8)
    assert (low <= default + 1e-9).all()
    assert (high >= default - 1e-9).all()
    assert high.sum() > low.sum()


class TestLegacyPathGuards:
    """
    gsee.legacy is frozen at pre-0.4 behaviour, so options added in 0.4 must
    be rejected with a clear message rather than failing inside frozen code.
    """

    @pytest.fixture(autouse=True)
    def _ignore_deprecation(self):
        pytest.importorskip("ephem")

    def test_temperature_correction_method_rejected(self, data):
        with pytest.warns(DeprecationWarning):
            with pytest.raises(ValueError, match="temperature_correction_method"):
                pv.run_model(
                    data,
                    (47.36, 8.55),
                    30,
                    180,
                    0,
                    1000.0,
                    legacy_solarposition=True,
                    temperature_correction_method="clip_high_efficiency",
                )

    def test_unsupported_technology_rejected(self, data):
        with pytest.warns(DeprecationWarning):
            with pytest.raises(ValueError, match="csi-new"):
                pv.run_model(
                    data,
                    (47.36, 8.55),
                    30,
                    180,
                    0,
                    1000.0,
                    legacy_solarposition=True,
                    technology="csi-new",
                )

    def test_albedo_rejected(self, data):
        with pytest.warns(DeprecationWarning):
            with pytest.raises(ValueError, match="albedo"):
                pv.run_model(
                    data,
                    (47.36, 8.55),
                    30,
                    180,
                    0,
                    1000.0,
                    legacy_solarposition=True,
                    albedo=0.5,
                )

    def test_supported_technology_still_runs(self, data):
        with pytest.warns(DeprecationWarning):
            result = pv.run_model(
                data,
                (47.36, 8.55),
                30,
                180,
                0,
                1000.0,
                legacy_solarposition=True,
                technology="cdte",
            )
        assert len(result) == len(data)


class TestCecToolsRelativeEff:
    """
    `cec_tools.relative_eff` documents "float or pandas.Series" but only ever
    worked for Series -- scalars hit `.fillna` on a numpy float.
    """

    @pytest.fixture
    def params(self):
        return pv.CEC_PARAMETERS["Mono-c-Si-Median"]

    def test_python_float(self, params):
        from gsee import cec_tools

        assert cec_tools.relative_eff(0.0, 25.0, params) == 0.0
        value = cec_tools.relative_eff(500.0, 25.0, params)
        assert isinstance(value, float)
        assert 0.9 < value < 1.1

    def test_numpy_scalar(self, params):
        from gsee import cec_tools

        # np.float64 is a float subclass, so the `== 0` shortcut must not
        # swallow numpy scalars and return a bare int
        assert cec_tools.relative_eff(np.float64(0.0), np.float64(25.0), params) == 0.0
        value = cec_tools.relative_eff(np.float64(500.0), np.float64(25.0), params)
        assert 0.9 < float(value) < 1.1

    def test_series_keeps_index(self, params):
        from gsee import cec_tools

        index = pd.date_range("2019-06-01", periods=3, freq="1h", tz="UTC")
        irradiance = pd.Series([0.0, 500.0, 1000.0], index=index)
        result = cec_tools.relative_eff(
            irradiance, pd.Series([25.0] * 3, index=index), params
        )
        assert isinstance(result, pd.Series)
        assert result.index.equals(index)
        assert result.iloc[0] == 0.0
        assert np.isfinite(result.to_numpy()).all()

    def test_matches_scalar_and_series(self, params):
        from gsee import cec_tools

        scalar = cec_tools.relative_eff(500.0, 25.0, params)
        series = cec_tools.relative_eff(
            pd.Series([500.0]), pd.Series([25.0]), params
        ).iloc[0]
        assert scalar == pytest.approx(series)
