"""
Tests for the rebuilt climate data interface (gsee.climate +
gsee.core.synthesis).

The tests check structural equivalences (monthly/annual runs must
equal daily runs over their representative days; grid runs must equal
stacked site runs), conservation properties (the diurnal profile
preserves daily means; PDF sampling preserves step means), and
plausibility.

"""

import pathlib

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from gsee import climate
from gsee.core import synthesis

SITES = {"zurich": (47.36, 8.55), "cape_town": (-33.9, 18.4)}
# Sites that exercise the two diurnal_profile branches the fixtures above
# never reach: a sunlit window wrapping past midnight UTC, and the polar
# fallback where the sun neither rises nor sets.
PACIFIC_SITE = (-45.9, 170.5)  # Dunedin, NZ -- solar noon near 00:38 UTC
POLAR_SITE = (78.25, 15.5)  # Svalbard -- midnight sun / polar night
PARAMS = {"tilt": 30, "azim": 180, "tracking": 0, "capacity": 1000.0}

LATS = np.array([lat for lat, _ in SITES.values()])
LONS = np.array([lon for _, lon in SITES.values()])


def _synthetic_pdfs():
    return xr.Dataset(
        {
            "xk": (
                ("month", "lat", "lon", "bin"),
                np.broadcast_to([50.0, 150.0, 300.0], (12, 2, 2, 3)).copy(),
            ),
            "pk": (
                ("month", "lat", "lon", "bin"),
                np.broadcast_to([0.3, 0.4, 0.3], (12, 2, 2, 3)).copy(),
            ),
        },
        coords={
            "month": np.arange(1, 13),
            "lat": [47.0, -34.0],
            "lon": [8.0, 18.0],
        },
    )


def _dataset(times, ghi, temperature=25.0):
    ghi = np.broadcast_to(np.asarray(ghi, dtype=float), (len(times), len(LATS)))
    return xr.Dataset(
        {
            "global_horizontal": (("time", "site"), ghi.copy()),
            "temperature": (
                ("time", "site"),
                np.full((len(times), len(LATS)), temperature),
            ),
        },
        coords={
            "time": times,
            "site": list(SITES),
            "lat": ("site", LATS),
            "lon": ("site", LONS),
        },
    )


class TestSynthesis:
    def test_diurnal_profile_preserves_daily_mean(self):
        days = pd.date_range("2019-06-01", periods=5, freq="D").values
        daily_mean = np.array([[200.0, 150.0]] * 5)
        times, hourly = synthesis.diurnal_profile(daily_mean, days, LATS, LONS)
        assert hourly.shape == (120, 2)
        assert len(times) == 120
        np.testing.assert_allclose(
            hourly.reshape(5, 24, 2).mean(axis=1), daily_mean, rtol=1e-12
        )

    def test_diurnal_profile_zero_at_night(self):
        days = pd.date_range("2019-06-01", periods=1, freq="D").values
        _, hourly = synthesis.diurnal_profile(
            np.array([[200.0, 200.0]]), days, LATS, LONS
        )
        # Zurich, June: no sun around midnight UTC
        assert hourly[0, 0] == 0.0
        assert (hourly[:, 0] > 0).sum() < 24

    def test_diurnal_profile_handles_zero_and_nan(self):
        days = pd.date_range("2019-06-01", periods=1, freq="D").values
        _, hourly = synthesis.diurnal_profile(
            np.array([[0.0, np.nan]]), days, LATS, LONS
        )
        assert (hourly[:, 0] == 0).all()
        assert np.isnan(hourly[:, 1]).all()

    def test_sample_from_pdfs(self):
        xk = np.array([[1.0, 2.0, 3.0], [5.0, 6.0, 7.0]])
        pk = np.array([[0.25, 0.5, 0.25], [0.0, 0.0, 0.0]])
        values = synthesis.sample_from_pdfs(xk, pk, 10000, np.random.default_rng(1))
        assert values.shape == (10000, 2)
        assert set(np.unique(values[:, 0])) <= {1.0, 2.0, 3.0}
        # Zero-probability site draws zeros
        assert (values[:, 1] == 0).all()
        assert abs((values[:, 0] == 2.0).mean() - 0.5) < 0.02


