import sys
from pathlib import Path

from _pytest.config import Config

from ape_test.fixtures import PytestApeFixtures
from ape_test.managers import (
    PytestApeRunner,
    PytestApeXdistManager,
    PytestApeXdistRunner,
)


# set commandline options
def pytest_addoption(parser):
    parser.addoption(
        "--showinternal",
        action="store_true",
        help="Include Ape internal frames in tracebacks",
    )
    # NOTE: Other testing plugins should integrate with pytest separately


def _hide_ape_internals_tracebacks():
    base_path = Path(sys.modules["ape"].__file__).parent.as_posix()

    modules = [
        v
        for v in sys.modules.values()
        if getattr(v, "__file__", None) and v.__file__.startswith(base_path)
    ]

    for module in modules:
        module.__tracebackhide__ = True


def _get_runner_class(config: Config):
    # If xdist is installed, register the master runner
    has_xdist = "numprocesses" in config.option
    if has_xdist and config.getoption("numprocesses"):
        return PytestApeXdistManager

    # Manager runner needs to use Child Process runners
    elif hasattr(config, "workerinput"):
        return PytestApeXdistRunner

    # X-dist not installed or disabled, using the normal runner
    return PytestApeRunner


def pytest_configure(config):
    # do not include ape internals in tracebacks unless explicitly asked
    if not config.getoption("showinternal"):
        _hide_ape_internals_tracebacks()

    # enable verbose output if stdout capture is disabled
    config.option.verbose = config.getoption("capture") == "no"

    plugin_cls = _get_runner_class(config)

    # Inject the runner plugin (must happen before fixtures registration)
    # NOTE: the runner contains the injected local project
    session = plugin_cls()
    config.pluginmanager.register(session, "ape-test")

    # Only inject fixtures if we're not configuring the x-dist master runner
    has_xdist = "numprocesses" in config.option
    if not has_xdist or not config.getoption("numprocesses"):
        fixtures = PytestApeFixtures()  # NOTE: contains all the registered fixtures
        config.pluginmanager.register(fixtures, "ape-fixtures")
