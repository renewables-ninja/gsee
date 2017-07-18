"""
Irradiance on an inclined plane
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Using trigonometry (Lambert's cosine law, etc).

"""

import datetime

import ephem
import numpy as np
import pandas as pd


def _sun_rise_set(datetime_index, obs):
    """
    Returns a list of (sunrise, sunset) tuples for the datetimes
    in the given datetime_index, assuming that the index is daily.

    Sunrise or sunset will be None if the sun doesn't rise/set.

    """
    sun = ephem.Sun()
    times = []

    def _get_datetime(date):
        obs.date = date
        sun.compute(obs)
        if sun.rise_time is None:
            rise_time = None
        else:
            rise_time = sun.rise_time.datetime()
        if sun.set_time is None:
            set_time = None
        else:
            set_time = sun.set_time.datetime()
        return (rise_time, set_time)

    for i in datetime_index:
        times.append(_get_datetime(i))
    return times


def sun_rise_set_times(datetime_index, coords):
    """
    Return sunrise and set times for the given datetime_index and coords.

    The datetime_index will be resampled to daily frequency.

    """
    obs = ephem.Observer()
    obs.lat = str(coords[0])
    obs.lon = str(coords[1])
    # Ensure datetime_index is daily
    dtindex = pd.DatetimeIndex(datetime_index.to_series().map(pd.Timestamp.date).unique())
    return _sun_rise_set(dtindex, obs)


def sun_angles(datetime_index, coords, rise_set_times=None):
    """Calculate sun angles. Returns a dataframe containing `sun_alt`,
    `sun_zenith`, `sun_azimuth` and `duration` over the passed datetime index.

    Parameters
    ----------
    datetime_index : pandas datetime index
        Handled as if they were UTC not matter what timezone info
        they may supply.
    coords : (float, float) or (int, int) tuple
        Latitude and longitude.
    rise_set_times : list, default None
        List of (sunrise, sunset) time tuples, if not passed, is computed
        here.

    """

    def _sun_alt_azim(sun, obs):
        sun.compute(obs)
        return sun.alt, sun.az

    # Initialize ephem objects
    obs = ephem.Observer()
    obs.lat = str(coords[0])
    obs.lon = str(coords[1])
    sun = ephem.Sun()

    # Calculate daily sunrise/sunset times
    if not rise_set_times:
        rise_set_times = _sun_rise_set(datetime_index, obs)

    # Calculate hourly altitute, azimuth, and sunshine
    alts = []
    azims = []
    durations = []

    for index, item in enumerate(datetime_index):
        obs.date = item
        # rise/set times are indexed by day, so need to scale the index
        rise_time, set_time = rise_set_times[int(index / 24)]

        # Set angles, sun altitude and duration based on hour of day:
        if rise_time is not None and item.hour == rise_time.hour:
            # Special case for sunrise hour
            duration = 60 - rise_time.minute - (rise_time.second / 60.0)
            obs.date = rise_time + datetime.timedelta(minutes=duration / 2)
            sun_alt, sun_azimuth = _sun_alt_azim(sun, obs)
        elif set_time is not None and item.hour == set_time.hour:
            # Special case for sunset hour
            duration = set_time.minute + set_time.second / 60.0
            obs.date = item + datetime.timedelta(minutes=duration / 2)
            sun_alt, sun_azimuth = _sun_alt_azim(sun, obs)
        else:
            # All other hours
            duration = 60
            obs.date = item + datetime.timedelta(minutes=30)
            sun_alt, sun_azimuth = _sun_alt_azim(sun, obs)
            if sun_alt < 0:  # If sun is below horizon
                sun_alt, sun_azimuth, duration = 0, 0, 0

        alts.append(sun_alt)
        azims.append(sun_azimuth)
        durations.append(duration)
    df = pd.DataFrame({'sun_alt': alts, 'sun_azimuth': azims,
                       'duration': durations},
                      index=datetime_index)
    df['sun_zenith'] = (np.pi / 2) - df.sun_alt
    return df


def _incidence_fixed(sun_alt, tilt, azimuth, sun_azimuth):
    return np.arccos(np.sin(sun_alt) * np.cos(tilt)
                     + np.cos(sun_alt) * np.sin(tilt)
                     * np.cos(azimuth - sun_azimuth))


