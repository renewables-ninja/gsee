"""
Time and solar irradiance calculations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Legacy code directly uses the `ephem` library, as of 2025 also includes
use of `pvlib` which implements additional algorithms such as SPA.

"""

import datetime

import ephem
import pvlib
import numpy as np
import pandas as pd


def _get_rise_and_set_time(date, sun, obs):
    """
    Returns a tuple of (rise, set) time for the given date, sun and observer.
    """
    obs.date = date
    sun.compute(obs)

    # Up to and including v0.2.1, old API was implicitly setting use_center
    # to True, but considering the sun's radius leads to slightly more
    # realistic rise/set time
    try:
        rising = obs.next_rising(sun, use_center=False)
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        rising = None

    try:
        setting = obs.next_setting(sun, use_center=False)
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        setting = None

    rise_time = None if not rising else rising.datetime()
    set_time = None if not setting else setting.datetime()

    return (rise_time, set_time)


def _daily_dtindex(datetime_index):
    return pd.DatetimeIndex(datetime_index.to_series().map(pd.Timestamp.date).unique())


def sun_rise_set_times(datetime_index, coords):
    """
    Returns sunrise and set times for the given datetime_index and coords,
    as a Series indexed by date (days, resampled from the datetime_index).

    `datetime_index` is localized to UTC and assumed to be either in UTC explicitly
    or implicitly.

    """
    dtindex = _daily_dtindex(datetime_index)
    loc = pvlib.location.Location(*coords)
    result = loc.get_sun_rise_set_transit(dtindex.tz_localize("UTC"), method="spa")
    result.index = dtindex.tz_localize("UTC")
    return result


def sun_rise_set_times_ephem(datetime_index, coords):
    """
    Returns sunrise and set times for the given datetime_index and coords,
    as a Series indexed by date (days, resampled from the datetime_index).

    """
    sun = ephem.Sun()
    obs = ephem.Observer()
    obs.lat = str(coords[0])
    obs.lon = str(coords[1])

    dtindex = _daily_dtindex(datetime_index)

    return pd.DataFrame(
        [_get_rise_and_set_time(i, sun, obs) for i in dtindex],
        index=dtindex,
        columns=["sunrise", "sunset"],
    )


def sun_angles(dt_index, coords, rise_set_times=None):
    if str(dt_index.tz) != "UTC":
        raise ValueError("Input data must be in UTC timezone.")

    lat, lon = coords

    dt_index.freq = pd.infer_freq(dt_index)
    dt_index_freq = dt_index.freq
    shift_freq = dt_index.freq / 2
    shifted_index = dt_index.shift(freq=shift_freq)

    angles = pvlib.solarposition.get_solarposition(shifted_index, lat, lon)

    if rise_set_times is None:
        rise_set_times = sun_rise_set_times(dt_index, coords)

    sunrises = pd.Series(
        rise_set_times["sunrise"].dropna().array,
        index=rise_set_times["sunrise"]
        .dropna()
        .apply(lambda x: x.floor(dt_index_freq))
        .array,
    )
    sunsets = pd.Series(
        rise_set_times["sunset"].dropna().array,
        index=rise_set_times["sunset"]
        .dropna()
        .apply(lambda x: x.floor(dt_index_freq))
        .array,
    )

    # In rare cases there are duplicate sunrises/sunsets
    sunsets = sunsets[~sunsets.index.duplicated(keep="first")]
    sunrises = sunrises[~sunrises.index.duplicated(keep="first")]

    angles.index = dt_index  # Set the original index

    angles["sunrise"] = sunrises
    angles["sunset"] = sunsets

    # risen_fraction for sunrise and sunset timesteps
    angles["risen_fraction"] = (
        1 - ((angles["sunrise"] - angles.index) / pd.Timedelta(dt_index_freq))
    ).add((angles["sunset"] - angles.index) / pd.Timedelta(dt_index_freq), fill_value=0)

    # risen_fraction is 1 where sun is above horizon outside of sunrise/sunset timesteps
    angles.loc[
        (angles.apparent_elevation > 0) & (angles.risen_fraction.isnull()),
        "risen_fraction",
    ] = 1

    # Recalculate angles for actual midpoint in sunrise timesteps
    d_sunrise = angles[angles.sunrise.notnull()]["sunrise"]
    next_step = d_sunrise.dt.floor(dt_index_freq) + dt_index_freq
    sunrise_recalc = d_sunrise + (next_step - d_sunrise) / 2
    new_sunrise_angles = pvlib.solarposition.get_solarposition(sunrise_recalc, lat, lon)
    angles.loc[d_sunrise.index, new_sunrise_angles.columns] = new_sunrise_angles.values

    # Recalculate angles for actual midpoint in sunset timesteps
    d_sunset = angles[angles.sunset.notnull()]["sunset"]
    prev_step = d_sunset.dt.floor(dt_index_freq)
    sunset_recalc = prev_step + (d_sunset - prev_step) / 2
    new_sunset_angles = pvlib.solarposition.get_solarposition(sunset_recalc, lat, lon)
    angles.loc[d_sunset.index, new_sunset_angles.columns] = new_sunset_angles.values

    # FIXME: if the sun's center does not rise above horizon,
    # we may be between sunrise and sunset events but the apparent_elevation is just below zero
    # For now, we set the rise_fraction in those cases to zero,
    # although there would be a very small non-zero irradiance
    angles.loc[angles.apparent_elevation <= 0, "risen_fraction"] = 0

    angles["sun_zenith"] = np.radians(angles["apparent_zenith"])
    angles["sun_azimuth"] = np.radians(angles["azimuth"])
    angles["sun_alt"] = np.radians(angles["apparent_elevation"])

    return angles


