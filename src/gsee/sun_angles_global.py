# Compute sun angles globally hourly for one year (2014)
# to speed up the incidence calculation for array data input in gsee
# Linh Ho (2025-01-24)

import ephem
import numpy as np
import pandas as pd
import xarray as xr
import datetime as dt

# Generate time (daily) and lat, lon values globally
# Select every 10th degree to get a coarser resolution
# chose 2012 for a leap year
time_values = pd.date_range("2012-01-01", "2012-01-03", freq="H")
lat_values = list(range(-90, 90, 10))
lon_values = list(range(-180, 180, 10))

# 1. get the rise and set times of the Sun all the coordinates (lat, lon) and time steps
# Initialize arrays to store the rise and set times
rise_times = np.empty(
    (len(time_values), len(lat_values), len(lon_values)), dtype="datetime64[ns]"
)
set_times = np.empty(
    (len(time_values), len(lat_values), len(lon_values)), dtype="datetime64[ns]"
)

# Initialize the ephem Sun and Observer objects
sun = ephem.Sun()
obs = ephem.Observer()

# Loop through all coordinates and time steps to calculate rise and set times
for i, lat in enumerate(lat_values):
    for j, lon in enumerate(lon_values):
        obs.lat = str(lat)
        obs.lon = str(lon)
        for k, time in enumerate(time_values):
            obs.date = time
            try:
                rise_time = obs.next_rising(sun, use_center=False).datetime()
            except (ephem.AlwaysUpError, ephem.NeverUpError):
                rise_time = None
            try:
                set_time = obs.next_setting(sun, use_center=False).datetime()
            except (ephem.AlwaysUpError, ephem.NeverUpError):
                set_time = None
            rise_times[k, i, j] = rise_time
            set_times[k, i, j] = set_time

# Convert the rise and set times to xarray DataArrays and then to a Dataset
ds_rise_set_times = xr.Dataset()
ds_rise_set_times["rise_time"] = xr.DataArray(
    rise_times,
    coords=[time_values, lat_values, lon_values],
    dims=["time", "lat", "lon"],
)
ds_rise_set_times["set_time"] = xr.DataArray(
    set_times, coords=[time_values, lat_values, lon_values], dims=["time", "lat", "lon"]
)


# 2. Calculate sun angles containing `sun_alt`,
# `sun_zenith`, `sun_azimuth` and `duration` over the passed datetime index.

time_values_hourly = pd.date_range("2014-01-01", "2014-12-31", freq="H")


def _sun_alt_azim(sun, obs):
    sun.compute(obs)
    return sun.alt, sun.az


# Initialize ephem objects
obs = ephem.Observer()
sun = ephem.Sun()

# Calculate hourly altitute, azimuth, and sunshine
# Initialize arrays to store the rise and set times
alts = np.empty(
    (len(time_values_hourly), len(lat_values), len(lon_values)), dtype="float64"
)
azims = np.empty(
    (len(time_values_hourly), len(lat_values), len(lon_values)), dtype="float64"
)
durations = np.empty(
    (len(time_values_hourly), len(lat_values), len(lon_values)), dtype="float64"
)


# Loop through all coordinates and time steps to calculate rise and set times
for i, lat in enumerate(lat_values):
    for j, lon in enumerate(lon_values):
        obs.lat = lat
        obs.lon = lon
        is_new_day = True
        the_day_of_year = time_values[0].date()

        for k, item in enumerate(time_values_hourly):
            obs.date = item
            is_new_day = item.date() == the_day_of_year

            # check if same day, then use the same rise and set times
            # use the sun rise and set times from the nearest data point in a pre-calculated coarser dataset (every 40th box)
            # set get_precise_incidence = True to calculate rise and set times with the actual coordinates (more computationally expensive)
            if is_new_day:
                the_day_of_year = item.date()
                the_nearest_point = ds_rise_set_times.sel(
                    lat=lat, lon=lon, time=the_day_of_year, method="nearest"
                )
                rise_time, set_time = pd.to_datetime(
                    the_nearest_point["rise_time"].values
                ), pd.to_datetime(the_nearest_point["set_time"].values)
            else:
                is_new_day = False

            # Set angles, sun altitude and duration based on hour of day:
            if rise_time is not None and item.hour == rise_time.hour:
                # Special case for sunrise hour
                duration = 60 - rise_time.minute - (rise_time.second / 60.0)
                obs.date = rise_time + dt.timedelta(minutes=duration / 2)
                sun_alt, sun_azimuth = _sun_alt_azim(sun, obs)
            elif set_time is not None and item.hour == set_time.hour:
                # Special case for sunset hour
                duration = set_time.minute + set_time.second / 60.0
                obs.date = item + dt.timedelta(minutes=duration / 2)
                sun_alt, sun_azimuth = _sun_alt_azim(sun, obs)
            else:
                # All other hours
                duration = 60
                obs.date = item + dt.timedelta(minutes=30)
                sun_alt, sun_azimuth = _sun_alt_azim(sun, obs)
                if sun_alt < 0:  # If sun is below horizon
                    sun_alt, sun_azimuth, duration = 0, 0, 0

            alts[k, i, j] = sun_alt
            azims[k, i, j] = sun_azimuth
            durations[k, i, j] = duration

# Convert the rise and set times to xarray DataArrays and then to a Dataset
ds_sun_angles = xr.Dataset()
ds_sun_angles["sun_alt"] = xr.DataArray(
    alts,
    coords=[time_values_hourly, lat_values, lon_values],
    dims=["time", "lat", "lon"],
)
ds_sun_angles["sun_azimuth"] = xr.DataArray(
    azims,
    coords=[time_values_hourly, lat_values, lon_values],
    dims=["time", "lat", "lon"],
)
ds_sun_angles["duration"] = xr.DataArray(
    alts,
    coords=[time_values_hourly, lat_values, lon_values],
    dims=["time", "lat", "lon"],
)

# Correct azimuth if we're on southern hemisphere, so that 3.14
# points north instead of south
ds_sun_angles["sun_azimuth"] = ds_sun_angles["sun_azimuth"].where(
    ds_sun_angles["lat"] >= 0, other=ds_sun_angles["sun_azimuth"] + np.pi, drop=False
)

ds_sun_angles["sun_zenith"] = (np.pi / 2) - ds_sun_angles["sun_alt"]
# Sun altitude considered zero if slightly below horizon
ds_sun_angles["sun_alt"] = ds_sun_angles["sun_alt"].clip(min=0)

ds_sun_angles.to_netcdf(
    "F:/Xiu new 30.8.2017/Delft/My_research/data/sun_angles_global_2012.nc"
)
