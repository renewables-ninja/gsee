[![Master branch build status](https://img.shields.io/azure-devops/build/renewables-ninja/dcefb182-6481-4ca4-8f5e-75b022ab426d/1?style=flat-square)](https://dev.azure.com/renewables-ninja/gsee/_build?definitionId=1)
[![Test coverage](https://img.shields.io/codecov/c/github/renewables-ninja/gsee?style=flat-square&token=1b25079ab156419b919462aaba0f469e)](https://codecov.io/gh/renewables-ninja/gsee)
[![PyPI version](https://img.shields.io/pypi/v/gsee.svg?style=flat-square)](https://pypi.python.org/pypi/gsee)
[![conda-forge version](https://img.shields.io/conda/vn/conda-forge/gsee.svg?style=flat-square)](https://anaconda.org/conda-forge/gsee)

# GSEE: Global Solar Energy Estimator

`GSEE` is a solar energy simulation library designed for rapid calculations and ease of use. [Renewables.ninja](https://www.renewables.ninja/) uses `GSEE`.

The development of `GSEE` predates the existence of [`pvlib-python`](https://pvlib-python.readthedocs.io/) but builds on its functionality as of v0.4.0. Use `GSEE` if you want fast simulations with sensible defaults and solar energy technologies other than PV, and `pvlib-python` if you need control over the nuts and bolts of simulating PV systems.

## Installation

`GSEE` requires Python 3. The recommended way to install is through the [Anaconda Python distribution](https://www.continuum.io/downloads) and `conda-forge`:

    conda install -c conda-forge gsee

You can also install with `pip install gsee`, but if you do so, and do not already have `numpy` installed, you will get a compiler error when pip tries to build to `climatedata_interface` Cython extension.

## Documentation

See the [documentation](https://gsee.readthedocs.io/) for more information on `GSEE`'s functionality and for examples.

## Credits and contact

Contact [Stefan Pfenninger](mailto:stefan.pfenninger@usys.ethz.ch) for questions about `GSEE`. `GSEE` is also a component of the [Renewables.ninja](https://www.renewables.ninja) project, developed by Stefan Pfenninger and Iain Staffell. Use the [contact page](https://www.renewables.ninja/about) there if you want more information about Renewables.ninja.

## Citation

If you use `GSEE` or code derived from it in academic work, please cite:

Stefan Pfenninger and Iain Staffell (2016). Long-term patterns of European PV output using 30 years of validated hourly reanalysis and satellite data. *Energy* 114, pp. 1251-1265. [doi: 10.1016/j.energy.2016.08.060](https://doi.org/10.1016/j.energy.2016.08.060)

## License

BSD-3-Clause
