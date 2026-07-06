"""
User-facing API built on the vectorized `gsee.core`.

- `sun_angles_frame()`: single-site solar angles pluggable into the
  existing pandas pipeline via `run_model(angles=...)`.
- `run_sites()` / `run_grid()`: multi-site PV simulation over
  `(time, site)` / `(time, lat, lon)` xarray Datasets, with site
  chunking for memory control and optional process-based parallelism.

"""

from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
import xarray as xr

from gsee.core import inverter, irradiance, panel, solarposition

#: Default cap on elements per (time, site) chunk array (~64 MB float64)
_DEFAULT_CHUNK_ELEMENTS = 8_000_000


def sun_angles_frame(datetime_index, coords, **kwargs):
    """
    Solar angles for a single site as a DataFrame compatible with
    `trigon.sun_angles()` output: radian columns `sun_alt`,
    `sun_zenith`, `sun_azimuth` plus `risen_fraction` (as consumed by
    `aperture_irradiance`), degree columns `apparent_elevation` and
    `azimuth`, and `sunrise`/`sunset` timestamps placed in the timestep
    they occur in.

    Results are physically equivalent to `trigon.sun_angles()` but not
    bit-identical: sunrise/sunset come from the vectorized hour-angle
    method rather than iterative SPA (see gsee.core.solarposition).

    Parameters
    ----------
    datetime_index : pandas DatetimeIndex
        Uniformly spaced, tz-aware in UTC.
    coords : (float, float)
        (lat, lon) tuple.
    kwargs : passed on to `gsee.core.solarposition.sun_angles`

    """
    if str(datetime_index.tz) != "UTC":
        raise ValueError("Input data must be in UTC timezone.")

    lat, lon = coords
    result = solarposition.sun_angles(datetime_index, lat, lon, **kwargs)

    elevation = result["apparent_elevation"][:, 0]
    azimuth = result["azimuth"][:, 0]
    frame = pd.DataFrame(
        {
            "apparent_elevation": elevation,
            "azimuth": azimuth,
            "risen_fraction": result["risen_fraction"][:, 0],
            "sun_alt": np.radians(elevation),
            "sun_zenith": np.radians(result["apparent_zenith"][:, 0]),
            "sun_azimuth": np.radians(azimuth),
        },
        index=datetime_index,
    )

    step = datetime_index[1] - datetime_index[0]
    for col, events in (("sunrise", result["sunrise"]), ("sunset", result["sunset"])):
        frame[col] = pd.Series(pd.NaT, index=datetime_index).dt.tz_localize("UTC")
        times = pd.to_datetime(events[:, 0]).tz_localize("UTC").dropna()
        floored = times.floor(step)
        in_range = floored.isin(datetime_index)
        frame.loc[floored[in_range], col] = times[in_range]

    return frame


def _per_site(value, lat, name):
    """Resolve a scalar, per-site array, or callable(lat) to (S,) floats."""
    if callable(value):
        value = np.array([float(value(site_lat)) for site_lat in lat])
    value = np.asarray(value, dtype=float)
    if value.ndim > 0 and value.shape != lat.shape:
        raise ValueError(
            "{} must be a scalar, a callable, or match the number of sites".format(name)
        )
    return np.broadcast_to(value, lat.shape)


def _compute_chunk(payload):
    """
    Full PV pipeline for one chunk of sites: solar angles, in-plane
    irradiance, panel DC power (clipped to capacity), inverter, system
    losses. Semantics replicate `gsee.pv.run_model`. Top-level so it is
    picklable for process-based parallelism.

    """
    angles = solarposition.sun_angles(payload["times"], payload["lat"], payload["lon"])
    plane = irradiance.aperture_irradiance(
        payload["direct"],
        payload["diffuse"],
        angles,
        payload["lat"],
        tilt=payload["tilt"],
        azimuth=payload["azimuth"],
        tracking=payload["tracking"],
        albedo=payload["albedo"],
    )
    total = plane["direct"] + plane["diffuse"]
    tamb = payload["tamb"]
    panel_args = (payload["technology"], payload["module_params"])
    panel_kwargs = payload["panel_kwargs"]

    dc_out = np.clip(
        panel.panel_power(
            total, tamb, payload["capacity"], *panel_args, **panel_kwargs
        ),
        None,
        payload["capacity"],
    )
    if payload["use_inverter"]:
        ac_out = np.clip(
            inverter.ac_output(dc_out, payload["inverter_capacity"]), 0.0, None
        )
    else:
        ac_out = dc_out
    result = {"pv": ac_out * (1 - payload["system_loss"])}

    if payload["include_raw_data"]:
        result["direct"] = plane["direct"]
        result["diffuse"] = plane["diffuse"]
        result["module_temperature"] = np.broadcast_to(
            panel.module_temperature(total, tamb, *panel_args, **panel_kwargs),
            total.shape,
        )
        result["relative_efficiency"] = np.broadcast_to(
            panel.relative_efficiency(total, tamb, *panel_args, **panel_kwargs),
            total.shape,
        )
    return result


