# Release History

## 0.4.0 (dev)

- Added: multi-site API with two functions, `gsee.api.run_sites` (xarray Dataset over `(time, site)`) and `gsee.api.run_grid` (`(time, lat, lon)`), with per-site parameters (including callable tilt), site chunking for memory control, and optional parallel processes. The `dtype="float32"` option for `run_sites`/`run_grid` allows halving memory use downstream of the (always float64) solar position computation. `run_sites`/`run_grid` load input data one site chunk at a time, so lazily-backed datasets (`xr.open_dataset(..., chunks=...)`, zarr) stream from disk.
- Added: vectorized core modules `gsee.core.irradiance` , `gsee.core.panel`, `gsee.core.inverter`, and `gsee.core.diffuse`
- Modified: `pv.run_model` is now wired through the vectorized core, making runs about 20 times faster, but with a small deviation due to the switch to (more accurate) sun position calculations
- Fixed: timesteps with NaN inputs to `pv.run_model` now return NaN instead of silently returning 0
- Added: climate data interface rebuilt on the vectorized core as `gsee.climate.run_climate`
- Added: the time-dependent SPA terms are cached per time index, so repeated computations over the same times only compute them once
- Fixed: two long-standing units bugs in the BRL diffuse-fraction model: apparent solar time was fed to the model in radians (`ephem.hours` floats are radians), and solar altitude was fed in radians, evaluated once at midnight instead of per hour. The correction raises the mean estimated diffuse fraction by ~+0.06, changing annual PV output by roughly -1.3% to -2.5% (fixed tilt).
- Added: vectorized multi-site solar position in `gsee.core.solarposition`
- Added: `gsee.api.sun_angles_frame`, a single-site sun angle calculation from the vectorized core, usable via `run_model(angles=...)`. This is equivalent to `trigon.sun_angles`.
- Added: reference regression test framework
- Added: `gsee.synthetic` module with a synthetic weather generator for tests
- Added: GitHub Actions CI replacing defunct Azure Pipelines
- Added: release publishing workflow via PyPI trusted publishing
- Modified: project environment and tasks now managed with pixi
- Added: ruff for formatting and linting (`pixi run format` / `pixi run lint`)
- Fixed: tests updated for pandas 3
- Added: PV model based on the [single-diode model in pvlib-python](https://pvlib-python.readthedocs.io/en/latest/generated/pvlib.pvsystem.singlediode.html)
- Added: `SingleDiodePanelCecCsiMedian`, based on the median CSi panel from the CEC database (available as "cec-csi-median")
- Added: `HuldCSiPanelUpdated` with revised parametrisation for the Huld model (available as "csi-new")
- Modified: Reorganise PV models; existing Huld-based models now subclass `HuldPanel`
- Added: Tools to deal with the CEC module database
- Added: Inverter model based on PVWatts Version 5 and differentiation between DC and AC output, alongside new `inverter_capacity` and `use_inverter` arguments to `pv.run_model()`
- Fixed: Clean up non-standard CMIP time attributes in climate data interface
- Fixed: Improve CF conformity of climate data interface
- Modified: Compatibility with more recent versions of pandas and xarray

## 0.3.1 (2019-07-23)

- Fixed: erroneous angles in 1-axis tracking with non-horizontal tracking axes
- Fixed: minor improvement in calculation of sunrise and sunset times to deal with cases where sun never rises or sets

## 0.3.0 (2018-12-19)

- Added: climate data interface
- Modified: PV model now expects inputs as W, not kW
- Fixed: minor improvements in `trigon.py` (sunrise/sunset times now take sun radius into consideration; clipping of zeros to avoid NaNs)

## 0.2.1 (2018-09-07)

- Fix: clip maximum panel output

## 0.2.0 (2018-08-10)

- PyPI package
- Minor bug fixes

## 0.1.0 (2016-09-01)

- First version
