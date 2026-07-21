"""
Frozen pre-0.4 panel and inverter models. Do not modify.

Copied verbatim from the pre-0.4 `gsee.pv` so that `gsee.legacy.run_model`
replicates old simulation runs regardless of how the current `gsee.pv`
panel classes evolve.

The `module_temperature` methods are the one addition: output-only
accessors used by `run_model(include_raw_data=True)`. They do not
affect computed output.

Sources:

{1} Huld, T. et al., 2010. Mapping the performance of PV modules,
    effects of module type and data averaging. Solar Energy, 84(2),
    p.324-338. DOI: 10.1016/j.solener.2009.12.002

{2} Dobos, Aron P., 2014. PVWatts Version 5 Manual. NREL Technical
    Report. Available at: https://www.nrel.gov/docs/fy14osti/62641.pdf

"""

import warnings

import numpy as np

# Constants
R_TAMB = 20  # Reference ambient temperature (degC)
R_TMOD = 25  # Reference module temperature (degC)
R_IRRADIANCE = 1000  # Reference irradiance (W/m2)
R_WINDSPEED = 5  # Reference wind speed (m/2)


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
    """

    def __init__(self, panel_aperture=1.0, panel_ref_efficiency=1.0):
        super().__init__()
        # Panel characteristics
        self.panel_aperture = panel_aperture
        self.panel_ref_efficiency = panel_ref_efficiency

    def panel_power(self, irradiance, tamb=None):
        """
        Returns electricity in W from PV panel(s) based on given input data.

        Parameters
        ----------
        irradiance : pandas Series
            Incident irradiance hitting the panel(s) in W/m2.
        tamb : pandas Series, default None
            Ambient temperature in deg C. If not given, R_TAMB is used
            for all values.

        """
        if tamb is not None:
            assert irradiance.index.equals(tamb.index), "Data indices must match"
        return (
            irradiance
            * self.panel_aperture
            * self.panel_relative_efficiency(irradiance, tamb)
            * self.panel_ref_efficiency
        )

    def panel_relative_efficiency(self, irradiance, tamb):
        raise NotImplementedError(
            "Must subclass and specify relative efficiency function"
        )


class HuldPanel(PVPanel):
    """
    Parametric PV panel model from Huld et al., 2010 {1}.

    c_temp_amb: float, default 1 degC / degC
        Panel temperature coefficient of ambient temperature
    c_temp_irrad: float, default 0.035 degC / (W/m2)
        Panel temperature coefficient of irradiance. According to {1},
        reasonable values for this for c-Si are:
            0.035  # Free-standing module, assuming no wind
            0.05   # Building-integrated module

    """

    def __init__(self, c_temp_amb=1, c_temp_irrad=0.035, **kwargs):
        super().__init__(**kwargs)
        # Panel temperature estimation
        self.c_temp_tamb = c_temp_amb
        self.c_temp_irrad = c_temp_irrad

    def module_temperature(self, irradiance, tamb):
        # Output-only accessor (see module docstring)
        return self.c_temp_tamb * tamb + self.c_temp_irrad * irradiance

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
            warnings.simplefilter("ignore")
            eff = (
                1
                + self.k_1 * np.log(G_)
                + self.k_2 * (np.log(G_)) ** 2
                + T_ * (self.k_3 + self.k_4 * np.log(G_) + self.k_5 * (np.log(G_)) ** 2)
                + self.k_6 * (T_**2)
            )
        eff = eff.fillna(0)  # NaNs in case that G_ was <= 0
        eff[eff < 0] = 0  # Also make sure efficiency can't be negative
        return eff


class HuldCSiPanel(HuldPanel):
    """c-Si technology, based on data from {1}"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.k_1 = -0.017162
        self.k_2 = -0.040289
        self.k_3 = -0.004681
        self.k_4 = 0.000148
        self.k_5 = 0.000169
        self.k_6 = 0.000005


class HuldCISPanel(HuldPanel):
    """CIS technology, based on data from {1}"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.k_1 = -0.005521
        self.k_2 = -0.038492
        self.k_3 = -0.003701
        self.k_4 = -0.000899
        self.k_5 = -0.001248
        self.k_6 = 0.000001


class HuldCdTePanel(HuldPanel):
    """CdTe technology, based on data from {1}"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.k_1 = -0.103251
        self.k_2 = -0.040446
        self.k_3 = -0.001667
        self.k_4 = -0.002075
        self.k_5 = -0.001445
        self.k_6 = -0.000023


_PANEL_TYPES = {"csi": HuldCSiPanel, "cis": HuldCISPanel, "cdte": HuldCdTePanel}


class Inverter(object):
    """
    PV inverter curve from {2}.

    By default, we assume that nominal DC-to-AC efficiency
    is 1.0, so that AC and DC nameplate capacities are equal.

    """

    def __init__(self, ac_capacity, eff_ref=0.9637, eff_nom=1.0):
        super().__init__()
        self.ac_capacity = ac_capacity
        self.dc_capacity = ac_capacity / eff_nom
        self.efficiency_term = eff_nom / eff_ref

    def ac_output(self, dc_in):
        """
        Parameters
        ----------
        df_in : float
            DC electricity input in W

        Returns
        -------
        ac_output : float
            AC electricity output in W

        """
        if dc_in == 0:
            return 0
        else:
            zeta = dc_in / self.dc_capacity
            eff = self.efficiency_term * (-0.0162 * zeta - 0.0059 / zeta + 0.9858)
            return min(self.ac_capacity, dc_in * eff)
