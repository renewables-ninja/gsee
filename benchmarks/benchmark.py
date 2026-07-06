"""
GSEE performance benchmark:

`pixi run benchmark`

Times the individual pipeline stages and end-to-end runs on one
site-year of deterministic synthetic data. Also runs a multi-site loop to
track how per-site cost scales.

Results are printed as a table and saved as JSON under
benchmarks/results/.

To compare two runs, e.g. across branches:

    pixi run benchmark --compare benchmarks/results/<baseline>.json

"""

import argparse
import datetime
import json
import os
import platform
import statistics
import subprocess
import sys
import time

import numpy as np
import pandas as pd
import xarray as xr

from gsee import api, brl_model, pv, trigon
from gsee.core import solarposition
from gsee.synthetic import synthetic_weather

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

SITE = (47.36, 8.55)  # Zurich

MULTI_SITES = [
    (78.25, 15.5),
    (60.2, 25.0),
    (47.36, 8.55),
    (27.7, 85.3),
    (0.0, -78.5),
    (-33.9, 18.4),
    (-45.9, 170.5),
    (-75.0, 123.0),
]

RUN_MODEL_PARAMS = {
    "tilt": 30,
    "azim": 180,
    "tracking": 0,
    "capacity": 1000.0,
}


def bench(results, name, fn, repeats):
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        times.append(time.perf_counter() - start)
    results[name] = {"min_s": min(times), "median_s": statistics.median(times)}
    print("  {:<38s} min {:>9.1f} ms".format(name, min(times) * 1000))


def build_benchmarks(quick):
    data = synthetic_weather(*SITE, seed=1)
    direct = data.global_horizontal * (1 - data.diffuse_fraction)
    diffuse = data.global_horizontal * data.diffuse_fraction
    angles = trigon.sun_angles(data.index, SITE)
    irradiance = direct + diffuse
    tamb = data.temperature
    panel = pv.HuldCSiPanel(panel_aperture=10.0, panel_ref_efficiency=0.1)
    inverter = pv.Inverter(1000.0)
    dc_out = panel.panel_power(irradiance, tamb).clip(upper=1000.0)
    clearness = pd.Series(
        np.clip(0.5 + 0.3 * np.sin(np.arange(len(data)) / 3.0), 0.05, 1.0),
        index=data.index,
    )

    lats_100 = np.linspace(-70.0, 70.0, 100)
    lons_100 = np.linspace(-180.0, 176.4, 100)
    dataset_100 = xr.Dataset(
        {
            var: (
                ("time", "site"),
                np.tile(data[var].to_numpy()[:, None], (1, 100)),
            )
            for var in ("global_horizontal", "diffuse_fraction", "temperature")
        },
        coords={
            "time": data.index.tz_localize(None),
            "site": np.arange(100),
            "lat": ("site", lats_100),
            "lon": ("site", lons_100),
        },
    )

    benchmarks = [
        (
            "sun_rise_set_times",
            lambda: trigon.sun_rise_set_times(data.index, SITE),
        ),
        ("sun_angles", lambda: trigon.sun_angles(data.index, SITE)),
        (
            "core_sun_angles_1_site",
            lambda: solarposition.sun_angles(data.index, *SITE),
        ),
        (
            "core_sun_angles_100_sites",
            lambda: solarposition.sun_angles(data.index, lats_100, lons_100),
        ),
        (
            "aperture_irradiance_given_angles",
            lambda: trigon.aperture_irradiance(
                direct, diffuse, SITE, tilt=0.5, azimuth=np.pi, angles=angles
            ),
        ),
        ("panel_model_huld", lambda: panel.panel_power(irradiance, tamb)),
        ("inverter_apply_loop", lambda: dc_out.apply(inverter.ac_output)),
        (
            "run_model_csi",
            lambda: pv.run_model(data, coords=SITE, **RUN_MODEL_PARAMS),
        ),
        (
            "run_sites_csi_100_sites",
            lambda: api.run_sites(dataset_100, **RUN_MODEL_PARAMS),
        ),
    ]

    if not quick:
        lats_1000 = np.linspace(-70.0, 70.0, 1000)
        lons_1000 = np.linspace(-180.0, 179.6, 1000)
        dataset_1000 = xr.Dataset(
            {
                var: (
                    ("time", "site"),
                    np.tile(data[var].to_numpy()[:, None], (1, 1000)),
                )
                for var in ("global_horizontal", "diffuse_fraction", "temperature")
            },
            coords={
                "time": data.index.tz_localize(None),
                "site": np.arange(1000),
                "lat": ("site", lats_1000),
                "lon": ("site", lons_1000),
            },
        )
        benchmarks += [
            (
                "run_sites_csi_1000_sites",
                lambda: api.run_sites(dataset_1000, **RUN_MODEL_PARAMS),
            ),
            (
                "run_sites_csi_1000_sites_float32",
                lambda: api.run_sites(
                    dataset_1000, dtype="float32", **RUN_MODEL_PARAMS
                ),
            ),
            ("sun_angles_legacy", lambda: trigon.sun_angles_legacy(data.index, SITE)),
            (
                "run_model_singlediode",
                lambda: pv.run_model(
                    data, coords=SITE, technology="cec-csi-median", **RUN_MODEL_PARAMS
                ),
            ),
            ("brl_model", lambda: brl_model.run(clearness, SITE)),
            (
                "run_model_csi_{}_sites".format(len(MULTI_SITES)),
                lambda: [
                    pv.run_model(
                        synthetic_weather(*site, seed=i),
                        coords=site,
                        **RUN_MODEL_PARAMS,
                    )
                    for i, site in enumerate(MULTI_SITES)
                ],
            ),
        ]

    return benchmarks


