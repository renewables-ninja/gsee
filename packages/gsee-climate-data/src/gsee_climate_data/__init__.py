"""
MERRA-2-derived monthly PDFs of daily global horizontal irradiance,
for GSEE's climate data interface. See README.md for provenance.

Arrays: `xk` (bin values) and `pk` (bin probabilities), float32 with
dims (lat, lon, month, bins); coordinate vectors `lat`, `lon`, `month`.

"""

from importlib import resources
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import numpy as np

# Single source of truth for the version is pyproject.toml, which the release
# workflow checks against the git tag; read it back from the install metadata.
# `__package__` avoids restating the distribution name (metadata lookup
# normalises the underscore/hyphen difference).
try:
    __version__ = version(__package__)
except PackageNotFoundError:  # not installed (e.g. run from a source tree)
    __version__ = "unknown"

_FILENAME = "merra2_rad3x3_2011-2015_pdfs_land_prox.npz"


def pdfs_path():
    """Filesystem path of the bundled .npz file."""
    return Path(str(resources.files(__package__).joinpath("data", _FILENAME)))


def load():
    """The PDFs as a numpy .npz mapping with keys xk, pk, lat, lon, month."""
    return np.load(pdfs_path())
