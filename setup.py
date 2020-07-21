#!/usr/bin/env python

import os
from setuptools import setup, find_packages, Extension

# Sets the __version__ variable
with open("gsee/_version.py", "r") as f:
    exec(f.read())

with open("README.md", "r") as f:
    long_description = f.read()

# Numpy headers are always required for compliation, but to allow
# `python setup.py egg_info` to work on install in a clean environment,
# the numpy import must be wrapped in a try-except block.
try:
    import numpy as np

    numpy_include = [np.get_include()]
except ImportError:
    numpy_include = []


setup(
    name="gsee",
    version=__version__,
    author="Stefan Pfenninger",
    author_email="stefan@pfenninger.org",
    description="GSEE: Global Solar Energy Estimator",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/renewables-ninja/gsee",
    packages=find_packages(),
    include_package_data=True,
    ext_modules=[
        Extension(
            "gsee.climatedata_interface.kt_h_sinusfunc",
            ["gsee/climatedata_interface/kt_h_sinusfunc.pyx"],
            include_dirs=numpy_include,
        )
    ],
    zip_safe=False,
    install_requires=[
        "dask >= 2.8",
        "distributed >= 2.8",
        "joblib >= 0.12",
        "numpy >= 1.15.0",
        "pandas >= 1.0, < 1.1",
        "pvlib >= 0.6.3",
        "pyephem >= 3.7.6",
        "scipy >= 1.1.0",
        "xarray >= 0.16, < 0.17",
    ],
    setup_requires=["cython", "numpy >= 1.15.0"],
    extras_require={"generate_pdfs": ["basemap >= 1.1.0", "seaborn >= 0.9.0"],},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
    ],
)
