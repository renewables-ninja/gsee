# Migrating from v0.3 to v0.4

v0.4.0 rebuilds GSEE on a vectorized computation core: solar positions come from a restructured NREL SPA implementation that is shared across sites and timesteps, and everything downstream operates on `(time, site)` arrays. The single-site `gsee.pv.run_model()` keeps its v0.3 call signature but now runs about 20x faster and has slightly more accurate results.

## At a glance

| v0.3 | v0.4 |
| --- | --- |
| `gsee.pv.run_model(...)` | Same call, with slightly shifted results, and the inverter modelled by default |
| Looping `run_model` over many sites | [`gsee.api.run_sites()` / `gsee.api.run_grid()`](running/multi-site.md) |
| `gsee.trigon.sun_angles(...)` | `gsee.api.sun_angles_frame(...)` |
| `gsee.trigon.aperture_irradiance(...)` | `run_model(..., include_raw_data=True)` returns in-plane irradiance |
| `gsee.brl_model.run(...)` | `gsee.core.diffuse.brl_diffuse_fraction(...)` |
| `gsee.climatedata_interface.run_interface(...)` | [`gsee.climate.run_climate(...)`](climatedata-interface.md) |
| `ephem` always installed | Optional, only for `gsee.legacy`: `pip install gsee[legacy]` |

## Installation and dependencies

* GSEE now requires Python ≥ 3.11, pandas ≥ 3 and xarray, and pvlib ≥ 0.15.
* `ephem` is no longer a dependency. It is only needed for the frozen pre-0.4 code in `gsee.legacy`, installed via the new optional extra `pip install gsee[legacy]`.
* The climate data interface's built-in irradiance PDFs now come from the `gsee-climate-data` companion package (`pip install gsee[climate]`) instead of a runtime download.
