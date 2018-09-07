#!/usr/bin/env python

from setuptools import setup, find_packages, Extension

# Sets the __version__ variable
with open('gsee/_version.py', 'r') as f:
    exec(f.read())

with open('README.md', 'r') as f:
    long_description = f.read()

# If Cython is available, cythonize the .pyx module to a C source file.
# Else, use the pre-compiled C module.
try:
    from Cython.Build import cythonize
    # If Cython is available, numpy must be available too.
    import numpy as np
except ImportError:
    print('Attempting to compile pre-built Cython module')
    from setuptools.command.build_ext import build_ext
    ext_modules = [Extension(
        "gsee/climatedata_interface/*",
        ["gsee/climatedata_interface/*.c"]
    )]
else:
    print('Attempting to build Cython module from Cython source')
    ext_modules = cythonize([
        Extension(
            "gsee/climatedata_interface/*",
            ["gsee/climatedata_interface/*.pyx"],
            include_dirs=[np.get_include()]
        )
    ])

setup(
    name='gsee',
    version=__version__,
    author='Stefan Pfenninger',
    author_email='stefan@pfenninger.org',
    description='GSEE: Global Solar Energy Estimator',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/renewables-ninja/gsee',
    packages=find_packages(),
    include_package_data=True,
    ext_modules=ext_modules,
    zip_safe=False,
    install_requires=[
        "numpy >= 1.15",
        "pandas >= 0.23",
        "pyephem >= 3.7.6",
        "scipy >= 1.1",
        "xarray >= 0.10.8",
    ],
    setup_requires=[
        'Cython >= 0.27.3',
        "numpy >= 1.15",
    ],
    extras_require={
        'multicore': ["joblib >= 0.12"],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Science/Research',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
)
