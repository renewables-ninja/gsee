import xarray as xr
import pandas as pd
import numpy as np
import multiprocessing
from calendar import monthrange
import os
import time
from scipy import spatial
from itertools import product
from gsee.climatedata_interface.pre_gsee_processing import resample_for_gsee, resample_for_gsee_with_pdfs


def run_interface_from_dataset(ds_in: xr.Dataset, params: dict, use_pdfs=True, pdfs_file_path='',
                               num_cores=multiprocessing.cpu_count()) -> xr.Dataset:
    """

    Parameters
    ----------
    ds_in: xarray dataset
        containing at lest one variable 'global_horizontal' with mean global horizontal irradiance in W/m2.
        Optional variables: 'diffuse_fraction', 'temperature' in °C
    params: dict
        of the parameters for the GSEE with entries 'tilt', 'azimuth', 'tracking', 'capacity', 'data_freq',
        tilt can be a function depending on latitude! See example input.Tracking can be 0, 1, 2 for no tracking,
        1-axis tracking, 2-axis tracking. 'data_freq': Frequency of the input data. One of ['A', 'S', 'M', 'D', 'H']
        for annual, seasonal, monthly, daily, hourly.
    use_pdfs: bool
        If True, the probability density functions for each month are used. Only for annual, seasonal and monthly data
    num_cores: int
        number of cores that should be used for the computation, default is all of them
    pdfs_file_path: string
        Path to the file in which the PDFs are stored.

    Returns
    -------
    xarray dataset
        containing the PV power output in Wh/hour if 'data_freq' in params is 'H' and kWh/day if 'data_freq
        is ['A', 'S', 'M', 'D']
    """
    ds = ds_in
    # Create list of all (lat, lon) pairs to be processed:
    coord_list = list(product(ds['lat'].values, ds['lon'].values))

    # Produces list of coordinates of all grid-points, over which to iterate afterwards

    # Modify Time dimension so it fits the requirements of the "resample_for_gsee" function:
    ds['time'] = mod_time_dim(pd.to_datetime(ds['time'].values), params['data_freq'])

    # Process al time series in coord_list
    # -------------------------------------------------------------------------------------

    # Shareable list with a place for every coordinate in the grid:
    manager = multiprocessing.Manager()
    shr_mem = manager.list([None] * len(coord_list))
    # Store length of coordinate list in prog_mem to draw the progress bar dynamically:
    prog_mem = manager.list()
    prog_mem.append(len(coord_list))

    start = time.time()
    if not use_pdfs:
        if num_cores > 1:
            print('Parallel mode: {} cores'.format(num_cores))
            from joblib import Parallel, delayed
            Parallel(n_jobs=num_cores)(delayed(resample_for_gsee)(ds.sel(lat=coords[0], lon=coords[1]), params,
                                                                  i, coords, shr_mem, prog_mem
                                                                  ) for i, coords in enumerate(coord_list))
        else:
            print('Single core mode')
            for i, coords in enumerate(coord_list):
                resample_for_gsee(ds.sel(lat=coords[0], lon=coords[1]), params, i, coords, shr_mem, prog_mem)
    elif use_pdfs and params['data_freq'] in ['A', 'S', 'M'] and pdfs_file_path:
        pdfs = xr.open_dataset(pdfs_file_path, autoclose=True)
        pdf_coords = list(product(pdfs['lat'].values, pdfs['lon'].values))
        tree = spatial.KDTree(pdf_coords)
        coord_list_nn = [pdf_coords[int(tree.query([x])[1])] for x in coord_list]
        if num_cores > 1:
            print('Parallel mode: {} cores'.format(num_cores))
            from joblib import Parallel, delayed
            Parallel(n_jobs=num_cores)(delayed(resample_for_gsee_with_pdfs)(ds.sel(lat=coords[0], lon=coords[1])
                                                                            , params, i, coords, shr_mem, prog_mem,
                                                                            pdfs.sel(lat=coord_list_nn[i][0],
                                                                                     lon=coord_list_nn[i][1]))
                                       for i, coords in enumerate(coord_list))
        else:
            print('Single core mode')
            for i, coords in enumerate(coord_list):
                resample_for_gsee_with_pdfs(ds.sel(lat=coords[0], lon=coords[1]), params, i, coords, shr_mem,
                                            prog_mem, pdfs.sel(lat=coord_list_nn[i][0], lon=coord_list_nn[i][1]))
    else:
        raise ValueError('PDFs file path not given, or frequency is not "A", "M", "D"')
    end = time.time()
    print('\nComputation part took: {} seconds'.format(str(round(end - start, 2))))

    # Stitch together:
    ds_pv = xr.Dataset()
    for piece in shr_mem:
        if type(piece) == type(ds):
            ds_pv = xr.merge([ds_pv, piece])
    ds_pv = ds_pv.transpose('time', 'lat', 'lon')
    ds_pv['time'] = ds_in['time']
    if params['data_freq'] == 'H':
        ds_pv['pv'].attrs['unit'] = 'Wh'
    elif params['data_freq'] in ['A', 'S', 'M', 'D']:
        ds_pv['pv'].attrs['unit'] = 'Wh/day'

    return ds_pv


