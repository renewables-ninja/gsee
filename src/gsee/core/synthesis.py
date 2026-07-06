"""
Synthetic hourly irradiance from coarse climate data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Vectorized re-implementation of the v0.3 climate data interface's
Cython kernels: a sinusoidal diurnal irradiance profile between
sunrise and sunset (normalized so the input daily mean is preserved
exactly), and sampling of daily irradiance totals from monthly
probability density functions (inverse-CDF instead of the original
scipy `rv_discrete`).

Sunrise/sunset hours come from the vectorized solar core instead of
ephem; days where the sun never rises or never sets use hour 0 /
23.999 as the profile bounds, as in v0.3.

"""

import numpy as np

from gsee.core import solarposition

_SECONDS_PER_DAY = 86400.0


def diurnal_profile(daily_mean, days, lat, lon):
    """
    Distribute daily mean irradiance over hours with a sinusoidal
    profile between sunrise and sunset.

    Parameters
    ----------
    daily_mean : (D, S) array
        Mean irradiance (W/m2) per day and site; NaN propagates.
    days : (D,) datetime64 array
        The days (UTC dates); need not be contiguous.
    lat, lon : float or (S,) arrays

    Returns
    -------
    (times, hourly) : ((24*D,) datetime64[ns], (24*D, S) array)
        Hourly timestep starts and hourly irradiance (W/m2), with each
        day's mean equal to the input daily mean.

    """
    days = np.asarray(days).astype("datetime64[D]")
    lat, lon = solarposition._sites(lat, lon)
    daily_mean = np.asarray(daily_mean, dtype=float)
    n_days, n_site = daily_mean.shape

    rise, set_, _ = solarposition._rise_set_transit_unix(
        days, lat, lon, solarposition.SUNRISE_DEPRESSION, solarposition.DELTA_T
    )
    with np.errstate(invalid="ignore"):
        rise_hour = (rise % _SECONDS_PER_DAY) / 3600.0
        set_hour = (set_ % _SECONDS_PER_DAY) / 3600.0
    rise_hour = np.where(np.isnan(rise_hour), 0.0, rise_hour)[:, None, :]
    set_hour = np.where(np.isnan(set_hour), 23.999, set_hour)[:, None, :]

    # Hour midpoints against the sunlit window; days where the sunlit
    # window wraps past midnight UTC (sites far from Greenwich) use the
    # wrapped form, as in the v0.3 kernel
    hour = (np.arange(24) + 0.5)[None, :, None]
    total = daily_mean[:, None, :] * 24.0  # Wh/day
    with np.errstate(invalid="ignore", divide="ignore"):
        width = set_hour - rise_hour
        wrapped_width = 24.0 - (rise_hour - set_hour)
        peak = total * np.pi / (2.0 * width)
        wrapped_peak = total * np.pi / (2.0 * wrapped_width)
        profile = np.where(
            rise_hour < set_hour,
            np.where(
                (hour > rise_hour) & (hour < set_hour),
                np.sin(np.pi * (hour - rise_hour) / width) * peak,
                0.0,
            ),
            np.where(
                hour <= set_hour,
                np.sin(np.pi * (hour + 24.0 - rise_hour) / wrapped_width)
                * wrapped_peak,
                np.where(
                    hour >= rise_hour,
                    np.sin(np.pi * (hour - rise_hour) / wrapped_width) * wrapped_peak,
                    0.0,
                ),
            ),
        )
        profile = np.clip(profile, 0.0, None)
        # Normalize so each day's mean matches the input exactly
        profile_mean = profile.mean(axis=1, keepdims=True)
        scale = np.where(profile_mean > 0, daily_mean[:, None, :] / profile_mean, 0.0)
    hourly = (profile * scale).reshape(n_days * 24, n_site)
    nan_hours = np.repeat(np.isnan(daily_mean)[:, None, :], 24, axis=1).reshape(
        n_days * 24, n_site
    )
    hourly[nan_hours] = np.nan

    times = (
        days[:, None].astype("datetime64[h]")
        + np.arange(24).astype("timedelta64[h]")[None, :]
    ).reshape(-1)
    return times.astype("datetime64[ns]"), hourly


def sample_from_pdfs(xk, pk, n_days, rng):
    """
    Draw `n_days` daily irradiance values per site from per-site
    discrete probability density functions.

    Parameters
    ----------
    xk, pk : (S, B) arrays
        Value bins and their probabilities (need not be normalized).
        Sites whose probabilities sum to zero (or are NaN) draw zeros,
        as in v0.3.
    n_days : int
    rng : numpy.random.Generator

    Returns
    -------
    (n_days, S) array of sampled values.

    """
    xk = np.nan_to_num(np.asarray(xk, dtype=float))
    pk = np.nan_to_num(np.asarray(pk, dtype=float))
    n_site, n_bins = xk.shape

    totals = pk.sum(axis=-1, keepdims=True)
    valid = totals[:, 0] > 0
    cdf = np.cumsum(pk, axis=-1) / np.where(totals > 0, totals, 1.0)

    uniform = rng.random((n_days, n_site))
    indices = np.clip(
        (uniform[:, :, None] > cdf[None, :, :]).sum(axis=-1), 0, n_bins - 1
    )
    values = xk[np.arange(n_site)[None, :], indices]
    return np.where(valid[None, :], values, 0.0)
