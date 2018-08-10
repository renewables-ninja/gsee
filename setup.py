#!/usr/bin/env python

from setuptools import setup, find_packages

# Sets the __version__ variable
exec(open('gsee/_version.py').read())

with open("README.md", "r") as f:
    long_description = f.read()

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
