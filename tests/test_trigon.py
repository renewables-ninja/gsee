import pytest  # pylint: disable=unused-import
import math
import os

import pandas as pd

import gsee.trigon


@pytest.fixture
def coords_and_datetimes():
    coords = (47.36, 8.55)  # Zurich, Switzerland
    datetimes = pd.date_range("2000-01-01 00:00", "2000-12-31 23:00", freq="1H")
    return coords, datetimes


@pytest.fixture
def irradiance():
    in_path = os.path.join(os.path.dirname(__file__), "test_irradiance.csv")
    return pd.read_csv(in_path, index_col=0, parse_dates=True).tz_localize("UTC")


def test_sun_rise_set_times_ephem(coords_and_datetimes):
    coords, datetimes = coords_and_datetimes
    rise_set_times = gsee.trigon.sun_rise_set_times_ephem(datetimes, coords)

    assert isinstance(rise_set_times, pd.DataFrame)

    assert len(rise_set_times) == len(datetimes) / 24

    assert rise_set_times.loc["2000-01-01", "sunrise"] == pd.Timestamp(
        "2000-01-01 07:12:40.268528"  # was 269239, now 268528 in ephem 4.1.3
    )
    assert rise_set_times.loc["2000-01-01", "sunset"] == pd.Timestamp(
        "2000-01-01 15:45:38.328344"  # was 350501, now 328344 in ephem 4.1.3
    )
    assert rise_set_times.loc["2000-07-15", "sunrise"] == pd.Timestamp(
        "2000-07-15 03:44:19.163496"  # was 170751, now 163496 in ephem 4.1.3
    )
    assert rise_set_times.loc["2000-07-15", "sunset"] == pd.Timestamp(
        "2000-07-15 19:18:38.515113"  # was 537100, now 515113 in ephem 4.1.3
    )


def test_sun_rise_set_times_pvlib(coords_and_datetimes):
    coords, datetimes = coords_and_datetimes
    rise_set_times = gsee.trigon.sun_rise_set_times(datetimes, coords)

    assert isinstance(rise_set_times, pd.DataFrame)

    assert len(rise_set_times) == len(datetimes) / 24

    assert rise_set_times.loc["2000-01-01", "sunrise"] == pd.Timestamp(
        "2000-01-01 07:13:04.637318656+0000", tz="UTC"
    )
    assert rise_set_times.loc["2000-01-01", "sunset"] == pd.Timestamp(
        "2000-01-01 15:45:13.925562496+0000", tz="UTC"
    )
    assert rise_set_times.loc["2000-07-15", "sunrise"] == pd.Timestamp(
        "2000-07-15 03:44:38.832119680+0000", tz="UTC"
    )
    assert rise_set_times.loc["2000-07-15", "sunset"] == pd.Timestamp(
        "2000-07-15 19:18:18.952050048+0000", tz="UTC"
    )


def test_sun_rise_set_times_pvlib_at_ephem_failure_location():
    # This combination of coords and datetimes causes ephem to get stuck in a loop
    # as of v4.1.3 through v4.1.6
    coords = (71.50, 179.50)
    datetimes = pd.date_range("2019-01-01 00:00", "2019-12-31 23:00", freq="1H")
    rise_set_times = gsee.trigon.sun_rise_set_times(datetimes, coords)

    assert isinstance(rise_set_times, pd.DataFrame)

    assert len(rise_set_times) == len(datetimes) / 24

    assert rise_set_times.loc["2019-01-01", "sunrise"] is pd.NaT  # Never rises
    assert rise_set_times.loc["2019-07-01", "sunrise"] is pd.NaT  # Never sets
    assert rise_set_times.loc["2019-03-01", "sunrise"] == pd.Timestamp(
        "2019-02-28 19:35:10.125801216+0000", tz="UTC"
    )


def test_sun_angles_non_utc(coords_and_datetimes):
    in_path = os.path.join(os.path.dirname(__file__), "test_irradiance.csv")
    irradiance = pd.read_csv(in_path, index_col=0, parse_dates=True)
    coords, datetimes = coords_and_datetimes
    direct, diffuse = irradiance["direct"], irradiance["diffuse"]
    with pytest.raises(ValueError) as e:
        gsee.trigon.aperture_irradiance(direct, diffuse, coords)
    assert "Input data must be in UTC timezone." in str(e.value)


def test_sun_angles_legacy(coords_and_datetimes):
    coords, datetimes = coords_and_datetimes
    angles = gsee.trigon.sun_angles_legacy(datetimes, coords)

    assert angles["sun_alt"].sum() == pytest.approx(2127.154644)
    assert angles["sun_azimuth"].sum() == pytest.approx(15224.532375)

    assert angles.loc["2000-01-01 07:00:00", "duration"] == pytest.approx(47.3333333)
    assert angles.loc["2000-01-01 12:00:00", "duration"] == pytest.approx(60)
    assert angles.loc["2000-01-01 15:00:00", "duration"] == pytest.approx(45.6333333)


def test_sun_angles(coords_and_datetimes):
    coords, datetimes = coords_and_datetimes
    datetimes = datetimes.tz_localize("UTC")
    angles = gsee.trigon.sun_angles(datetimes, coords)

    assert angles["sun_alt"].sum() == pytest.approx(79.269849)
    assert angles[angles.sun_alt > 0]["sun_alt"].sum() == pytest.approx(2127.645941)
    assert angles["sun_azimuth"].sum() == pytest.approx(27436.169951)
    assert angles[angles.sun_alt > 0]["sun_azimuth"].sum() == pytest.approx(
        15091.976727
    )

    assert angles.loc["2000-01-01 07:00:00", "risen_fraction"] == pytest.approx(
        0.782045
    )
    assert angles.loc["2000-01-01 12:00:00", "risen_fraction"] == 1
    assert angles.loc["2000-01-01 15:00:00", "risen_fraction"] == pytest.approx(
        0.753868
    )
    assert angles.loc["2000-01-01 16:00:00", "risen_fraction"] == 0


