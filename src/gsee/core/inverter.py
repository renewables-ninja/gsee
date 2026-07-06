"""
PVWatts v5 inverter model, vectorized
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Same curve as `gsee.pv.Inverter.ac_output` (Dobos 2014), as a pure
function on arrays of any shape, with `ac_capacity` broadcastable per
site.

"""

import numpy as np


def ac_output(dc_in, ac_capacity, eff_ref=0.9637, eff_nom=1.0):
    """
    AC output (W) for DC input (W). Zero where the DC input is zero;
    capped at `ac_capacity`. Not clipped below zero (the caller does
    that, matching `gsee.pv.run_model`).

    """
    dc_capacity = np.asarray(ac_capacity, dtype=float) / eff_nom
    with np.errstate(invalid="ignore", divide="ignore"):
        zeta = dc_in / dc_capacity
        efficiency = (eff_nom / eff_ref) * (-0.0162 * zeta - 0.0059 / zeta + 0.9858)
        out = np.minimum(ac_capacity, dc_in * efficiency)
    return np.where(dc_in == 0, 0.0, out)
