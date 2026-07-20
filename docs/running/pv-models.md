# PV models

The same model options apply to all entry points: `gsee.pv.run_model()` (single site), [`gsee.api.run_sites()`/`run_grid()`](multi-site.md) (many sites), and [`gsee.climate.run_climate()`](../climatedata-interface.md).

## Panel technologies

The `technology` parameter selects the panel model:

| `technology`            | Model        | Description                                                                                                                                        |
| ----------------------- | ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `csi` (default)         | Huld         | Crystalline silicon, coefficients from Huld et al. (2010)                                                                                          |
| `csi-new` (recommended) | Huld         | Crystalline silicon with a revised parametrisation ([doi:10.1002/pip.3926](https://doi.org/10.1002/pip.3926)), as referenced in pvlib's Huld model |
| `cis`                   | Huld         | CIS/CIGS thin film, coefficients from Huld et al. (2010)                                                                                           |
| `cdte`                  | Huld         | CdTe thin film, coefficients from Huld et al. (2010)                                                                                               |
| `cec-csi-median`        | Single-diode | The median mono-c-Si module from the CEC database                                                                                                  |
| `singlediode`           | Single-diode | Custom module: requires `module_params`                                                                                                            |

!!! note "Which crystalline silicon model?"
The default `csi` is kept for continuity with earlier GSEE versions and Renewables.ninja simulations. For modern installations we recommend `csi-new`: its coefficients are fitted to recent module data and track the physics-based single-diode model much more closely, particularly at low irradiance (see [the comparison below](#comparing-the-panel-models)). It may become the default in a future version.

### The Huld model

The empirical model of Huld et al. (2010) computes the panel's relative efficiency as a function of in-plane irradiance and module temperature, where module temperature is estimated from ambient temperature and irradiance:

- `c_temp_amb` (default 1 °C/°C): module temperature coefficient of ambient temperature.
- `c_temp_irrad` (default 0.035 °C/(W/m²)): module temperature coefficient of irradiance. The default value is appropriate for free-standing modules. Use 0.05 for building-integrated modules

This module temperature estimate assumes no wind: at full sun it heats the module 35 °C above ambient, closely matching pvlib's SAPM open-rack model at 0 m/s wind speed. The single-diode path below instead uses SAPM at a 5 m/s reference wind speed.

### The single-diode model

The single-diode path uses [pvlib's De Soto parameter and single-diode calculations](https://pvlib-python.readthedocs.io/en/latest/reference/generated/pvlib.pvsystem.singlediode.html). With `technology="singlediode"`, you must pass `module_params`, a dict with the CEC database parameters `alpha_sc`, `a_ref`, `I_L_ref`, `I_o_ref`, `R_sh_ref` and `R_s`.

Module temperature is estimated with the SAPM cell temperature model; `temperature_params` accepts one of the SAPM mounting presets (`"open_rack_glass_glass"` by default, `"close_mount_glass_glass"`, `"open_rack_glass_polymer"`, `"insulated_back_glass_polymer"`) or a dict with `a`, `b` and `deltaT`.

## Comparing the panel models

The figure below compares the relative efficiency of the three crystalline silicon panel models against in-plane irradiance (left, at STC module temperature) and against module temperature (right, at STC irradiance). Both panels vary module temperature directly, so the comparison shows only the efficiency models, not the models' different ambient-to-module temperature estimates. The code to reproduce it is in [`docs/figures/plot_model_comparison.py`](https://github.com/renewables-ninja/gsee/blob/main/docs/figures/plot_model_comparison.py) (`pixi run docs-figures`).

![Relative efficiency of the c-Si panel models against irradiance and module temperature](../figures/model-comparison.svg)

## Tracking

- `tracking=0`: fixed panels at the given `tilt` and `azim`.
- `tracking=1`: 1-axis tracking. `tilt` gives the tilt of the tracking axis relative to horizontal (0 = horizontal axis) and `azim` the orientation of the axis.
- `tracking=2`: 2-axis tracking. The panel always faces the sun directly (`tilt` and `azim` are ignored).

`gsee.pv.optimal_tilt(lat)` provides a simple latitude-dependent tilt estimate that can be used directly, or passed as a callable to the multi-site and climate entry points.

## Plane-of-array irradiance

Global horizontal irradiance is split into its direct and diffuse components via `diffuse_fraction` and transposed onto the panel plane with an isotropic diffuse model, including ground reflection controlled by `albedo` (default 0.3).

## Inverter and system losses

DC output is clipped to `capacity`, then converted to AC with the inverter model from PVWatts v5 (Dobos 2014), whose efficiency varies with load:

- `inverter_capacity` (default: equal to `capacity`): AC inverter capacity in W. Set this lower than `capacity` for a DC/AC ratio above 1.
- `use_inverter=False`: skip the inverter model entirely (returns DC output).

Finally, `system_loss` (default 0.10) is subtracted as a flat fraction covering all losses not caused by panel and inverter.

## References

- Huld, T. et al., 2010: Mapping the performance of PV modules, effects of module type and data averaging. Solar Energy, 84(2), 324-338. [doi:10.1016/j.solener.2009.12.002](https://doi.org/10.1016/j.solener.2009.12.002)
- Dobos, A. P., 2014: PVWatts Version 5 Manual. NREL Technical Report. [nrel.gov/docs/fy14osti/62641.pdf](https://www.nrel.gov/docs/fy14osti/62641.pdf)
- Revised Huld c-Si parametrisation ('csi-new'): [doi:10.1002/pip.3926](https://onlinelibrary.wiley.com/doi/10.1002/pip.3926)
