# Release History

## 0.4.0 (dev)

* Added: PV model based on the [single-diode model in pvlib-python](https://pvlib-python.readthedocs.io/en/latest/generated/pvlib.pvsystem.singlediode.html)
* Modified: Reorganise PV models; existing Huld-based models now subclass `HuldPanel`
* Added: Tools to deal with the CEC module database
* Added: Inverter model based on PVWatts Version 5 and differentiation between DC and AC output, alongside new `inverter_capacity` and `use_inverter` arguments to `pv.run_model()`
* Fixed: Clean up non-standard CMIP time attributes in climate data interface
* Fixed: Improve CF conformity of climate data interface
* Modified: Clean up and blacken code
* Modified: Compatibility with more recent versions of pandas and xarray

## 0.3.1 (2019-07-23)

* Fixed: erroneous angles in 1-axis tracking with non-horizontal tracking axes
* Fixed: minor improvement in calculation of sunrise and sunset times to deal with cases where sun never rises or sets

## 0.3.0 (2018-12-19)

* Added: climate data interface
* Modified: PV model now expects inputs as W, not kW
* Fixed: minor improvements in `trigon.py` (sunrise/sunset times now take sun radius into consideration; clipping of zeros to avoid NaNs)

## 0.2.1 (2018-09-07)

* Fix: clip maximum panel output

## 0.2.0 (2018-08-10)

* PyPI package
* Minor bug fixes

## 0.1.0 (2016-09-01)

* First version
