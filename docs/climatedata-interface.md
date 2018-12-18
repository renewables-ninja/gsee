# Submodule: GSEE - Climate Data Interface

The climate data interface is included as a submodule to GSEE. It allows the processing of gridded climate data with GSEE. Climate data with annual, seasonal, monthly, daily and hourly temporal resolution are supported.

The interface reads climate data from the provided files and turns it into hourly simulations of PV electricity generation using GSEE.

The motivation behind this submodule was to simplify the use of GSEE with large sets of gridded data and to provide methods to process data with lower-than-hourly resolution. The module also allows the use of characteristic probability density functions (PDFs) describing the distribution of irradiance on the days of each month. These PDFs allow for a much more accurate calculation of monthly, seasonal and annual PV due to the non-linear character of the PV-model.

## Requirements for input files

The provided data files should be in the NetCDF4 format (other xarray-compatible data formats may work too), and contain at least the dimensions with the names 'lat', 'lon', 'time', and a data variable. At least one file with mean total irradiance data (by default in W/m2) must be provided.

Known limitations:

* Only dates up to the year 2500 can be processed (due to limitations of pandas).
* Climate data files use a 360-days calendar with 12x30 days do not work (as pandas timestamp parsing does not like days like 30th February).

## Use cases

### Working with NetCDF input files

```python

from gsee.climatedata_interface.interface import run_interface

run_interface(
    ghi_data,
    outfile,
    params,
    frequency='detect',
    diffuse_data=('', ''),
    temp_data=('', ''),
    timeformat=None,
    pdfs_file='builtin',
    num_cores=multiprocessing.cpu_count()
)
```

Required Parameters:

* __`ghi_data`__: Tuple containing the file path and the name of the data-variable for the mean total horizontal solar irradiance. E.g. `('/home/user/data/th_solar_.nc', 'rsds')`
* __`outfile`__: File path and name for the output file. E.g. */home/username/GSEE/output-file.nc*
* __`params`__: Dictionary, containing entries for each parameter used by GSEE, i.e.`'tilt', 'azim', 'tracking', 'capacity'`.

Optional Parameters:

* __`frequency`__: Temporal resolution of the input data. In addition to the default, 'detect', accepts the following strings: `['A', 'S', 'M', 'D', 'H']`, which stand for *annual, seasonal, monthly, daily, hourly* data.
* __`diffuse_data`__: Tuple containing the file path and the name of the data variable for the diffuse fraction. Only useful when horizontal irradiance is provided in hourly resolution. With higher temporal resolutions, the diffuse fraction is always anyways with the BRL model.
* __`temp_data`__: Tuple containing the file path and the name of the data variable for the ambient temperature. Can be in °C or °K (automatically detected). If no ambient temperature is provided, GSEE will assume 20°C by default.
* __`timeformat`__: Some CMIP5 datasets have time saved in the format: *day as %Y%m%d.%f* (e.g. '20070104.5'), which `xarray` cannot parse. If that is the case, `'cmip5'` can be passed and the dates will be correctly interpreted.
* __`pdfs_file`__: Either leave at its default of `'builtin'` to use the built-in PDF file, give path to a PDF file to use, or set to None to disable the use of PDFs.
* __`num_cores`__: By default all cores are used to parallelise computations. This can be limited here. If `1` is passed, then no parallelisation will be used.

### Passing an `xarray.Dataset`

Instead of letting the script read and prepare the data, an ``xarray.Dataset`` can also be passed directly to the following function (e.g. when using the module in combination with a larger application):

```python

from gsee.climatedata_interface.interface import run_interface_from_dataset

result = run_interface_from_dataset(
    data=my_dataset,  # my_dataset is an xarray.Dataset
    params=dict(tilt=35, azim=180, tracking=0, capacity=1000)
)
```

## Dealing with less-than-hourly-resolution data in GSEE

Depending on the temporal resolution of the input data and chosen options, the interface applies different methods to create synthetic hourly data to feed into GSEE.

### Diffuse irradiance fraction

The diffuse fraction is calculated using the BRL model (Ridley, 2010) with the use of the atmospheric clearness index (k<sub>t</sub>). The clearness index is estimated using the method from Elminir (2007).

### Probability density functions (PDFs)

The use of PDFs is enabled by default, as it generally produces better results. It triggers the use characteristic probability density functions (PDFs) that describe the probability with which a day with a certain amount of radiation occurs within a month. A default set of PDFs is available on a worldwide grid of 2°x2° for each month and downloaded automatically on first use.

Example PDFs:

![alt text](probability_densitiy_functions.png "Examples for characteristic PDFs")

Each PDF consists of 128 bins, each assigned a value for an amount of daily radiation and the probability of that radiation occurring.

The PDFs are then used to upsample annual, seasonal, and monthly data to daily data. This daily data gets upsampled to hourly values using a sinusoidal diurnal cycle model, taking the sum of daily radiation as well as sunrise and sunset into account. Now the data is ready to be passed to `GSEE`.

If PDFs are disabled (`pdfs_file=None`) this case the mean value given by the data is regarded as one representative day for the whole season or month. In case of annual data, two days, one in spring and one in autumn, are calculated. These days are again upsampled to hourly values using the sinusoidal diurnal cycle.

#### Creating custom monthly PDFs

By default, the climate data interface automatically downloads a set of PDFs based on the NASA MERRA-2 reanalysis `SWGDN` (surface incoming shortwave flux) field from 2011-2016, remapped to a 3°x3° grid and filtered for grid cells in proximity of land masses.

Using the function ``gsee.generate_pdfs.create_pdfs_from_ds``, additional input datasets, e.g. with higher resolution, can be processed to create custom PDFs.

## References

* Elminir, H. K., Y. A. Azzam, and F. I. Younes, 2007: Prediction of hourly and daily diffuse fraction using neural network, as compared to linear regression models. Energy, 32, 1513–1523, [doi:10.1016/j.energy.2006.10.010](http://dx.doi.org/10.1016/j.energy.2006.10.010)
* Ridley, B., J. Boland, and P. Lauret, 2010: Modelling of diffuse solar fraction with multiple predictors. Renew. Energy, 35, 478–483, [doi:10.1016/j.renene.2009.07.018](http://dx.doi.org/10.1016/j.renene.2009.07.018)