def run_interface(ghi_tuple: tuple, outfile: str, params: dict, diffuse_tuple=('', ''), temp_tuple=('', ''),
                  timeformat='other', use_pdfs=True,
                  pdfs_file_path='', num_cores=multiprocessing.cpu_count()):
    """
    Input file must include 'time', 'lat' and 'lon' dimension.

    Parameters
    ----------
    ghi_tuple: Tuple
        with Filepath for .nc file with diffuse fraction data and variable name in that file
    outfile: string
        Filepath where the output should be saved
    params: dict
        of the parameters for the GSEE with entries 'tilt', 'azimuth', 'tracking', 'capacity', 'data_freq',
        tilt can be a function depending on latitude! See example input.Tracking can be 0, 1, 2 for no tracking,
        1-axis tracking, 2-axis tracking. 'data_freq': Frequency of the input data. One of ['A', 'S', 'M', 'D', 'H'] for annual, seasonal, monthly, daily, hourly.
        Can also be 'detect' in that case the frequency is guessed, works mostly except for seasonal data
    diffuse_tuple: Tuple
        Tuple with Filepath for .nc file with diffuse fraction data and variable name in that file
    temp_tuple: Tuple
        Tuple with Filepath for .nc file with temperature data (°C or °K) and variable name in that file
    timeformat: string
        if 'cmip5' is given, then the dateformat common in the CMIP5 dataset (e.g. '20070104.5') is converted.
        Otherwise its left to xarray to detect the time
    use_pdfs: bool
        If True, the probability density functions for each month are used. Only for annual, seasonal and monthly data
    num_cores: int
        number of cores that should be used for the computation, default is all of them
    pdfs_file_path: string
        Path to the file in which the PDFs are stored.
    """

    # Read Files:
    ds_merged, ds_in = open_files(ghi_tuple, diffuse_tuple, temp_tuple)
    # Tries to detect frequency, otherwise falls back to manual entry, also compares if the two match:
    params['data_freq'] = detect_frequency(ds_in, params['data_freq'])

    # If 'cmip5' is given the string of the form %Y%m%d.%f will be transformed to datetime object
    if timeformat == 'cmip5':
        ds_merged['time'] = parse_cmip_time_data(ds_merged)

    # Check whether the time dimension was recognised correctly and interpreted as time by dataset
    if not type(ds_merged['time'].values[0]) is np.datetime64:
        raise TypeError('Time format not recognisable, select "cmip5" as timeformat input or provide other datafile')

    if not os.path.isfile(outfile):
        print('Output file {} file does not yet exist --> Computing in '.format(outfile.split('/', -1)[-1]), end='')

        ds_pv = run_interface_from_dataset(ds_in=ds_merged, params=params, use_pdfs=use_pdfs,
                                           pdfs_file_path=pdfs_file_path, num_cores=num_cores)

        for var in ds_in.data_vars:
            if var == 'time_bnds':
                ds_pv[var] = ds_in[var]
        # Save Dataset
        encoding_params = {'dtype': 'float32', '_FillValue': -9999, 'zlib': True, 'complevel': 4}
        encoding = {k: encoding_params for k in list(ds_pv.data_vars)}
        if outfile[-3:] == '.nc':
            outfile.replace('.nc', 'nc4')
        ds_pv.to_netcdf(path=outfile, mode='w', format='NETCDF4', encoding=encoding)

    else:
        print('{} file already exists --> skipping'.format(outfile.split('/', -1)[-1]))


