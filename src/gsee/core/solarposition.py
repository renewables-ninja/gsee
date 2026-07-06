"""
Vectorized multi-site solar position
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The expensive part of the NREL SPA algorithm — Earth heliocentric
position, nutation, and sidereal time — depends only on time, not
location. `time_terms()` computes it once for a shared time index;
`topocentric_position()` broadcasts the cheap per-site corrections over
a (time, site) grid. This makes solar position for S sites cost
O(T) + O(T*S) trigonometry instead of S full SPA runs.

Sunrise/sunset (`sun_rise_set`) uses the closed-form hour-angle
equation around the SPA solar transit, with SPA declination evaluated
at the event time itself (via fixed-point iteration) — fully
vectorized over (day, site). Ground-truth checks (evaluating the true
apparent elevation at the event times) show this lands within ~1 s of
the -0.8333 deg crossing, closer than the iterative SPA-appendix
method in pvlib, whose interpolation error reaches ~2 min at
mid-latitudes for events far from 0h UT and minutes at polar
latitudes' slow horizon crossings.

`sun_angles()` combines both into the full (time, site) frame the PV
model needs: apparent elevation/azimuth at timestep midpoints, with
angles recalculated at the midpoint of the sunlit portion for timesteps
containing sunrise or sunset, and the risen fraction of each timestep.

All functions take and return plain numpy arrays; shapes are (T,) for
time-only, (S,) for site-only, and (T, S) for combined quantities.
Times are UTC throughout.

"""

import numpy as np
from pvlib import spa

if spa.USE_NUMBA:
    raise ImportError(
        "gsee.core.solarposition requires pvlib.spa in numpy mode; "
        "unset the PVLIB_USE_NUMBA environment variable"
    )

#: Difference between terrestrial time and UT1 (seconds), matching the
#: pvlib.solarposition default so results are comparable
DELTA_T = 67.0

#: Sun depression angle below the horizon at sunrise/sunset (degrees):
#: sun radius plus standard atmospheric refraction, as in SPA
SUNRISE_DEPRESSION = 0.8333

# Defaults matching pvlib.solarposition.get_solarposition
PRESSURE = 101325.0  # Pa
TEMPERATURE = 12.0  # deg C
ATMOS_REFRACT = 0.5667  # deg

_SECONDS_PER_DAY = 86400.0


def _to_unixtime(times):
    """Times (datetime64 array or DatetimeIndex, UTC) to float unix seconds."""
    if hasattr(times, "as_unit"):  # pandas DatetimeIndex, possibly tz-aware;
        # normalize the resolution: pandas 3 defaults to microseconds
        return times.as_unit("ns").asi8 / 1e9
    times = np.asarray(times)
    if not np.issubdtype(times.dtype, np.datetime64):
        raise TypeError("times must be datetime64 or a pandas DatetimeIndex")
    return times.astype("datetime64[ns]").astype(np.int64) / 1e9


def _sites(lat, lon):
    lat = np.atleast_1d(np.asarray(lat, dtype=float))
    lon = np.atleast_1d(np.asarray(lon, dtype=float))
    if lat.shape != lon.shape or lat.ndim != 1:
        raise ValueError("lat and lon must be scalars or 1-D arrays of equal length")
    return lat, lon


def time_terms(unixtime, delta_t=DELTA_T):
    """
    Location-independent part of NREL SPA for the given float unix
    seconds array (T,). Returns a dict of (T,) arrays, all in degrees:
    `v` (apparent sidereal time), `alpha` (geocentric sun right
    ascension), `delta` (geocentric sun declination), and `xi`
    (equatorial horizontal parallax).

    """
    unixtime = np.atleast_1d(np.asarray(unixtime, dtype=float))
    jd = spa.julian_day(unixtime)
    jde = spa.julian_ephemeris_day(jd, delta_t)
    jc = spa.julian_century(jd)
    jce = spa.julian_ephemeris_century(jde)
    jme = spa.julian_ephemeris_millennium(jce)
    R = spa.heliocentric_radius_vector(jme)
    L = spa.heliocentric_longitude(jme)
    B = spa.heliocentric_latitude(jme)
    Theta = spa.geocentric_longitude(L)
    beta = spa.geocentric_latitude(B)
    x0 = spa.mean_elongation(jce)
    x1 = spa.mean_anomaly_sun(jce)
    x2 = spa.mean_anomaly_moon(jce)
    x3 = spa.moon_argument_latitude(jce)
    x4 = spa.moon_ascending_longitude(jce)
    nutation = np.empty((2, len(x0)))
    spa.longitude_obliquity_nutation(jce, x0, x1, x2, x3, x4, nutation)
    delta_psi, delta_epsilon = nutation
    epsilon0 = spa.mean_ecliptic_obliquity(jme)
    epsilon = spa.true_ecliptic_obliquity(epsilon0, delta_epsilon)
    delta_tau = spa.aberration_correction(R)
    lamd = spa.apparent_sun_longitude(Theta, delta_psi, delta_tau)
    v0 = spa.mean_sidereal_time(jd, jc)
    v = spa.apparent_sidereal_time(v0, delta_psi, epsilon)
    alpha = spa.geocentric_sun_right_ascension(lamd, epsilon, beta)
    delta = spa.geocentric_sun_declination(lamd, epsilon, beta)
    xi = spa.equatorial_horizontal_parallax(R)
    return {"v": v, "alpha": alpha, "delta": delta, "xi": xi}


