from pathlib import Path

import pytest

from ape.pytest.fixtures import PytestApeFixtures
from tests.conftest import GETH_URI, geth_process_test
from tests.integration.cli.utils import skip_projects_except

BASE_PROJECTS_PATH = Path(__file__).parent / "projects"
TOKEN_B_GAS_REPORT = """
                         TokenB Gas

  Method     Times called    Min.    Max.    Mean   Median
 ──────────────────────────────────────────────────────────
  transfer              1   50911   50911   50911    50911
"""
EXPECTED_GAS_REPORT = rf"""
                      TestContractVy Gas

  Method       Times called    Min.    Max.    Mean   Median
 ────────────────────────────────────────────────────────────
  setNumber               3   51033   51033   51033    51033
  fooAndBar               1   23430   23430   23430    23430
  setAddress              1   44850   44850   44850    44850

                         TokenA Gas

  Method     Times called    Min.    Max.    Mean   Median
 ──────────────────────────────────────────────────────────
  transfer              1   50911   50911   50911    50911
{TOKEN_B_GAS_REPORT}
"""
GETH_LOCAL_CONFIG = f"""
geth:
  ethereum:
    local:
      uri: {GETH_URI}
"""


@pytest.fixture
def setup_pytester(pytester):
    def setup(project_name: str):
        tests_path = BASE_PROJECTS_PATH / project_name / "tests"

        # Assume all tests should pass
        number_of_tests = 0
        test_files = {}
        for file_path in tests_path.iterdir():
            if file_path.name.startswith("test_") and file_path.suffix == ".py":
                content = file_path.read_text()
                test_files[file_path.name] = content
                number_of_tests += len(
                    [x for x in content.split("\n") if x.startswith("def test_")]
                )

        pytester.makepyfile(**test_files)

        # Check for a conftest.py
        conftest = tests_path / "conftest.py"
        if conftest.is_file():
            pytester.makeconftest(conftest.read_text())

        # Returns expected number of passing tests.
        return number_of_tests

    return setup


def run_gas_test(result, expected_number_passed: int, expected_report: str = EXPECTED_GAS_REPORT):
    if not result.outlines:
        raise AssertionError("Missing output")

    output_str = "\n".join(result.outlines)
    fail_message = f"Complete pytest output:\n{output_str}"
    result.assert_outcomes(passed=expected_number_passed), fail_message

    gas_header_line_index = None
    for index, line in enumerate(result.outlines):
        if "Gas Profile" in line:
            gas_header_line_index = index

    assert gas_header_line_index is not None, "'Gas Profile' not in output."
    expected = expected_report.split("\n")[1:]
    start_index = gas_header_line_index + 1
    end_index = start_index + len(expected)
    actual = [x.rstrip() for x in result.outlines[start_index:end_index]]
    assert "WARNING: No gas usage data found." not in actual, "Gas data missing!"

    actual_len = len(actual)
    expected_len = len(expected)

    if actual_len > expected_len:
        remainder = "\n".join(actual[expected_len:])
        pytest.xfail(f"Actual contains more than expected:\n{remainder}")
    elif expected_len > actual_len:
        remainder = "\n".join(expected[actual_len:])
        pytest.xfail(f"Expected contains more than actual:\n{remainder}")

    for actual_line, expected_line in zip(actual, expected):
        assert actual_line == expected_line


@geth_process_test
@skip_projects_except("geth")
def test_gas_flag_in_tests(geth_provider, setup_pytester, project, pytester):
    assert project.TestContractVy
    expected_test_passes = setup_pytester(project.path.name)
    result = pytester.runpytest("--gas")
    run_gas_test(result, expected_test_passes)
