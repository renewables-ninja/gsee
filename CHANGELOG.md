# Release History

## 0.4.0 (dev)

- Modified: minimum supported Python is now 3.12 (was 3.11), matching the versions the test suite actually runs on
- Modified: relative efficiency is no longer capped by default. It exceeds 1.0 at cold module temperatures, which is physically expected and agreed on by all panel models; `temperature_correction_method="clip_high_efficiency"` is the opt-in cap, honoured by `pv.run_model`, `api.run_sites`/`run_grid` and `climate.run_climate`. The interim `clip_low_temperature` option has been removed.
- Modified: the frozen legacy path (`pv.run_model(legacy_solarposition=True)`) now rejects options it cannot honour -- `temperature_correction_method`, a non-default `albedo`, and technologies other than 'csi'/'cis'/'cdte' -- with a clear error instead of failing inside the frozen code with a `TypeError`/`KeyError`
- Removed: `gsee.climatedata_interface`, rebuilt as `gsee.climate` (see below)
- Added: `albedo` is now settable on `pv.run_model` (previously hardcoded to 0.3 despite being documented as an option)
- Added: `api.run_grid` and `climate.run_climate` accept CF-conventional `latitude`/`longitude` dimension names as well as `lat`/`lon` (output keeps the input's names), and raise a clear error for anything else instead of a bare `KeyError`
- Fixed: `climate.run_climate` now raises instead of silently ignoring `include_raw_data` on input it cannot honour (coarser-than-hourly input, or hourly input without a `diffuse_fraction` variable)
- Fixed: `climate.detect_frequency` recognises the CMIP5/6 `frequency` attribute values 'yr' and '1hr', so `timeformat='cmip5'` works with attribute-based detection. Multi-hour sampling ('3hr', '6hr') is rejected with a clear error rather than being treated as hourly, which would silently mislabel the output
- Fixed: `climate.parse_cmip_time` rounds the fractional-day part instead of truncating it
- Fixed: `cec_tools.relative_eff` works for the scalar inputs its docstring documents rather than just for pandas.Series
- Modified: `gsee.legacy` now carries its own frozen copy of the pre-0.4 panel and inverter models
- Added: multi-site API with two functions, `gsee.api.run_sites` (xarray Dataset over `(time, site)`) and `gsee.api.run_grid` (`(time, lat, lon)`), with per-site parameters (including callable tilt), site chunking for memory control, and optional parallel processes. The `dtype="float32"` option for `run_sites`/`run_grid` allows halving memory use downstream of the (always float64) solar position computation. `run_sites`/`run_grid` load input data one site chunk at a time, so lazily-backed datasets (`xr.open_dataset(..., chunks=...)`, zarr) stream from disk.
- Added: vectorized core modules `gsee.core.irradiance` , `gsee.core.panel`, `gsee.core.inverter`, and `gsee.core.diffuse`
- Modified: `pv.run_model` is now wired through the vectorized core, making runs about 20 times faster, but with a small deviation due to the switch to (more accurate) sun position calculations
- Fixed: timesteps with NaN inputs to `pv.run_model` now return NaN instead of silently returning 0
- Modified: frozen pre-0.4 single-site implementation now lives in `gsee.legacy` and requires the new optional `legacy` extra (`pip install gsee[legacy]`)
- Modified: `ephem` is no longer a required dependency; it is only needed for `gsee.legacy`
- Deprecated: `gsee.trigon` and `gsee.brl_model` (now aliases of their `gsee.legacy` counterparts) and `pv.run_model(legacy_solarposition=True)`
- Added: climate data interface rebuilt on the vectorized core as `gsee.climate.run_climate`
- Added: the time-dependent SPA terms are cached per time index, so repeated computations over the same times only compute them once
- Fixed: two long-standing units bugs in the BRL diffuse-fraction model: apparent solar time was fed to the model in radians (`ephem.hours` floats are radians), and solar altitude was fed in radians, evaluated once at midnight instead of per hour. The correction raises the mean estimated diffuse fraction by ~+0.06, changing annual PV output by roughly -1.3% to -2.5% (fixed tilt).
- Added: vectorized multi-site solar position in `gsee.core.solarposition`
- Added: `gsee.api.sun_angles_frame`, a single-site sun angle calculation from the vectorized core, usable via `run_model(angles=...)`. This is physically equivalent to `gsee.legacy.trigon.sun_angles`, but not bit-identical: sunrise and sunset come from the vectorized hour-angle method rather than iterative SPA.
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
- Added: Inverter model based on PVWatts Version 5 and differentiation between DC and AC output, alongside new `inverter_capacity` and `use_inverter` arguments to `pv.run_model()`. **The inverter is modelled by default** (`use_inverter=True`), so results are lower than v0.3 for the same inputs; pass `use_inverter=False` for DC output
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
