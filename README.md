[![Build Status](https://img.shields.io/travis/com/renewables-ninja/gsee/master.svg?style=flat-square)](https://travis-ci.com/renewables-ninja/gsee) [![Coverage](https://img.shields.io/coveralls/renewables-ninja/gsee.svg?style=flat-square)](https://coveralls.io/r/renewables-ninja/gsee) [![PyPI version](https://img.shields.io/pypi/v/gsee.svg?style=flat-square)](https://pypi.python.org/pypi/gsee)

# GSEE: Global Solar Energy Estimator

`GSEE` is a solar energy simulation library designed for rapid calculations and ease of use. [Renewables.ninja](https://www.renewables.ninja/) uses `GSEE`.

## Requirements

Works only with Python 3. Required libraries:

* [joblib](https://joblib.readthedocs.io/en/latest/)
* [numpy](https://numpy.org/)
* [pandas](https://pandas.pydata.org/)
* [pyephem](https://pypi.org/project/ephem/)
* [scipy](https://scipy.org/)
* [xarray](https://xarray.pydata.org/)

## Installation

Simply install with `pip`:

    pip install gsee

The recommended way to install the required scientific libraries is to use the [Anaconda Python distribution](https://www.continuum.io/downloads).

**Known issue**: If you do not already have `numpy` installed, you will get a compiler error when pip tries to build to `climatedata_interface` Cython extension.

## Functionality

The following submodules are available:

* __``brl_model``__: an implementation of the BRL model, a method to derive the diffuse fraction of irradiance, based on Ridley et al. (2010)
* __``climatedata_interface``__: an interface to use GSEE with annual, seasonal, monthly or daily data. See [docs/climatedata_interface](docs/climatedata_interface.md) for details.
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

For more information, see the [climate data interface documentation](docs/climatedata-interface.md).

## Development

To install the latest development version directly from GitHub:

    pip install -e git+https://github.com/renewables-ninja/gsee.git#egg=gsee

To build the `climatedata_interface` submodule [Cython >= 0.28.5](http://cython.org/) is required.

## Credits and contact

Contact [Stefan Pfenninger](mailto:stefan.pfenninger@usys.ethz.ch) for questions about `GSEE`. `GSEE` is also a component of the [Renewables.ninja](https://www.renewables.ninja) project, developed by Stefan Pfenninger and Iain Staffell. Use the [contact page](https://www.renewables.ninja/about) there if you want more information about Renewables.ninja.

## Citation

If you use `GSEE` or code derived from it in academic work, please cite:

Stefan Pfenninger and Iain Staffell (2016). Long-term patterns of European PV output using 30 years of validated hourly reanalysis and satellite data. *Energy* 114, pp. 1251-1265. [doi: 10.1016/j.energy.2016.08.060](https://doi.org/10.1016/j.energy.2016.08.060)

## License

BSD-3-Clause