def _incidence_single_tracking(sun_alt, tilt, azimuth, sun_azimuth):
    if tilt == 0:
        return np.arccos(np.sqrt(1 - np.cos(sun_alt) ** 2
                         * np.cos(sun_azimuth - azimuth) ** 2))
    else:
        return np.arccos(np.sqrt(1 - (np.cos(sun_alt + tilt) * np.cos(tilt)
                         * np.cos(sun_alt) * (1 - np.cos(sun_azimuth
                                                         - azimuth))) ** 2))


def _tilt_single_tracking(sun_alt, tilt, azimuth, sun_azimuth):
    if tilt == 0:
        return np.arctan(np.sin(sun_azimuth - azimuth) / np.tan(sun_alt))
    else:
        return np.arctan((np.cos(sun_alt) * np.sin(sun_azimuth - azimuth))
                         / (np.sin(sun_alt - tilt) + np.sin(tilt)
                            * np.cos(sun_alt) * (1 - np.cos(sun_azimuth)
                                                 - azimuth)))


def aperture_irradiance(direct, diffuse, coords,
                        tilt=0, azimuth=0, tracking=0, albedo=0.3,
                        dni_only=False, angles=None):
    """
    Args:
        direct : a series of direct horizontal irradiance with a datetime index
        diffuse : a series of diffuse horizontal irradiance with the same
                  datetime index as for direct
        coords : (lat, lon) tuple of location coordinates
        tilt : angle of panel relative to the horizontal plane, 0 = flat
        azimuth : deviation of the tilt direction from the meridian,
                  0 = towards pole, going clockwise, 3.14 = towards equator
        tracking : 0 (none, default), 1 (tilt), or 2 (tilt and azimuth).
                   If 1, azimuth is the orientation of the tilt axis, which
                   can be horizontal (tilt=0) or tilted.
        albedo : reflectance of the surrounding surface
        dni_only : only calculate and directly return a DNI time series
                   (ignores tilt, azimuth, tracking and albedo arguments)
        angles : solar angles, if default (None), is computed here

    """
    # 0. Correct azimuth if we're on southern hemisphere, so that 3.14
    # points north instead of south
    if coords[0] < 0:
        azimuth = azimuth + np.pi
    # 1. Calculate solar angles
    if angles is None:
        sunrise_set_times = sun_rise_set_times(direct.index, coords)
        angles = sun_angles(direct.index, coords, sunrise_set_times)
    # 2. Calculate direct normal irradiance
    dni = (direct * (angles['duration'] / 60)) / np.cos(angles['sun_zenith'])
    if dni_only:
        return dni
    # 3. Calculate appropriate aperture incidence angle
    if tracking == 0:
        incidence = _incidence_fixed(angles['sun_alt'], tilt, azimuth,
                                     angles['sun_azimuth'])
        panel_tilt = tilt
    elif tracking == 1:
        # 1-axis tracking with horizontal or tilted tracking axis
        incidence = _incidence_single_tracking(angles['sun_alt'],
                                               tilt, azimuth,
                                               angles['sun_azimuth'])
        panel_tilt = _tilt_single_tracking(angles['sun_alt'], tilt, azimuth,
                                           angles['sun_azimuth'])
    elif tracking == 2:
        # 2-axis tracking means incidence angle is zero
        # Assuming azimuth/elevation tracking for tilt/azimuth angles
        incidence = 0
        panel_tilt = angles['sun_zenith']
        azimuth = angles['sun_azimuth']
    else:
        raise ValueError('Invalid setting for tracking: {}'.format(tracking))
    # 4. Compute direct and diffuse irradiance on plane
    plane_direct = (dni * np.cos(incidence)).fillna(0)
    plane_direct = plane_direct.clip_lower(0)
    plane_diffuse = (diffuse * ((1 + np.cos(panel_tilt)) / 2)
                     + albedo * (direct + diffuse)
                     * ((1 - np.cos(panel_tilt)) / 2)).fillna(0)
    return pd.DataFrame({'direct': plane_direct, 'diffuse': plane_diffuse})
