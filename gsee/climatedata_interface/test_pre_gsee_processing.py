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


def test_clearness_index_hourly():
    coords = (45, 9)
    df = pd.DataFrame(data={'global_horizontal': [100, 300, 500, 700, 900],
                            'sunrise_h': [5.3, 7.4, 6.35, 5.88, 7.467],
                            'Eo': [1.006446, 1.12318, 1.148916, 1.00891, 1.098145],
                            'n': [44, 55, 88, 198, 200],
                            'hour': [12, 16, 9, 14, 12]})
    result = pre.clearness_index_hourly(df, coords)
    check = [0.17764986, 0.76200541, 0.60162922, 0.5717562, 0.7684602]

    assert np.array_equal(np.round(result['kt_h'].values, 8),
                          np.array([0.17764986, 0.76200541, 0.60162922, 0.5717562, 0.7684602]))


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


def test_decimal_hours():
    for rise_set in ['sunrise', 'sunset']:
        timeobject = dt.datetime(year=2011, month=random.randint(1, 12), day=random.randint(1, 28),
                                 hour=random.randint(0, 23), minute=random.randint(0, 59))
        result = pre.decimal_hours(timeobject, rise_set)
        assert isinstance(result, (int, float, complex))
        assert (result >= 0) and (result <= 24)
        assert timeobject.hour == int(result)

        minutes = [12, 15, 30, 48]
        results = [4.2, 6.25, 15.5, 20.8]
        for i, hour in enumerate([4, 6, 15, 20]):
            minute = minutes[i]
            timeobject = dt.datetime(year=2011, month=random.randint(1, 12), day=random.randint(1, 28),
                                     hour=hour, minute=minute)
            result = pre.decimal_hours(timeobject, rise_set)
            assert result == results[i]

        result = pre.decimal_hours(None, rise_set)
        if rise_set == 'sunrise':
            assert result == 0.0
        elif rise_set == 'sunset':
            assert result == 23.999


def test_return_pv():
    coords = (45, 8.5)
    i = np.random.randint(0, 48)
    pv = pd.Series(data=np.random.rand(48) / 2, index=pd.date_range(start='2000-01-01', periods=48, freq='D'))
    pv.index.name = 'time'
    manager = multiprocessing.Manager()
    shr_mem = manager.list([None] * 48)
    prog_mem = manager.list()
    prog_mem.append(48)

    pre.return_pv(pv=pv, shr_mem=shr_mem, prog_mem=prog_mem, coords=coords, i=i)

    shr_obj = shr_mem[i].resample(time='D').pad()
    assert isinstance(shr_obj, xr.Dataset)
    assert len(shr_obj.data_vars) == 1
    assert 'pv' in shr_obj.data_vars
    assert shr_obj.sizes['time'] == len(pv)
    assert shr_obj.sizes['lat'] == 1
    assert shr_obj.sizes['lon'] == 1
    assert np.array_equal(pv.index.values, shr_obj['time'].values)
