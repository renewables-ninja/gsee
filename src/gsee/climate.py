"""
Climate data interface
~~~~~~~~~~~~~~~~~~~~~~

Run the PV model directly on gridded climate data at annual, seasonal,
monthly, daily or hourly resolution. This is a conversion of the v0.3
`climatedata_interface` as a thin layer on the vectorized core.

"""

import warnings
from calendar import monthrange

import numpy as np
import pandas as pd
import xarray as xr

from gsee import api
from gsee.core import diffuse, solarposition, synthesis

FREQUENCIES = ("A", "S", "M", "D", "H")

#: Months covered by one input timestep per frequency
_MONTHS_PER_STEP = {"A": 12, "S": 3, "M": 1}

_SOLAR_CONSTANT = 1367.0  # W/m2


def builtin_pdfs():
    """
    The built-in MERRA-2-derived daily-irradiance PDFs (3x3 degrees,
    land cells, 2011-2015) as an xarray Dataset, loaded from the
    optional `gsee-climate-data` companion package.

    """
    try:
        import gsee_climate_data
    except ImportError:
        raise ImportError(
            "pdfs='builtin' requires the gsee-climate-data package; "
            "install it with: pip install gsee[climate]"
        ) from None
    arrays = gsee_climate_data.load()
    return xr.Dataset(
        {
            "xk": (("lat", "lon", "month", "bins"), arrays["xk"]),
            "pk": (("lat", "lon", "month", "bins"), arrays["pk"]),
        },
        coords={
            "lat": arrays["lat"],
            "lon": arrays["lon"],
            "month": arrays["month"],
        },
    )


def run_climate(
    data,
    tilt,
    azim,
    tracking,
    capacity,
    frequency="detect",
    pdfs=None,
    seed=None,
    timeformat=None,
    legacy_brl_predictors=False,
    **run_sites_kwargs,
):
    """
    Run the PV model on (coarse) climate data.

    Parameters
    ----------
    data : xarray.Dataset
        Either `(time, site)` with `lat(site)`/`lon(site)` coordinates
        (as for `api.run_sites`) or a regular grid `(time, lat, lon)`.
        Must contain `global_horizontal` (mean irradiance, W/m2); may
        contain `temperature` (degC) and, for hourly data,
        `diffuse_fraction`. Coarser-than-hourly diffuse fraction input
        is ignored (the BRL estimate is used), as in v0.3.
    tilt, azim, tracking, capacity :
        As for `api.run_sites` (tilt may be a callable of latitude).
    frequency : str, optional
        'A', 'S', 'M', 'D', 'H' (annual, seasonal, monthly, daily,
        hourly) or 'detect' (default): detect from the data.
    pdfs : xarray.Dataset, path, or 'builtin', optional
        Monthly probability density functions of daily irradiance with
        `month`, `lat` and `lon` dimensions plus one bin dimension (any
        order), and variables `xk` (value bins) and `pk`
        (probabilities). 'builtin' uses the MERRA-2-derived PDFs from
        the optional `gsee-climate-data` package
        (`pip install gsee[climate]`).
        If given (for 'A'/'S'/'M' data), each month is filled with days
        sampled from the nearest grid cell's PDF, scaled to preserve
        the input mean; if not, one representative day per month
        (mid-month) is simulated, or two equinox days for annual data.
    seed : int, optional
        Seed for the PDF day sampling.
    timeformat : str, optional
        Set to 'cmip5' to parse numeric CMIP-style time values
        ("%Y%m%d.%f" days).
    legacy_brl_predictors : bool, optional
        Passed to the BRL model (see `gsee.core.diffuse`).
    run_sites_kwargs : passed on to `api.run_sites` (e.g. `workers`,
        `dtype`, `technology`, `system_loss`).

    Returns
    -------
    xarray.Dataset with `pv` over the input time dimension(s), in Wh
    per hour for hourly input and Wh per day otherwise (as in v0.3).

    """
    if "lat" in data.dims and "lon" in data.dims:
        stacked = run_climate(
            data.stack(site=("lat", "lon")),
            tilt,
            azim,
            tracking,
            capacity,
            frequency=frequency,
            pdfs=pdfs,
            seed=seed,
            timeformat=timeformat,
            legacy_brl_predictors=legacy_brl_predictors,
            **run_sites_kwargs,
        )
        return stacked.unstack("site").transpose("time", "lat", "lon")

    if "global_horizontal" not in data:
        raise ValueError("data must contain a 'global_horizontal' variable")
    if timeformat == "cmip5":
        data = data.assign_coords(time=parse_cmip_time(data["time"].to_numpy()))
    frequency = detect_frequency(data, frequency)
    params = dict(
        tilt=tilt, azim=azim, tracking=tracking, capacity=capacity, **run_sites_kwargs
    )

    if frequency == "H":
        return _run_hourly_input(data, params, legacy_brl_predictors)
    return _run_coarse_input(data, frequency, pdfs, seed, params, legacy_brl_predictors)


