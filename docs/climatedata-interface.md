# Submodule: GSEE - Climate Data Interface

The climate data interface is included as a submodule to the GSEE. It allows the processing of gridded climate data with the GSEE. Climate data with annual, seasonal, monthly, daily and hourly temporal resolution is supported. The motivation behind this submodule was to simplify the use of the GSEE with large sets of gridded data and to provide methods to process data with lower resolution than hourly data, since this is a rare good. The module also allows the use of characteristic probability densitiy functions (PDFs) describing the distribution of irradiance on the days of each month. These PDFs allow for a much more accurate calculation of monthly, seasonal and annual PV due to the non-linear character of the PV-model.

#### Required libraries:
Additionally to the requirements of the gsee:

+ [joblib](https://pypi.org/project/joblib/)
+ [SciPy](https://www.scipy.org/)
+ [Xarray](http://xarray.pydata.org/en/stable/)
+ [Cython](http://cython.org/)

#### Requirements for input files:
The provided data files must be in the the ```netCDF``` format and contain at least the three dimensions with the names 'lat', 'lon', 'time' and a data-variable. At least one file with mean total irradiance data (by default in W/m2) must be provided. Up to this moment only dates with up to the years 2500 can be processed (due to limitations of pandas). Working on a fix... Some climate data files also use a 360-days calendar with 12x30 days. These files do not work as pandas does not like days like 30. February.

## What does it do?
**Very short**: The interface reads climate data from the provided files and processes it with the GSEE in different manners depending on the temporal resolution and chosen options.

**Much longer**:

#### The main function an its parameters
The main function has the following parameters: (imported with ```import gsee.climdata_interface.interface```)

```python
def run_interface(th_tuple: tuple, outfile: str, params: List[str],
                  df_tuple=('', ''), at_tuple=('', ''),
                  in_freq='detect', timeformat='other', use_PDFs=True,
                  th_factor=1/1000, num_cores=multiprocessing.cpu_count()):
```

**Required Parameters:**

* __`th_tuple`__: Tuple containing the filepath and the name of the data-variable for the mean total horizontal solar iradiance. E.g. `('/home/user/data/th_solar_.nc', 'rsds')`
* __`outfile`__: File path and name for the output file. E.g. */home/username/GSEE/output-file.nc*
* __`parameters`__: List of strings containing parameters for the GSEE in the following order `['tilt', 'azimuth', 'tracking', 'capacity']`. Instead of a number you can also pass a function depending on latitute for `tilt`, see Example.

**Optional Paramters:**

* __`df_tuple`__: Tuple containing the filepath and the name of the data-variable for the diffuse fraction. Only usefull when horizontal irradianceis provided in hourly resolution. With higher temporal resolutions, the diffuse fraction is estimated anyways with the BRL-model (`from gsee import brl_model`)
* __`at_tuple`__: Tuple containing the filepath and the name of the data-variable for the ambient temperature. Can be in °C or °K. If no ambient temperature is provided, GSEE will assume 20°C by default.
*  __`in_freq`__: Temporal resolution of the input data. Accepts the following strings: `['A', 'S', 'M', 'D', 'H']`, which stand for *annual, seasonal, monthly, daily, hourly* data. If no argument is passed  the program tries to guess the resolution from the input data. Works in many cases, however not for seasonal data.
* __`timeformat`__: Some CMIP5 datasets have time saved in the format: *day as %Y%m%d.%f* (e.g. '20070104.5'). Xarray cannot parse this dataformat. If that is the case, `'cmip5'` can be passed and the dates will be correctly interpreted.
* __`use_PDFs`__: Boolean. Toggle option whether to use the characteristic probability density functions or not.
* __`th_factor`__: Factor by which the radiation of the input file is multiplied with. The GSEE requires **kW** and as almost all data for irradiance is given in **W**, the default factor is *1/1000*.
* __`num_cores`__: By default all CPU-cores are used. However this can be limited here.
* __``pdfs_file_path``__: Path to the file in which the PDFs are stored, if not passed it will use the internal file.

#### Pre-Processing the climate data for the gsee
Depending on the temporal resolution of the input data and chosen options, the interface applies different methods to ready the data for the GSEE.

##### __`use_PDFs=True`__:
This is enabled by default, as it generally produces better results. It triggers the use characteristic probability density functions (PDFs) that describe the probability with which a day with a certain amount of radiation occurs within a month. The PDFs are available on a worldwide grid of 2°x2° for each month.
Example PDFs:
![alt text](probability_densitiy_functions.png "Examples for characteristic PDFs")
Each PDF consists of 128 bins, each assigned a value for an amount of daily radiation and the probability of that radiation occuring.
The PDFs are then used to upsample Annual, seasonal, and monthly data to daily data. This daily data gets upsampled to hourly values using a sinusoidal diurnal cycle model, taking the sum of daily radiation as well as sunrise and sunset into account. Now the data is ready to be passed to the gsee.

##### __`use_PDFs=False`__:

In this case the mean value given by the data is regarded as one representative day for the whole season or month. In case of annual data, two days, one in spring and one in autum, are calculated. These days are again upsampled to hourly values using the sinusoidal diurnal cycle.

##### Diffuse fraction:
The diffuse fraction is calculated using the BRL-model (Ridley, 2010) with the use of the atmospheric clearness index (k<sub>t</sub>). The clearness index is extimated using the method from Elminir (2007).

#### Output
The climatdata-interface outputs the data in the same resolution as the input data was in. The unit of the output data is **kWh/day**. Except for hourly values it is **kW/hour**.

#### Example:

The following scripts should serve as an example of parameters with which the interface can be used.

```python
#!/usr/bin/python

import gsee.climdata_interface.interface as inter

basefolder = '/home/username/data/sis-dni-tas-NN'

#th-tuple:
th_tuple = ('{}/sis-2011-monmean.nc'.format(basefolder), 'SIS')
#df-tuple: Diffuse fraction is only used when calculating hourly data, otherwise automatically estimated with BRL-model
df_tuple = ('{}/df-2011-monmean.nc'.format(basefolder), 'df')
#at-tuple:
at_tuple = ('{}/tas-2011-monmean.nc'.format(basefolder), 'T2M')

#outfile:
outfile = '{}/output-monmean-pdfs-new.nc'.format(basefolder)

timeformat = 'other' #'cmip5' # two options: 'cmip5-datestring': date as number e.g. 20071215.5 or 'other':whatever xarray reads in

#Paramters: A function of tilt depending on lat can be privided, or simply a fixed value returned
def tilt_function(lat):
    return 0.353959636801573 * lat + 16.8477501393928
tilt = tilt_function
azimuth = 180
tracking = 0
capacity = 1
params =[tilt, azimuth, tracking, capacity]

#in_freq:
data_freq = 'detect' # is either 'A', 'S', 'M', 'D', 'H' or 'detect' mostly detects everything but seasonal
use_PDFs = True
th_factor = 1/1000 #GSEE requires kW

inter.run_interface(th_tuple=th_tuple, df_tuple=df_tuple, at_tuple=at_tuple,
                        outfile=outfile, params=params, in_freq=data_freq, timeformat=timeformat,
                        use_PDFs=use_PDFs, th_factor=th_factor)
```


##### References

* Elminir, H. K., Y. A. Azzam, and F. I. Younes, 2007: Prediction of hourly and daily diffuse fraction using neural network, as compared to linear regression models. Energy, 32, 1513–1523, [doi:10.1016/j.energy.2006.10.010](http://dx.doi.org/10.1016/j.energy.2006.10.010)
* Ridley, B., J. Boland, and P. Lauret, 2010: Modelling of diffuse solar fraction with multiple predictors. Renew. Energy, 35, 478–483, [doi:10.1016/j.renene.2009.07.018](http://dx.doi.org/10.1016/j.renene.2009.07.018)
