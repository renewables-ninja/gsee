# gsee -- global solar energy estimator

`gsee` is a lightweight library designed for speed and ease of use. [Renewables.ninja](https://www.renewables.ninja/) PV data is generated with `gsee`.

## Requirements

Only tested on Python 3.

Required libraries:

* [pyephem](http://rhodesmill.org/pyephem/)
* [numpy](http://www.numpy.org/)
* [pandas](http://pandas.pydata.org/)

## Installation

The recommended way to get numpy and pandas is to use the [Anaconda Python distribution](https://www.continuum.io/downloads), then install gsee:

    pip install -e git+https://github.com/renewables-ninja/gsee.git#egg=gsee

## Background

This is a collection of tools to estimate output from solar power plants.

`trigon` contains functions to calculate irradiance on an inclined plane. `brl_model` is an implementation of a method to derive the diffuse fraction of irradiance, based on Ridley et al. (2010). `pv` is a model to derive power output from solar irradiance.

## Examples

### Aperture irradiance on a panel with 2-axis tracking

```python
locations = (22.78, 5.51)
plane_irradiance = gsee.trigon.aperture_irradiance(data['direct_horizontal'],
                                                   data['diffuse_horizontal'],
                                                   location, tracking=2)
```

## Plant models

Currently available: pv

* __pv__: based on published PV module performance data, see `pv.py` for details

A model can be imported like this: ``import gsee.pv``

A model implements a model class (e.g. ``PVPlant``) with the relevant settings, and a ``run_model()`` function that take time series data (a pandas Series) and runs a default instance of the model class, but can also take a ``model`` argument to specify a custom-configured model instance.

## Citation

Stefan Pfenninger and Iain Staffell (2016). Long-term patterns of European PV output using 30 years of validated hourly reanalysis and satellite data. *Energy* 114, pp. 1251-1265. [doi: 10.1016/j.energy.2016.08.060](https://dx.doi.org/10.1016/j.energy.2016.08.060)

## License

BSD-3-Clause
