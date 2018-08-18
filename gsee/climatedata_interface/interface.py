import xarray as xr
import pandas as pd
import numpy as np
from joblib import Parallel, delayed
from calendar import monthrange
import multiprocessing
import os
import time
from scipy import spatial
from itertools import product
from gsee.climatedata_interface.pre_gsee_processing import resample_for_gsee, resample_for_gsee_with_pdfs, PVstation


def run_interface(th_tuple: tuple, outfile: str, params, df_tuple=('', ''), at_tuple=('', ''),
                  in_freq='detect', timeformat='other', use_PDFs=True, th_factor=1/1000,
                  num_cores=multiprocessing.cpu_count(),
                  pdfs_file_path='{}/PDFs/MERRA2_rad3x3_2011-2015-PDFs_land_prox.nc4'
                  .format(os.path.dirname(os.path.abspath(__file__)))):
    """
    Important: GSEE uses kW, so th_factor is set to 1000 by default, as often data is in W.
    Input file must include 'time', 'lat' and 'lon' dimension.
    :param th_tuple: Tuple with Filepath for .nc file with mean irradiance data (e.g. W/m2)
     and variable name in that file
    :param df_tuple: Tuple with Filepath for .nc file with diffuse fraction data and variable name in that file
    :param at_tuple: Tuple with Filepath for .nc file with temperature data (°C or °K) and variable name in that file
    :param outfile: Filepath where the output should be saved
    :param params: List of the parameters for the GSEE [tilt, azimuth, tracking, capacity],
     tilt can be a function depending on latitude! See example input.
     Tracking can be 0, 1, 2 for no tracking, 1-axis tracking, 2-axis tracking
    :param in_freq: Frequency of the input data. One of ['A', 'S', 'M', 'D', 'H']
     for annual, seasonal, monthly, daily, hourly. Can also be 'detect' in that case the frequency is guessed,
     works mostly except for seasonal data
    :param timeformat: if 'cmip5' is given, then the dateformat common in the CMIP5 dataset
     (e.g. '20070104.5') is converted. Otherwise its left to xarray to detect the time
    :param use_PDFs: Option whether the probability density functions for each month should be used, onyl for annual,
     seasonal and monthly data
    :param th_factor: by which the total_horizontal irradiance is multiplied, e.g. to convert from W to kW
    :param num_cores: number of cores that should be used for the computation, default is all of them
    :param pdfs_file_path: Path to the file in which the PDFs are stored, if not passed it will use the internal file
    """
    tilt, azim, tracking, capacity = params

    th_file, th_var = th_tuple
    df_file, df_var = df_tuple
    at_file, at_var = at_tuple

    # Read-files, detect frequency, convert, check for consistency in dimensions and merge to single dataset
    # -------------------------------------------------------------------------------------
    try:
        ds_th_in = xr.open_dataset(th_file, autoclose=True)
    except:
        raise FileNotFoundError('Radiation file not found')

    # Tries to detect frequency, otherwise falls back to manual entry, also compares if the two match:
    try:
        nc_freq = ds_th_in.attrs['frequency']
    except KeyError:
        try:
            nc_freq = pd.DatetimeIndex(data=ds_th_in['time'].values).inferred_freq
        except:
            pass
    if not nc_freq:
        print('> No frequency detected --> checking manual entry')
        if in_freq in ['A', 'S', 'M', 'D', 'H']:
            print('....Manual entry is valid')
            data_freq = in_freq
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
    if data_freq in ['A', 'S', 'M', 'D', 'H'] and in_freq != data_freq and in_freq != 'detect':
        raise Warning('\tManual given frequency is valid, however it does not match detected frequency. Check settings!')
    if data_freq not in ['A', 'S', 'M', 'D', 'H']:
        raise ValueError('> Time frequency invalid, use one from ["A", "S", "M", "D", "H"]')

    # makes sure only the specified variable gets used further:
    ds_th = ds_th_in[th_var].to_dataset()
    # converts the values of radiation according to the given factor
    ds_tot = ds_th * th_factor
    ds_tot.rename({th_var: 'global_horizontal'}, inplace=True)

    # Open diffuse_fraction file:
    try:
        ds_df_in = xr.open_dataset(df_file, autoclose=True)
        ds_df = ds_df_in[df_var].to_dataset()
        if ds_th.dims != ds_df.dims:
            raise ValueError('Dimension of diffuse fraciton file does not match radiation file')
        ds_tot = xr.merge([ds_tot, ds_df])
        ds_tot.rename({df_var: 'diffuse_fraction'}, inplace=True)

    except OSError:
        print('> No diffuse fraction file found -> will calculate with BRL-Model')
    # Open temperature file:
    try:
        ds_at_in = xr.open_dataset(at_file, autoclose=True)
        ds_at = ds_at_in[at_var].to_dataset()
        if ds_at[at_var].mean().values > 200:
            print('> Average temperature above 200° detected --> will convert to °C')
            ds_at = ds_at - 273.15  # convert form kelvin to celsius
        if ds_th.dims != ds_at.dims:
            raise ValueError('Dimension of temperature file does not match radiation file')
        ds_tot = xr.merge([ds_tot, ds_at])
        ds_tot.rename({at_var: 'temperature'}, inplace=True)

    except OSError:
        print('> No temperature file found -> will assume 20°C default value')

    assert ds_tot.dims == ds_th.dims

    # If 'cmip5' is given the string of the form %Y%m%d.%f will be transformed to datetime object
    if timeformat == 'cmip5':
        try:
            # Translates date-string used in CMIP5 data to datetime-objects
            timestr = [str(ti) for ti in ds_tot['time'].values]
            vfunc = np.vectorize(lambda x: np.datetime64('{}-{}-{}T{:02d}-{}'.format(x[:4], x[4:6], x[6:8],
                                                                                     int(24 * float('0.' + x[9:])), '00')))
            ds_tot['time'] = vfunc(timestr)
        except:
            raise RuntimeError('Parsing of "cmip5" time-dimension failed. Take "other" as timeformat or check data.')

    # Create list of all (lat, lon) pairs to be processed
    # -------------------------------------------------------------------------------------
    tlat = ds_tot['lat'].values
    tlon = ds_tot['lon'].values
    ttime = ds_tot['time'].values.copy()
    # ttime = pd.to_datetime(ds_tot['time'].values.copy())
    # Produces list of coordinates of all grid-points, over which to iterate afterwards
    coord_list = list(product(tlat, tlon))

    # Modify Time dimension so it fits the requirements of the "resample_for_gsee" function
    # -------------------------------------------------------------------------------------

    # Check whether the time dimension was recognised correctly and interpreted as time by dataset
    if not type(ds_tot['time'].values[0]) is np.datetime64:
        raise TypeError('Time format not recognisable, select "cmip5" as timeformat input or provide other datafile')

    na_time = pd.to_datetime(ds_tot['time'].values)
    if data_freq == 'A':
        # Annual data is set to the beginning of the year
        ds_tot['time'] = na_time.map(lambda x: pd.Timestamp(year=x.year, month=1, day=1, hour=0, minute=0))
    elif data_freq in ['S', 'M']:
        # Seasonal data is set to middle of the month, as it is often
        # represented with the day in the middle of the season.
        # Monthly data is set to middle of month
        ds_tot['time'] = na_time.map(lambda x: pd.Timestamp(year=x.year, month=x.month,
                                                            day=int(monthrange(x.year, x.month)[1]/2),
                                                            hour=0, minute=0))
    elif data_freq == 'D':
        # Daily data is set to 00:00 hours of the day
        ds_tot['time'] = na_time.map(lambda x: pd.Timestamp(year=x.year, month=x.month, day=x.day, hour=0, minute=0))

    # Process al time series in coord_list
    # -------------------------------------------------------------------------------------

    station = PVstation(tilt, azim, tracking, capacity, data_freq)
    manager = multiprocessing.Manager()

    if not os.path.isfile(outfile):
        print('Output file {} file does not yet exist --> Computing...'.format(outfile.split('/', -1)[-1]))
        # Shareable list with a place for every coordinate in the grid:
        shr_mem = manager.list([None] * len(tlat)*len(tlon))
        start = time.time()
        prog_mem = manager.list()
        # Store length of coordinate list in prog_mem to draw the progress bar dynamically:
        prog_mem.append(len(coord_list))
        if not use_PDFs:
            Parallel(n_jobs=num_cores)(delayed(resample_for_gsee)(ds_tot.sel(lat=coords[0], lon=coords[1]), station,
                                                                  i, coords, shr_mem, prog_mem,
                                                                  ) for i, coords in enumerate(coord_list))
        elif use_PDFs and data_freq in ['A', 'S', 'M']:
            pdfs = xr.open_dataset(pdfs_file_path, autoclose=True)
            # convert values in PFDS from W to kW:
            pdfs = pdfs / 1000
            # Find closest PDF for each coordinate in coord_list:
            pdf_coords = list(product(pdfs['lat'].values, pdfs['lon'].values))
            tree = spatial.KDTree(pdf_coords)
            coord_list_NN = [pdf_coords[int(tree.query([x])[1])] for x in coord_list]
            Parallel(n_jobs=num_cores)(delayed(resample_for_gsee_with_pdfs)(ds_tot.sel(lat=coords[0], lon=coords[1]), station, i,
                                                                            coords, shr_mem, prog_mem,
                                                                            pdfs.sel(lat=coord_list_NN[i][0], lon=coord_list_NN[i][1])
                                                                            ) for i, coords in enumerate(coord_list))
        else:
            raise ValueError('If use_PDFs is selected, use one of the following frequencies ["A", "S", "M"]')
        end = time.time()
        print('\nComputation part took: {} seconds'.format(str(round(end-start, 2))))

        # Stitch together and save
        # -------------------------------------------------------------------------------------
        print('Saving to: {}'.format(outfile))
        ds_pv = xr.Dataset()
        for piece in shr_mem:
            if type(piece) == type(ds_tot):
                ds_pv = xr.merge([ds_pv, piece])
        ds_pv = ds_pv.transpose('time', 'lat', 'lon')
        ds_pv['time'] = ttime
        for var in ds_th_in.data_vars:
            if var != th_var:
                ds_pv[var] = ds_th_in[var]

        if data_freq == 'H':
            ds_pv['pv'].attrs['unit'] = 'kWh'
        elif data_freq in ['A', 'S', 'M', 'D']:
            ds_pv['pv'].attrs['unit'] = 'kWh/day'

        encoding_params = {'dtype': 'float32', '_FillValue': -9999, 'zlib': True, 'complevel': 4}
        encoding = {k: encoding_params for k in list(ds_pv.data_vars)}
        if outfile[-3:] == '.nc':
            outfile.replace('.nc', 'nc4')
        ds_pv.to_netcdf(path=outfile, mode='w', format='NETCDF4', encoding=encoding)

    else:
        print('{} file already exists --> skipping'.format(outfile.split('/', -1)[-1]))
