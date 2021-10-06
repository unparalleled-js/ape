from pathlib import Path as _Path

import click


class SourceFilePath(click.Path):
    """
    The path to the source files for a project
    """

    def __init__(self):
        super().__init__(exists=True, path_type=_Path, resolve_path=True)
