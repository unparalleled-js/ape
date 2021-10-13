class PytestApeRunner:
    """
    Hooks in this class are loaded when running without xdist, and by xdist
    worker processes.
    """

    def __init__(self, config):
        self.config = config

    def pytest_sessionstart(self):
        """
        Called after the `Session` object has been created and before performing
        collection and entering the run test loop.

        * Removes `PytestAssertRewriteWarning` warnings from the terminalreporter.
          This prevents warnings that "the `brownie` library was already imported and
          so related assertions cannot be rewritten". The warning is not relevant
          for end users who are performing tests with brownie, not on ape,
          so we suppress it to avoid confusion.

        Removal of pytest warnings must be handled in this hook because session
        information is passed between xdist workers and master prior to test execution.
        """
        reporter = self.config.pluginmanager.get_plugin("terminalreporter")
        warnings = reporter.stats.pop("warnings", [])
        warnings = [i for i in warnings if "PytestAssertRewriteWarning" not in i.message]
        if warnings and not self.config.getoption("--disable-warnings"):
            reporter.stats["warnings"] = warnings


class PytestApeXdistRunner(PytestApeRunner):
    """
    Hooks in this class are loaded on worker processes when using xdist.
    """


class PytestApeXdistManager:
    pass
