from typing import Any

import click

from ape.logging import logger


class Abort(click.ClickException):
    """Wrapper around a CLI exception"""

    def show(self, file=None):
        """Override default ``show`` to print CLI errors in red text."""
        logger.error(self.format_message())


class ApeCliContext:
    """A class that can be auto-imported into a plugin ``click.command()``
    via ``@ape_cli_context()``. It can help do common CLI tasks such as log
    messages to the user or abort execution."""

    def __init__(self):
        self.logger = logger

    @classmethod
    def echo(cls, *args, **kwargs):
        click.echo(*args, **kwargs)

    @classmethod
    def secure_prompt(cls, *args, **kwargs):
        return cls.prompt(*args, hide_input=True, **kwargs)

    @classmethod
    def prompt(cls, *args, **kwargs) -> Any:
        return click.prompt(*args, **kwargs)

    @classmethod
    def confirm(cls, *args, **kwargs) -> bool:
        return click.confirm(*args, **kwargs)

    @staticmethod
    def abort(msg: str, base_error: Exception = None):
        logger.error(msg)
        if base_error:
            raise Abort(msg) from base_error

        raise Abort(msg)