def detect_frequency(data, frequency="detect"):
    """
    Detect the input data frequency ('A', 'S', 'M', 'D' or 'H') from
    the dataset's `frequency` attribute or its time coordinate;
    a manually given `frequency` is validated against the detected one
    (mismatch warns) and takes precedence.

    """
    detected = None
    attr = str(data.attrs.get("frequency", ""))[:4]
    by_attr = {"year": "A", "mon": "M", "day": "D", "hour": "H"}
    if attr:
        detected = by_attr.get(attr, attr[0].upper() if attr else None)
    else:
        try:
            inferred = pd.infer_freq(data["time"].to_index())
        except (TypeError, ValueError):
            inferred = None
        if inferred:
            detected = {"Y": "A", "A": "A", "Q": "S", "M": "M", "D": "D", "H": "H"}.get(
                inferred[0].upper()
            )
    if frequency == "detect":
        if detected not in FREQUENCIES:
            raise ValueError(
                "Could not detect data frequency; pass frequency= explicitly"
            )
        return detected
    if frequency not in FREQUENCIES:
        raise ValueError("frequency must be one of {}".format(FREQUENCIES))
    if detected is not None and detected != frequency:
        warnings.warn(
            "Given frequency '{}' does not match detected '{}'".format(
                frequency, detected
            )
        )
    return frequency


def parse_cmip_time(values):
    """Convert CMIP-style numeric time values ("%Y%m%d.%f" days) to datetimes."""
    numeric = np.asarray(values, dtype=float)
    dates = pd.to_datetime([str(int(value)) for value in numeric], format="%Y%m%d")
    hours = np.floor((numeric % 1) * 24)
    return dates + pd.to_timedelta(hours, unit="h")


