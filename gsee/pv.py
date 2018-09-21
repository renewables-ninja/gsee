"""
PV power model
~~~~~~~~~~~~~~

Sources:

{1} Huld, T. et al., 2010. Mapping the performance of PV modules,
    effects of module type and data averaging. Solar Energy, 84(2),
    p.324-338. DOI: 10.1016/j.solener.2009.12.002


General assumptions made:
-------------------------

Maximum power point tracking is assumed.

"""

import math
import warnings

import numpy as np
import pandas as pd

from gsee import trigon

# Constants
R_TAMB = 20  # Reference ambient temperature (degC)
R_TMOD = 25  # Reference module temperature (degC)
R_IRRADIANCE = 1000  # Reference irradiance (W/m2)


class PVPanel(object):
    """
    PV panel model class

    Unit for power is W, for energy, Wh.

    By default, self.module_aperture is set to 1.0, so the output will
    correspond to output per m2 of solar field given the other
    input values.

    Parameters
    ----------
    panel_aperture : float
        Panel aperture area (m2)
    ref_efficiency : float
        Reference conversion efficiency
    c_temp_amb: float, default 1 degC / degC
        Panel temperature coefficient of ambient temperature
    c_temp_irrad: float, default 0.035 degC / (W/m2)
        Panel temperature coefficient of irradiance. According to {1},
        reasonable values for this for c-Si are:
            0.035  # Free-standing module, assuming no wind
            0.05   # Building-integrated module

    """
    def __init__(self, panel_aperture=1.0, panel_ref_efficiency=1.0,
                 c_temp_amb=1, c_temp_irrad=0.035):
        super().__init__()
        # Panel characteristics
        self.panel_aperture = panel_aperture
        self.panel_ref_efficiency = panel_ref_efficiency
        self.use_diffuse = True  # Whether to also use diffuse irradiance
        # Panel temperature estimation
        self.c_temp_tamb = c_temp_amb
        self.c_temp_irrad = c_temp_irrad

    def panel_power(self, direct, diffuse=None, tamb=None):
        """
        Returns electricity in W from PV panel(s) based on given input data.

        Parameters
        ----------
        direct : pandas Series
            Direct irradiance hitting the panel(s) in W/m2.
        diffuse : pandas Series, default None
            Diffuse irradiance hitting the panel(s) in W/m2.
        tamb : pandas Series, default None
            Ambient temperature in deg C. If not given, R_TAMB is used
            for all values.

        """
        index_msg = 'Data indices must match'
        if diffuse is not None:
            assert direct.index.equals(diffuse.index), index_msg
        if tamb is not None:
            assert direct.index.equals(tamb.index), index_msg
        if self.use_diffuse:
            irradiance = direct + diffuse
        else:
            irradiance = direct
        return (irradiance * self.panel_aperture
                * self.panel_relative_efficiency(irradiance, tamb)
                * self.panel_ref_efficiency)

    def panel_relative_efficiency(self, irradiance, tamb):
        """
        Returns the relative conversion efficiency modifier as a
        function of irradiance and ambient temperature.

        Source: {1}

        Parameters
        ----------
        irradiance : pandas Series
            Irradiance in W
        tamb : pandas Series
            Ambient temperature in deg C

        """
        # G_: normalized in-plane irradiance
        G_ = irradiance / R_IRRADIANCE
        # T_: normalized module temperature
        T_ = (self.c_temp_tamb * tamb + self.c_temp_irrad * irradiance) - R_TMOD
        # NB: np.log without base implies base e or ln
        # Catching warnings to suppress "RuntimeWarning: invalid value encountered in log"
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            eff = (
                1 + self.k_1 * np.log(G_)
                + self.k_2 * (np.log(G_)) ** 2
                + T_ * (self.k_3
                        + self.k_4 * np.log(G_)
                        + self.k_5 * (np.log(G_)) ** 2)
                + self.k_6 * (T_ ** 2)
            )
        eff.fillna(0, inplace=True)  # NaNs in case that G_ was <= 0
        eff[eff < 0] = 0  # Also make sure efficiency can't be negative
        return eff


class CSiPanel(PVPanel):
    """c-Si technology, based on data from {1}"""
    def __init__(self, **kwargs):
        super(CSiPanel, self).__init__(**kwargs)
        self.k_1 = -0.017162
        self.k_2 = -0.040289
        self.k_3 = -0.004681
        self.k_4 = 0.000148
        self.k_5 = 0.000169
        self.k_6 = 0.000005