class TestClearness:
    def test_hourly_clearness_index(self):
        times = pd.date_range("2019-06-01", periods=24, freq="1h").values
        ghi = np.zeros((24, 2))
        ghi[10:14, :] = 400.0
        clearness = climate.hourly_clearness_index(ghi, times, LATS, LONS)
        assert np.isnan(clearness[0, 0])  # night / zero input
        assert 0.0 < clearness[12, 0] <= 1.0


class TestRunClimate:
    def test_daily(self):
        times = pd.date_range("2019-06-01", periods=10, freq="D")
        result = climate.run_climate(_dataset(times, 220.0), **PARAMS)
        pv = result["pv"].to_numpy()
        assert result["pv"].attrs["unit"] == "Wh/day"
        assert pv.shape == (10, 2)
        assert (pv > 0).all()
        assert (pv < 1000.0 * 24).all()

    def test_monthly_equals_daily_on_representative_days(self):
        times = pd.date_range("2019-01-01", periods=12, freq="MS")
        ghi = np.linspace(80, 260, 12)[:, None]
        monthly = climate.run_climate(_dataset(times, ghi), **PARAMS)

        from calendar import monthrange

        mid_days = pd.DatetimeIndex(
            [
                pd.Timestamp(t.year, t.month, monthrange(t.year, t.month)[1] // 2)
                for t in times
            ]
        )
        daily = climate.run_climate(_dataset(mid_days, ghi), frequency="D", **PARAMS)
        np.testing.assert_allclose(
            monthly["pv"].to_numpy(), daily["pv"].to_numpy(), rtol=1e-12
        )

    def test_annual_equals_mean_of_equinox_days(self):
        times = pd.DatetimeIndex([pd.Timestamp("2019-01-01")])
        annual = climate.run_climate(_dataset(times, 180.0), frequency="A", **PARAMS)
        equinox_days = pd.DatetimeIndex(["2019-03-31", "2019-09-30"])
        daily = climate.run_climate(
            _dataset(equinox_days, 180.0), frequency="D", **PARAMS
        )
        np.testing.assert_allclose(
            annual["pv"].to_numpy()[0],
            daily["pv"].to_numpy().mean(axis=0),
            rtol=1e-12,
        )

    def test_hourly_with_diffuse_fraction_equals_run_sites(self):
        from gsee import api, synthetic

        frames = {
            name: synthetic.synthetic_weather(lat, lon, seed=3)
            for name, (lat, lon) in SITES.items()
        }
        index = next(iter(frames.values())).index.tz_localize(None)
        ds = xr.Dataset(
            {
                var: (
                    ("time", "site"),
                    np.stack([f[var].to_numpy() for f in frames.values()], axis=1),
                )
                for var in ("global_horizontal", "diffuse_fraction", "temperature")
            },
            coords={
                "time": index,
                "site": list(SITES),
                "lat": ("site", LATS),
                "lon": ("site", LONS),
            },
        )
        via_climate = climate.run_climate(ds, **PARAMS)
        via_run_sites = api.run_sites(ds, **PARAMS)
        assert via_climate["pv"].attrs["unit"] == "Wh"
        np.testing.assert_array_equal(
            via_climate["pv"].to_numpy(), via_run_sites["pv"].to_numpy()
        )

    def test_hourly_without_diffuse_fraction_uses_brl(self):
        times = pd.date_range("2019-06-01", periods=3 * 24, freq="1h")
        day_shape = np.clip(np.sin(np.pi * (times.hour.to_numpy() - 5) / 14), 0, None)
        ghi = np.tile(600.0 * day_shape[:, None], (1, 2))
        ds = _dataset(times, 0.0)
        ds["global_horizontal"].values[:] = ghi
        result = climate.run_climate(ds, **PARAMS)
        pv = result["pv"].to_numpy()
        assert (pv[ghi[:, 0] == 0.0] == 0.0).all()
        assert pv.max() > 0
        assert pv.max() <= 1000.0

    def test_pdf_sampling(self):
        times = pd.date_range("2019-01-01", periods=12, freq="MS")
        pdfs = _synthetic_pdfs()
        data = _dataset(times, 180.0)
        first = climate.run_climate(data, pdfs=pdfs, seed=7, **PARAMS)
        again = climate.run_climate(data, pdfs=pdfs, seed=7, **PARAMS)
        other = climate.run_climate(data, pdfs=pdfs, seed=8, **PARAMS)
        np.testing.assert_array_equal(first["pv"].to_numpy(), again["pv"].to_numpy())
        assert not np.array_equal(first["pv"].to_numpy(), other["pv"].to_numpy())
        assert np.isfinite(first["pv"].to_numpy()).all()
        assert (first["pv"].to_numpy() > 0).all()

    def test_grid_input(self):
        times = pd.date_range("2019-01-01", periods=3, freq="MS")
        grid = xr.Dataset(
            {
                "global_horizontal": (
                    ("time", "lat", "lon"),
                    np.full((3, 2, 2), 150.0),
                )
            },
            coords={"time": times, "lat": [40.0, 50.0], "lon": [0.0, 10.0]},
        )
        result = climate.run_climate(grid, **PARAMS)
        assert result["pv"].dims == ("time", "lat", "lon")
        assert result["pv"].shape == (3, 2, 2)
        stacked = climate.run_climate(grid.stack(site=("lat", "lon")), **PARAMS)
        np.testing.assert_array_equal(
            result["pv"].to_numpy().reshape(3, 4), stacked["pv"].to_numpy()
        )


class TestBuiltinPdfs:
    def test_builtin_pdfs_load(self):
        pdfs = climate.builtin_pdfs()
        assert {"xk", "pk"} <= set(pdfs.data_vars)
        assert {"month", "lat", "lon"} <= set(pdfs.dims)
        assert pdfs["month"].to_numpy().tolist() == list(range(1, 13))

    def test_run_with_builtin_pdfs(self):
        data = _dataset(pd.date_range("2019-01-01", periods=3, freq="MS"), 180.0)
        first = climate.run_climate(data, pdfs="builtin", seed=1, **PARAMS)
        second = climate.run_climate(data, pdfs="builtin", seed=1, **PARAMS)
        np.testing.assert_array_equal(first["pv"].to_numpy(), second["pv"].to_numpy())
        assert np.isfinite(first["pv"].to_numpy()).all()
        assert (first["pv"].to_numpy() > 0).all()

    def test_version_resolves_from_metadata(self):
        # The companion package declares its version only in its pyproject.toml
        # (which the release workflow checks against the git tag) and reads it
        # back via importlib.metadata, so the two cannot drift. What can break
        # is that lookup itself -- e.g. renaming the distribution, which would
        # silently degrade __version__ to "unknown" -- so assert it resolves.
        # (The equality check below cannot fail under pixi, which re-syncs the
        # environment from pyproject.toml before running; it only bites on a
        # stale non-pixi install.)
        import tomllib

        import gsee_climate_data

        assert gsee_climate_data.__version__ != "unknown"

        pyproject = (
            pathlib.Path(__file__).parents[1]
            / "packages"
            / "gsee-climate-data"
            / "pyproject.toml"
        )
        if not pyproject.exists():  # installed without the source tree alongside
            pytest.skip("companion package source not available")
        declared = tomllib.loads(pyproject.read_text())["project"]["version"]
        assert gsee_climate_data.__version__ == declared

    def test_missing_data_package_raises(self, monkeypatch):
        import sys

        monkeypatch.setitem(sys.modules, "gsee_climate_data", None)
        with pytest.raises(ImportError, match=r"gsee\[climate\]"):
            climate.builtin_pdfs()

    def test_user_supplied_pdf_file(self, tmp_path):
        pytest.importorskip("h5netcdf")
        path = tmp_path / "pdfs.nc"
        _synthetic_pdfs().to_netcdf(path, engine="h5netcdf")
        data = _dataset(pd.date_range("2019-01-01", periods=3, freq="MS"), 180.0)
        from_file = climate.run_climate(data, pdfs=path, seed=1, **PARAMS)
        from_dataset = climate.run_climate(
            data, pdfs=_synthetic_pdfs(), seed=1, **PARAMS
        )
        np.testing.assert_array_equal(
            from_file["pv"].to_numpy(), from_dataset["pv"].to_numpy()
        )


class TestGlobalCoverage:
    """
    Coverage for the `core.synthesis.diurnal_profile` branches that only
    trigger far from Greenwich or inside the polar circles -- i.e. most of
    the Americas and Asia, and every high-latitude cell of a global grid.
    """

    def test_diurnal_profile_wraps_past_midnight_utc(self):
        lat, lon = np.array([PACIFIC_SITE[0]]), np.array([PACIFIC_SITE[1]])
        days = pd.date_range("2019-06-01", periods=1, freq="D").values
        _, hourly = synthesis.diurnal_profile(np.array([[200.0]]), days, lat, lon)
        profile = hourly[:, 0]
        sunlit = np.flatnonzero(profile > 0)
        # The window straddles midnight UTC: lit at both ends of the day...
        assert sunlit.min() == 0
        assert sunlit.max() == 23
        # ...and dark through the middle, which is local night in New Zealand
        assert not profile[8:16].any()
        # Peak at solar noon, which at 170.5 deg east falls just after 00:00 UTC
        assert int(np.argmax(profile)) == 0
        # Southern-hemisphere midwinter at 45.9 deg S: a short day
        assert 8 <= len(sunlit) <= 10
        np.testing.assert_allclose(profile.mean(), 200.0, rtol=1e-12)

    def test_diurnal_profile_polar_fallback(self):
        lat, lon = np.array([POLAR_SITE[0]]), np.array([POLAR_SITE[1]])
        summer_day = pd.date_range("2019-06-21", periods=1, freq="D").values
        winter_day = pd.date_range("2019-12-21", periods=1, freq="D").values
        _, summer = synthesis.diurnal_profile(np.array([[200.0]]), summer_day, lat, lon)
        _, winter = synthesis.diurnal_profile(np.array([[200.0]]), winter_day, lat, lon)
        for profile in (summer[:, 0], winter[:, 0]):
            # No sunrise/sunset to anchor to, so the mean is spread over the
            # whole day; the normalisation still preserves it exactly
            assert (profile > 0).sum() == 24
            np.testing.assert_allclose(profile.mean(), 200.0, rtol=1e-12)
        # KNOWN LIMITATION (core/synthesis.py, the NaN rise/set fallback):
        # midnight sun and polar night are indistinguishable to the fallback,
        # since both return NaN, so a December day at Svalbard is spread as if
        # the sun were up even though it stays ~12 deg below the horizon. Real
        # polar-night irradiance is ~0, so this is harmless for real data, but
        # a non-zero input is not zeroed out. Pinned here so any future change
        # to that behaviour is a deliberate one.
        np.testing.assert_array_equal(summer[:, 0], winter[:, 0])

    def test_diurnal_profile_zero_at_night_across_longitudes(self):
        # Sweep the globe: wherever the profile is non-zero the sun must be up
        lons = np.arange(-180.0, 180.0, 30.0)
        lats = np.full_like(lons, 40.0)
        days = pd.date_range("2019-03-21", periods=1, freq="D").values
        times, hourly = synthesis.diurnal_profile(
            np.full((1, len(lons)), 200.0), days, lats, lons
        )
        from gsee.core import solarposition

        elevation = solarposition.solar_position(
            np.asarray(times, dtype="datetime64[ns]"), lats, lons
        )["apparent_elevation"]
        lit = hourly > 0
        # Allow the hour containing sunrise/sunset to straddle the horizon
        assert (elevation[lit] > -15.0).all()
        np.testing.assert_allclose(hourly.mean(axis=0), 200.0, rtol=1e-12)


class TestPinnedMagnitudes:
    """
    Absolute checks. The rest of the climate suite is self-consistent
    (monthly vs daily, grid vs stacked), which cannot catch a systematically
    wrong diurnal profile or clearness index -- these can.
    """

    def test_hourly_clearness_index_matches_pvlib(self):
        # Independent cross-check: extraterrestrial normal irradiance from
        # pvlib times sin(apparent elevation), rather than a pinned constant.
        pvlib = pytest.importorskip("pvlib")
        times = pd.date_range("2019-06-01", periods=24, freq="1h")
        lat, lon = np.array([47.36]), np.array([8.55])
        ghi = np.zeros((24, 1))
        ghi[8:18, 0] = 500.0
        clearness = climate.hourly_clearness_index(ghi, times.values, lat, lon)

        midpoints = pd.DatetimeIndex(times + pd.Timedelta("30min")).tz_localize("UTC")
        position = pvlib.solarposition.get_solarposition(midpoints, lat[0], lon[0])
        extra_normal = pvlib.irradiance.get_extra_radiation(midpoints, method="spencer")
        horizontal = extra_normal.to_numpy() * np.sin(
            np.radians(position["apparent_elevation"].to_numpy())
        )
        with np.errstate(invalid="ignore", divide="ignore"):
            expected = np.where(
                horizontal > 0, np.clip(ghi[:, 0] / horizontal, 0.0, 1.0), 0.0
            )
        expected = np.where(ghi[:, 0] > 0, expected, np.nan)
        np.testing.assert_allclose(clearness[:, 0], expected, rtol=2e-3, equal_nan=True)

    def test_monthly_output_is_pinned(self):
        # Regression pin against silent drift in the synthesis -> PV chain.
        # Not a physical validation: the input is a synthetic ramp.
        times = pd.date_range("2019-01-01", periods=12, freq="MS")
        ghi = np.linspace(80, 260, 12)[:, None]
        result = climate.run_climate(_dataset(times, ghi), **PARAMS)
        assert result["pv"].attrs["unit"] == "Wh/day"
        expected_zurich = [
            3191.6769,
            2512.2147,
            2228.5410,
            2404.3959,
            2649.0744,
            2946.0635,
            3250.6555,
            3706.5915,
            4967.1208,
            6984.9952,
            7453.4419,
            7274.2673,
        ]
        np.testing.assert_allclose(
            result["pv"].to_numpy()[:, 0], expected_zurich, rtol=1e-6
        )

    def test_seasonal_frequency_runs(self):
        times = pd.date_range("2019-01-01", periods=4, freq="QS-DEC")
        result = climate.run_climate(_dataset(times, 180.0), **PARAMS)
        pv = result["pv"].to_numpy()
        assert pv.shape == (4, 2)
        assert np.isfinite(pv).all()
        assert (pv > 0).all()


class TestRawDataAndLegacyPredictors:
    def test_include_raw_data_on_coarse_input_raises(self):
        # Coarse input synthesises its own hourly irradiance and aggregates
        # it away, so there is no per-timestep raw data to return
        times = pd.date_range("2019-01-01", periods=3, freq="MS")
        with pytest.raises(ValueError, match="only available for hourly input"):
            climate.run_climate(_dataset(times, 180.0), include_raw_data=True, **PARAMS)

    def test_include_raw_data_without_diffuse_fraction_raises(self):
        times = pd.date_range("2019-06-01", periods=48, freq="1h")
        with pytest.raises(ValueError, match="diffuse_fraction"):
            climate.run_climate(_dataset(times, 300.0), include_raw_data=True, **PARAMS)

    def test_include_raw_data_with_diffuse_fraction_returns_raw_variables(self):
        times = pd.date_range("2019-06-01", periods=48, freq="1h")
        data = _dataset(times, 300.0)
        data["diffuse_fraction"] = (
            ("time", "site"),
            np.full((len(times), len(LATS)), 0.4),
        )
        result = climate.run_climate(data, include_raw_data=True, **PARAMS)
        assert {"pv", "direct", "diffuse", "module_temperature"} <= set(
            result.data_vars
        )

    def test_legacy_brl_predictors_changes_results(self):
        # The sole escape hatch for reproducing v0.3 diffuse fractions
        times = pd.date_range("2019-06-01", periods=3 * 24, freq="1h")
        day_shape = np.clip(np.sin(np.pi * (times.hour.to_numpy() - 5) / 14), 0, None)
        data = _dataset(times, 0.0)
        data["global_horizontal"].values[:] = np.tile(
            600.0 * day_shape[:, None], (1, len(LATS))
        )
        corrected = climate.run_climate(data, **PARAMS)
        legacy = climate.run_climate(data, legacy_brl_predictors=True, **PARAMS)
        corrected_pv = corrected["pv"].to_numpy()
        legacy_pv = legacy["pv"].to_numpy()
        assert np.isfinite(legacy_pv).all()
        # The units fix raises the diffuse fraction, so it lowers output
        assert not np.array_equal(corrected_pv, legacy_pv)
        assert corrected_pv.sum() < legacy_pv.sum()


class TestGridDimensionNames:
    def test_cf_dimension_names_match_short_names(self):
        # gsee.climate's input is CF-conventional climate data by definition,
        # so latitude/longitude must work as well as lat/lon
        times = pd.date_range("2019-01-01", periods=3, freq="MS")

        def grid(lat_name, lon_name):
            return xr.Dataset(
                {
                    "global_horizontal": (
                        ("time", lat_name, lon_name),
                        np.full((3, 2, 2), 150.0),
                    )
                },
                coords={"time": times, lat_name: [40.0, 50.0], lon_name: [0.0, 10.0]},
            )

        short = climate.run_climate(grid("lat", "lon"), **PARAMS)
        cf = climate.run_climate(grid("latitude", "longitude"), **PARAMS)
        assert short["pv"].dims == ("time", "lat", "lon")
        assert cf["pv"].dims == ("time", "latitude", "longitude")
        np.testing.assert_array_equal(short["pv"].to_numpy(), cf["pv"].to_numpy())


class TestFrequencyDetection:
    @pytest.mark.parametrize(
        "freq,expected",
        [("MS", "M"), ("D", "D"), ("1h", "H"), ("YS", "A"), ("QS-DEC", "S")],
    )
    def test_detect_from_index(self, freq, expected):
        times = pd.date_range("2019-01-01", periods=8, freq=freq)
        data = xr.Dataset(coords={"time": times})
        assert climate.detect_frequency(data) == expected

    def test_detect_from_attribute(self):
        data = xr.Dataset(
            coords={"time": pd.DatetimeIndex(["2019-01-01"])},
            attrs={"frequency": "mon"},
        )
        assert climate.detect_frequency(data) == "M"

    def test_manual_overrides_with_warning(self):
        times = pd.date_range("2019-01-01", periods=8, freq="D")
        data = xr.Dataset(coords={"time": times})
        with pytest.warns(UserWarning, match="does not match"):
            assert climate.detect_frequency(data, "M") == "M"

    def test_undetectable_raises(self):
        data = xr.Dataset(coords={"time": pd.DatetimeIndex(["2019-01-01"])})
        with pytest.raises(ValueError, match="detect"):
            climate.detect_frequency(data)

    @pytest.mark.parametrize("frequency", ["detect", "H"])
    def test_sub_hourly_raises(self, frequency):
        # The climate interface is hourly-and-coarser only; sub-hourly
        # data with a diffuse_fraction goes directly to run_sites/run_model
        times = pd.date_range("2019-01-01", periods=48, freq="30min")
        data = xr.Dataset(coords={"time": times})
        with pytest.raises(ValueError, match="hourly and coarser"):
            climate.detect_frequency(data, frequency)

    def test_parse_cmip_time(self):
        parsed = climate.parse_cmip_time([20070104.5, 20070105.0])
        assert parsed[0] == pd.Timestamp("2007-01-04 12:00")
        assert parsed[1] == pd.Timestamp("2007-01-05 00:00")

    def test_parse_cmip_time_rounds_rather_than_truncates(self):
        # 0.9583 * 24 = 22.999...; truncating gives hour 22, rounding gives 23.
        # The cases above cannot tell the two apart, since floor and round agree
        # on exact halves and whole days.
        parsed = climate.parse_cmip_time([20500716.9583, 20500716.0417])
        assert parsed[0] == pd.Timestamp("2050-07-16 23:00")
        assert parsed[1] == pd.Timestamp("2050-07-16 01:00")

    @pytest.mark.parametrize(
        "attribute,freq,expected",
        [("yr", "YS", "A"), ("1hr", "1h", "H"), ("hour", "1h", "H")],
    )
    def test_detect_from_cmip_attribute(self, attribute, freq, expected):
        data = xr.Dataset(
            coords={"time": pd.date_range("2019-01-01", periods=8, freq=freq)},
            attrs={"frequency": attribute},
        )
        assert climate.detect_frequency(data) == expected

    @pytest.mark.parametrize("attribute", ["3hr", "6hr"])
    def test_multi_hour_frequency_rejected(self, attribute):
        # Treating these as hourly would silently mislabel the output: the
        # hourly path assumes 1-hour steps for the clearness-index midpoint,
        # the BRL lag, and the Wh-per-step unit.
        data = xr.Dataset(
            coords={"time": pd.date_range("2019-01-01", periods=8, freq="3h")},
            attrs={"frequency": attribute},
        )
        with pytest.raises(ValueError, match="not supported"):
            climate.detect_frequency(data)
