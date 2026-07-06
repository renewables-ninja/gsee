[![Tests](https://img.shields.io/github/actions/workflow/status/renewables-ninja/gsee/test.yml?style=flat-square&label=tests)](https://github.com/renewables-ninja/gsee/actions/workflows/test.yml)
[![Test coverage](https://img.shields.io/codecov/c/github/renewables-ninja/gsee?style=flat-square)](https://codecov.io/gh/renewables-ninja/gsee)
[![PyPI version](https://img.shields.io/pypi/v/gsee.svg?style=flat-square)](https://pypi.python.org/pypi/gsee)
[![conda-forge version](https://img.shields.io/conda/vn/conda-forge/gsee.svg?style=flat-square)](https://anaconda.org/conda-forge/gsee)

# GSEE: Global Solar Energy Estimator

`GSEE` is a solar energy simulation library designed for rapid calculations and ease of use. It can run for a single site with a pandas DataFrame to hundreds of thousands of sites or global grids with xarray Datasets. [Renewables.ninja](https://www.renewables.ninja/) uses `GSEE`.

The development of `GSEE` predates the existence of [`pvlib-python`](https://pvlib-python.readthedocs.io/) but builds on its functionality as of v0.4.0. Use `GSEE` if you want fast simulations with sensible defaults and/or its climate data interface, and `pvlib-python` if you need control over the nuts and bolts of simulating PV systems.

## Installation

    pip install gsee

To also install the built-in irradiance probability density functions used by the climate data interface:

    pip install gsee[climate]

`GSEE` is also available via `conda-forge`.

## Documentation

See the [documentation](https://gsee.readthedocs.io/) for more information on `GSEE`'s functionality and for examples.

## Credits and contact

Contact [Stefan Pfenninger](mailto:s.pfenninger@tudelft.nl) for questions about `GSEE`. `GSEE` is also a component of the [Renewables.ninja](https://www.renewables.ninja) project, developed by Stefan Pfenninger and Iain Staffell. Use the [contact page](https://www.renewables.ninja/about) there if you want more information about Renewables.ninja.

## Citation

If you use `GSEE` or code derived from it in academic work, please cite:

Stefan Pfenninger and Iain Staffell (2016). Long-term patterns of European PV output using 30 years of validated hourly reanalysis and satellite data. _Energy_ 114, pp. 1251-1265. [doi: 10.1016/j.energy.2016.08.060](https://doi.org/10.1016/j.energy.2016.08.060)

## License

BSD-3-Clause
