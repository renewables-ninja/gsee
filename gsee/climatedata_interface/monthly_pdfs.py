import xarray as xr
import pandas as pd
import numpy as np
from joblib import Parallel, delayed
import multiprocessing
from gsee.climatedata_interface.progress import progress_bar
from seaborn import distplot as sns_distplot
import matplotlib.pyplot as plt
import warnings
from mpl_toolkits.basemap import Basemap


def create_pdfs_from_ds(ds, outfile, only_land=True, proximity=True, lat_bounds=(-60, 75)):
    """
    Creates new file contaning the probabiliy densitiy functions for each month of how often a specific amount of
    radation can occur. This is done for every grid-cell from the incoming dataset.

    Parameters
    ----------
    ds: xarray dataset
        with 'time', 'lat', 'lon' dimensions and data-variable 'SWGDN'
    outfile: string
        path and filename where the resulting file should be stored. Must end with .nc4
    only_land: bool
        If true: only gridcells whose center is on land will be computed. False: all cells are computed
    proximity: bool
        If true: A cell is also computed if one of the surrounding cells is land. This makes shure that all coastal
        regions are included, as sometimes the middle of a gridcell can be on the ocean, but still a great part is
        on land. Without this option, all these cases would not be included.
    lat_bounds: Tuple
        containing boundaries for the latitude to be included in the resulting datset. All latitudes between the two
        values of the tuple will be inlcuded.
    """

    # Create list of all (lat, lon) pairs to be processed:
    tlat = ds['lat'].values
    tlon = ds['lon'].values
    lat_dist = np.unique(np.diff(tlat))
    assert len(lat_dist) == 1
    lat_dist = int(lat_dist[0])
    lon_dist = np.unique(np.diff(tlon))
    assert len(lon_dist) == 1
    lon_dist = int(lon_dist[0])

    time = pd.to_datetime(ds['time'].values)
    ds['time'] = time.map(lambda x: x.month)
    ds.rename({'time': 'month'}, inplace=True)
    coord_list = []
    if only_land:
        bm = Basemap()
        for lat in tlat:
            if lat >= lat_bounds[0] and lat <= lat_bounds[1]:
                for lon in tlon:
                    if bm.is_land(lon, lat):
                        coord_list.append((lat, lon))
                    elif proximity:
                        for prox_lat in [lat + x * lat_dist for x in range(-1, 2)]:
                            for prox_lon in [lon + x * lon_dist for x in range(-1, 2)]:
                                if bm.is_land(prox_lon, prox_lat):
                                    if not (lat, lon) in coord_list:
                                        coord_list.append((lat, lon))
    else:
        for lat in tlat:
            if lat >= lat_bounds[0] and lat <= lat_bounds[1]:
                for lon in tlon:
                    coord_list.append((lat, lon))
    # Processing all the data of the coordinate tuples in coord_list
    num_cores = multiprocessing.cpu_count()
    manager = multiprocessing.Manager()
    assert len(tlat)*len(tlon) >= len(coord_list)
    shr_mem = manager.list([None] * len(tlat)*len(tlon))
    prog_mem = manager.list()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        Parallel(n_jobs=num_cores)(delayed(calc_pdfs)(ds.sel(lon=coords[1], lat=coords[0]),
                                                      i, shr_mem, prog_mem, coords, len(coord_list))
                                                        for i, coords in enumerate(coord_list))
    print('\nfinished parallel part, stitching together')
    ds_out = xr.Dataset()
    xartype = type(ds)
    for piece in shr_mem:
        if type(piece) == xartype:
            ds_out = xr.merge([ds_out, piece])

    ds_out = ds_out.sel(lat=slice(lat_bounds[0], lat_bounds[1]))
    # encoding_params = {'dtype': 'int16', 'scale_factor': 0.00005, '_FillValue': -9999, 'zlib': True, 'complevel': 2}
    encoding_params = {'dtype': 'float32', '_FillValue': -9999, 'zlib': True, 'complevel': 4}
    encoding = {
        'pk': {'dtype': 'float32', '_FillValue': -9999, 'zlib': True, 'complevel': 5},
        'xk': {'dtype': 'int16', 'scale_factor': 0.02, '_FillValue': -9999, 'zlib': True, 'complevel': 5},
    }
    # encoding = {k: encoding_params for k in list(ds_out.data_vars)}
    ds_out.to_netcdf(path=outfile, format='NETCDF4', encoding=encoding)
    print('File is saved')


def calc_pdfs(ds, i, shr_mem, prog_mem, coords, len_coord_list):
    """
    Calculates the probability density functions of the radiation for each month of the given dataset and
    saves it to a new dataset.
    Parameters
    ----------
    ds: xarray dataset
        with a data-variable 'SWGDN' containing time-series data at coordiantes coords
    i: int
        index where in shr_mem the result is to be saved
    shr_mem : shared List
        shared memory where all the calculated xk, pk values are stored
    prog_mem : List
        list indicating the overall progress of the computation, first value ([0]) is the total number
        of coordinate tuples to compute.
    coords: Tuple
        (lat, lon) representing the location of the time-series in ds
    len_coord_list: int
        length of coord_list, used for progress bar
    """
    ds_out = xr.Dataset()
    for mo in range(1,13):
        ds_mo = ds.sel(month=mo)
        da_mo = ds_mo['SWGDN'].values
        fig = plt.figure()
        ax = fig.add_subplot()
        xk, pk = sns_distplot(da_mo, ax=ax).get_lines()[0].get_data()
        pk = pk / sum(pk)
        ds_out_mo = pd.DataFrame({'xk': xk, 'pk': pk, 'lat': coords[0], 'lon': coords[1], 'month': mo, 'bins': range(0, len(pk))})
        ds_out_mo.set_index(['lat', 'lon', 'month', 'bins'], inplace=True)
        ds_out_xk_pk = ds_out_mo.to_xarray().copy()
        ds_out = xr.merge([ds_out, ds_out_xk_pk])
        plt.close()

    shr_mem[i] = ds_out
    prog_mem.append(1)
    progress_bar(len(prog_mem), len_coord_list)

