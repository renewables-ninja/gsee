"""
BRL diffuse-fraction model, vectorized over (time, site)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Ridley et al. (2010) BRL model with Lauret et al. (2013)
parameters, ephem-free and as pure numpy over `(time, site)` arrays:
solar time and altitude come from the vectorized SPA core instead of
per-hour ephem calls.

"""

import numpy as np

from gsee.core import solarposition

#: Updated parameters from Lauret et al. (2013)
DEFAULT_PARAMS = {
    "a0": -5.32,
    "a1": 7.28,
    "b1": -0.03,
    "b2": -0.0047,
    "b3": 1.72,
    "b4": 1.08,
}

_SECONDS_PER_DAY = 86400.0


def _persistence(clearness_days, rise_hour, set_hour):
    """
    The BRL persistence term psi for `clearness_days` shaped
    (D, 24, S), replicating `brl_model._get_psi_func` branch by
    branch. `rise_hour`/`set_hour` are (D, S) integer hours.

    """
    previous = np.roll(clearness_days, 1, axis=1)
    following = np.roll(clearness_days, -1, axis=1)
    # The legacy rise-hour branch indexes ks[hour + 1] guarded by
    # IndexError -> ks[hour]; np.roll would wrap to hour 0 instead
    following[:, 23, :] = clearness_days[:, 23, :]
    # (The set-hour branch's ks[hour - 1] at hour 0 wraps to ks[23]
    # via Python negative indexing, which np.roll reproduces.)

    with np.errstate(invalid="ignore"):
        mid = (previous + following) / 2
    mid = np.where(
        np.isnan(mid), np.where(np.isnan(previous), following, previous), mid
    )

    hour = np.arange(24)[None, :, None]
    rise = rise_hour[:, None, :]
    set_ = set_hour[:, None, :]
    return np.select(
        [(hour > rise) & (hour < set_), hour == rise, hour == set_],
        [mid, following, previous],
        default=0.0,
    )


def brl_diffuse_fraction(
    clearness, times, lat, lon, params=DEFAULT_PARAMS, legacy_predictors=False
):
    """
    Diffuse fraction estimated from hourly clearness indices.

    Parameters
    ----------
    clearness : (T, S) array
        Hourly clearness indices; NaN where undefined (night). NaNs
        propagate to the output.
    times : (T,) datetime64 array or DatetimeIndex (UTC)
        Hourly timestep starts covering whole days (T divisible by 24,
        starting at midnight UTC).
    lat, lon : float or (S,) arrays
        Site coordinates in degrees.
    legacy_predictors : bool, default False
        If True, replicates the historical gsee behaviour of feeding
        solar time and solar altitude to the model in the wrong units.
        Only use for backwards compatibility with older simulation runs.

    Returns
    -------
    (T, S) array of diffuse fractions.

    """
    unixtime = solarposition._to_unixtime(times)
    steps = np.diff(unixtime)
    if not np.allclose(steps, 3600.0):
        raise ValueError("BRL model requires hourly data")
    if len(unixtime) % 24 != 0 or unixtime[0] % _SECONDS_PER_DAY != 0:
        raise ValueError("BRL model requires whole days starting at midnight UTC")

    lat, lon = solarposition._sites(lat, lon)
    clearness = np.asarray(clearness, dtype=float)
    if clearness.ndim == 1:
        clearness = clearness[:, None]
    n_time, n_site = clearness.shape
    n_days = n_time // 24
    clearness_days = clearness.reshape(n_days, 24, n_site)

    day_starts = unixtime.reshape(n_days, 24)[:, 0]
    time_terms = solarposition.time_terms(unixtime)
    hour_angle = (
        time_terms["v"][:, None] + lon[None, :] - time_terms["alpha"][:, None]
    ) % 360.0

    if legacy_predictors:
        # Historical gsee behaviour (wrong units, see module
        # docstring): solar time in radians; solar altitude in
        # radians, evaluated at midnight and held constant all day
        solar_time = np.radians((hour_angle + 180.0) % 360.0)
        midnight_position = solarposition.solar_position(
            (day_starts * 1e9).astype("datetime64[ns]"), lat, lon
        )
        altitude = np.repeat(
            np.radians(midnight_position["apparent_elevation"])[:, None, :],
            24,
            axis=1,
        ).reshape(n_time, n_site)
    else:
        # Predictor units per the papers: apparent solar time in
        # hours, the current hour's apparent solar elevation in
        # degrees
        solar_time = (hour_angle / 15.0 + 12.0) % 24.0
        altitude = solarposition.topocentric_position(
            time_terms["v"][:, None],
            time_terms["alpha"][:, None],
            time_terms["delta"][:, None],
            time_terms["xi"][:, None],
            lat,
            lon,
        )["apparent_elevation"]

    with np.errstate(invalid="ignore"):
        daily_clearness = np.nanmean(clearness_days, axis=1)  # (D, S)

    days = (day_starts / _SECONDS_PER_DAY).astype(int).astype("datetime64[D]")
    rise, set_, _ = solarposition._rise_set_transit_unix(
        days, lat, lon, solarposition.SUNRISE_DEPRESSION, solarposition.DELTA_T
    )
    with np.errstate(invalid="ignore"):
        rise_hour = np.floor((rise % _SECONDS_PER_DAY) / 3600.0)
        set_hour = np.floor((set_ % _SECONDS_PER_DAY) / 3600.0)
    rise_hour = np.where(np.isnan(rise_hour), 0.0, rise_hour)
    set_hour = np.where(np.isnan(set_hour), 23.0, set_hour)

    psi = _persistence(clearness_days, rise_hour, set_hour)

    per_hour = lambda values: np.repeat(values[:, None, :], 24, axis=1).reshape(
        n_time, n_site
    )
    power = (
        params["a0"]
        + params["a1"] * clearness
        + params["b1"] * solar_time
        + params["b2"] * altitude
        + params["b3"] * per_hour(daily_clearness)
        + params["b4"] * psi.reshape(n_time, n_site)
    )
    return 1.0 / (1.0 + np.exp(power))
