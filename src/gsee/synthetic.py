"""
Synthetic weather data
~~~~~~~~~~~~~~~~~~~~~~

Deterministic synthetic irradiance and temperature series for testing, benchmarking and examples.

"""

import numpy as np
import pandas as pd


def _smooth(values, window, rng_pad=0.0):
    """Centred moving average with edge padding."""
    kernel = np.ones(window) / window
    padded = np.concatenate(
        [np.full(window, values[0] + rng_pad), values, np.full(window, values[-1])]
    )
    return np.convolve(padded, kernel, mode="same")[window:-window]


def _clearsky_ghi(index, lat, lon, step_hours):
    """
    Clear-sky global horizontal irradiance (W/m2) via the Haurwitz model,
    evaluated at the midpoint of each timestep. `index` must be a
    tz-aware UTC DatetimeIndex labelling timestep starts.

    """
    n = index.dayofyear.to_numpy()
    hour_utc = index.hour.to_numpy() + index.minute.to_numpy() / 60.0 + step_hours / 2.0

    # Spencer (1971) declination and equation of time
    b = 2 * np.pi * (n - 1) / 365.0
    declination = (
        0.006918
        - 0.399912 * np.cos(b)
        + 0.070257 * np.sin(b)
        - 0.006758 * np.cos(2 * b)
        + 0.000907 * np.sin(2 * b)
        - 0.002697 * np.cos(3 * b)
        + 0.00148 * np.sin(3 * b)
    )
    eot_minutes = 229.18 * (
        0.000075
        + 0.001868 * np.cos(b)
        - 0.032077 * np.sin(b)
        - 0.014615 * np.cos(2 * b)
        - 0.04089 * np.sin(2 * b)
    )

    solar_hour = hour_utc + lon / 15.0 + eot_minutes / 60.0
    hour_angle = np.radians(15.0 * (solar_hour - 12.0))
    phi = np.radians(lat)
    cos_zenith = np.sin(phi) * np.sin(declination) + np.cos(phi) * np.cos(
        declination
    ) * np.cos(hour_angle)
    cos_zenith = np.clip(cos_zenith, 0.0, 1.0)

    ghi = 1098.0 * cos_zenith * np.exp(-0.059 / np.maximum(cos_zenith, 1e-6))
    return np.where(cos_zenith > 0, ghi, 0.0), solar_hour


def synthetic_weather(
    lat, lon, year=2019, freq="1h", seed=42, include_temperature=True
):
    """
    Returns a DataFrame with 'global_horizontal' (W/m2),
    'diffuse_fraction', and optionally 'temperature' (deg C) columns,
    indexed by a tz-aware UTC DatetimeIndex covering the given year.
    Fully deterministic for a given set of arguments.

    """
    index = pd.date_range(
        "{}-01-01 00:00".format(year),
        "{}-12-31 23:59".format(year),
        freq=freq,
        tz="UTC",
    )
    step_hours = (index[1] - index[0]) / pd.Timedelta("1h")
    steps_per_day = int(round(24 / step_hours))
    n_days = len(index) // steps_per_day

    rng = np.random.default_rng(seed)

    ghi_clear, solar_hour = _clearsky_ghi(index, lat, lon, step_hours)

    # Daily clearness index with hourly variation on top
    kt_day = 0.25 + 0.75 * rng.beta(3.0, 1.8, size=n_days)
    kt = np.repeat(kt_day, steps_per_day)
    kt = kt + 0.12 * _smooth(rng.normal(0.0, 1.0, size=len(index)), 3)
    kt = np.clip(kt, 0.03, 1.0)

    global_horizontal = ghi_clear * kt

    # Smooth Erbs-like clearness-to-diffuse-fraction mapping
    diffuse_fraction = 0.165 + (1 - 0.165) / (1 + np.exp(10.0 * (kt - 0.45)))
    diffuse_fraction = np.clip(diffuse_fraction, 0.05, 1.0)

    data = {
        "global_horizontal": global_horizontal,
        "diffuse_fraction": diffuse_fraction,
    }

    if include_temperature:
        doy = index.dayofyear.to_numpy()
        # Seasonal cycle peaking ~19 July in the north, ~mid-January in the south
        seasonal_phase = -np.cos(2 * np.pi * (doy - 19) / 365.25)
        seasonal = seasonal_phase if lat >= 0 else -seasonal_phase
        zonal_mean = 25.0 - 30.0 * abs(lat) / 90.0
        seasonal_amplitude = 2.0 + 18.0 * abs(lat) / 90.0
        diurnal = -4.0 * np.cos(2 * np.pi * (solar_hour - 14.0) / 24.0)
        noise = 2.0 * _smooth(rng.normal(0.0, 1.0, size=len(index)), 6)
        data["temperature"] = (
            zonal_mean + seasonal_amplitude * seasonal + diurnal + noise
        )

    return pd.DataFrame(data, index=index)
