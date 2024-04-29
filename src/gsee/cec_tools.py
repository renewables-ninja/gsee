import pvlib


def get_efficiency(irradiance, cell_temperature, module_params):
    """
    irradiance : float or pandas.Series
        Effective irradiance (W/m2) that is converted to photocurrent.
    cell_temperature : float or pandas.Series
        Average cell temperature of cells within a module in deg C.
    module_params : dict
        Module params 'alpha_sc', 'a_ref', 'I_L_ref', 'I_o_ref', 'R_sh_ref', 'R_s'.

    """
    params = pvlib.pvsystem.calcparams_desoto(
        effective_irradiance=irradiance, temp_cell=cell_temperature, **module_params
    )

    # Ensure that the shunt resistance is not infinite
    # Commented out because we want to still return valid Series when
    # some of the values are zero -- NaNs from 0-divisions are filled later
    # assert params[3] != math.inf

    dc = pvlib.pvsystem.singlediode(*params)
    efficiency = dc["p_mp"] / irradiance
    return efficiency


def relative_eff(irradiance, cell_temperature, params):
    """
    Compute relative efficiency of PV module as a function of irradiance
    and cell/module temperature, from Huld (2010):

    .. math:: n_{rel} = \frac{P_{stc} * (G / G_{stc})}{P}

    Where G is in-plane irradiance, P is power output,
    and STC conditions are :math:`G = 1000` and
    :math:`T_{mod} = 25`.

    When irradiance is zero, a zero relative efficiency is returned.

    Parameters
    ----------

    irradiance : float or pandas.Series
        Irradiance in W/m2.
    cell_temperature : float or pandas.Series
        Average cell temperature of cells within a module in deg C.
    params : dict
        Module params 'alpha_sc', 'a_ref', 'I_L_ref', 'I_o_ref', 'R_sh_ref', 'R_s'.

    """
    if isinstance(irradiance, float) and irradiance == 0:
        return 0

    power_stc = 1000 * get_efficiency(1000, 25, params)
    power = irradiance * get_efficiency(irradiance, cell_temperature, params)

    # Fill NaNs from any possible divisions by zero with 0
    return (power / (power_stc * (irradiance / 1000))).fillna(0)
