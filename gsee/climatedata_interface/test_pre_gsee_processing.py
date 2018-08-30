import gsee.climatedata_interface.pre_gsee_processing as pre
import gsee.climatedata_interface.kt_h_sinusfunc as cyth
import datetime as dt
import random
import pandas as pd
import numpy as np
from gsee.climatedata_interface.pre_gsee_processing import PVstation
import xarray as xr
import multiprocessing
import pytest


@pytest.mark.skip
def test_add_kd_run_gsee():
    df = pd.DataFrame(data={'global_horizontal': 1000 * np.random.rand(25) / 2,
                            'temperature': np.random.randint(0, 25, 25)},
                      index=pd.DatetimeIndex(start='2000-05-18', periods=25, freq='D'))
    station = PVstation(35, 180, 0, 1000, 'D')

    result = pre.add_kd_run_gsee(df, station)
    assert type(result) == pd.Series
    assert len(df['global_horizontal'] == len(result))
    assert np.array_equal(df.index.values, result.index.values)
    assert 'pv' in result.columns


@pytest.mark.skip
def test_resample_for_gsee():
    for freq in ['AS', 'D', 'H']:
        coords = (45, 8.5)
        i = np.random.randint(0, 48)
        ds = xr.Dataset(data_vars={'global_horizontal': (('time'), np.random.rand(48) / 2)},
                        coords={'time': pd.date_range(start='2000-01-01', periods=48, freq=freq),
                                'lat': [coords[0]], 'lon': [coords[1]]})
        ds = ds.sel(lat=coords[0], lon=coords[1])
        params = {'tilt': 35, 'azimuth': 180, 'tracking': 0, 'capacity': 1000, 'data_freq': freq[0]}
        manager = multiprocessing.Manager()
        shr_mem = manager.list([None] * 48)
        prog_mem = manager.list()
        prog_mem.append(48)

        pre.resample_for_gsee(ds, params, i, coords, shr_mem, prog_mem)

        shr_obj = shr_mem[i].resample(time=freq).pad()
        assert isinstance(shr_obj, xr.Dataset)
        assert len(shr_obj.data_vars) == 1
        assert 'pv' in shr_obj.data_vars
        assert shr_obj.sizes['time'] == len(ds['global_horizontal'])
        assert shr_obj.sizes['lat'] == 1
        assert shr_obj.sizes['lon'] == 1
        assert np.array_equal(ds['time'].values, shr_obj['time'].values)


@pytest.mark.skip
def test_resample_for_gsee_with_pdfs():
    for freq in ['AS', 'MS']:
        coords = (45, 8.5)
        i = np.random.randint(0, 48)
        ds = xr.Dataset(data_vars={'global_horizontal': (('time'), np.random.rand(48) / 2)},
                        coords={'time': pd.date_range(start='2000-01-01', periods=48, freq=freq),
                                'lat': [coords[0]], 'lon': [coords[1]]})
        ds = ds.sel(lat=coords[0], lon=coords[1])
        ds_pdfs = xr.Dataset(data_vars={'xk': (('bins', 'month'), 10 * np.random.rand(128, 12) / 2),
                                        'pk': (('bins', 'month'), np.random.rand(128, 12))},
                        coords={'bins': range(0, 128), 'month': range(1, 13),
                                'lat': [coords[0]], 'lon': [coords[1]]})
        ds_pdfs = ds_pdfs.sel(lat=coords[0], lon=coords[1])
        params = {'tilt': 35, 'azimuth': 180, 'tracking': 0, 'capacity': 1000, 'data_freq': freq[0]}
        manager = multiprocessing.Manager()
        shr_mem = manager.list([None] * 48)
        prog_mem = manager.list()
        prog_mem.append(48)

        pre.resample_for_gsee_with_pdfs(ds, params, i, coords, shr_mem, prog_mem, ds_pdfs)

        shr_obj = shr_mem[i].resample(time=freq).pad()
        assert isinstance(shr_obj, xr.Dataset)
        assert len(shr_obj.data_vars) == 1
        assert 'pv' in shr_obj.data_vars
        assert shr_obj.sizes['time'] == len(ds['global_horizontal'])
        assert shr_obj.sizes['lat'] == 1
        assert shr_obj.sizes['lon'] == 1
        assert np.array_equal(ds['time'].values, shr_obj['time'].values)


@pytest.mark.skip
def test_kt_h():
    gsc = 1367
    lat = 50
    h = 12
    n = 180
    Eo = 1
    sunrise_h = 5.35
    glob_h = 300

    kt_h = cyth.kt_h(gsc, lat, n, h, Eo, sunrise_h, glob_h)

    assert isinstance(kt_h, float)
    assert kt_h <= 1 and kt_h >= 0
    assert round(kt_h, 4) == 0.3105


@pytest.mark.skip
def test_convert_to_diurnal():
    df = pd.DataFrame(data={'global_horizontal': 1000 * np.random.rand(25) / 2},
                      index=pd.DatetimeIndex(start='2000-05-18', periods=25, freq='D'))
    coords = (45, 10)
    result = pre.convert_to_durinal(df, coords, factor=24)

    column_list = ['global_horizontal', 'rise_set', 'sunrise_h', 'sunset_h', 'global_horizontal_day', 'hour']
    for col in column_list:
        assert col in result.columns
    assert len(result) == 24 * len(df)
    assert np.array_equal(df['global_horizontal'].round(10),
                          result.resample(rule='D').mean()['global_horizontal'].round(10))


@pytest.mark.skip
def test_decimal_hours():
    timeobject = dt.datetime(year=2011, month=random.randint(1, 12), day=random.randint(1, 28),
                             hour=random.randint(0, 23), minute=random.randint(0, 59))
    result = pre.decimal_hours(timeobject, 'sunrise')
    assert isinstance(result, (int, float, complex))
    assert (result >= 0) and (result <= 24)
    assert timeobject.hour == int(result)

