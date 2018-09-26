import pytest  # pylint: disable=unused-import
import datetime

import pandas as pd

import gsee.trigon


@pytest.fixture
def coords_and_datetimes():
    coords = (47.36, 8.55)  # Zurich, Switzerland
    datetimes = pd.date_range('2000-01-01 00:00', '2000-12-31 23:00', freq='1H')
    return coords, datetimes


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

    assert angles.sum()['sun_alt'] == pytest.approx(2127.044406)
    assert angles.sum()['sun_azimuth'] == pytest.approx(15224.532375)

    assert angles.loc['2000-01-01 07:00:00', 'duration'] == pytest.approx(47.3333333)
    assert angles.loc['2000-01-01 12:00:00', 'duration'] == pytest.approx(60)
    assert angles.loc['2000-01-01 15:00:00', 'duration'] == pytest.approx(45.6333333)
