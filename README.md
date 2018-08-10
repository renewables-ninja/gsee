# GSEE: global solar energy estimator

`GSEE` is a small solar energy simulation library designed for speed and ease of use. [Renewables.ninja](https://www.renewables.ninja/) PV data is generated with `GSEE`.

## Requirements

Works only with Python 3. Required libraries:

* [pyephem](http://rhodesmill.org/pyephem/)
* [numpy](http://www.numpy.org/)
* [pandas](http://pandas.pydata.org/)

## Installation

Simply install with `pip`:

    pip install gsee

The recommended way to get the required numpy and pandas libraries is to use the [Anaconda Python distribution](https://www.continuum.io/downloads).

## Functionality

The following submodules are available:

* __``pv``__: electric output from PV a panel
* __``trigon``__: functions to calculate irradiance on an inclined plane
* __``brl_model``__: an implementation of the BRL model, a method to derive the diffuse fraction of irradiance, based on Ridley et al. (2010)

A model can be imported like this: ``import gsee.pv``

A plant simulation model implements a model class (e.g. ``PVPlant``) with the relevant settings, and a ``run_model()`` function that take time series data (a pandas Series) and runs a default instance of the model class, but can also take a ``model`` argument to specify a custom-configured model instance.

## Examples

### Power output from a PV system with fixed panels

In this example, ``data`` must be a pandas.DataFrame with columns ``global_horizontal`` (in kW/m2), ``diffuse_fraction``, and optionally a ``temperature`` column for ambient air temperature (in degrees Celsius).

```python
result = gsee.pv.run_model(
    data,
    coords=(22.78, 5.51),  # Latitude and longitude
    tilt=30, # 30 degrees tilt angle
    azim=180,  # facing towards equator,
    tracking=0,  # fixed - no tracking
    capacity=1,  # 1kW
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

## Development

To install the latest development version directly from GitHub:

    pip install -e git+https://github.com/renewables-ninja/gsee.git#egg=gsee

## Credits and contact

Contact [Stefan Pfenninger](mailto:stefan.pfenninger@usys.ethz.ch) for questions about `GSEE`. `GSEE` is also a component of the [Renewables.ninja](https://www.renewables.ninja) project, developed by Stefan Pfenninger and Iain Staffell. Use the [contact page](https://www.renewables.ninja/about) there if you want more information about Renewables.ninja.

## Citation

If you use `GSEE` or code derived from it in academic work, please cite:

Stefan Pfenninger and Iain Staffell (2016). Long-term patterns of European PV output using 30 years of validated hourly reanalysis and satellite data. *Energy* 114, pp. 1251-1265. [doi: 10.1016/j.energy.2016.08.060](https://doi.org/10.1016/j.energy.2016.08.060)

## License

BSD-3-Clause