def sun_angles_legacy(datetime_index, coords, rise_set_times=None):
    """
    Calculates sun angles. Returns a dataframe containing `sun_alt`,
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

    if rise_set_times is None:
        # Calculate daily sunrise/sunset times
        rise_set_times = sun_rise_set_times_ephem(datetime_index, coords)

    # Calculate hourly altitude, azimuth, and sunshine
    alts = []
    azims = []
    durations = []

    for index, item in enumerate(datetime_index):
        obs.date = item
        # rise/set times are indexed by day, so need to adjust lookup
        rise_time, set_time = rise_set_times.loc[
            pd.Timestamp(item.date()), ["sunrise", "sunset"]
        ]

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
    df = pd.DataFrame(
        {"sun_alt": alts, "sun_azimuth": azims, "duration": durations},
        index=datetime_index,
    )
    df["sun_zenith"] = (np.pi / 2) - df.sun_alt
    # Sun altitude considered zero if slightly below horizon
    df["sun_alt"] = df["sun_alt"].clip(lower=0)
    return df


def _incidence_fixed(sun_alt, tilt, azimuth, sun_azimuth):
    """Returns incidence angle for a fixed panel"""
    return np.arccos(
        np.sin(sun_alt) * np.cos(tilt)
        + np.cos(sun_alt) * np.sin(tilt) * np.cos(azimuth - sun_azimuth)
    )


def _incidence_single_tracking(sun_alt, tilt, azimuth, sun_azimuth):
    """
    Returns incidence angle for a 1-axis tracking panel

    Parameters
    ----------
    sun_alt : sun altitude angle
    tilt : tilt of tilt axis
    azimuth : rotation of tilt axis
    sun_azimuth : sun azimuth angle

    """
    if tilt == 0:
        return np.arccos(
            np.sqrt(1 - np.cos(sun_alt) ** 2 * np.cos(sun_azimuth - azimuth) ** 2)
        )
    else:
        return np.arccos(
            np.sqrt(
                1
                - (
                    np.cos(sun_alt + tilt)
                    - np.cos(tilt)
                    * np.cos(sun_alt)
                    * (1 - np.cos(sun_azimuth - azimuth))
                )
                ** 2
            )
        )


def _tilt_single_tracking(sun_alt, tilt, azimuth, sun_azimuth):
    """
    Returns panel tilt angle for a 1-axis tracking panel

    Parameters
    ----------
    sun_alt : sun altitude angle
    tilt : tilt of tilt axis
    azimuth : rotation of tilt axis
    sun_azimuth : sun azimuth angle

    """
    if tilt == 0:
        return np.arctan(np.sin(sun_azimuth - azimuth) / np.tan(sun_alt))
    else:
        return np.arctan(
            (np.cos(sun_alt) * np.sin(sun_azimuth - azimuth))
            / (
                np.sin(sun_alt - tilt)
                + np.sin(tilt) * np.cos(sun_alt) * (1 - np.cos(sun_azimuth - azimuth))
            )
        )


def aperture_irradiance(
    direct,
    diffuse,
    coords,
    tilt=0,
    azimuth=0,
    tracking=0,
    albedo=0.3,
    dni_only=False,
    angles=None,
    legacy_solarposition=False,
):
    """
    Parameters
    ----------

    direct : pandas.Series
        Direct horizontal irradiance with a datetime index
    diffuse : pandas.Series
        Diffuse horizontal irradiance with the same datetime index as `direct`
    coords : (float, float)
        (lat, lon) tuple of location coordinates
    tilt : float, default=0
        Angle of panel relative to the horizontal plane.
        0 = flat.
    azimuth : float, default=0
        Deviation of the tilt direction from the meridian.
        0 = towards pole, going clockwise, 3.14 = towards equator.
    tracking : int, default=0
        0 (none, default), 1 (tilt), or 2 (tilt and azimuth).
        If 1, `tilt` gives the tilt of the tilt axis relative to horizontal
        (tilt=0) and `azimuth` gives the orientation of the tilt axis.
    albedo : float, default=0.3
        reflectance of the surrounding surface
    dni_only : bool, default False
        only calculate and directly return a DNI time series (ignores
        tilt, azimuth, tracking and albedo arguments).
    angles : pandas.DataFrame, optional
        Solar angles. If default (None), they are computed automatically.

    """
    # 0. Correct azimuth if we're on southern hemisphere, so that 3.14
    # points north instead of south
    if coords[0] < 0:
        azimuth = azimuth + np.pi

    # 1. Calculate solar angles
    if angles is None:
        if legacy_solarposition:
            # Returns a dataframe containing `sun_alt`,
            # `sun_zenith`, `sun_azimuth` and `duration`
            angles = sun_angles_legacy(direct.index, coords)
        else:
            # Returns a dataframe containing `sun_alt`,
            # `sun_zenith`, `sun_azimuth` and `risen_fraction`
            angles = sun_angles(direct.index, coords)

    # 2. Calculate direct normal irradiance
    if "duration" in angles.columns:
        dni = (direct * (angles["duration"] / 60)) / np.cos(angles["sun_zenith"])
    else:
        dni = (direct * angles["risen_fraction"]) / np.cos(angles["sun_zenith"])

    if dni_only:
        return dni

    # 3. Calculate appropriate aperture incidence angle
    if tracking == 0:
        incidence = _incidence_fixed(
            angles["sun_alt"], tilt, azimuth, angles["sun_azimuth"]
        )
        panel_tilt = tilt
    elif tracking == 1:
        # 1-axis tracking with horizontal or tilted tracking axis
        incidence = _incidence_single_tracking(
            angles["sun_alt"], tilt, azimuth, angles["sun_azimuth"]
        )
        panel_tilt = _tilt_single_tracking(
            angles["sun_alt"], tilt, azimuth, angles["sun_azimuth"]
        )
    elif tracking == 2:
        # 2-axis tracking means incidence angle is zero
        # Assuming azimuth/elevation tracking for tilt/azimuth angles
        incidence = 0
        panel_tilt = angles["sun_zenith"]
        azimuth = angles["sun_azimuth"]
    else:
        raise ValueError("Invalid setting for tracking: {}".format(tracking))

    # 4. Compute direct and diffuse irradiance on plane
    # Clipping ensures that very low panel to sun altitude angles do not
    # result in negative direct irradiance (reflection)
    plane_direct = (dni * np.cos(incidence)).fillna(0).clip(lower=0)
    plane_diffuse = (
        diffuse * ((1 + np.cos(panel_tilt)) / 2)
        + albedo * (direct + diffuse) * ((1 - np.cos(panel_tilt)) / 2)
    ).fillna(0)

    return pd.DataFrame({"direct": plane_direct, "diffuse": plane_diffuse})