@pytest.mark.parametrize(
    "test_input,expected",
    [
        ((math.radians(90), math.radians(0), math.radians(0), math.radians(45)), 0),
        ((math.radians(45), math.radians(5), math.radians(0), math.radians(0)), 40),
        ((math.radians(0), math.radians(0), math.radians(0), math.radians(45)), 45),
        ((math.radians(45), math.radians(0), math.radians(90), math.radians(90)), 45),
        ((math.radians(45), math.radians(5), math.radians(180), math.radians(0)), 50),
    ],
)
def test_incidence_single_tracking(test_input, expected):
    result = math.degrees(gsee.trigon._incidence_single_tracking(*test_input))
    assert result == pytest.approx(expected)


def test_aperture_irradiance_dni_only_legacy(irradiance, coords_and_datetimes):
    coords = coords_and_datetimes[0]
    direct, diffuse = irradiance["direct"], irradiance["diffuse"]
    result = gsee.trigon.aperture_irradiance(
        direct, diffuse, coords, dni_only=True, legacy_solarposition=True
    )
    assert isinstance(result, pd.Series)
    assert result.mean() == pytest.approx(260.940362)
    assert result.loc["2000-12-31 12:00:00"] == pytest.approx(1448.694722)


def test_aperture_irradiance_dni_only(irradiance, coords_and_datetimes):
    coords = coords_and_datetimes[0]
    direct, diffuse = irradiance["direct"], irradiance["diffuse"]
    result = gsee.trigon.aperture_irradiance(direct, diffuse, coords, dni_only=True)
    assert result.mean() == pytest.approx(260.794548)
    assert result.loc["2000-12-31 12:00:00"] == pytest.approx(1448.534620)


def _aperture_irradiance(
    irradiance,
    coords_and_datetimes,
    tracking,
    tilt=math.radians(30),
    azimuth=math.radians(180),
    legacy_solarposition=True,
):
    coords = coords_and_datetimes[0]
    direct, diffuse = irradiance["direct"], irradiance["diffuse"]
    result = gsee.trigon.aperture_irradiance(
        direct,
        diffuse,
        coords,
        tilt=tilt,
        azimuth=azimuth,
        tracking=tracking,
        legacy_solarposition=legacy_solarposition,
    )
    return result


def test_aperture_irradiance_tracking_0_legacy(irradiance, coords_and_datetimes):
    result = _aperture_irradiance(
        irradiance, coords_and_datetimes, tracking=0, legacy_solarposition=True
    )
    assert isinstance(result, pd.DataFrame)
    assert result.mean()["direct"] == pytest.approx(185.266330)
    assert result.mean()["diffuse"] == pytest.approx(59.506055)


def test_aperture_irradiance_tracking_0(irradiance, coords_and_datetimes):
    result = _aperture_irradiance(
        irradiance, coords_and_datetimes, tracking=0, legacy_solarposition=False
    )
    assert isinstance(result, pd.DataFrame)
    assert result.mean()["direct"] == pytest.approx(185.224865)
    assert result.mean()["diffuse"] == pytest.approx(59.506054)


def test_aperture_irradiance_tracking_1_horizontal_legacy(
    irradiance, coords_and_datetimes
):
    result = _aperture_irradiance(
        irradiance, coords_and_datetimes, tracking=1, tilt=0, legacy_solarposition=True
    )
    assert isinstance(result, pd.DataFrame)
    assert result.mean()["direct"] == pytest.approx(200.394662)
    assert result.mean()["diffuse"] == pytest.approx(57.748641)


def test_aperture_irradiance_tracking_1_30deg_legacy(irradiance, coords_and_datetimes):
    result = _aperture_irradiance(
        irradiance,
        coords_and_datetimes,
        tracking=1,
        tilt=math.radians(30),
        legacy_solarposition=True,
    )
    assert isinstance(result, pd.DataFrame)
    assert result.mean()["direct"] == pytest.approx(242.210095)
    assert result.mean()["diffuse"] == pytest.approx(57.851825)


def test_aperture_irradiance_tracking_2_legacy(irradiance, coords_and_datetimes):
    result = _aperture_irradiance(
        irradiance, coords_and_datetimes, tracking=2, legacy_solarposition=True
    )
    assert isinstance(result, pd.DataFrame)
    assert result.mean()["direct"] == pytest.approx(260.944585)
    assert result.mean()["diffuse"] == pytest.approx(58.169813)
    assert result.loc["2000-12-31 12:00:00", "direct"] == pytest.approx(1448.694722)


def test_aperture_irradiance_tracking_2(irradiance, coords_and_datetimes):
    result = _aperture_irradiance(
        irradiance, coords_and_datetimes, tracking=2, legacy_solarposition=False
    )
    assert isinstance(result, pd.DataFrame)
    assert result.mean()["direct"] == pytest.approx(260.794548)
    assert result.mean()["diffuse"] == pytest.approx(58.169965)
    assert result.loc["2000-12-31 12:00:00", "direct"] == pytest.approx(1448.534620)
