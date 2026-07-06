"""
Generate reference data:

`pixi run generate-reference`

Regenerate when a deliberate and verified change in model results occurs.
The regenerated files should be committed together with the code change
that caused them.

Every case runs `gsee.pv.run_model(include_raw_data=True)` on
synthetic input.
Base cases additionally store the `trigon.sun_angles()` solar position frame.
Inputs are stored alongside outputs so the reference data is self-contained.

"""

import datetime
import json
import os
import platform
import subprocess
import sys

import numpy as np
import pandas as pd

import gsee
from gsee import pv, trigon
from tests.reference import cases

ANGLE_COLUMNS = ["apparent_elevation", "azimuth", "risen_fraction", "sunrise", "sunset"]

# Stored values are quantized to keep the committed files small.
# Rounded inputs are used for the model.
# Output rounding is about ~2 orders of magnitude below the "exact" tolerances in tests.reference.compare.
INPUT_DECIMALS = {"global_horizontal": 2, "diffuse_fraction": 4, "temperature": 2}
OUTPUT_DECIMALS = {
    "output": 4,
    "direct": 4,
    "diffuse": 4,
    "module_temperature": 4,
    "relative_efficiency": 6,
}
ANGLE_DECIMALS = {"apparent_elevation": 6, "azimuth": 6, "risen_fraction": 6}


def _quantize(df, decimals):
    for col, n in decimals.items():
        if col in df.columns:
            df[col] = df[col].round(n)
    return df


# Wide plausibility bounds on annual capacity factor
CF_BOUNDS = (0.005, 0.45)

# Polar night spot checks:
# (case_id, month with zero output)
POLAR_NIGHT = [("svalbard-base", 12), ("antarctica-base", 6)]


def run_case(case):
    # Quantized inputs are the canonical model inputs: the model must
    # run on exactly what gets stored
    data = _quantize(cases.make_input(case), INPUT_DECIMALS)
    result = pv.run_model(
        data,
        coords=(case["lat"], case["lon"]),
        include_raw_data=True,
        **case["params"],
    )
    # The temperature column just repeats the input and is not stored
    result = _quantize(result.drop(columns=["temperature"]), OUTPUT_DECIMALS)
    angles = None
    if case["store_angles"]:
        angles = _quantize(
            trigon.sun_angles(data.index, (case["lat"], case["lon"]))[ANGLE_COLUMNS],
            ANGLE_DECIMALS,
        )
    return data, result, angles


def sanity_check(case_id, case, result):
    output = result["output"]
    capacity = case["params"]["capacity"]
    assert not result.isna().any().any(), "{}: NaNs in result".format(case_id)
    assert np.isfinite(result.to_numpy()).all(), "{}: non-finite values".format(case_id)
    assert output.min() >= -1e-9, "{}: negative output".format(case_id)
    assert output.max() <= capacity * 1.0001, "{}: output above capacity".format(
        case_id
    )
    cf = output.mean() / capacity
    assert (
        CF_BOUNDS[0] < cf < CF_BOUNDS[1]
    ), "{}: implausible capacity factor {}".format(case_id, cf)
    return cf


def roundtrip_check(frame, path):
    stored = cases.read_frame(path)
    pd.testing.assert_frame_equal(
        stored, frame, check_exact=True, check_freq=False, check_names=False
    )


def write_metadata():
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    versions = {}
    for module in ("pandas", "numpy", "pvlib", "ephem"):
        versions[module] = __import__(module).__version__
    metadata = {
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "git_sha": sha,
        "gsee_version": gsee.__version__,
        "python": sys.version,
        "platform": platform.platform(),
        "versions": versions,
    }
    path = os.path.join(cases.DATA_DIR, "metadata.json")
    with open(path, "w") as f:
        json.dump(metadata, f, indent=2)


def main():
    os.makedirs(cases.DATA_DIR, exist_ok=True)
    all_cases = cases.build_cases()
    print(
        "Generating {} reference cases into {}".format(len(all_cases), cases.DATA_DIR)
    )

    for case_id, case in all_cases.items():
        data, result, angles = run_case(case)
        cf = sanity_check(case_id, case, result)

        data.to_csv(cases.input_path(case_id), compression="xz")
        result.to_csv(cases.output_path(case_id), compression="xz")
        roundtrip_check(data, cases.input_path(case_id))
        roundtrip_check(result, cases.output_path(case_id))
        if angles is not None:
            angles.to_csv(cases.angles_path(case_id), compression="xz")
            roundtrip_check(angles, cases.angles_path(case_id))

        print("  {:<40s} CF={:.3f}".format(case_id, cf))

    for case_id, month in POLAR_NIGHT:
        output = cases.read_frame(cases.output_path(case_id))["output"]
        polar_night_sum = output[output.index.month == month].sum()
        assert polar_night_sum == 0, "{}: output during polar night (month {})".format(
            case_id, month
        )
        print("  polar night check OK: {} month {}".format(case_id, month))

    write_metadata()
    print("Done.")


if __name__ == "__main__":
    main()