def hourly_clearness_index(ghi, times, lat, lon):
    """
    Hourly clearness index: measured irradiance over extraterrestrial
    horizontal irradiance at the timestep midpoint (exact solar
    positions; the v0.3 Cython kernel used an approximate declination).
    NaN where the input irradiance is zero, negative or NaN.

    """
    lat, lon = solarposition._sites(lat, lon)
    unixtime = solarposition._to_unixtime(times)
    position = solarposition.solar_position(
        ((unixtime + 1800.0) * 1e9).astype("datetime64[ns]"), lat, lon
    )
    day_of_year = pd.DatetimeIndex(np.asarray(times)).dayofyear.to_numpy()
    t = 2 * np.pi * (day_of_year - 1) / 365.0
    eccentricity = (
        1.000110
        + 0.034221 * np.cos(t)
        + 0.001280 * np.sin(t)
        + 0.000719 * np.cos(2 * t)
        + 0.00077 * np.sin(2 * t)
    )
    extraterrestrial = (
        _SOLAR_CONSTANT
        * eccentricity[:, None]
        * np.sin(np.radians(position["apparent_elevation"]))
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        clearness = np.where(
            extraterrestrial > 0, np.clip(ghi / extraterrestrial, 0.0, 1.0), 0.0
        )
    return np.where(np.nan_to_num(ghi) > 0, clearness, np.nan)


def _run_hourly_block(times, ghi, tamb, diffuse_fraction, lat, lon, params, legacy):
    """
    kt -> BRL -> run_sites for one contiguous hourly block (whole days
    starting at midnight, as the BRL model requires). Returns the pv
    array (T, S) in W (== Wh per hourly step).

    """
    if diffuse_fraction is None:
        clearness = hourly_clearness_index(ghi, times, lat, lon)
        diffuse_fraction = diffuse.brl_diffuse_fraction(
            clearness, times, lat, lon, legacy_predictors=legacy
        )
        # The BRL estimate is NaN at night (clearness undefined); any
        # value works there since irradiance is zero, but NaN inputs
        # would (correctly) blank the output
        diffuse_fraction = np.where(
            np.isnan(diffuse_fraction) & ~np.isnan(ghi), 1.0, diffuse_fraction
        )

    variables = {
        "global_horizontal": (("time", "site"), ghi),
        "diffuse_fraction": (("time", "site"), diffuse_fraction),
    }
    if tamb is not None:
        variables["temperature"] = (("time", "site"), tamb)
    dataset = xr.Dataset(
        variables,
        coords={
            "time": pd.DatetimeIndex(times),
            "site": np.arange(ghi.shape[1]),
            "lat": ("site", lat),
            "lon": ("site", lon),
        },
    )
    return api.run_sites(dataset, **params)["pv"].to_numpy()


def _run_hourly_input(data, params, legacy):
    times = data["time"].to_index()
    lat = np.asarray(data["lat"].to_numpy(), dtype=float)
    lon = np.asarray(data["lon"].to_numpy(), dtype=float)
    if "diffuse_fraction" in data:
        result = api.run_sites(data, **params)
    else:
        ghi = data["global_horizontal"].transpose("time", "site").to_numpy()
        tamb = (
            data["temperature"].transpose("time", "site").to_numpy()
            if "temperature" in data
            else None
        )
        pv = _run_hourly_block(times.values, ghi, tamb, None, lat, lon, params, legacy)
        result = xr.Dataset(coords=data.coords)
        result["pv"] = (("time", "site"), pv)
    result["pv"].attrs["unit"] = "Wh"
    return result


def _representative_days(times, frequency):
    """
    One (day, input step) pair per simulated day: the input day itself
    for daily data, the mid-month day for monthly/seasonal data, and
    two near-equinox days (31 March, 30 September) for annual data,
    replicating the v0.3 choices.

    """
    step_index = []
    days = []
    for step, timestamp in enumerate(times):
        if frequency == "D":
            step_days = [timestamp.normalize()]
        elif frequency in ("M", "S"):
            mid = monthrange(timestamp.year, timestamp.month)[1] // 2
            step_days = [pd.Timestamp(timestamp.year, timestamp.month, mid)]
        else:  # A
            step_days = [
                pd.Timestamp(timestamp.year, 3, 31),
                pd.Timestamp(timestamp.year, 9, 30),
            ]
        step_index.extend([step] * len(step_days))
        days.extend(step_days)
    return np.asarray(step_index), pd.DatetimeIndex(days).values.astype("datetime64[D]")


def _sampled_days(times, frequency, ghi, lat, lon, pdfs, rng):
    """
    Days drawn from monthly PDFs: for each input step, every day of
    each month it covers is sampled from the nearest PDF grid cell and
    scaled per site so the step's mean irradiance is preserved.

    """
    nearest_lat = np.abs(pdfs["lat"].to_numpy()[:, None] - lat[None, :]).argmin(axis=0)
    nearest_lon = np.abs(pdfs["lon"].to_numpy()[:, None] - lon[None, :]).argmin(axis=0)
    # (month, site, bin)
    xk = (
        pdfs["xk"]
        .transpose("month", "lat", "lon", ...)
        .to_numpy()[:, nearest_lat, nearest_lon, :]
    )
    pk = (
        pdfs["pk"]
        .transpose("month", "lat", "lon", ...)
        .to_numpy()[:, nearest_lat, nearest_lon, :]
    )
    months_of_step = _MONTHS_PER_STEP[frequency]

    step_index = []
    days = []
    daily_ghi = []
    for step, timestamp in enumerate(times):
        year, month = timestamp.year, timestamp.month
        step_values = []
        for _ in range(months_of_step):
            n_days = monthrange(year, month)[1]
            step_values.append(
                synthesis.sample_from_pdfs(xk[month - 1], pk[month - 1], n_days, rng)
            )
            month += 1
            if month > 12:
                month, year = 1, year + 1
        step_values = np.concatenate(step_values, axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean_values = step_values.mean(axis=0)
            scale = np.where(mean_values > 0, ghi[step] / mean_values, 0.0)
        step_values = step_values * scale[None, :]
        step_days = pd.date_range(
            pd.Timestamp(timestamp.year, timestamp.month, 1),
            periods=len(step_values),
            freq="D",
        )
        step_index.extend([step] * len(step_days))
        days.extend(step_days)
        daily_ghi.append(step_values)
    return (
        np.asarray(step_index),
        pd.DatetimeIndex(days).values.astype("datetime64[D]"),
        np.concatenate(daily_ghi, axis=0),
    )


def _run_coarse_input(data, frequency, pdfs, seed, params, legacy):
    times = data["time"].to_index()
    lat = np.asarray(data["lat"].to_numpy(), dtype=float)
    lon = np.asarray(data["lon"].to_numpy(), dtype=float)
    n_site = len(lat)
    ghi = data["global_horizontal"].transpose("time", "site").to_numpy()
    tamb = (
        data["temperature"].transpose("time", "site").to_numpy()
        if "temperature" in data
        else None
    )

    if pdfs is None:
        step_index, days = _representative_days(times, frequency)
        daily_ghi = ghi[step_index]
    else:
        if frequency == "D":
            raise ValueError("PDF-based day sampling applies to 'A'/'S'/'M' data only")
        if isinstance(pdfs, str) and pdfs == "builtin":
            pdfs = builtin_pdfs()
        if not isinstance(pdfs, xr.Dataset):
            pdfs = xr.open_dataset(pdfs)
        rng = np.random.default_rng(seed)
        step_index, days, daily_ghi = _sampled_days(
            times, frequency, ghi, lat, lon, pdfs, rng
        )
    daily_tamb = tamb[step_index] if tamb is not None else None

    hourly_times, hourly_ghi = synthesis.diurnal_profile(daily_ghi, days, lat, lon)
    hourly_tamb = np.repeat(daily_tamb, 24, axis=0) if daily_tamb is not None else None

    # The solar core and the BRL model need uniformly spaced times, so
    # non-contiguous simulated days run block by block
    day_numbers = days.astype("datetime64[D]").astype(int)
    block_bounds = [0, *(np.nonzero(np.diff(day_numbers) != 1)[0] + 1), len(days)]
    pv_hourly = np.full((len(hourly_times), n_site), np.nan)
    for begin, end in zip(block_bounds[:-1], block_bounds[1:]):
        hours = slice(begin * 24, end * 24)
        pv_hourly[hours] = _run_hourly_block(
            hourly_times[hours],
            hourly_ghi[hours],
            hourly_tamb[hours] if hourly_tamb is not None else None,
            None,
            lat,
            lon,
            params,
            legacy,
        )

    daily_wh = pv_hourly.reshape(len(days), 24, n_site).sum(axis=1)
    sums = np.zeros((len(times), n_site))
    counts = np.zeros(len(times))
    np.add.at(sums, step_index, daily_wh)
    np.add.at(counts, step_index, 1)

    result = xr.Dataset(coords=data.coords)
    result["pv"] = (("time", "site"), sums / counts[:, None])
    result["pv"].attrs["unit"] = "Wh/day"
    return result
