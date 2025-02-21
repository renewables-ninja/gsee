"""
Time and solar irradiance calculations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Legacy code directly uses the `ephem` library, as of 2025 also includes
use of `pvlib` which implements additional algorithms such as SPA.

"""

import ephem
import datetime
import pvlib
import numpy as np
import pandas as pd
import xarray as xr


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
    result.index = dtindex
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


def _rise_duration(ts):
    return 60 - (ts.minute + (ts.second / 60))


def _set_duration(ts):
    return ts.minute + (ts.second / 60)


def sun_angles(datetime_index, coords, rise_set_times=None):
    if str(datetime_index.tz) != "UTC":
        raise ValueError("Input data must be in UTC timezone.")

    if rise_set_times is None:
        # 1. Daily time series of sunrise and sunset times
        rise_set_times = sun_rise_set_times(datetime_index, coords)

    # 2. Time series with input resolution,
    # with duration of sunshine + timestamp of midpoint for each time step
    _DURATIONS = []
    _MIDPOINT_TIMES = []
    _INDEXES = []

    def _rise_set_duration_and_index(row):
        rise_duration = _rise_duration(row["sunrise"])
        set_duration = _set_duration(row["sunset"])
        _DURATIONS.append(rise_duration)
        _DURATIONS.append(set_duration)
        _MIDPOINT_TIMES.append(
            row["sunrise"] + pd.Timedelta(rise_duration / 2, unit="m")
        )
        _MIDPOINT_TIMES.append(row["sunset"] - pd.Timedelta(set_duration / 2, unit="m"))
        _INDEXES.append(row["sunrise"].floor("H"))
        _INDEXES.append(row["sunset"].floor("H"))

    rise_set_times.apply(_rise_set_duration_and_index, axis=1)
    duration = pd.DataFrame(
        {"duration": _DURATIONS, "midpoint": _MIDPOINT_TIMES}, index=_INDEXES
    ).reindex(datetime_index)
    duration.index.name = "time"

    na_index = duration[duration["duration"].isna()].index

    duration.loc[na_index, "duration"] = 60
    duration.loc[na_index, "midpoint"] = (
        duration.loc[na_index, :]
        .reset_index()["time"]
        .apply(lambda x: x + pd.Timedelta("30m"))
        .array
    )
    midpoint_times_index = pd.Index(duration["midpoint"])

    # 3. Solar positions for each time step midpoint, combined with duration
    # `get_solarposition` returns a dataframe containing `apparent_zenith`, `zenith`,
    # `apparent_elevation`, `elevation`, `azimuth`, `equation_of_time`
    lat, lon = coords
    angles = pvlib.solarposition.get_solarposition(midpoint_times_index, lat, lon)
    angles["sun_zenith"] = np.radians(angles["apparent_zenith"])
    angles["sun_azimuth"] = np.radians(angles["azimuth"])
    angles["sun_alt"] = np.radians(angles["apparent_elevation"])
    angles.index = datetime_index  # Set the original index
    angles["duration"] = duration["duration"]
    # Relevant properties are set to zero if sun is below horizon
    angles.loc[angles.sun_alt <= 0, ["duration", "sun_alt"]] = 0

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


def get_sun_angles_from_coarser_dataset(ds_input):
    """
    Get sun_angles from a pre-calculated coarser global dataset for 2012
    with the nearest method to save computational time
    A sensitivity test concerning the effect of using a single year for tilt angle
    calculation yields a small difference of 0.35% (Christopher Frank PhD thesis, 2019).

    Parameters
    ----------
    ds_input: xarray dataset with desired dimensions (time, lat, lon) and shape for the output

    Return
    ----------
    Dataset with `sun_alt`, `sun_azimuth`, `duration`, `sun_zenith` values from ds_global
    and dimensions from ds_input

    """
    global_sun_angles = xr.open_dataset("../data/sun_angles_global_2012.nc")
    _angles = xr.Dataset(
        coords={
            "time": ds_input["time"],
            "lat": ds_input["lat"],
            "lon": ds_input["lon"],
        }
    )
    _year = 2012
    _time_with_replaced_year = [
        pd.to_datetime(x).replace(year=_year) for x in _angles["time"].values
    ]
    for var in list(global_sun_angles.keys()):
        _angles[var] = xr.DataArray(
            global_sun_angles[var]
            .sel(
                time=_time_with_replaced_year,
                lat=_angles["lat"],
                lon=_angles["lon"],
                method="nearest",
            )
            .values,
            dims=["time", "lat", "lon"],
        )

    return _angles


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
    data,
    coords=None,
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
    data xarray with three variables: direct_horizontal, diffuse_horizontal, temperature
    in three dimensions (time, lon, lat)

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
    # Define if the input data is a dataframe or an array
    is_dataframe = isinstance(data, pd.DataFrame)
    is_array = isinstance(data, xr.Dataset)

    # 1. Calculate solar angles
    if angles is None:
        if is_array:
            angles = get_sun_angles_from_coarser_dataset(data)
        elif is_dataframe:
            # 0. Correct azimuth if we're on southern hemisphere, so that 3.14
            # points north instead of south
            # not yet for array data <<<-------------------------
            if coords[0] < 0:
                azimuth = azimuth + np.pi

            # Returns a dataframe containing `sun_alt`,
            # `sun_zenith`, `sun_azimuth` and `duration`
            if legacy_solarposition:
                angles = sun_angles_legacy(data.index, coords)
            else:
                angles = sun_angles(data.index, coords)

    # 2. Calculate direct normal irradiance
    dni = (data["direct_horizontal"] * (angles["duration"] / 60)) / np.cos(
        angles["sun_zenith"]
    )

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
    plane_diffuse = data["diffuse_horizontal"] * (
        (1 + np.cos(panel_tilt)) / 2
    ) + albedo * (data["direct_horizontal"] + data["diffuse_horizontal"]) * (
        (1 - np.cos(panel_tilt)) / 2
    )
    plane_direct = dni * np.cos(incidence)

    if is_array:
        return xr.Dataset(
            {
                "direct": (
                    ("time", "lat", "lon"),
                    np.nan_to_num(plane_direct).clip(min=0),
                ),
                "diffuse": (
                    ("time", "lat", "lon"),
                    np.nan_to_num(plane_diffuse).clip(min=0),
                ),
            },
            coords=data.coords,
        )
    elif is_dataframe:
        return pd.DataFrame(
            {
                "direct": plane_direct.fillna(0).clip(lower=0),
                "diffuse": plane_diffuse.fillna(0).clip(lower=0),
            }
        )