def topocentric_position(
    v,
    alpha,
    delta,
    xi,
    lat,
    lon,
    altitude=0.0,
    pressure=PRESSURE,
    temperature=TEMPERATURE,
    atmos_refract=ATMOS_REFRACT,
):
    """
    Location-dependent part of NREL SPA. All angle arguments in degrees;
    input shapes must broadcast against each other (typically time terms
    shaped (T, 1) against sites shaped (S,), or flat matched arrays).
    Returns a dict with `apparent_elevation`, `apparent_zenith` and
    `azimuth` (degrees, 0..360 clockwise from north) in the broadcast
    shape.

    """
    with np.errstate(invalid="ignore", divide="ignore"):
        H = spa.local_hour_angle(v, lon, alpha)
        u = spa.uterm(lat)
        x = spa.xterm(u, lat, altitude)
        y = spa.yterm(u, lat, altitude)
        delta_alpha = spa.parallax_sun_right_ascension(x, xi, H, delta)
        delta_prime = spa.topocentric_sun_declination(delta, x, y, xi, delta_alpha, H)
        h_prime = spa.topocentric_local_hour_angle(H, delta_alpha)
        e0 = spa.topocentric_elevation_angle_without_atmosphere(
            lat, delta_prime, h_prime
        )
        delta_e = spa.atmospheric_refraction_correction(
            pressure / 100.0, temperature, e0, atmos_refract
        )
        e = spa.topocentric_elevation_angle(e0, delta_e)
        gamma = spa.topocentric_astronomers_azimuth(h_prime, delta_prime, lat)
        phi = spa.topocentric_azimuth_angle(gamma)
    return {
        "apparent_elevation": e,
        "apparent_zenith": spa.topocentric_zenith_angle(e),
        "azimuth": phi,
    }


def solar_position(times, lat, lon, delta_t=DELTA_T, **site_kwargs):
    """
    Solar position for all combinations of `times` (T,) and sites
    (lat/lon scalars or (S,) arrays). Returns a dict of (T, S) arrays:
    `apparent_elevation`, `apparent_zenith`, `azimuth`, in degrees.

    Numerically identical to per-site
    `pvlib.solarposition.get_solarposition`, but the time-dependent SPA
    terms are computed only once and shared across sites.

    """
    unixtime = _to_unixtime(times)
    lat, lon = _sites(lat, lon)
    tt = time_terms(unixtime, delta_t=delta_t)
    return topocentric_position(
        tt["v"][:, None],
        tt["alpha"][:, None],
        tt["delta"][:, None],
        tt["xi"][:, None],
        lat,
        lon,
        **site_kwargs,
    )


