"""
Validation of the multi-site API.

1. Per-site equivalence:
`run_sites` must reproduce `pv.run_model` (fed with the same vectorized
solar angles) to numerical precision for every configuration, since both
express the same model. Only the container and broadcasting differ.

2. Reference check:
`run_sites` output is validated against the committed reference
data, and grid/chunking/worker code paths must be exact rearrangements.

"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from gsee import api, pv, synthetic
from tests.reference import cases, compare

SITES = {
    "zurich": (47.36, 8.55),
    "cape_town": (-33.9, 18.4),
    "svalbard": (78.25, 15.5),
}

CONFIGS = {
    "base": {"tilt": 30, "azim": 180, "tracking": 0, "capacity": 1000.0},
    "tracking1_horizontal": {"tilt": 0, "azim": 180, "tracking": 1, "capacity": 1000.0},
    "tracking1_tilted": {"tilt": 30, "azim": 180, "tracking": 1, "capacity": 1000.0},
    "tracking2": {"tilt": 30, "azim": 180, "tracking": 2, "capacity": 1000.0},
    "cdte": {
        "tilt": 30,
        "azim": 180,
        "tracking": 0,
        "capacity": 1000.0,
        "technology": "cdte",
    },
    "singlediode": {
        "tilt": 30,
        "azim": 180,
        "tracking": 0,
        "capacity": 1000.0,
        "technology": "cec-csi-median",
    },
    "no_inverter": {
        "tilt": 30,
        "azim": 180,
        "tracking": 0,
        "capacity": 1000.0,
        "use_inverter": False,
    },
    "dc_ac_ratio": {
        "tilt": 30,
        "azim": 180,
        "tracking": 0,
        "capacity": 1000.0,
        "inverter_capacity": 800.0,
    },
    "east_facing": {"tilt": 30, "azim": 90, "tracking": 0, "capacity": 1000.0},
}


@pytest.fixture(scope="module")
def site_inputs():
    return {
        name: synthetic.synthetic_weather(lat, lon, seed=hash(name) % 2**16)
        for name, (lat, lon) in SITES.items()
    }


@pytest.fixture(scope="module")
def dataset(site_inputs):
    return _dataset(site_inputs)


def _dataset(site_inputs):
    frames = list(site_inputs.values())
    index = frames[0].index
    lats = [SITES[name][0] for name in site_inputs]
    lons = [SITES[name][1] for name in site_inputs]
    return xr.Dataset(
        {
            var: (
                ("time", "site"),
                np.stack([frame[var].to_numpy() for frame in frames], axis=1),
            )
            for var in ("global_horizontal", "diffuse_fraction", "temperature")
        },
        coords={
            "time": index.tz_localize(None),
            "site": list(site_inputs),
            "lat": ("site", lats),
            "lon": ("site", lons),
        },
    )


def _per_site_reference(site_inputs, config):
    """pv.run_model per site, using the vectorized core's solar angles."""
    outputs = {}
    for name, frame in site_inputs.items():
        coords = SITES[name]
        angles = api.sun_angles_frame(frame.index, coords)
        outputs[name] = pv.run_model(frame, coords=coords, angles=angles, **config)
    return outputs


@pytest.mark.parametrize("config_name", sorted(CONFIGS))
def test_run_sites_equals_run_model_per_site(config_name, site_inputs, dataset):
    config = CONFIGS[config_name]
    expected = _per_site_reference(site_inputs, config)
    result = api.run_sites(dataset, **config)
    for i, name in enumerate(site_inputs):
        np.testing.assert_allclose(
            result["pv"].to_numpy()[:, i],
            expected[name].to_numpy(),
            rtol=1e-9,
            atol=1e-6,
            err_msg="{} @ {}".format(config_name, name),
        )


def test_per_site_parameter_arrays(site_inputs, dataset):
    tilts = np.array([10.0, 35.0, 0.0])
    capacities = np.array([1000.0, 2000.0, 500.0])
    result = api.run_sites(
        dataset, tilt=tilts, azim=180, tracking=0, capacity=capacities
    )
    for i, name in enumerate(site_inputs):
        frame = site_inputs[name]
        coords = SITES[name]
        angles = api.sun_angles_frame(frame.index, coords)
        expected = pv.run_model(
            frame,
            coords=coords,
            angles=angles,
            tilt=tilts[i],
            azim=180,
            tracking=0,
            capacity=capacities[i],
        )
        np.testing.assert_allclose(
            result["pv"].to_numpy()[:, i], expected.to_numpy(), rtol=1e-9, atol=1e-6
        )


