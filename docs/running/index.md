# Running GSEE

This section covers running the PV model directly:

- [PV models](pv-models.md): the available panel technologies, the inverter model, and their parameters (shared by all entry points).
- [Multi-site simulations](multi-site.md): running many sites or whole grids at once on the vectorized core.
- [Legacy options](legacy.md): flags that reproduce the behaviour of older GSEE versions.

For running on coarse-resolution climate data, see the [climate data interface](../climatedata-interface.md).

## Single-site simulations

The classic entry function is `gsee.pv.run_model()`, which simulates one PV system from hourly or finer time series data:

```python
import gsee.pv

result = gsee.pv.run_model(
    data,
    coords=(22.78, 5.51),  # lat and lon
    tilt=30,               # degrees
    azim=180,              # degrees, 180 = towards equator
    tracking=0,            # 0 = fixed, 1 = 1-axis, 2 = 2-axis
    capacity=1000,         # W
)
```

`data` must be a pandas DataFrame indexed with a timezone-aware UTC DatetimeIndex at a uniform resolution, with columns:

- **`global_horizontal`**: mean global horizontal irradiance per timestep, in W/m2.
- **`diffuse_fraction`**: fraction of the irradiance that is diffuse (if you only have global horizontal irradiance, estimate it with the [BRL model](../diffuse-fraction.md)).
- **`temperature`** (optional): ambient air temperature in degrees Celsius. 20 °C is assumed if absent.

Any uniform resolution, hourly or finer, is supported. Sub-hourly data (e.g. 30- or 15-minute) must supply the `diffuse_fraction` column directly, since the [BRL model](../diffuse-fraction.md) used to estimate it works on hourly data only.

The result is a pandas Series of mean AC power output per timestep, in W (power is in W, energy in Wh throughout GSEE). Energy per timestep is power times the timestep length in hours, so power in W and energy in Wh are numerically identical for hourly data, but not for finer resolutions.
With `include_raw_data=True`, a DataFrame is returned that also contains the in-plane direct and diffuse irradiance, module temperature and relative panel efficiency.

Model configuration beyond the required parameters, including panel technology, inverter sizing, and system losses, is described on the [PV models](pv-models.md) page.

!!! tip
When calling `run_model` repeatedly over the same time index and site (e.g. to compare configurations), compute the solar angles once with `gsee.api.sun_angles_frame()` and pass them via `angles=`.
See [speeding up single-site runs](multi-site.md#speeding-up-single-site-runs) for details.