def _rise_set_transit_unix(days, lat, lon, depression, delta_t):
    """
    Sunrise, sunset and solar transit as float unix seconds (D, S);
    sunrise/sunset are NaN on days without them (polar day/night).
    `days` is a (D,) datetime64[D] array of UTC dates.

    """
    lat, lon = _sites(lat, lon)
    noons = days.astype("datetime64[s]").astype(np.float64) + _SECONDS_PER_DAY / 2
    # One extra noon so daily rates exist for the last day
    noons_ext = np.concatenate([noons, [noons[-1] + _SECONDS_PER_DAY]])
    tt = time_terms(noons_ext, delta_t=delta_t)

    # Sun hour angle at each noon, wrapped to [-180, 180); zero at transit
    H = (tt["v"][:, None] + lon[None, :] - tt["alpha"][:, None] + 180.0) % 360.0 - 180.0
    # The hour angle advances ~360 deg/day; use the actual daily rate so
    # the transit is exact to sub-second level
    rate = 360.0 + ((H[1:] - H[:-1] + 180.0) % 360.0 - 180.0)  # (D, S) deg/day
    offset = -H[:-1] / rate  # days relative to noon, within [-0.5, 0.5]
    transit = noons[:, None] + offset * _SECONDS_PER_DAY

    # Declination varies linearly to very good approximation across a
    # day; interpolate it from the daily noon values
    ddelta = np.diff(tt["delta"])[:, None]  # deg/day

    def _declination(at):
        offset_days = (at - noons[:, None]) / _SECONDS_PER_DAY
        return tt["delta"][:-1, None] + ddelta * offset_days

    def _half_width(declination):
        dec = np.radians(declination)
        cos_ws = (np.sin(np.radians(-depression)) - np.sin(phi) * np.sin(dec)) / (
            np.cos(phi) * np.cos(dec)
        )
        # NaN outside [-1, 1]: sun never crosses the horizon that day
        return np.degrees(np.arccos(cos_ws)) / rate * _SECONDS_PER_DAY

    phi = np.radians(lat)[None, :]
    with np.errstate(invalid="ignore"):
        # First guess with declination at transit, then re-evaluate the
        # hour-angle width with declination at the event time itself:
        # at high latitudes sunrise can be ~10 h before transit, over
        # which the declination moves enough (~0.2 deg) to shift the
        # event by minutes at the slow polar horizon-crossing speeds
        half_rise = half_set = _half_width(_declination(transit))
        for _ in range(2):
            half_rise = _half_width(_declination(transit - half_rise))
            half_set = _half_width(_declination(transit + half_set))
    return transit - half_rise, transit + half_set, transit


def _to_datetime64(unix_seconds):
    """Float unix seconds (NaN allowed) to datetime64[ns] (NaT for NaN)."""
    out = np.full(unix_seconds.shape, np.datetime64("NaT", "ns"))
    valid = ~np.isnan(unix_seconds)
    out[valid] = (unix_seconds[valid] * 1e9).astype(np.int64).astype("datetime64[ns]")
    return out


def sun_rise_set(days, lat, lon, depression=SUNRISE_DEPRESSION, delta_t=DELTA_T):
    """
    Sunrise, sunset and solar transit for all combinations of `days`
    (any datetime64 array, floored to UTC dates) and sites. Returns
    three (D, S) datetime64[ns] arrays; sunrise/sunset are NaT on days
    when the sun does not cross the horizon.

    """
    days = np.asarray(days).astype("datetime64[D]")
    rise, set_, transit = _rise_set_transit_unix(days, lat, lon, depression, delta_t)
    return _to_datetime64(rise), _to_datetime64(set_), _to_datetime64(transit)


