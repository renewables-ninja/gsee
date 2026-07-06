"""
Frozen pre-0.4 single-site implementation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Superseded by the vectorized core (`gsee.core`).
Kept for backwards compatibility.
Requires the optional `ephem` dependency:

    pip install gsee[legacy]

"""

try:
    import ephem  # noqa: F401
except ImportError as err:
    raise ImportError(
        "gsee.legacy requires the optional 'ephem' dependency; "
        "install it with: pip install gsee[legacy]"
    ) from err

from gsee.legacy import brl_model, trigon
from gsee.legacy.pv import run_model

__all__ = ["brl_model", "run_model", "trigon"]
