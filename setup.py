#!/usr/bin/env python

from setuptools import setup, find_packages

# Sets the __version__ variable
exec(open('gsee/_version.py').read())

setup(
    name='gsee',
    version=__version__,
    author='Stefan Pfenninger',
    author_email='stefan@pfenninger.org',
    description='gsee -- global solar energy estimator',
    packages=find_packages(),
    install_requires=[
        "pyephem >= 3.7.6.0",
        "numpy >= 1.10.1",
        "pandas >= 0.18.0"
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Science/Research',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
)
