import pytest


class PytestApeRunner:
    """
    Hooks in this class are loaded when running without xdist, and by xdist
    worker processes.
    """
    #
    # def pytest_generate_tests(self, metafunc):
    #     """
    #     Generate parametrized calls to a test function.
    #     Ensure that `module_isolation` and `fn_isolation` are always the
    #     first fixtures to run within their respective scopes.
    #     Arguments
    #     ---------
    #     metafunc : _pytest.python.Metafunc
    #         Used to inspect a test function generate tests according to test
    #         configuration or values specified in the class or module where a
    #         test function is defined.
    #     """
    #
    # def pytest_collection_modifyitems(self, items):
    #     """
    #     Called after collection has been performed, may filter or re-order the
    #     items in-place.
    #     Determines which modules are isolated, and skips tests based on
    #     the `--update` and `--stateful` flags.
    #     Arguments
    #     ---------
    #     items : List[_pytest.nodes.Item]
    #         List of item objects representing the collected tests
    #     """
    #
    # @pytest.hookimpl(trylast=True, hookwrapper=True)
    # def pytest_collection_finish(self, session):
    #     """
    #     Called after collection has been performed and modified.
    #     This is the final hookpoint that executes prior to running tests. If
    #     the number of tests collected is > 0 and there is not an active network
    #     at this point, Brownie connects to the the default network and launches
    #     the RPC client if required.
    #     Arguments
    #     ---------
    #     session : pytest.Session
    #         The pytest session object.
    #     """
    #
    #
    # def pytest_runtest_protocol(self, item):
    #     """
    #     Implements the runtest_setup/call/teardown protocol for the given test item,
    #     including capturing exceptions and calling reporting hooks.
    #     * With the `-s` flag, enable custom stdout handling
    #     * When the test is from a new module, creates an entry in `self.results`
    #       and populates it with previous outcomes (if available).
    #     Arguments
    #     ---------
    #     item : _pytest.nodes.Item
    #         Test item for which the runtest protocol is performed.
    #     """
    #
    # def pytest_runtest_setup(self, item):
    #     """
    #     Called to perform the setup phase for a test item.
    #     * The `require_network` marker is applied.
    #     Arguments
    #     ---------
    #     item : _pytest.nodes.Item
    #         Test item for which setup is performed.
    #     """
    #
    # def pytest_runtest_logreport(self, report):
    #     """
    #     Process a test setup/call/teardown report relating to the respective phase
    #     of executing a test.
    #     * Updates isolation data for the given test module
    #     * Stores the outcome of the test in `self.results`
    #     * During teardown of the final test in a given module, resets coverage
    #       data and records results for that module in `self.tests`
    #     Arguments
    #     ---------
    #     report : _pytest.reports.BaseReport
    #         Report object for the current test.
    #     """
    #
    # @pytest.hookimpl(hookwrapper=True)
    # def pytest_runtest_call(self, item):
    #     """
    #     Called to run the test for test item (the call phase).
    #     * Handles logic for the `always_transact` marker.
    #     Arguments
    #     ---------
    #     item : _pytest.nodes.Item
    #         Test item for which setup is performed.
    #     """
    #
    # def pytest_report_teststatus(self, report):
    #     """
    #     Return result-category, shortletter and verbose word for status reporting.
    #     Stops at first non-None result.
    #     With the `-s` flag, disables `PytestPrinter` prior to the teardown phase
    #     of each test.
    #     Arguments
    #     ---------
    #     report : _pytest.reports.BaseReport
    #         Report object for the current test.
    #     """
    #
    # def pytest_exception_interact(self, report, call):
    #     """
    #     Called when an exception was raised which can potentially be
    #     interactively handled.
    #     With the `--interactive` flag, outputs the full repr of the failed test
    #     and opens an interactive shell using `brownie._cli.console.Console`.
    #     Arguments
    #     ---------
    #     report : _pytest.reports.BaseReport
    #         Report object for the failed test.
    #     call : _pytest.runner.CallInfo
    #         Result/Exception info for the failed test.
    #     """
    #
    # def pytest_sessionfinish(self):
    #     """
    #     Called after whole test run finished, right before returning the exit
    #     status to the system.
    #     Stores test results in `build/tests.json`.
    #     """
    #
    # def pytest_terminal_summary(self, terminalreporter):
    #     """
    #     Add a section to terminal summary reporting.
    #     When `--gas` is active, outputs the gas profile report.
    #     Arguments
    #     ---------
    #     terminalreporter : `_pytest.terminal.TerminalReporter`
    #         The internal terminal reporter object
    #     """


class PytestApeXdistRunner(PytestApeRunner):
    """
    Hooks in this class are loaded on worker processes when using xdist.
    """


class PytestApeXdistManager:
    pass
    # def pytest_xdist_make_scheduler(self, config, log):
    #     """
    #     Return a node scheduler implementation.
    #     Uses file scheduling to ensure consistent test execution with module-level
    #     isolation.
    #     """
    #
    # def pytest_xdist_node_collection_finished(self, ids):
    #     """
    #     Called by the master node when a node finishes collecting.
    #     * Generates the node map
    #     * Populates `self.results` with previous test results. For tests that
    #       are executed by one of the runners, these results will be overwritten.
    #     """
    #
    # def pytest_sessionfinish(self, session):
    #     """
    #     Called after whole test run finished, right before returning the exit
    #     status to the system.
    #     * Aggregates results from `build/tests-{workerid}.json` files and stores
    #       them as `build/test.json`.
    #     """