def sun_angles(
    times,
    lat,
    lon,
    altitude=0.0,
    pressure=PRESSURE,
    temperature=TEMPERATURE,
    atmos_refract=ATMOS_REFRACT,
    depression=SUNRISE_DEPRESSION,
    delta_t=DELTA_T,
):
    """
    Full solar geometry for a PV simulation on a uniformly spaced time
    grid: solar position at timestep midpoints (recalculated at the
    midpoint of the sunlit portion for timesteps containing sunrise or
    sunset) and the risen fraction of every timestep.

    Parameters
    ----------
    times : (T,) datetime64 array or DatetimeIndex (UTC)
        Uniformly spaced timestep start labels.
    lat, lon : float or (S,) arrays
        Site coordinates in degrees.

    Returns
    -------
    dict with `apparent_elevation`, `apparent_zenith`, `azimuth`
    (degrees) and `risen_fraction`, all (T, S); plus `sunrise` and
    `sunset` as (D, S) datetime64[ns] and the corresponding `days`.

    """
    unixtime = _to_unixtime(times)
    if len(unixtime) < 2:
        raise ValueError("times must contain at least two timesteps")
    steps = np.diff(unixtime)
    step = steps[0]
    if not np.allclose(steps, step):
        raise ValueError("times must be uniformly spaced")
    lat, lon = _sites(lat, lon)
    n_site = len(lat)

    # 1. Sunrise/sunset for all days touched by the grid, padded by one
    # day on each side so intervals spilling across UTC midnight (e.g.
    # near the dateline) are seen by their neighbouring steps
    day_first = int(np.floor(unixtime[0] / _SECONDS_PER_DAY)) - 1
    day_last = int(np.floor(unixtime[-1] / _SECONDS_PER_DAY)) + 1
    days = np.arange(day_first, day_last + 1).astype("datetime64[D]")
    rise, set_, _ = _rise_set_transit_unix(days, lat, lon, depression, delta_t)

    # 2. Risen fraction: overlap of each timestep with the sunlit
    # intervals of its own and the adjacent days
    t0 = unixtime[:, None]
    t1 = t0 + step
    day_index = (np.floor(unixtime / _SECONDS_PER_DAY)).astype(int) - day_first
    overlap = np.zeros((len(unixtime), n_site))
    best_overlap = np.zeros((len(unixtime), n_site))
    best_lo = np.broadcast_to(t0, overlap.shape).copy()
    best_hi = np.broadcast_to(t1, overlap.shape).copy()
    for k in (-1, 0, 1):
        r = rise[day_index + k, :]
        s = set_[day_index + k, :]
        lo = np.maximum(t0, r)
        hi = np.minimum(t1, s)
        with np.errstate(invalid="ignore"):
            ov = np.nan_to_num(np.clip(hi - lo, 0.0, None))
        better = ov > best_overlap
        best_lo = np.where(better, lo, best_lo)
        best_hi = np.where(better, hi, best_hi)
        best_overlap = np.maximum(best_overlap, ov)
        overlap += ov
    risen_events = overlap / step

    # 3. Solar position at regular midpoints; time terms on a grid
    # extended by one step so partial-step midpoints never extrapolate
    mids = unixtime + step / 2
    grid = np.concatenate([[mids[0] - step], mids, [mids[-1] + step]])
    tt = time_terms(grid, delta_t=delta_t)
    site_kwargs = {
        "altitude": altitude,
        "pressure": pressure,
        "temperature": temperature,
        "atmos_refract": atmos_refract,
    }
    pos = topocentric_position(
        tt["v"][1:-1, None],
        tt["alpha"][1:-1, None],
        tt["delta"][1:-1, None],
        tt["xi"][1:-1, None],
        lat,
        lon,
        **site_kwargs,
    )
    elevation = pos["apparent_elevation"]
    azimuth = pos["azimuth"]

    # 4. Recalculate angles at the midpoint of the sunlit portion of
    # partial (sunrise/sunset) steps. The time terms vary slowly and
    # smoothly, so linear interpolation from the step grid is accurate
    # to well below the physical tolerances (v is near-linear in time;
    # alpha and delta drift ~1 deg/day)
    partial = (risen_events > 0.0) & (risen_events < 1.0)
    if partial.any():
        idx_time, idx_site = np.nonzero(partial)
        mid_partial = (best_lo[partial] + best_hi[partial]) / 2
        v_unwrapped = np.unwrap(tt["v"], period=360.0)
        alpha_unwrapped = np.unwrap(tt["alpha"], period=360.0)
        altitude_sites = np.broadcast_to(np.asarray(altitude, dtype=float), (n_site,))
        pos_partial = topocentric_position(
            np.interp(mid_partial, grid, v_unwrapped) % 360.0,
            np.interp(mid_partial, grid, alpha_unwrapped) % 360.0,
            np.interp(mid_partial, grid, tt["delta"]),
            np.interp(mid_partial, grid, tt["xi"]),
            lat[idx_site],
            lon[idx_site],
            altitude=altitude_sites[idx_site],
            pressure=pressure,
            temperature=temperature,
            atmos_refract=atmos_refract,
        )
        elevation[partial] = pos_partial["apparent_elevation"]
        azimuth[partial] = pos_partial["azimuth"]

    # 5. Final risen fraction: where no sunlit interval touches a step
    # (polar day/night have no sunrise/sunset events), fall back to the
    # sun's position at the step midpoint; and as in the reference
    # implementation, a sun whose centre stays just below the horizon
    # counts as not risen
    risen_fraction = np.where(
        overlap > 0.0, risen_events, (elevation > 0.0).astype(float)
    )
    risen_fraction[elevation <= 0.0] = 0.0

    return {
        "apparent_elevation": elevation,
        "apparent_zenith": 90.0 - elevation,
        "azimuth": azimuth,
        "risen_fraction": risen_fraction,
        "sunrise": _to_datetime64(rise),
        "sunset": _to_datetime64(set_),
        "days": days,
    }
