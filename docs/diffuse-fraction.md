# Diffuse fraction (BRL model)

GSEE's PV model requires a `diffuse_fraction` input.
When you only have global horizontal irradiance, GSEE estimates it with the BRL model.

## The BRL model

The BRL model (Ridley et al. 2010, with the parameters from Lauret et al. 2013) estimates the diffuse fraction from the hourly clearness index.
Its coefficients are calibrated on hourly data, and it only accepts hourly input.
This is why sub-hourly simulations must supply the diffuse fraction themselves.
In GSEE it is vectorized over `(time, site)`.

## When GSEE applies it automatically

Only the [climate data interface](climatedata-interface.md) estimates the diffuse fraction automatically.
`gsee.climate.run_climate` runs the BRL model for all synthesized hourly data, and for hourly input that lacks a `diffuse_fraction` variable.

The direct-simulation entry points do not run the BRL model automatically.

## Calling it directly

`gsee.core.diffuse.brl_diffuse_fraction(clearness, times, lat, lon)` takes the hourly clearness index as a `(time, site)` array over whole days (the time index must be hourly and start at midnight UTC) and returns the diffuse fraction as a `(time, site)` array:

```python
from gsee.core import diffuse

diffuse_fraction = diffuse.brl_diffuse_fraction(
    hourly_clearness.to_numpy(), hourly_clearness.index, lat, lon
)
```

## References

- Ridley, B., J. Boland, and P. Lauret, 2010: Modelling of diffuse solar fraction with multiple predictors. Renew. Energy, 35, 478–483, [doi:10.1016/j.renene.2009.07.018](http://dx.doi.org/10.1016/j.renene.2009.07.018)
- Lauret, P., J. Boland, and B. Ridley, 2013: Bayesian statistical analysis applied to solar radiation modelling. Renew. Energy, 49, 124–127, [doi:10.1016/j.renene.2012.01.049](http://dx.doi.org/10.1016/j.renene.2012.01.049)