def environment():
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    versions = {
        module: __import__(module).__version__
        for module in ("pandas", "numpy", "pvlib", "ephem")
    }
    return {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "git_sha": sha,
        "git_branch": branch,
        "python": sys.version.split()[0],
        "machine": platform.machine(),
        "platform": platform.platform(),
        "versions": versions,
    }


def print_comparison(results, baseline_path):
    with open(baseline_path) as f:
        baseline = json.load(f)
    print(
        "\nComparison vs {} ({}@{}):".format(
            os.path.basename(baseline_path),
            baseline["environment"].get("git_branch", "?"),
            baseline["environment"].get("git_sha", "?"),
        )
    )
    for name, result in results.items():
        base = baseline["results"].get(name)
        if base is None:
            print("  {:<38s} (not in baseline)".format(name))
            continue
        ratio = result["min_s"] / base["min_s"]
        print(
            "  {:<38s} {:>9.1f} ms vs {:>9.1f} ms  ({:.2f}x)".format(
                name, result["min_s"] * 1000, base["min_s"] * 1000, ratio
            )
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick", action="store_true", help="fewer repeats, skip slow benchmarks"
    )
    parser.add_argument(
        "--compare", metavar="FILE", help="baseline results JSON to compare against"
    )
    args = parser.parse_args()

    repeats = 1 if args.quick else 3
    env = environment()
    print(
        "GSEE benchmarks | {}@{} | python {} on {}".format(
            env["git_branch"], env["git_sha"], env["python"], env["machine"]
        )
    )
    print("One site-year, hourly (8760 steps); min of {} run(s)\n".format(repeats))

    results = {}
    for name, fn in build_benchmarks(args.quick):
        bench(results, name, fn, repeats)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    filename = "{}-{}.json".format(
        env["timestamp"].replace(":", "").split(".")[0], env["git_sha"]
    )
    out_path = os.path.join(RESULTS_DIR, filename)
    with open(out_path, "w") as f:
        json.dump({"environment": env, "results": results}, f, indent=2)
    print("\nSaved: {}".format(os.path.relpath(out_path)))

    if args.compare:
        print_comparison(results, args.compare)


if __name__ == "__main__":
    main()
