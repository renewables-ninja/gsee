import pytest  # pylint: disable=unused-import
import datetime
import math
import os

import pandas as pd

import gsee.trigon


@pytest.fixture
def coords_and_datetimes():
    coords = (47.36, 8.55)  # Zurich, Switzerland
    datetimes = pd.date_range('2000-01-01 00:00', '2000-12-31 23:00', freq='1H')
    return coords, datetimes


@pytest.fixture
def irradiance():
    in_path = os.path.join(os.path.dirname(__file__), 'test_irradiance.csv')
    return pd.read_csv(in_path, index_col=0, parse_dates=True)


def test_sun_rise_set_times(coords_and_datetimes):
    coords, datetimes = coords_and_datetimes
    rise_set_times = gsee.trigon.sun_rise_set_times(datetimes, coords)

    assert isinstance(rise_set_times, pd.Series)

    assert len(rise_set_times) == len(datetimes) / 24

    assert rise_set_times.loc['2000-01-01'][0] == datetime.datetime(2000, 1, 1, 7, 12, 40, 269239)
    assert rise_set_times.loc['2000-01-01'][1] == datetime.datetime(2000, 1, 1, 15, 45, 38, 350501)

    assert rise_set_times.loc['2000-07-15'][0] == datetime.datetime(2000, 7, 15, 3, 44, 19, 170751)
    assert rise_set_times.loc['2000-07-15'][1] == datetime.datetime(2000, 7, 15, 19, 18, 38, 537100)


def test_sun_angles(coords_and_datetimes):
    coords, datetimes = coords_and_datetimes
    angles = gsee.trigon.sun_angles(datetimes, coords)

    assert angles.sum()['sun_alt'] == pytest.approx(2127.154644)
    assert angles.sum()['sun_azimuth'] == pytest.approx(15224.532375)

    assert angles.loc['2000-01-01 07:00:00', 'duration'] == pytest.approx(47.3333333)
    assert angles.loc['2000-01-01 12:00:00', 'duration'] == pytest.approx(60)
    assert angles.loc['2000-01-01 15:00:00', 'duration'] == pytest.approx(45.6333333)


def test_aperture_irradiance_dni_only(irradiance, coords_and_datetimes):
    coords = coords_and_datetimes[0]
    direct, diffuse = irradiance['direct'], irradiance['diffuse']
    result = gsee.trigon.aperture_irradiance(
        direct, diffuse, coords,
        dni_only=True
    )
    assert isinstance(result, pd.Series)
    assert result.mean() == pytest.approx(260.940362)
    assert result.loc['2000-12-31 12:00:00'] == pytest.approx(1448.694722)


def _aperture_irradiance(irradiance, coords_and_datetimes, tracking):
    coords = coords_and_datetimes[0]
    direct, diffuse = irradiance['direct'], irradiance['diffuse']
    result = gsee.trigon.aperture_irradiance(
        direct, diffuse, coords,
        tilt=math.radians(30), azimuth=math.radians(180),
        tracking=tracking
    )
    return result


def test_aperture_irradiance_tracking_0(irradiance, coords_and_datetimes):
    result = _aperture_irradiance(irradiance, coords_and_datetimes, tracking=0)
    assert isinstance(result, pd.DataFrame)
    assert result.mean()['direct'] == pytest.approx(185.266330)
    assert result.mean()['diffuse'] == pytest.approx(59.506055)


def test_aperture_irradiance_tracking_1(irradiance, coords_and_datetimes):
    result = _aperture_irradiance(irradiance, coords_and_datetimes, tracking=1)
    assert isinstance(result, pd.DataFrame)
    assert result.mean()['direct'] == pytest.approx(255.623662)
    assert result.mean()['diffuse'] == pytest.approx(59.608747)


def test_aperture_irradiance_tracking_2(irradiance, coords_and_datetimes):
    result = _aperture_irradiance(irradiance, coords_and_datetimes, tracking=2)
    assert isinstance(result, pd.DataFrame)
    assert result.mean()['direct'] == pytest.approx(260.944585)
    assert result.mean()['diffuse'] == pytest.approx(58.169813)
    assert result.loc['2000-12-31 12:00:00', 'direct'] == pytest.approx(1448.694722)