# ----------------------------------------------------------------------------------------------------------------------
# Support functions for run_interface_from_dataset:
# ----------------------------------------------------------------------------------------------------------------------

def mod_time_dim(time_dim: pd.DatetimeIndex, freq: str):
    """
    Modify Time dimension so it fits the requirements of the "resample_for_gsee" function
    Parameters
    ----------
    time_dim: array
        with datetime entries
    freq: string
        representing data frequency of na_time

    Returns
    -------
    array
        modified time dimension
    """
    if freq == 'A':
        # Annual data is set to the beginning of the year
        return time_dim.map(lambda x: pd.Timestamp(year=x.year, month=1, day=1, hour=0, minute=0))
    elif freq in ['S', 'M']:
        # Seasonal data is set to middle of month, as it is often represented with the day in the middle of the season.
        # Monthly data is set to middle of month
        return time_dim.map(lambda x: pd.Timestamp(year=x.year, month=x.month,
                                                   day=int(monthrange(x.year, x.month)[1] / 2), hour=0,
                                                   minute=0))
    elif freq == 'D':
        # Daily data is set to 00:00 hours of the day
        return time_dim.map(lambda x: pd.Timestamp(year=x.year, month=x.month, day=x.day, hour=0, minute=0))
    else:
        return time_dim

# ----------------------------------------------------------------------------------------------------------------------
# Support functions for run_interface:
# ----------------------------------------------------------------------------------------------------------------------


def detect_frequency(ds: xr.Dataset, in_freq: str):
    """
    Tries to detect the frequency of the given dataset. Raises error if detected freqency and does not match
    the given in in_freq
    Parameters
    ----------
    ds: xarray Dataset
        with a 'time' dimension
    in_freq: string
        Frequency given by user. One of ['A', 'S', 'M', 'D', 'H'] for annual, seasonal, monthly, daily, hourly.
        Can also be 'detect' in that case the frequency is guessed, works mostly except for seasonal data

    Returns
    -------
    string
        Detected or validated frequency

    """
    # Tries to detect frequency, otherwise falls back to manual entry, also compares if the two match:
    nc_freq = None
    try:
        nc_freq = ds.attrs['frequency']
    except KeyError:
        try:
            nc_freq = pd.DatetimeIndex(data=ds['time'].values).inferred_freq[0]
        except:
            pass
    if not nc_freq:
        print('> No frequency detected --> checking manual entry', end='')
        if in_freq in ['A', 'S', 'M', 'D', 'H']:
            print('...Manual entry is valid')
            data_freq = in_freq
        else:
            raise ValueError('detect failed or manual entry is invalid input check settings')
    else:
        if nc_freq == 'year':
            data_freq = 'A'
        elif nc_freq == 'mon':
            data_freq = 'M'
        elif nc_freq == 'day':
            data_freq = 'D'
        else:
            data_freq = nc_freq
        print('> Detected frequency: {}'.format(data_freq))

    if in_freq == 'S' and not data_freq in ['A', 'M', 'D', 'H']:
        print('> Frequency is detected, but is not "A", "M", "D", or "H" thus assumed some kind of seasonal')
        return in_freq
    if data_freq in ['A', 'S', 'M', 'D', 'H'] and in_freq != data_freq and in_freq != 'detect':
        raise Warning(
            '\tManual given frequency is valid, however it does not match detected frequency. Check settings!')
    if data_freq not in ['A', 'S', 'M', 'D', 'H']:
        raise ValueError('> Time frequency invalid, use one from ["A", "S", "M", "D", "H"]')
    return data_freq


