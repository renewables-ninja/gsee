"""
Generate `model-comparison.svg` for the PV models documentation page.

"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from gsee import cec_tools
from gsee.core import panel
from gsee.pv import CEC_PARAMETERS

OUTFILE = "docs/figures/model-comparison.svg"

TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e0dfdc"

SERIES = {
    "Huld c-Si ('csi')": dict(color="#2a78d6", ls="-"),
    "Huld c-Si updated ('csi-new')": dict(color="#1baf7a", ls="--"),
    "CEC median mono-c-Si ('cec-csi-median')": dict(color="#eda100", ls="-."),
}

R_TMOD = 25.0
R_IRRADIANCE = 1000.0


def huld_eff(technology, irradiance, module_temperature):
    # c_temp_amb=1, c_temp_irrad=0: tamb input is the module temperature
    return panel.huld_relative_efficiency(
        irradiance, module_temperature, technology, c_temp_amb=1.0, c_temp_irrad=0.0
    )


def cec_eff(irradiance, module_temperature):
    return cec_tools.relative_eff(
        pd.Series(irradiance),
        pd.Series(module_temperature, index=range(len(irradiance))),
        CEC_PARAMETERS["Mono-c-Si-Median"],
    ).to_numpy()


def compute(irradiance, module_temperature):
    return {
        "Huld c-Si ('csi')": huld_eff("csi", irradiance, module_temperature),
        "Huld c-Si updated ('csi-new')": huld_eff(
            "csi-new", irradiance, module_temperature
        ),
        "CEC median mono-c-Si ('cec-csi-median')": cec_eff(
            irradiance, module_temperature
        ),
    }


def style_axis(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(TEXT_SECONDARY)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=9)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.axhline(1.0, color=TEXT_SECONDARY, lw=0.8, alpha=0.5)


def main():
    fig, (ax0, ax1) = plt.subplots(
        ncols=2, figsize=(9.6, 4.2), layout="constrained", sharey=True
    )

    irradiance = np.arange(10.0, 1001.0)
    for label, curve in compute(irradiance, np.full_like(irradiance, R_TMOD)).items():
        ax0.plot(irradiance, curve, lw=2, label=label, **SERIES[label])
    ax0.set_xlabel("In-plane irradiance (W/m²)", color=TEXT_PRIMARY)
    ax0.set_ylabel("Relative efficiency", color=TEXT_PRIMARY)
    ax0.set_xlim(0, 1000)
    ax0.text(
        0.95,
        0.08,
        "$T_{module}$ = 25 °C",
        transform=ax0.transAxes,
        ha="right",
        fontsize=10,
        color=TEXT_SECONDARY,
    )

    module_temperature = np.arange(-30.0, 81.0)
    for label, curve in compute(
        np.full_like(module_temperature, R_IRRADIANCE), module_temperature
    ).items():
        ax1.plot(module_temperature, curve, lw=2, label=label, **SERIES[label])
    ax1.set_xlabel("Module temperature (°C)", color=TEXT_PRIMARY)
    ax1.set_xlim(-30, 80)
    ax1.axvline(R_TMOD, color=GRID, lw=0.8)
    ax1.text(
        0.95,
        0.08,
        "$G$ = 1000 W/m²",
        transform=ax1.transAxes,
        ha="right",
        fontsize=10,
        color=TEXT_SECONDARY,
    )

    ax0.set_ylim(0.65, 1.3)
    ax0.legend(
        loc="upper left",
        bbox_to_anchor=(0.02, 1.0),
        frameon=False,
        fontsize=9,
        labelcolor=TEXT_PRIMARY,
    )

    fig.savefig(OUTFILE, format="svg", bbox_inches="tight")
    print("Written to", OUTFILE)


if __name__ == "__main__":
    main()
