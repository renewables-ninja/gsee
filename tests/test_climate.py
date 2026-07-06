"""
Tests for the rebuilt climate data interface (gsee.climate +
gsee.core.synthesis).

The tests check structural equivalences (monthly/annual runs must
equal daily runs over their representative days; grid runs must equal
stacked site runs), conservation properties (the diurnal profile
preserves daily means; PDF sampling preserves step means), and
plausibility.

"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from gsee import climate
from gsee.core import synthesis

SITES = {"zurich": (47.36, 8.55), "cape_town": (-33.9, 18.4)}
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
        # Zero-probability site draws zeros, as in v0.3
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

    def test_missing_data_package_raises(self, monkeypatch):
        import sys

        monkeypatch.setitem(sys.modules, "gsee_climate_data", None)
        with pytest.raises(ImportError, match=r"gsee\[climate\]"):
            climate.builtin_pdfs()

    def test_user_supplied_pdf_file(self, tmp_path):
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

    def test_parse_cmip_time(self):
        parsed = climate.parse_cmip_time([20070104.5, 20070105.0])
        assert parsed[0] == pd.Timestamp("2007-01-04 12:00")
        assert parsed[1] == pd.Timestamp("2007-01-05 00:00")