def parse_cmip_time_data(ds: xr.Dataset):
    """
    Converts time data saved as number with format "day as %Y%m%d.%f" to datetime64 format
    Parameters
    ----------
    ds: xarray dataset
        with 'time' dimension in "day as %Y%m%d.%f" format

    Returns
    -------
    array
        with converted datetime64 entries
    """
    try:
        # Translates date-string used in CMIP5 data to datetime-objects
        timestr = [str(ti) for ti in ds['time'].values]
        vfunc = np.vectorize(lambda x: np.datetime64('{}-{}-{}T{:02d}-{}'.format(x[:4], x[4:6], x[6:8],
                                                                                 int(24 * float('0.' + x[9:])), '00')))
        return vfunc(timestr)
    except:
        raise RuntimeError('Parsing of "cmip5" time-dimension failed. Take "other" as timeformat or check data.')


def open_files(ghi_tuple: tuple, diffuse_tuple: tuple, temp_tuple: tuple):
    """
    Opens the given files for GHI, diffuse Fraction and temperature, extracts the corresponding variables
    and merges all three together to one dataset.
    Parameters
    ----------
    ghi_tuple: Tuple
        with Filepath for .nc file with diffuse fraction data and variable name in that file
    diffuse_tuple: Tuple
        Tuple with Filepath for .nc file with diffuse fraction data and variable name in that file
    temp_tuple: Tuple
        Tuple with Filepath for .nc file with temperature data (°C or °K) and variable name in that file

    Returns
    -------
    ds_tot: xarray dataset
        merged dataset with all available variables: global_horizontal, diffuse_fraction, temperature
    ds_th_in: xarray dataset
        dataset of input file without any being processed. Is used later to detect frequency
    """
    ghi_file, ghi_var = ghi_tuple
    diffuse_file, diffuse_var = diffuse_tuple
    temp_file, temp_var = temp_tuple

    try:
        ds_ghi_in = xr.open_dataset(ghi_file, autoclose=True)
    except:
        raise FileNotFoundError('Radiation file not found')

    # makes sure only the specified variable gets used further:
    ds_ghi = ds_ghi_in[ghi_var].to_dataset()
    ds_merged = ds_ghi
    ds_merged.rename({ghi_var: 'global_horizontal'}, inplace=True)

    # Open diffuse_fraction file:
    try:
        ds_diffuse_in = xr.open_dataset(diffuse_file, autoclose=True)
        ds_diffuse = ds_diffuse_in[diffuse_var].to_dataset()
        if ds_ghi.dims != ds_diffuse.dims:
            raise ValueError('Dimension of diffuse fraciton file does not match radiation file')
        ds_merged = xr.merge([ds_merged, ds_diffuse])
        ds_merged.rename({diffuse_var: 'diffuse_fraction'}, inplace=True)

    except OSError:
        print('> No diffuse fraction file found -> will calculate with BRL-Model')
    # Open temperature file:
    try:
        ds_temp_in = xr.open_dataset(temp_file, autoclose=True)
        ds_temp = ds_temp_in[temp_var].to_dataset()
        if ds_temp[temp_var].mean().values > 200:
            print('> Average temperature above 200° detected --> will convert to °C')
            ds_temp = ds_temp - 273.15  # convert form kelvin to celsius
        if ds_ghi.dims != ds_temp.dims:
            raise ValueError('Dimension of temperature file does not match radiation file')
        ds_merged = xr.merge([ds_merged, ds_temp])
        ds_merged.rename({temp_var: 'temperature'}, inplace=True)

    except OSError:
        print('> No temperature file found -> will assume 20°C default value')

    assert ds_merged.dims == ds_ghi.dims

    return ds_merged, ds_ghi_in

# ----------------------------------------------------------------------------------------------------------------------
