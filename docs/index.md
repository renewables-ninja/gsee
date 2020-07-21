<h1 style="font-size: 2.1rem; margin: 0">GSEE: Global Solar Energy Estimator</h1>

---

[![Master branch build status](https://img.shields.io/azure-devops/build/renewables-ninja/dcefb182-6481-4ca4-8f5e-75b022ab426d/1?style=flat-square)](https://dev.azure.com/renewables-ninja/gsee/_build?definitionId=1)
[![Test coverage](https://img.shields.io/codecov/c/github/renewables-ninja/gsee?style=flat-square&token=1b25079ab156419b919462aaba0f469e)](https://codecov.io/gh/renewables-ninja/gsee)
[![PyPI version](https://img.shields.io/pypi/v/gsee.svg?style=flat-square)](https://pypi.python.org/pypi/gsee)
[![conda-forge version](https://img.shields.io/conda/vn/conda-forge/gsee.svg?style=flat-square)](https://anaconda.org/conda-forge/gsee)

<br>

`GSEE` is a solar energy simulation library designed for rapid calculations and ease of use. [Renewables.ninja](https://www.renewables.ninja/) uses `GSEE`.

The development of `GSEE` predates the existence of [`pvlib-python`](https://pvlib-python.readthedocs.io/) but builds on its functionality as of v0.4.0. Use `GSEE` if you want fast simulations with sensible defaults and solar energy technologies other than PV, and `pvlib-python` if you need control over the nuts and bolts of simulating PV systems.

## Installation

`GSEE` requires Python 3. The recommended way to install is through the [Anaconda Python distribution](https://www.continuum.io/downloads) and `conda-forge`:

    conda install -c conda-forge gsee

You can also install with `pip install gsee`, but if you do so, and do not already have `numpy` installed, you will get a compiler error when pip tries to build to `climatedata_interface` Cython extension.

### Development version

To install the latest development version directly from GitHub:

    pip install -e git+https://github.com/renewables-ninja/gsee.git#egg=gsee

To build the `climatedata_interface` submodule [Cython >= 0.28.5](http://cython.org/) is required.

## Functionality

The following submodules are available:

* __``brl_model``__: an implementation of the BRL model, a method to derive the diffuse fraction of irradiance, based on Ridley et al. (2010)
* __``climatedata_interface``__: an interface to use GSEE with annual, seasonal, monthly or daily data. See [Climate Data Interface](climatedata-interface.md) for details.
* __``pv``__: electric output from PV a panel
* __``trigon``__: functions to calculate irradiance on an inclined plane

A model can be imported like this: ``import gsee.pv``

A plant simulation model implements a model class (e.g. ``PVPlant``) with the relevant settings, and a ``run_model()`` function that take time series data (a pandas Series) and runs a default instance of the model class, but can also take a ``model`` argument to specify a custom-configured model instance.

## Examples

### Power output from a PV system with fixed panels

In this example, ``data`` must be a pandas.DataFrame with columns ``global_horizontal`` (in W/m2), ``diffuse_fraction``, and optionally a ``temperature`` column for ambient air temperature (in degrees Celsius).

```python
result = gsee.pv.run_model(
    data,
    coords=(22.78, 5.51),  # Latitude and longitude
    tilt=30, # 30 degrees tilt angle
    azim=180,  # facing towards equator,
    tracking=0,  # fixed - no tracking
    capacity=1000,  # 1000 W
)
```

### Aperture irradiance on a panel with 2-axis tracking

```python
location = (22.78, 5.51)
plane_irradiance = gsee.trigon.aperture_irradiance(
    data['direct_horizontal'], data['diffuse_horizontal'],
    location, tracking=2
)
```

### Climate data Interface

Example use directly reading NetCDF files with GHI, diffuse irradiance fraction, and temperature data:

```python
from gsee.climatedata_interface.interface import run_interface

run_interface(
    ghi_data=('ghi_input.nc', 'ghi'),  # Tuple of (input file path, variable name)
    diffuse_data=('diffuse_fraction_input.nc', 'diff_frac'),
    temp_data=('temperature_input.nc', 't2m'),
    outfile='output_file.nc',
    params=dict(tilt=35, azim=180, tracking=0, capacity=1000),
    frequency='detect'
)
```

Tilt can be given as a latitude-dependent function instead of static value:

```python
params = dict(tilt=lambda lat: 0.35396 * lat + 16.84775, ...)
```

Instead of letting the climate data interface read and prepare data from NetCDF files, an `xarray.Dataset` can also be passed directly (e.g. when using the module in combination with a larger application):

```python
from gsee.climatedata_interface.interface import run_interface_from_dataset

result = run_interface_from_dataset(
    data=my_dataset,  # my_dataset is an xarray.Dataset
    params=dict(tilt=35, azim=180, tracking=0, capacity=1000)
)
```

By default, a built-in file with monthly probability density functions is automatically downloaded and used to generate synthetic daily irradiance.

For more information, see the [climate data interface documentation](climatedata-interface.md).

## Credits and contact

Contact [Stefan Pfenninger](mailto:stefan.pfenninger@usys.ethz.ch) for questions about `GSEE`. `GSEE` is also a component of the [Renewables.ninja](https://www.renewables.ninja) project, developed by Stefan Pfenninger and Iain Staffell. Use the [contact page](https://www.renewables.ninja/about) there if you want more information about Renewables.ninja.

## Citation

If you use `GSEE` or code derived from it in academic work, please cite:

Stefan Pfenninger and Iain Staffell (2016). Long-term patterns of European PV output using 30 years of validated hourly reanalysis and satellite data. *Energy* 114, pp. 1251-1265. [doi: 10.1016/j.energy.2016.08.060](https://doi.org/10.1016/j.energy.2016.08.060)

## License

BSD-3-Clause
