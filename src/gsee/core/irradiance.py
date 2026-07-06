"""
Plane-of-array irradiance, vectorized over (time, site)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The same formulas as `gsee.trigon.aperture_irradiance` (DNI from
horizontal direct irradiance and risen fraction, incidence geometry
for fixed and 1-/2-axis tracking, isotropic diffuse transposition with
ground reflection), as pure numpy over `(T, S)` arrays with per-site
parameters as `(S,)` arrays.

The southern-hemisphere azimuth correction is applied here per site
(vectorized), so mixed-hemisphere site sets are handled correctly.

"""

import numpy as np


def _incidence_fixed(sun_alt, tilt, azimuth, sun_azimuth):
    """Incidence angle for a fixed panel; all angles in radians."""
    return np.arccos(
        np.sin(sun_alt) * np.cos(tilt)
        + np.cos(sun_alt) * np.sin(tilt) * np.cos(azimuth - sun_azimuth)
    )


def _incidence_single_tracking(sun_alt, tilt, azimuth, sun_azimuth):
    """
    Incidence angle for a 1-axis tracking panel with the tilt axis at
    `tilt` from horizontal, oriented at `azimuth`; radians. `tilt` may
    be an (S,) array mixing horizontal and tilted axes.

    """
    horizontal = np.arccos(
        np.sqrt(1 - np.cos(sun_alt) ** 2 * np.cos(sun_azimuth - azimuth) ** 2)
    )
    tilted = np.arccos(
        np.sqrt(
            1
            - (
                np.cos(sun_alt + tilt)
                - np.cos(tilt) * np.cos(sun_alt) * (1 - np.cos(sun_azimuth - azimuth))
            )
            ** 2
        )
    )
    return np.where(tilt == 0, horizontal, tilted)


def _tilt_single_tracking(sun_alt, tilt, azimuth, sun_azimuth):
    """
    Panel tilt angle for a 1-axis tracking panel; radians. `tilt` (the
    tilt of the tracking axis) may be an (S,) array.

    """
    horizontal = np.arctan(np.sin(sun_azimuth - azimuth) / np.tan(sun_alt))
    tilted = np.arctan(
        (np.cos(sun_alt) * np.sin(sun_azimuth - azimuth))
        / (
            np.sin(sun_alt - tilt)
            + np.sin(tilt) * np.cos(sun_alt) * (1 - np.cos(sun_azimuth - azimuth))
        )
    )
    return np.where(tilt == 0, horizontal, tilted)


def _fill_nan(values):
    """NaN to 0, like pandas fillna(0) (infinities pass through)."""
    return np.where(np.isnan(values), 0.0, values)


def aperture_irradiance(
    direct, diffuse, angles, lat, tilt=0.0, azimuth=0.0, tracking=0, albedo=0.3
):
    """
    In-plane direct and diffuse irradiance.

    Parameters
    ----------
    direct, diffuse : (T, S) arrays
        Direct and diffuse horizontal irradiance (W/m2).
    angles : dict
        Result of `gsee.core.solarposition.sun_angles` for the same
        times and sites.
    lat : (S,) array
        Site latitudes in degrees (used for the southern-hemisphere
        azimuth correction).
    tilt, azimuth : scalar or (S,) arrays
        Panel (or tracking-axis) tilt and azimuth in RADIANS; azimuth 0
        points towards the pole, pi towards the equator (as in
        `trigon.aperture_irradiance`).
    tracking : int
        0 (fixed), 1 (1-axis) or 2 (2-axis).
    albedo : scalar or (S,) array
        Ground reflectance.

    Returns
    -------
    dict with 'direct' and 'diffuse' (T, S) arrays of in-plane
    irradiance (W/m2).

    """
    tilt = np.atleast_1d(np.asarray(tilt, dtype=float))
    azimuth = np.atleast_1d(np.asarray(azimuth, dtype=float))
    lat = np.atleast_1d(np.asarray(lat, dtype=float))

    # On the southern hemisphere, flip so that pi points north
    azimuth = np.where(lat < 0, azimuth + np.pi, azimuth)

    sun_alt = np.radians(angles["apparent_elevation"])
    sun_zenith = np.radians(angles["apparent_zenith"])
    sun_azimuth = np.radians(angles["azimuth"])

    with np.errstate(invalid="ignore", divide="ignore"):
        dni = (direct * angles["risen_fraction"]) / np.cos(sun_zenith)

        if tracking == 0:
            incidence = _incidence_fixed(sun_alt, tilt, azimuth, sun_azimuth)
            panel_tilt = tilt
        elif tracking == 1:
            incidence = _incidence_single_tracking(sun_alt, tilt, azimuth, sun_azimuth)
            panel_tilt = _tilt_single_tracking(sun_alt, tilt, azimuth, sun_azimuth)
        elif tracking == 2:
            # 2-axis tracking means incidence angle is zero
            incidence = 0.0
            panel_tilt = sun_zenith
        else:
            raise ValueError("Invalid setting for tracking: {}".format(tracking))

        plane_direct = np.clip(_fill_nan(dni * np.cos(incidence)), 0.0, None)
        plane_diffuse = _fill_nan(
            diffuse * ((1 + np.cos(panel_tilt)) / 2)
            + albedo * (direct + diffuse) * ((1 - np.cos(panel_tilt)) / 2)
        )

    return {"direct": plane_direct, "diffuse": plane_diffuse}
