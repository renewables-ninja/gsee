# Multi-site simulations

`GSEE` can compute many sites at once on a vectorized core that operates on `(time, site)` arrays. Two entry points wrap this:

- **`gsee.api.run_sites(data, ...)`** for an arbitrary list of sites (e.g. a portfolio of PV systems), and
- **`gsee.api.run_grid(data, ...)`** for a regular latitude/longitude grid (e.g. reanalysis data), which is stacked to a flat site list internally and unstacked again.

## Input data format

`run_sites` expects an `xarray.Dataset` with dimensions `time` and `site`:

- `time`: uniformly spaced timestep starts, interpreted as UTC; hourly or finer ([sub-hourly data must supply `diffuse_fraction`](index.md#single-site-simulations))
- coordinates `lat(site)` and `lon(site)` in degrees
- variables `global_horizontal` (W/m2) and `diffuse_fraction`, and optionally `temperature` (degrees Celsius; 20 °C is assumed if absent)

```python
import numpy as np
import pandas as pd
import xarray as xr

dataset = xr.Dataset(
    {
        "global_horizontal": (("time", "site"), ghi_array),
        "diffuse_fraction": (("time", "site"), diffuse_fraction_array),
        "temperature": (("time", "site"), temperature_array),
    },
    coords={
        "time": pd.date_range("2019-01-01", "2019-12-31 23:00", freq="1h"),
        "site": ["a", "b", "c"],
        "lat": ("site", [47.4, -33.9, 78.3]),
        "lon": ("site", [8.5, 18.4, 15.5]),
    },
)
```

`run_grid` expects the same variables over `(time, lat, lon)` instead.

## Running

```python
import gsee.api

result = gsee.api.run_sites(
    dataset,
    tilt=30,       # degrees
    azim=180,      # degrees, 180 = towards equator
    tracking=0,    # 0 = fixed, 1 = 1-axis, 2 = 2-axis
    capacity=1000, # W
)
result["pv"]  # (time, site) power output in W
```

All the options of `gsee.pv.run_model` are available (`technology`, `inverter_capacity`, `use_inverter`, `system_loss`, ... — see [PV models](pv-models.md)). The results are physically equivalent to running `gsee.pv.run_model` per site. However, sunrise and sunset times come from a vectorized hour-angle method rather than the iterative SPA routine, so the numerical results are not 1:1 the same.

## Per-site parameters

`tilt`, `azim`, `capacity`, `inverter_capacity` and `albedo` accept either a scalar (same for all sites) or an array with one value per site. For `tilt`, a callable evaluated per site latitude is also possible:

```python
result = gsee.api.run_sites(
    dataset,
    tilt=gsee.pv.optimal_tilt,     # function of latitude
    azim=180,
    tracking=0,
    capacity=np.array([1000.0, 5000.0, 2000.0]),  # per site
)
```

Sites on the southern hemisphere are handled automatically (the azimuth convention flips per site).

## Performance and memory

Several options control how large runs execute:

- **Site chunking** (`chunk_size`): sites are processed in chunks (by default sized to ~64 MB arrays), so the full `(time, site)` intermediate arrays are not loaded at once.
- **Parallel execution** (`workers=N`): chunks run on `N` worker processes, with a bounded number of chunks in flight.
- **Single precision** (`dtype="float32"`): halves memory use for inputs and everything following after the solar position computation (which always runs in float64 for accuracy).

In addition, input data is loaded one site chunk at a time. You can pass a lazily loaded Dataset such as from `xr.open_dataset("data.nc", chunks={"lat": 10, "lon": 10})`. Also possible is an open zarr store. Inputs stream from disk instead of being read into memory at the start.

```python
data = xr.open_dataset("merra2_year.nc", chunks={"lat": 20, "lon": 20})
result = gsee.api.run_grid(
    data,
    tilt=gsee.pv.optimal_tilt,
    azim=180,
    tracking=0,
    capacity=1000,
    workers=8,
    dtype="float32",
)
```

## Speeding up single-site runs

The vectorized solar position core can also accelerate the classic single-site `run_model` path, which spends most of its time computing solar positions:

```python
angles = gsee.api.sun_angles_frame(data.index, coords)
result = gsee.pv.run_model(data, coords=coords, angles=angles, ...)
```

This is useful when running `run_model` repeatedly over the same time index (e.g. multiple configurations for the same site and year can re-use `angles` after it has been computed once).
