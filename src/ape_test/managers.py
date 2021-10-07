class PytestApeRunner:
    """
    Hooks in this class are loaded when running without xdist, and by xdist
    worker processes.
    """


class PytestApeXdistRunner(PytestApeRunner):
    """
    Hooks in this class are loaded on worker processes when using xdist.
    """


class PytestApeXdistManager:
    pass
