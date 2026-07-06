"""
Reference case matrix.

The single source of truth used by both
the generation script and the
regression tests.

Each case is a `gsee.pv.run_model()` run on synthetic input.
The base configuration runs at every test site.
Variant configurations run at a subset of three sites, covering northern mid-latitude, southern hemisphere (azimuth correction) and polar conditions.

"""

import os

import pandas as pd

from gsee import synthetic

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

YEAR = 2019

# (lat, lon): chosen to cover polar day/night in both hemispheres,
# the equator, both mid-latitudes, and a near-dateline longitude
SITES = {
    "svalbard": (78.25, 15.5),
    "arctic_circle": (67.5, -21.0),
    "helsinki": (60.2, 25.0),
    "zurich": (47.36, 8.55),
    "kathmandu": (27.7, 85.3),
    "quito": (0.0, -78.5),
    "cape_town": (-33.9, 18.4),
    "otago": (-45.9, 170.5),
    "antarctica": (-75.0, 123.0),
}

CAPACITY = 1000.0

BASE_PARAMS = {
    "tilt": 30,
    "azim": 180,
    "tracking": 0,
    "capacity": CAPACITY,
    "technology": "csi",
}

# Variants run only at these sites
VARIANT_SITES = ["zurich", "cape_town", "svalbard"]

# Non-run_model keys: "freq" (input resolution), "drop_temperature"
VARIANTS = {
    "tracking1_horizontal": {"tracking": 1, "tilt": 0},
    "tracking1_tilted": {"tracking": 1, "tilt": 30},
    "tracking2": {"tracking": 2},
    "cdte": {"technology": "cdte"},
    "csi_new": {"technology": "csi-new"},
    "singlediode": {"technology": "cec-csi-median"},
    "no_temperature": {"drop_temperature": True},
    "no_inverter": {"use_inverter": False},
    "dc_ac_ratio": {"inverter_capacity": 800.0},
    "east_facing": {"azim": 90},
    "halfhourly": {"freq": "30min"},
    "legacy_solarposition": {"legacy_solarposition": True},
}


def build_cases():
    """Returns {case_id: case_dict} for all reference cases."""
    cases = {}
    for site in SITES:
        cases["{}-base".format(site)] = _case(site, {}, store_angles=True)
    for site in VARIANT_SITES:
        for variant, overrides in VARIANTS.items():
            cases["{}-{}".format(site, variant)] = _case(site, overrides)
    return cases


def _case(site, overrides, store_angles=False):
    overrides = dict(overrides)
    freq = overrides.pop("freq", "1h")
    drop_temperature = overrides.pop("drop_temperature", False)
    params = {**BASE_PARAMS, **overrides}
    lat, lon = SITES[site]
    return {
        "site": site,
        "lat": lat,
        "lon": lon,
        "freq": freq,
        "drop_temperature": drop_temperature,
        "params": params,
        "store_angles": store_angles,
    }


def make_input(case):
    """Deterministic model input for a case (seeded by site coordinates)."""
    seed = int(abs(case["lat"]) * 1000 + abs(case["lon"]) * 10)
    data = synthetic.synthetic_weather(
        case["lat"],
        case["lon"],
        year=YEAR,
        freq=case["freq"],
        seed=seed,
        include_temperature=not case["drop_temperature"],
    )
    return data


def input_path(case_id):
    return os.path.join(DATA_DIR, "{}.input.csv.xz".format(case_id))


def output_path(case_id):
    return os.path.join(DATA_DIR, "{}.output.csv.xz".format(case_id))


def angles_path(case_id):
    return os.path.join(DATA_DIR, "{}.angles.csv.xz".format(case_id))


def read_frame(path):
    df = pd.read_csv(
        path,
        index_col=0,
        parse_dates=True,
        compression="xz",
        float_precision="round_trip",
    )
    for col in ("sunrise", "sunset"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="ISO8601", utc=True)
    return df
