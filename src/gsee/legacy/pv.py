"""
Frozen pre-0.4 `pv.run_model`. Do not modify.
"""

import math

import pandas as pd

from gsee.legacy import trigon
from gsee.legacy.panel import _PANEL_TYPES, R_TAMB, Inverter


def run_model(
    data,
    coords,
    tilt,
    azim,
    tracking,
    capacity,
    inverter_capacity=None,
    use_inverter=True,
    technology="csi",
    system_loss=0.10,
    angles=None,
    include_raw_data=False,
    legacy_solarposition=False,
    **kwargs,
):
    """
    Run the pre-0.4 PV plant model.

    Parameters
    ----------
    data : pandas DataFrame
        Must contain columns 'global_horizontal' (in W/m2)
        and 'diffuse_fraction', and may contain a 'temperature' column
        for ambient air temperature (in deg C).
    coords : (float, float) tuple
        Latitude and longitude.
    tilt : float
        Tilt angle (degrees).
    azim : float
        Azimuth angle (degrees, 180 = towards equator).
    tracking : int
        Tracking (0: none, 1: 1-axis, 2: 2-axis).
    capacity : float
        Installed DC panel capacity in W.
    inverter_capacity : float, optional
        Installed AC inverter capacity in W. If not given, the DC panel
        capacity is assumed to be equal to AC inverter capacity.
    use_inverter : bool, optional
        Model inverter capacity and inverter losses (defaults to True).
    technology : str, default 'csi'
        Panel technology, must be one of 'csi', 'cis', 'cdte', 'singlediode'
    system_loss : float, default 0.10
        Additional system losses not caused by panel and inverter (fraction).
    angles : pandas DataFrame, default None
        Solar angles. If already computed, speeds up the computations.
    include_raw_data : bool, default False
        If true, returns a DataFrame instead of Series which includes
        the input data (panel irradiance and temperature).
    legacy_solarposition : bool, default False
        If true, uses the ephem library for solar position calculations. If false, uses
        `pvlib.solarposition.get_solarposition`. Because of issues with the ephem
        library, this should only be set to True if required for backwards compatibility
        or consistency with older simulation runs.
    kwargs : additional kwargs passed on the model constructor

    Returns
    -------
    result : pandas Series
        Electric output from PV system in each hour (W).

    """
    if (system_loss < 0) or (system_loss > 1):
        raise ValueError("system_loss must be >=0 and <=1")

    # Process data
    dir_horiz = data.global_horizontal * (1 - data.diffuse_fraction)
    diff_horiz = data.global_horizontal * data.diffuse_fraction

    # NB: aperture_irradiance expects azim/tilt in radians!
    irrad = trigon.aperture_irradiance(
        dir_horiz,
        diff_horiz,
        coords,
        tracking=tracking,
        azimuth=math.radians(azim),
        tilt=math.radians(tilt),
        angles=angles,
        legacy_solarposition=legacy_solarposition,
    )
    datetimes = irrad.index

    # Temperature, if it was given
    if "temperature" in data.columns:
        tamb = data["temperature"]
    else:
        tamb = pd.Series(R_TAMB, index=datetimes)

    # Set up the panel model
    # NB: panel efficiency is not used here, but we retain the possibility
    # to adjust both efficiency and panel size in case we want to emulate
    # specific panel types
    panel_class = _PANEL_TYPES[technology]
    panel_efficiency = 0.1
    area_per_capacity = 0.001 / panel_efficiency

    panel = panel_class(
        panel_aperture=capacity * area_per_capacity,
        panel_ref_efficiency=panel_efficiency,
        **kwargs,
    )

    # Run the panel model and return output
    irradiance = irrad.direct + irrad.diffuse
    output = panel.panel_power(irradiance, tamb)
    relative_efficiency = panel.panel_relative_efficiency(irradiance, tamb)
    dc_out = pd.Series(output, index=datetimes).clip(upper=capacity)

    if inverter_capacity is None:
        inverter_capacity = capacity

    if use_inverter:
        inverter = Inverter(inverter_capacity)
        ac_out = dc_out.apply(inverter.ac_output).clip(lower=0)
        ac_out_final = ac_out * (1 - system_loss)
    else:
        ac_out_final = dc_out * (1 - system_loss)

    if include_raw_data:
        return pd.DataFrame.from_dict(
            {
                "output": ac_out_final,
                "direct": irrad.direct,
                "diffuse": irrad.diffuse,
                "temperature": tamb,
                "module_temperature": panel.module_temperature(irradiance, tamb),
                "relative_efficiency": relative_efficiency,
            }
        )
    else:
        return ac_out_final