def test_callable_tilt(dataset):
    result = api.run_sites(
        dataset, tilt=pv.optimal_tilt, azim=180, tracking=0, capacity=1000.0
    )
    explicit = api.run_sites(
        dataset,
        tilt=np.array([pv.optimal_tilt(lat) for lat in dataset["lat"].to_numpy()]),
        azim=180,
        tracking=0,
        capacity=1000.0,
    )
    np.testing.assert_array_equal(result["pv"].to_numpy(), explicit["pv"].to_numpy())


def test_chunking_is_exact(dataset):
    whole = api.run_sites(dataset, chunk_size=None, **CONFIGS["base"])
    chunked = api.run_sites(dataset, chunk_size=1, **CONFIGS["base"])
    np.testing.assert_array_equal(whole["pv"].to_numpy(), chunked["pv"].to_numpy())


def test_workers_are_exact(dataset):
    sequential = api.run_sites(dataset, chunk_size=2, workers=1, **CONFIGS["base"])
    parallel = api.run_sites(dataset, chunk_size=2, workers=2, **CONFIGS["base"])
    np.testing.assert_array_equal(
        sequential["pv"].to_numpy(), parallel["pv"].to_numpy()
    )


def test_include_raw_data(dataset):
    result = api.run_sites(dataset, include_raw_data=True, **CONFIGS["base"])
    for var in ("pv", "direct", "diffuse", "module_temperature", "relative_efficiency"):
        assert var in result
        assert result[var].dims == ("time", "site")


def test_run_grid_matches_run_sites():
    lats = [40.0, 50.0]
    lons = [0.0, 10.0]
    frames = {
        (lat, lon): synthetic.synthetic_weather(lat, lon, seed=int(lat + lon))
        for lat in lats
        for lon in lons
    }
    index = next(iter(frames.values())).index.tz_localize(None)
    grid = xr.Dataset(
        {
            var: (
                ("time", "lat", "lon"),
                np.stack(
                    [
                        np.stack(
                            [frames[(lat, lon)][var].to_numpy() for lon in lons],
                            axis=1,
                        )
                        for lat in lats
                    ],
                    axis=1,
                ),
            )
            for var in ("global_horizontal", "diffuse_fraction", "temperature")
        },
        coords={"time": index, "lat": lats, "lon": lons},
    )
    from_grid = api.run_grid(grid, **CONFIGS["base"])
    from_sites = api.run_sites(grid.stack(site=("lat", "lon")), **CONFIGS["base"])
    assert from_grid["pv"].dims == ("time", "lat", "lon")
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            np.testing.assert_array_equal(
                from_grid["pv"].to_numpy()[:, i, j],
                from_sites["pv"].to_numpy()[:, i * len(lons) + j],
            )


def test_float32_dtype(dataset):
    float64 = api.run_sites(dataset, **CONFIGS["base"])
    float32 = api.run_sites(dataset, dtype="float32", **CONFIGS["base"])
    assert float32["pv"].dtype == np.float32
    np.testing.assert_allclose(
        float32["pv"].to_numpy(),
        float64["pv"].to_numpy(),
        atol=1.0,  # W, on 1000 W capacity
        rtol=2e-3,
    )
    energy_64 = float(float64["pv"].sum())
    assert abs(float(float32["pv"].sum()) - energy_64) / energy_64 < 1e-4


def test_dtype_rejects_non_float(dataset):
    with pytest.raises(ValueError, match="dtype"):
        api.run_sites(dataset, dtype="int32", **CONFIGS["base"])


def test_missing_required_variable_raises(dataset):
    with pytest.raises(ValueError, match="diffuse_fraction"):
        api.run_sites(dataset.drop_vars("diffuse_fraction"), **CONFIGS["base"])
    with pytest.raises(ValueError, match="global_horizontal"):
        api.run_sites(dataset.drop_vars("global_horizontal"), **CONFIGS["base"])


