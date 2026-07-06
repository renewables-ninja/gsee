"""
Reference regression tests.

Each test recomputes a case from its stored input and compares against
the stored reference with the "exact" tolerance profile. On failure,
the report also shows the "physical" profile verdict.

If the "physical" profile passes, results changed only within the
physical-equivalence tolerances, so it should be safe to regenerate
via `pixi run generate-reference` and document in CHANGELOG.md.

If both tests fail, the model's behaviour has definitely changed.

"""

import pytest

from gsee import pv, trigon
from tests.reference import cases, compare

CASES = cases.build_cases()


def _fail_with_reports(exact_report, physical_ok, physical_report):
    pytest.fail(
        "Exact-profile comparison against reference data failed.\n"
        "{}\n\n"
        "Physical-equivalence profile: {}\n"
        "{}\n\n".format(
            exact_report,
            (
                "PASS (change within physical tolerances)"
                if physical_ok
                else "FAIL (model behaviour has changed)"
            ),
            physical_report,
        ),
        pytrace=False,
    )


@pytest.mark.reference
@pytest.mark.parametrize("case_id", sorted(CASES))
def test_reference_output(case_id):
    case = CASES[case_id]
    data = cases.read_frame(cases.input_path(case_id))
    result = pv.run_model(
        data,
        coords=(case["lat"], case["lon"]),
        include_raw_data=True,
        **case["params"],
    )
    ref = cases.read_frame(cases.output_path(case_id))
    capacity = case["params"]["capacity"]

    ok, report = compare.check_output(result, ref, capacity, "exact")
    if not ok:
        physical_ok, physical_report = compare.check_output(
            result, ref, capacity, "physical"
        )
        _fail_with_reports(report, physical_ok, physical_report)


@pytest.mark.reference
@pytest.mark.parametrize(
    "case_id", sorted(c for c in CASES if CASES[c]["store_angles"])
)
def test_reference_angles(case_id):
    case = CASES[case_id]
    data = cases.read_frame(cases.input_path(case_id))
    angles = trigon.sun_angles(data.index, (case["lat"], case["lon"]))
    ref = cases.read_frame(cases.angles_path(case_id))

    ok, report = compare.check_angles(angles, ref, "exact")
    if not ok:
        physical_ok, physical_report = compare.check_angles(angles, ref, "physical")
        _fail_with_reports(report, physical_ok, physical_report)
