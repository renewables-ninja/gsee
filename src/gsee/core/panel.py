"""
PV panel models, vectorized over (time, site)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Huld et al. (2010) empirical model and the pvlib single-diode model,
as pure functions on numpy arrays of any shape.

"""

import numpy as np
import pandas as pd
import pvlib

from gsee import cec_tools

R_TAMB = 20.0  # Reference ambient temperature (degC)
R_TMOD = 25.0  # Reference module temperature (degC)
R_IRRADIANCE = 1000.0  # Reference irradiance (W/m2)
R_WINDSPEED = 5.0  # Reference wind speed (m/s)

#: Huld model coefficients (k_1..k_6) per technology, as in gsee.pv
HULD_COEFFICIENTS = {
    "csi": (-0.017162, -0.040289, -0.004681, 0.000148, 0.000169, 0.000005),
    "csi-new": (-0.006756, -0.016444, -0.003015, -0.000045, -0.000043, 0.000005),
    "cis": (-0.005521, -0.038492, -0.003701, -0.000899, -0.001248, 0.000001),
    "cdte": (-0.103251, -0.040446, -0.001667, -0.002075, -0.001445, -0.000023),
}

HULD_TECHNOLOGIES = frozenset(HULD_COEFFICIENTS)
SINGLEDIODE_TECHNOLOGIES = frozenset(["singlediode", "cec-csi-median"])

TEMPERATURE_CORRECTION_METHODS = (None, "clip_high_efficiency")


def _check_temperature_correction_method(method):
    if method not in TEMPERATURE_CORRECTION_METHODS:
        raise ValueError(
            "Unknown temperature_correction_method: {!r}; must be one of {}".format(
                method, TEMPERATURE_CORRECTION_METHODS
            )
        )


def huld_module_temperature(irradiance, tamb, c_temp_amb=1.0, c_temp_irrad=0.035):
    """Module temperature estimate of the Huld model (degC)."""
    return c_temp_amb * tamb + c_temp_irrad * irradiance


def huld_relative_efficiency(
    irradiance,
    tamb,
    technology="csi",
    c_temp_amb=1.0,
    c_temp_irrad=0.035,
    temperature_correction_method=None,
):
    """
    Relative conversion efficiency of the Huld model. Zero where
    irradiance is zero or negative; never negative. Values above 1.0
    at cold module temperatures are physically expected and returned
    as-is by default; `temperature_correction_method=
    "clip_high_efficiency"` caps the result at 1.0.

    """
    _check_temperature_correction_method(temperature_correction_method)
    k_1, k_2, k_3, k_4, k_5, k_6 = HULD_COEFFICIENTS[technology]
    g = irradiance / R_IRRADIANCE
    t = huld_module_temperature(irradiance, tamb, c_temp_amb, c_temp_irrad) - R_TMOD
    with np.errstate(invalid="ignore", divide="ignore"):
        log_g = np.log(g)
        eff = (
            1
            + k_1 * log_g
            + k_2 * log_g**2
            + t * (k_3 + k_4 * log_g + k_5 * log_g**2)
            + k_6 * t**2
        )
    eff = np.clip(np.where(np.isnan(eff), 0.0, eff), 0.0, None)
    if temperature_correction_method == "clip_high_efficiency":
        eff = np.clip(eff, None, 1.0)
    return eff


def _resolve_temperature_params(temperature_params):
    if isinstance(temperature_params, str):
        return pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"][
            temperature_params
        ]
    return temperature_params


def singlediode_module_temperature(
    irradiance, tamb, windspeed=R_WINDSPEED, temperature_params="open_rack_glass_glass"
):
    """SAPM cell temperature (degC), as in `gsee.pv.SingleDiodePanel`."""
    params = _resolve_temperature_params(temperature_params)
    return pvlib.temperature.sapm_cell(
        irradiance, tamb, windspeed, params["a"], params["b"], params["deltaT"]
    )


def singlediode_relative_efficiency(
    irradiance,
    tamb,
    module_params,
    windspeed=R_WINDSPEED,
    temperature_params="open_rack_glass_glass",
    temperature_correction_method=None,
):
    """
    Relative efficiency via the pvlib single-diode model. Works on arrays of any
    shape by flattening through `cec_tools.relative_eff` (which requires a pandas Series).

    """
    _check_temperature_correction_method(temperature_correction_method)
    irradiance = np.asarray(irradiance, dtype=float)
    cell_temperature = np.broadcast_to(
        np.asarray(
            singlediode_module_temperature(
                irradiance, tamb, windspeed, temperature_params
            ),
            dtype=float,
        ),
        irradiance.shape,
    )
    efficiency = cec_tools.relative_eff(
        pd.Series(irradiance.ravel()),
        pd.Series(cell_temperature.ravel()),
        module_params,
    )
    efficiency = efficiency.to_numpy().reshape(irradiance.shape)
    if temperature_correction_method == "clip_high_efficiency":
        efficiency = np.clip(efficiency, None, 1.0)
    return efficiency


def panel_power(
    irradiance,
    tamb,
    capacity,
    technology="csi",
    module_params=None,
    **panel_kwargs,
):
    """
    DC power output (W) for in-plane irradiance and ambient
    temperature, replicating `gsee.pv.run_model`'s panel setup: panel
    aperture sized from `capacity` with 0.1 reference efficiency, so
    power = irradiance/1000 * capacity * relative_efficiency. NOT
    clipped to capacity (the caller does that, as in `run_model`).

    `capacity` may be scalar or (S,); `technology` selects the Huld
    coefficient set or the single-diode model ('singlediode' /
    'cec-csi-median', the latter with built-in CEC median parameters).

    """
    efficiency = relative_efficiency(
        irradiance, tamb, technology, module_params, **panel_kwargs
    )
    return (irradiance / R_IRRADIANCE) * capacity * efficiency


def relative_efficiency(
    irradiance, tamb, technology="csi", module_params=None, **panel_kwargs
):
    """Relative efficiency for any supported technology."""
    if technology in HULD_COEFFICIENTS:
        return huld_relative_efficiency(irradiance, tamb, technology, **panel_kwargs)
    if technology in SINGLEDIODE_TECHNOLOGIES:
        if module_params is None:
            if technology == "cec-csi-median":
                from gsee.pv import CEC_PARAMETERS

                module_params = CEC_PARAMETERS["Mono-c-Si-Median"]
            else:
                raise ValueError("technology 'singlediode' requires module_params")
        return singlediode_relative_efficiency(
            irradiance, tamb, module_params, **panel_kwargs
        )
    raise ValueError("Unknown technology: {}".format(technology))


def module_temperature(
    irradiance, tamb, technology="csi", module_params=None, **panel_kwargs
):
    """Module temperature for any supported technology (degC)."""
    if technology in HULD_COEFFICIENTS:
        kwargs = {
            k: v for k, v in panel_kwargs.items() if k in ("c_temp_amb", "c_temp_irrad")
        }
        return huld_module_temperature(irradiance, tamb, **kwargs)
    kwargs = {
        k: v
        for k, v in panel_kwargs.items()
        if k in ("windspeed", "temperature_params")
    }
    return singlediode_module_temperature(irradiance, tamb, **kwargs)