def test_run_sites_sub_hourly():
    # Sub-hourly resolutions are supported when the input provides
    # `diffuse_fraction`; output stays mean power per timestep (W)
    halfhourly = {
        name: synthetic.synthetic_weather(*coords, seed=1, freq="30min")
        for name, coords in list(SITES.items())[:2]
    }
    result = api.run_sites(_dataset(halfhourly), **CONFIGS["base"])
    assert result["pv"].attrs["unit"] == "W"
    assert np.isfinite(result["pv"].to_numpy()).all()
    for i, (name, frame) in enumerate(halfhourly.items()):
        expected = pv.run_model(frame, coords=SITES[name], **CONFIGS["base"])
        np.testing.assert_allclose(
            result["pv"].to_numpy()[:, i],
            expected.to_numpy(),
            rtol=1e-9,
            atol=1e-6,
            err_msg=name,
        )


def test_nan_steps_propagate(dataset):
    modified = dataset.copy(deep=True)
    modified["global_horizontal"].values[100:110, 1] = np.nan
    result = api.run_sites(modified, **CONFIGS["base"])
    clean = api.run_sites(dataset, **CONFIGS["base"])
    pv = result["pv"].to_numpy()
    assert np.isnan(pv[100:110, 1]).all()
    unaffected = np.ones(pv.shape, dtype=bool)
    unaffected[100:110, 1] = False
    np.testing.assert_array_equal(pv[unaffected], clean["pv"].to_numpy()[unaffected])


def test_all_nan_site_skipped(dataset):
    modified = dataset.copy(deep=True)
    for var in ("global_horizontal", "diffuse_fraction", "temperature"):
        modified[var].values[:, 0] = np.nan
    result = api.run_sites(modified, **CONFIGS["base"])
    clean = api.run_sites(dataset, **CONFIGS["base"])
    pv = result["pv"].to_numpy()
    assert np.isnan(pv[:, 0]).all()
    np.testing.assert_array_equal(pv[:, 1:], clean["pv"].to_numpy()[:, 1:])


def test_fully_nan_dataset(dataset):
    modified = dataset.copy(deep=True)
    for var in ("global_horizontal", "diffuse_fraction", "temperature"):
        modified[var].values[:] = np.nan
    result = api.run_sites(modified, **CONFIGS["base"])
    assert np.isnan(result["pv"].to_numpy()).all()


def test_lazy_chunked_input_matches_eager(dataset):
    pytest.importorskip("dask")
    lazy = dataset.chunk({"site": 1})
    result = api.run_sites(lazy, **CONFIGS["base"])
    eager = api.run_sites(dataset, **CONFIGS["base"])
    np.testing.assert_array_equal(result["pv"].to_numpy(), eager["pv"].to_numpy())


@pytest.mark.reference
def test_run_sites_physically_equivalent_to_reference():
    case_ids = sorted(c for c in cases.build_cases() if c.endswith("-base"))
    all_cases = cases.build_cases()
    inputs = {c: cases.read_frame(cases.input_path(c)) for c in case_ids}
    index = next(iter(inputs.values())).index
    ds = xr.Dataset(
        {
            var: (
                ("time", "site"),
                np.stack(
                    [
                        (
                            inputs[c][var].to_numpy()
                            if var in inputs[c]
                            else np.full(len(index), np.nan)
                        )
                        for c in case_ids
                    ],
                    axis=1,
                ),
            )
            for var in ("global_horizontal", "diffuse_fraction", "temperature")
        },
        coords={
            "time": index.tz_convert("UTC").tz_localize(None),
            "site": case_ids,
            "lat": ("site", [all_cases[c]["lat"] for c in case_ids]),
            "lon": ("site", [all_cases[c]["lon"] for c in case_ids]),
        },
    )
    result = api.run_sites(ds, tilt=30, azim=180, tracking=0, capacity=1000.0)
    failures = []
    for i, case_id in enumerate(case_ids):
        ref = cases.read_frame(cases.output_path(case_id))
        new = pd.DataFrame({"output": result["pv"].to_numpy()[:, i]}, index=ref.index)
        ok, report = compare.check_output(new, ref, 1000.0, "physical")
        if not ok:
            failures.append("{}:\n{}".format(case_id, report))
    assert not failures, "\n\n".join(failures)
