"""
User-facing API built on the vectorized `gsee.core`.

- `sun_angles_frame()`: single-site solar angles pluggable into the
  existing pandas pipeline via `run_model(angles=...)`.
- `run_sites()` / `run_grid()`: multi-site PV simulation over
  `(time, site)` / `(time, lat, lon)` xarray Datasets, with site
  chunking for memory control and optional process-based parallelism.

"""

from collections import deque
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
import xarray as xr

from gsee.core import inverter, irradiance, panel, solarposition

#: Default cap on elements per (time, site) chunk array (~64 MB float64)
_DEFAULT_CHUNK_ELEMENTS = 8_000_000

_RAW_DATA_VARIABLES = ("direct", "diffuse", "module_temperature", "relative_efficiency")


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
    losses. Semantics replicate `gsee.pv.run_model`, except that NaN
    inputs yield NaN output (run_model silently yields 0). Top-level so
    it is picklable for process-based parallelism.

    Solar positions are always computed in float64 (SPA needs the
    precision); with a float32 payload, everything downstream of the
    angles runs and returns in float32.

    """
    dtype = np.dtype(payload["dtype"])
    angles = solarposition.sun_angles(payload["times"], payload["lat"], payload["lon"])
    if dtype != np.float64:
        angles = {
            key: (
                value.astype(dtype)
                if getattr(value, "dtype", None) == np.float64
                else value
            )
            for key, value in angles.items()
        }
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

    # NaN inputs must not masquerade as valid output: the irradiance
    # step maps NaN to 0 internally (as run_model does), so mask here
    nan_input = (
        np.isnan(payload["direct"]) | np.isnan(payload["diffuse"]) | np.isnan(tamb)
    )
    return {
        name: np.where(nan_input, np.nan, values).astype(dtype, copy=False)
        for name, values in result.items()
    }


def _iter_chunk_results(payloads, workers):
    """
    Run chunk payloads sequentially (workers=1) or on a process pool,
    keeping at most 2*workers chunks in flight so that lazily loaded
    payloads do not all materialize in memory at once. Yields results
    in submission order.

    """
    if workers <= 1:
        for payload in payloads:
            yield _compute_chunk(payload)
        return
    with ProcessPoolExecutor(max_workers=workers) as executor:
        pending = deque()
        for payload in payloads:
            pending.append(executor.submit(_compute_chunk, payload))
            while len(pending) >= 2 * workers:
                yield pending.popleft().result()
        while pending:
            yield pending.popleft().result()


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
    dtype=None,
    **panel_kwargs,
):
    """
    Run the PV model for many sites at once.

    Physically equivalent to per-site `gsee.pv.run_model` but computed
    on `(time, site)` arrays: the time-dependent solar position terms
    are shared across sites, so per-site cost is ~20x lower than the
    single-site path.

    Memory behaviour: input data is loaded one site chunk at a time —
    pass a lazily loaded Dataset (e.g. from
    `xr.open_dataset(..., chunks=...)` or an open zarr store) to
    stream inputs from disk without materializing them all at once.
    Sites without any finite irradiance data (e.g. ocean cells in
    gridded climate data) are skipped entirely and returned as NaN;
    timesteps with NaN inputs return NaN (not 0).

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
        sequentially in-process. At most 2*workers chunks are in
        flight at a time. Note process startup imports gsee in each
        worker, so parallelism pays off for large site counts.
    dtype : str or numpy dtype, optional
        float64 (default) or float32. With float32, inputs and
        everything downstream of the solar position run in single
        precision, halving memory; solar positions themselves are
        always computed in float64. (The single-diode panel model
        computes in float64 internally regardless.)
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
    dtype = np.dtype(np.float64 if dtype is None else dtype)
    if dtype.kind != "f" or dtype.itemsize not in (4, 8):
        raise ValueError("dtype must be float32 or float64")

    lat = np.asarray(data["lat"].to_numpy(), dtype=float)
    lon = np.asarray(data["lon"].to_numpy(), dtype=float)
    times = data["time"].to_index()
    n_time, n_site = len(times), len(lat)

    # Kept as DataArrays: chunks load their slice on demand, so lazily
    # backed inputs (dask/zarr) are streamed rather than materialized
    ghi = data["global_horizontal"].transpose("time", "site")
    diffuse_fraction = data["diffuse_fraction"].transpose("time", "site")
    temperature = (
        data["temperature"].transpose("time", "site") if "temperature" in data else None
    )

    # Sites with no finite irradiance data at all (e.g. ocean cells in
    # gridded climate data) are not computed and stay NaN in the output
    finite = np.isfinite(ghi).any("time") & np.isfinite(diffuse_fraction).any("time")
    valid_sites = np.nonzero(finite.to_numpy())[0]

    tilt = np.radians(_per_site(tilt, lat, "tilt")).astype(dtype)
    azimuth = np.radians(_per_site(azim, lat, "azim")).astype(dtype)
    capacity = _per_site(capacity, lat, "capacity").astype(dtype)
    if inverter_capacity is None:
        inverter_capacity = capacity
    else:
        inverter_capacity = _per_site(
            inverter_capacity, lat, "inverter_capacity"
        ).astype(dtype)
    albedo = _per_site(albedo, lat, "albedo").astype(dtype)

    if chunk_size is None:
        chunk_size = max(1, _DEFAULT_CHUNK_ELEMENTS // max(n_time, 1))
    selections = [
        valid_sites[start : start + chunk_size]
        for start in range(0, len(valid_sites), chunk_size)
    ]

    def _payloads():
        for sel in selections:
            ghi_chunk = ghi.isel(site=sel).to_numpy().astype(dtype, copy=False)
            fraction_chunk = (
                diffuse_fraction.isel(site=sel).to_numpy().astype(dtype, copy=False)
            )
            if temperature is not None:
                tamb_chunk = (
                    temperature.isel(site=sel).to_numpy().astype(dtype, copy=False)
                )
            else:
                tamb_chunk = np.full((n_time, len(sel)), panel.R_TAMB, dtype=dtype)
            yield {
                "times": times.values,
                "lat": lat[sel],
                "lon": lon[sel],
                "direct": ghi_chunk * (1 - fraction_chunk),
                "diffuse": ghi_chunk * fraction_chunk,
                "tamb": tamb_chunk,
                "tilt": tilt[sel],
                "azimuth": azimuth[sel],
                "capacity": capacity[sel],
                "inverter_capacity": inverter_capacity[sel],
                "albedo": albedo[sel],
                "tracking": tracking,
                "technology": technology,
                "module_params": module_params,
                "use_inverter": use_inverter,
                "system_loss": system_loss,
                "include_raw_data": include_raw_data,
                "panel_kwargs": panel_kwargs,
                "dtype": dtype.str,
            }

    names = ["pv"] + (list(_RAW_DATA_VARIABLES) if include_raw_data else [])
    outputs = {name: np.full((n_time, n_site), np.nan, dtype=dtype) for name in names}
    effective_workers = workers if len(selections) > 1 else 1
    for sel, chunk in zip(
        selections, _iter_chunk_results(_payloads(), effective_workers)
    ):
        for name, values in chunk.items():
            outputs[name][:, sel] = values

    result = xr.Dataset(coords=data.coords)
    for name in names:
        result[name] = (("time", "site"), outputs[name])
    result["pv"].attrs["unit"] = "W"
    return result


def run_grid(data, *args, **kwargs):
    """
    Run the PV model over a regular lat/lon grid: `data` has dimensions
    `(time, lat, lon)`; the grid is stacked to a flat site axis, run
    through `run_sites` (same parameters), and unstacked again.

    Cells without any finite irradiance data (e.g. ocean cells in
    gridded climate data) are skipped and returned as NaN, so masked
    global grids only pay for their land cells.

    Returns an xarray.Dataset with `pv` over (time, lat, lon).

    """
    stacked = data.stack(site=("lat", "lon"))
    result = run_sites(stacked, *args, **kwargs)
    return result.unstack("site").transpose("time", "lat", "lon")
