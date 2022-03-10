# GSEE Redux: Global Solar Energy Estimator

This is a fork of [GSEE](https://github.com/renewables-ninja/gsee).

`GSEE` is a solar energy simulation library designed for rapid calculations and ease of use. [Renewables.ninja](https://www.renewables.ninja/) uses `GSEE`.

The development of `GSEE` predates the existence of [`pvlib-python`](https://pvlib-python.readthedocs.io/) but builds on its functionality as of v0.4.0. Use `GSEE` if you want fast simulations with sensible defaults and solar energy technologies other than PV, and `pvlib-python` if you need control over the nuts and bolts of simulating PV systems.

## Installation

`GSEE` requires Python 3. The recommended way to install is through the [Anaconda Python distribution](https://www.continuum.io/downloads) and `conda-forge`:

    conda install -c conda-forge gsee

You can also install with `pip install gsee`, but if you do so, and do not already have `numpy` installed, you will get a compiler error when pip tries to build to `climatedata_interface` Cython extension.

## Documentation

See the [documentation](https://gsee.readthedocs.io/) for more information on `GSEE`'s functionality and for examples.

## License

BSD-3-Clause
