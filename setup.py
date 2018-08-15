#!/usr/bin/env python

from setuptools import setup, find_packages
from Cython.Build import cythonize #added
import numpy

# Sets the __version__ variable
exec(open('gsee/_version.py').read())

with open("README.md", "r") as f:
    long_description = f.read()

setup(
    name='gsee',
    version=__version__,
    author='Stefan Pfenninger',
    author_email='stefan@pfenninger.org',
    description='GSEE: Global Solar Energy Estimator, including climate data interface',
    packages=find_packages(),
    install_requires=[
        "pyephem >= 3.7.6.0",
        "numpy >= 1.10.1",
        "pandas >= 0.18.0",
        "joblib >= 0.11",
        "scipy >= 0.19.1",
        "xarray >= 0.10.7",
        "Cython >= 0.27.3"
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Science/Research',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
    ext_modules = cythonize("gsee/climdata_interface/cyth_func.pyx"), #added
    include_package_data=True,
    include_dirs=[numpy.get_include()]
)
