import pytest

import numpy as np
import pandas as pd
import xarray as xr

import gsee.climatedata_interface.interface as interface


def test_run_interface_from_dataset():
    for freq in ['A', 'S', 'M', 'D', 'H']:

        freq_string = freq if freq != 'S' else 'QS-DEC'
        ds = xr.Dataset(
            data_vars={'global_horizontal': (
                ('time', 'lat', 'lon'),
                1000 * np.random.rand(48, 2, 2) / 2)
            },
            coords={
                'time': pd.date_range(start='2000-01-01', periods=48, freq=freq_string),
                'lat': [40, 50], 'lon': [8.5, 9.5]
            }
        )
        params = {'tilt': 35, 'azim': 180, 'tracking': 0, 'capacity': 1}
        result = interface.run_interface_from_dataset(ds, params, freq, pdfs_file=None)

        assert type(result) == xr.Dataset
        assert ds.dims == result.dims
        assert np.array_equal(ds['time'].values, result['time'].values)
        assert 'pv' in result.variables


def test_mod_time_dim():
    timeseries = pd.date_range('2000-05-18', periods=20, freq='A')
    result = interface._mod_time_dim(timeseries, 'A')
    days = np.unique(result.map(lambda x: x.day))
    assert len(days) == 1
    assert days[0] == 1
    # assert np.array_equal(result.values, pd.date_range(start='2000-01-01', periods=20, freq='A').values)
    compare = pd.DatetimeIndex(start='2000-01-01', periods=20, freq='AS')
    for date in result:
        assert date in compare

    timeseries = pd.date_range('2000-05-18', periods=20, freq='D')
    result = interface._mod_time_dim(timeseries, 'D')
    hours = np.unique(result.map(lambda x: x.hour))
    assert len(hours) == 1
    assert hours[0] == 0
    minutes = np.unique(result.map(lambda x: x.minute))
    assert len(minutes) == 1
    assert minutes[0] == 0
    compare = pd.DatetimeIndex(start='2000-05-18', periods=20, freq='D')
    for date in result:
        assert date in compare

    timeseries = pd.date_range('2000-05-18', periods=20, freq='M')
    result = interface._mod_time_dim(timeseries, 'M')
    days = np.unique(result.map(lambda x: x.day))
    assert len(days) >= 2
    for day in days:
        assert day in [14, 15]
    hours = np.unique(result.map(lambda x: x.hour))
    assert len(hours) == 1
    assert hours[0] == 0
    minutes = np.unique(result.map(lambda x: x.minute))
    assert len(minutes) == 1
    assert minutes[0] == 0


def test_detect_frequency():
    for freq in ['A', 'M', 'D', 'H']:
        in_freq = 'detect'
        da = xr.DataArray(np.random.rand(50), [('time', pd.DatetimeIndex(start='2000-01-01', periods=50, freq=freq))])
        ds = da.to_dataset(name='random')
        out_freq = interface._detect_frequency(ds, in_freq)
        assert out_freq == freq
        in_freq = freq
        out_freq = interface._detect_frequency(ds, in_freq)
        assert out_freq == freq

    in_freq = 'S'
    da = xr.DataArray(np.random.rand(50), [('time', pd.DatetimeIndex(start='2000-01-01', periods=50, freq='QS-DEC'))])
    ds = da.to_dataset(name='random')
    out_freq = interface._detect_frequency(ds, in_freq)
    assert out_freq == 'S'


def test_parse_cmip_time_data():
    for tupl in [(1, 'D', 28), (100, 'MS', 12), (10000, 'AS', 12)]:
        arr_time = [20070101 + tupl[0] * x for x in range(0, tupl[2])]
        ds = xr.Dataset(data_vars={'global_horizontal': (('time'), np.random.rand(tupl[2]) / 2)},
                        coords={'time': arr_time, 'lat': [50], 'lon': [8.5]})
        result_day = interface._parse_cmip_time_data(ds)
        result_target = pd.date_range(start='20070101', periods=len(arr_time), freq=tupl[1])
        assert np.array_equal(result_day, result_target.values)
