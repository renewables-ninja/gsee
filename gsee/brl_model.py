"""

An implementation of the `BRL` diffuse solar fraction model as described in
Ridley et al. (2010):

http://dx.doi.org/10.1016/j.renene.2009.07.018

Includes updated model parameters estimated via Bayesian inference in
Lauret et al. (2013):

http://dx.doi.org/10.1016/j.renene.2012.01.049

"""

import datetime
import math

import ephem
import pandas as pd
import numpy as np

from gsee import trigon


def _solartime(observer, sun):
    """Return solar time for given observer and sun"""
    # sidereal time == ra (right ascension) is the highest point (noon)
    hour_angle = observer.sidereal_time() - sun.ra
    return ephem.hours(hour_angle + ephem.hours('12:00')).norm  # norm for 24h


def _get_psi_func(sunrise, sunset):
    """
    Return a function, psi(hour, ks), for the given sunrise and
    sunset times

    """
    try:
        sunrise_hour = sunrise.hour
    except AttributeError:
        sunrise_hour = 0
    try:
        sunset_hour = sunset.hour
    except AttributeError:
        sunset_hour = 23

    def f(hour, ks):
        if (hour > sunrise_hour) and (hour < sunset_hour):
            psi = (ks[hour - 1] + ks[hour + 1]) / 2
            # Extra check: in some cases there is no data in `ks` even before
            # sunset / afer sunrise. For example, if the sun sets just minutes
            # after the hour, there may be no irradiance data in that hour.
            # This if-clause ensures that for practical reasons such cases
            # are treated as if they were sunrise/sunset hours.
            if np.isnan(psi):
                if np.isnan(ks[hour - 1]):
                    psi = ks[hour + 1]
                else:
                    psi = ks[hour - 1]
        elif hour == sunrise_hour:
            try:
                psi = ks[hour + 1]
            except IndexError:
                psi = ks[hour]
        elif hour == sunset_hour:
            try:
                psi = ks[hour - 1]
            except IndexError:
                psi = ks[hour]
        else:
            psi = 0
        return psi
    return f


# Updated params from Lauret et al. (2013)
DEFAULT_PARAMS = {'a0': -5.32,
                  'a1': 7.28,
                  'b1': -0.03,
                  'b2': -0.0047,
                  'b3': 1.72,
                  'b4': 1.08}


# Parameters from Ridley et al. (2010)
# DEFAULT_PARAMS = {'a0': -5.38,
#                   'a1': 6.63,
#                   'b1': 0.006,
#                   'b2': -0.007,
#                   'b3': 1.75,
#                   'b4': 1.31}


# TODO make this into a get_daily_diffuse_func with p param,
# so that can easily switch the predictor parameters!
def _daily_diffuse(obs, ks, sunrise, sunset, p=DEFAULT_PARAMS):
    """
    Returns a list of diffuse fractions for the given observer
    which must have its coordinates and date set, and given the ``ks``,
    a list of 24 hourly clearness indices, and sunrise and sunset times.

    """
    date = obs.date.datetime()
    # whether date was set or not, ensure it's at hour 0
    obs.date = datetime.datetime(date.year, date.month, date.day)
    sun = ephem.Sun()
    sun.compute(obs)
    # sunrise, sunset = _sunrise_sunset(obs, sun)
    alpha = sun.alt
    values = []
    k_day = pd.Series(ks).mean()  # using pandas to ignore NaN
    psi = _get_psi_func(sunrise, sunset)
    for hour in range(24):
        if np.isnan(ks[hour]):
            d = np.nan
        else:
            ast = _solartime(obs, sun)
            pwr = (p['a0'] + p['a1'] * ks[hour]
                   + p['b1'] * ast + p['b2'] * alpha
                   + p['b3'] * k_day + p['b4'] * psi(hour, ks))
            d = 1 / (1 + math.e ** pwr)
        values.append(d)
        # Increase obs.date by one hour for the next iteration
        obs.date = obs.date.datetime() + datetime.timedelta(hours=1)
        sun.compute(obs)
    return values


def run(hourly_clearness, coords, rise_set_times=None):
    """Run the BRL model

    Parameters
    ----------
    hourly_clearness : pandas Series
        Hourly clearness indices with a datetime index.
    coords : 2-tuple of floats or ints
        Latitude and longitude
    rise_set_times : list
        List of (sunrise, sunset) time tuples, if not given, is
        calculated here.

    Returns
    -------
    result : pandas Series
        Diffuse fractions with the same datetime index as hourly_clearness.

    """
    obs = ephem.Observer()
    obs.lat = str(coords[0])
    obs.lon = str(coords[1])
    if rise_set_times is None:
        rise_set_times = trigon._sun_rise_set(hourly_clearness.index, obs)
    diffuse_fractions = []
    for i in range(0, len(hourly_clearness), 24):
        # for entry in list in hourly clearness indices:
        ks = hourly_clearness.iloc[i:i+24].tolist()
        obs.date = hourly_clearness.index[i]
        # These are indexed by day, so need to scale the index
        sunrise, sunset = rise_set_times[int(i / 24)]
        results = _daily_diffuse(obs, ks, sunrise, sunset)
        diffuse_fractions.extend(results)
    return pd.Series(diffuse_fractions, index=hourly_clearness.index)
