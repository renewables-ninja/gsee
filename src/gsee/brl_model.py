"""
Deprecated alias of `gsee.legacy.brl_model`, which requires the
optional 'legacy' extra (`pip install gsee[legacy]`). Will be removed
in 0.5.0.

"""

import warnings

from gsee.legacy.brl_model import DEFAULT_PARAMS, run

warnings.warn(
    "gsee.brl_model has moved to gsee.legacy.brl_model; this alias will be "
    "removed in 0.5.0 and requires the optional 'legacy' extra "
    "(pip install gsee[legacy])",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["DEFAULT_PARAMS", "run"]
