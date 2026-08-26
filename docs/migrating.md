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

## Results change numerically

v0.4 keeps the v0.3 call signature, but the same input no longer produces the same numbers.
The changes below are listed roughly in order of how much they move annual output.
Where you need to reproduce a v0.3 run exactly, use the frozen pre-0.4 code in [`gsee.legacy`](running/legacy.md) rather than trying to configure v0.4 to match.

### The inverter is modelled by default

v0.3 had no inverter model; its output was effectively DC.
v0.4 clips DC output to `capacity` and then converts it to AC with the PVWatts v5 inverter model, whose efficiency varies with load.
This reduces output relative to v0.3, most visibly at low load.

Pass `use_inverter=False` to skip the inverter model and get the v0.3-style DC output.
`inverter_capacity` (default: equal to `capacity`) sets the AC-side capacity; set it below `capacity` for a DC/AC ratio above 1.
See [Inverter and system losses](running/pv-models.md#inverter-and-system-losses).

### BRL diffuse-fraction units fix

Two long-standing units bugs in the [BRL diffuse-fraction model](diffuse-fraction.md) are fixed:

* Apparent solar time was fed to the model in radians (the `ephem.hours` floats it came from are radians) instead of hours.
* Solar altitude was fed in radians instead of degrees, and evaluated once at midnight rather than for each hour of the day.

The correction raises the mean estimated diffuse fraction by about +0.06, which changes annual PV output by roughly -1.3% to -2.5% for fixed tilt.

This affects results only where GSEE estimates the diffuse fraction itself: the [climate data interface](climatedata-interface.md) and direct calls to the BRL model.
`gsee.pv.run_model()` and the multi-site entry points take `diffuse_fraction` as an input and are unaffected.

To reproduce the v0.3 diffuse fractions, opt back into the old (wrong) predictor units:

```python
import gsee.climate
from gsee.core import diffuse

diffuse_fraction = diffuse.brl_diffuse_fraction(
    clearness, times, lat, lon, legacy_predictors=True
)

result = gsee.climate.run_climate(data, ..., legacy_brl_predictors=True)
```

### Relative efficiency is no longer capped at 1.0

At cold module temperatures, PV modules are more efficient than at the 25 °C standard test conditions, so relative efficiency exceeds 1.0.
v0.4 lets this through by default, which raises output at cold sites.
Pass `temperature_correction_method="clip_high_efficiency"` to cap relative efficiency at 1.0 instead.
The v0.3-era `clip_low_temperature` option has been removed.
See [Efficiency at cold temperatures](running/pv-models.md#efficiency-at-cold-temperatures).

### Solar positions come from the new vectorized core

Solar positions are now computed by the vectorized NREL SPA implementation in `gsee.core.solarposition`, including a vectorized hour-angle method for sunrise and sunset.
It is more accurate than either pre-0.4 path, so results shift slightly.

### NaN inputs return NaN

Timesteps with NaN inputs now produce NaN output instead of silently producing 0.
Summing or averaging results across a series that contains gaps therefore no longer treats those gaps as zero generation; handle them explicitly (e.g. with `Series.sum(skipna=True)` or by filling the input).

## Installation and dependencies

* GSEE now requires Python ≥ 3.12, pandas ≥ 3 and xarray, and pvlib ≥ 0.15.
* `ephem` is no longer a dependency. It is only needed for the frozen pre-0.4 code in `gsee.legacy`, installed via the new optional extra `pip install gsee[legacy]`.
* The climate data interface's built-in irradiance PDFs now come from the `gsee-climate-data` companion package (`pip install gsee[climate]`) instead of a runtime download.
