import pytest

import numpy as np
import pandas as pd
import xarray as xr

import gsee.climatedata_interface.interface as interface


def test_run_interface_from_dataset():
    data_l = 48
    x1 = np.linspace(0, 500, data_l)
    x2 = np.linspace(100, 800, data_l)
    x3 = np.linspace(500, 900, data_l)
    x4 = np.linspace(400, 1000, data_l)
    data_nonhourly = np.reshape([[x1, x2], [x3, x4]], (data_l, 2, 2))

    x = [
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 4.9, 87.9, 231.2, 385.6,
        478.1, 507.1, 580.3, 630.3, 508.5, 316.1, 208.1, 80.9, 3.0,
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        5.3, 72.9, 121.3, 164.3, 358.5, 854.5, 904.0, 938.0, 917.0,
        844.3, 551.8, 519.8, 454.3, 205.8, 70.0, 4.4, 0.0, 0.0, 0.0
    ]
    data_hourly = np.reshape([[x, x], [x, x]], (data_l, 2, 2))

    # Tuples of (sum, nanmean) of resulting PV output
    expected_results = {
        'A': (1553340.936608, 8090.317378),
        'S': (1460912.563737, 7608.919602),
        'M': (1447349.091776, 7538.276519),
        'D': (1474694.583939, 7680.700958),
        'H': (47012.573166, 244.857151)
    }

    for freq in ['A', 'S', 'M', 'D', 'H']:
        if freq == 'H':
            data = data_hourly
        else:
            data = data_nonhourly

        freq_string = freq if freq != 'S' else 'QS-DEC'
        ds = xr.Dataset(
            data_vars={'global_horizontal': (
                ('time', 'lat', 'lon'),
                data)
            },
            coords={
                'time': pd.date_range(start='2000-01-01', periods=data_l, freq=freq_string),
                'lat': [40, 50], 'lon': [8.5, 9.5]
            }
        )
        params = {'tilt': 35, 'azim': 180, 'tracking': 0, 'capacity': 1000, 'use_inverter': False}
        result = interface.run_interface_from_dataset(ds, params, freq, pdfs_file=None)

        assert type(result) == xr.Dataset
        assert ds.dims == result.dims
        assert np.array_equal(ds['time'].values, result['time'].values)
        assert 'pv' in result.variables
        assert result['pv'].sum() == pytest.approx(expected_results[freq][0], abs=1e-5)
        assert np.nanmean(result['pv'].values) == pytest.approx(expected_results[freq][1], abs=1e-5)


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