def run_sites(
    data,
    tilt,
    azim,
    tracking,
    capacity,
    inverter_capacity=None,
    use_inverter=True,
    technology="csi",
    system_loss=0.10,
    albedo=0.3,
    module_params=None,
    include_raw_data=False,
    chunk_size=None,
    workers=1,
    **panel_kwargs,
):
    """
    Run the PV model for many sites at once.

    Physically equivalent to per-site `gsee.pv.run_model` but computed
    on `(time, site)` arrays: the time-dependent solar position terms
    are shared across sites, so per-site cost is ~20x lower than the
    single-site path.

    Parameters
    ----------
    data : xarray.Dataset
        Dimensions `time` (uniformly spaced; interpreted as UTC) and
        `site`, with coordinates `lat(site)` and `lon(site)` in
        degrees. Variables: `global_horizontal` (W/m2),
        `diffuse_fraction`, and optionally `temperature` (degC,
        assumed 20 if absent).
    tilt, azim : float, (site,) array, or callable
        Panel tilt and azimuth in DEGREES (as in `run_model`; azim 180
        = towards equator). A callable is evaluated per site latitude
        (e.g. `gsee.pv.optimal_tilt`).
    tracking : int
        0 (fixed), 1 (1-axis) or 2 (2-axis); same for all sites.
    capacity : float or (site,) array
        Installed DC panel capacity in W.
    inverter_capacity : float or (site,) array, optional
        AC inverter capacity in W (defaults to `capacity`).
    use_inverter : bool, optional
        Model the PVWatts inverter (default True).
    technology : str, optional
        'csi' (default), 'csi-new', 'cis', 'cdte', 'cec-csi-median',
        or 'singlediode' (requires `module_params`); same for all
        sites.
    system_loss : float, optional
        Additional loss fraction (default 0.10).
    albedo : float or (site,) array, optional
        Ground reflectance (default 0.3).
    include_raw_data : bool, optional
        Also return in-plane `direct`/`diffuse` irradiance,
        `module_temperature` and `relative_efficiency` variables.
    chunk_size : int, optional
        Sites per chunk; defaults to a memory-motivated value
        (~8e6 array elements per chunk).
    workers : int, optional
        Number of worker processes; 1 (default) runs chunks
        sequentially in-process. Note process startup imports gsee in
        each worker, so parallelism pays off for large site counts.
    panel_kwargs : passed on to the panel model (e.g. `c_temp_amb`,
        `c_temp_irrad` for Huld; `windspeed`, `temperature_params` for
        single-diode).

    Returns
    -------
    xarray.Dataset with `pv` (W) over (time, site), plus raw-data
    variables if requested.

    """
    if (system_loss < 0) or (system_loss > 1):
        raise ValueError("system_loss must be >=0 and <=1")
    for required in ("global_horizontal", "diffuse_fraction"):
        if required not in data:
            raise ValueError("data must contain a '{}' variable".format(required))
    for coord in ("lat", "lon"):
        if coord not in data.coords:
            raise ValueError("data must have a '{}' coordinate on 'site'".format(coord))

    lat = np.asarray(data["lat"].to_numpy(), dtype=float)
    lon = np.asarray(data["lon"].to_numpy(), dtype=float)
    times = data["time"].to_index()
    n_time, n_site = len(times), len(lat)

    ghi = data["global_horizontal"].transpose("time", "site").to_numpy()
    diffuse_fraction = data["diffuse_fraction"].transpose("time", "site").to_numpy()
    direct = ghi * (1 - diffuse_fraction)
    diffuse = ghi * diffuse_fraction
    if "temperature" in data:
        tamb = data["temperature"].transpose("time", "site").to_numpy()
    else:
        tamb = np.full((n_time, n_site), panel.R_TAMB)

    tilt = np.radians(_per_site(tilt, lat, "tilt"))
    azimuth = np.radians(_per_site(azim, lat, "azim"))
    capacity = _per_site(capacity, lat, "capacity")
    if inverter_capacity is None:
        inverter_capacity = capacity
    else:
        inverter_capacity = _per_site(inverter_capacity, lat, "inverter_capacity")
    albedo = _per_site(albedo, lat, "albedo")

    if chunk_size is None:
        chunk_size = max(1, _DEFAULT_CHUNK_ELEMENTS // max(n_time, 1))
    starts = range(0, n_site, chunk_size)
    payloads = [
        {
            "times": times.values,
            "lat": lat[s : s + chunk_size],
            "lon": lon[s : s + chunk_size],
            "direct": direct[:, s : s + chunk_size],
            "diffuse": diffuse[:, s : s + chunk_size],
            "tamb": tamb[:, s : s + chunk_size],
            "tilt": tilt[s : s + chunk_size],
            "azimuth": azimuth[s : s + chunk_size],
            "capacity": capacity[s : s + chunk_size],
            "inverter_capacity": inverter_capacity[s : s + chunk_size],
            "albedo": albedo[s : s + chunk_size],
            "tracking": tracking,
            "technology": technology,
            "module_params": module_params,
            "use_inverter": use_inverter,
            "system_loss": system_loss,
            "include_raw_data": include_raw_data,
            "panel_kwargs": panel_kwargs,
        }
        for s in starts
    ]

    if workers > 1 and len(payloads) > 1:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            chunk_results = list(executor.map(_compute_chunk, payloads))
    else:
        chunk_results = [_compute_chunk(payload) for payload in payloads]

    result = xr.Dataset(coords=data.coords)
    for name in chunk_results[0]:
        result[name] = (
            ("time", "site"),
            np.concatenate([chunk[name] for chunk in chunk_results], axis=1),
        )
    result["pv"].attrs["unit"] = "W"
    return result


def run_grid(data, *args, **kwargs):
    """
    Run the PV model over a regular lat/lon grid: `data` has dimensions
    `(time, lat, lon)`; the grid is stacked to a flat site axis, run
    through `run_sites` (same parameters), and unstacked again.

    Returns an xarray.Dataset with `pv` over (time, lat, lon).

    """
    stacked = data.stack(site=("lat", "lon"))
    result = run_sites(stacked, *args, **kwargs)
    return result.unstack("site").transpose("time", "lat", "lon")