class CdTePanel(PVPanel):
    """CdTe technology, based on data from {1}"""
    def __init__(self, **kwargs):
        super(CdTePanel, self).__init__(**kwargs)
        self.k_1 = -0.103251
        self.k_2 = -0.040446
        self.k_3 = -0.001667
        self.k_4 = -0.002075
        self.k_5 = -0.001445
        self.k_6 = -0.000023


_PANEL_TYPES = {
    'csi': CSiPanel,
    'cdte': CdTePanel
}


def run_model(
        data, coords, tilt, azim, tracking, capacity,
        technology='csi', system_loss=0.10, angles=None,
        include_raw_data=False, **kwargs):
    """
    Run PV plant model.

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
        Installed capacity in W.
    technology : str, default 'csi'
        Panel technology, must be one of 'csi', 'cdte', 'cpv'
    system_loss : float, default 0.10
        Total system power losses (fraction).
    angles : pandas DataFrame, default None
        Solar angles. Ff already computed, speeds up the computations.
    include_raw_data : bool, default False
        If true, returns a DataFrame instead of Series which includes
        the input data (panel irradiance and temperature).
    kwargs : additional kwargs passed on the model constructor

    Returns
    -------
    result : pandas Series
        Electric output from PV system in each hour (W).

    """
    if (system_loss < 0) or (system_loss > 1):
        raise ValueError('system_loss must be >=0 and <=1')

    # Process data
    dir_horiz = data.global_horizontal * (1 - data.diffuse_fraction)
    diff_horiz = data.global_horizontal * data.diffuse_fraction
    # TODO more flexibilty when passing in data, e.g. allow passing in
    # other combinations of data like DNI + global horizontal
    # NB: aperture_irradiance expects azim/tilt in radians!
    irrad = trigon.aperture_irradiance(dir_horiz, diff_horiz, coords,
                                       tracking=tracking,
                                       azimuth=math.radians(azim),
                                       tilt=math.radians(tilt),
                                       angles=angles)
    datetimes = irrad.index

    # Temperature, if it was given
    if 'temperature' in data.columns:
        tamb = data['temperature']
    else:
        tamb = pd.Series(R_TAMB, index=datetimes)

    # Set up the panel model
    # NB: panel efficiency is not used here, but we retain the possibility
    # to adjust both efficiency and panel size in case we want to emulate
    # specific panel types
    panel_class = _PANEL_TYPES[technology]
    panel_efficiency = 0.1
    area_per_capacity = 0.001 / panel_efficiency

    # TODO allow panel_aperture to change through day as shading takes place
    panel = panel_class(panel_aperture=capacity * area_per_capacity,
                        panel_ref_efficiency=panel_efficiency,
                        **kwargs)

    # Run the panel model and return output
    # TODO this ignores details like shading due to close panels
    output = panel.panel_power(irrad.direct,
                               irrad.diffuse,
                               tamb)
    sim = pd.Series(output, index=datetimes).clip_upper(capacity) * (1 - system_loss)
    if include_raw_data:
        items = [
            ('output', sim),
            ('direct', irrad.direct),
            ('diffuse', irrad.diffuse),
            ('temperature', tamb)
        ]
        return pd.DataFrame.from_items(items)
    else:
        return sim


def optimal_tilt(lat):
    """
    Returns an optimal tilt angle for the given ``lat``, assuming that
    the panel is facing towards the equator, using a simple method from [1].

    This method only works for latitudes between 0 and 50. For higher
    latitudes, a static 40 degree angle is returned.

    These results should be used with caution, but there is some
    evidence that tilt angle may not be that important [2].

    [1] http://www.solarpaneltilt.com/#fixed
    [2] http://dx.doi.org/10.1016/j.solener.2010.12.014

    Parameters
    ----------
    lat : float
        Latitude in degrees.

    Returns
    -------
    angle : float
        Optimal tilt angle in degrees.

    """
    lat = abs(lat)
    if lat <= 25:
        return lat * 0.87
    elif lat <= 50:
        return (lat * 0.76) + 3.1
    else:  # lat > 50
        # raise NotImplementedError('Not implemented for latitudes beyond 50.')
        return 40  # Simply use 40 degrees above lat 50
