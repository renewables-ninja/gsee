# gsee -- global solar energy estimator

## Requirements

Only tested on Python 3.

* [pyephem](http://rhodesmill.org/pyephem/) >= 3.7.5.1
* [pandas](http://pandas.pydata.org/) >= 0.15.0

## Installation

    pip install -e git+https://github.com/renewables-ninja/gsee.git#egg=gsee

## Background

This is a collection of tools to estimate output from solar power plants.

`trigon` contains functions to calculate irradiance on an inclined plane. `brl_model` is an implementation of a method to derive the diffuse fraction of irradiance, based on Ridley et al. (2010). `pv` is a model to derive power output from solar irradiance.

`processing` contains helper functions to access the `trigon` and `brl_model` parts of the code.

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

## License

BSD-3-Clause
