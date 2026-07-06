"""
Deprecated alias of `gsee.legacy.trigon`, which requires the optional
'legacy' extra (`pip install gsee[legacy]`). Will be removed in 0.5.0.

"""

import warnings

from gsee.legacy.trigon import (
    aperture_irradiance,
    sun_angles,
    sun_angles_legacy,
    sun_rise_set_times,
    sun_rise_set_times_ephem,
)

warnings.warn(
    "gsee.trigon has moved to gsee.legacy.trigon; this alias will be removed "
    "in 0.5.0 and requires the optional 'legacy' extra "
    "(pip install gsee[legacy])",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "aperture_irradiance",
    "sun_angles",
    "sun_angles_legacy",
    "sun_rise_set_times",
    "sun_rise_set_times_ephem",
]
