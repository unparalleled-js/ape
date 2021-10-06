import difflib
import re
from typing import Any, Callable, Dict

import click
import yaml

from ape.cli.commands import NetworkBoundCommand
from ape.cli.options import ape_cli_context, network_option
from ape.cli.utils import Abort
from ape.exceptions import ApeException
from ape.logging import logger
from ape.plugins import clean_plugin_name

try:
    from importlib import metadata  # type: ignore
except ImportError:
    import importlib_metadata as metadata  # type: ignore

_DIFFLIB_CUT_OFF = 0.6


class ApeGroup(click.Group):
    def command_with_cli_context(
        self, *args: Any, **kwargs: Any
    ) -> Callable[[Callable[..., Any]], click.Command]:
        def decorator(f):
            f = ape_cli_context()(f)
            f = self.command(*args, **kwargs)(f)
            return f

        return decorator

    def command_using_network_option(self, *args, **kwargs):
        def decorator(f):
            f = network_option(f)
            f = self.command(cls=NetworkBoundCommand, *args, **kwargs)(f)
            return f

        return decorator


def ape_group(*args, **kwargs) -> Callable[[click.core.F], ApeGroup]:
    return click.group(cls=ApeGroup, *args, **kwargs)  # type: ignore


class ApeCLI(click.MultiCommand):
    _commands = None

    def invoke(self, ctx) -> Any:
        try:
            return super().invoke(ctx)
        except click.UsageError as err:
            self._suggest_cmd(err)
        except ApeException as err:
            raise Abort(str(err)) from err

    @staticmethod
    def _suggest_cmd(usage_error):
        if usage_error.message is None:
            raise usage_error

        match = re.match("No such command '(.*)'.", usage_error.message)
        if not match:
            raise usage_error

        bad_arg = match.groups()[0]
        suggested_commands = difflib.get_close_matches(
            bad_arg, list(usage_error.ctx.command.commands.keys()), cutoff=_DIFFLIB_CUT_OFF
        )
        if suggested_commands:
            if bad_arg not in suggested_commands:
                usage_error.message = (
                    f"No such command '{bad_arg}'. Did you mean {' or '.join(suggested_commands)}?"
                )

        raise usage_error

    @property
    def commands(self) -> Dict:
        if not self._commands:
            entry_points = metadata.entry_points()  # type: ignore

            if "ape_cli_subcommands" not in entry_points:
                raise Abort("Missing registered cli subcommands")

            self._commands = {
                clean_plugin_name(entry_point.name): entry_point.load
                for entry_point in entry_points["ape_cli_subcommands"]
            }

        return self._commands

    def list_commands(self, ctx):
        return list(sorted(self.commands))

    def get_command(self, ctx, name):

        if name in self.commands:
            try:
                return self.commands[name]()
            except Exception as err:
                # NOTE: don't return anything so Click displays proper error
                logger.warning(f"Unable to load CLI endpoint for plugin 'ape_{name}'.\n\t{err}")


def display_config(ctx, param, value):
    # NOTE: This is necessary not to interrupt how version or help is intercepted
    if not value or ctx.resilient_parsing:
        return

    from ape import project

    click.echo("# Current configuration")
    click.echo(yaml.dump(project.config.serialize()))

    ctx.exit()  # NOTE: Must exit to bypass running ApeCLI


def ape_cli():
    def decorator(f):
        f = click.command(cls=ApeCLI, context_settings=dict(help_option_names=["-h", "--help"]))(f)
        f = click.version_option(message="%(version)s", package_name="eth-ape")(f)
        f = click.option(
            "--config",
            is_flag=True,
            is_eager=True,
            expose_value=False,
            callback=display_config,
            help="Show configuration options (using `ape-config.yaml`)",
        )(f)
        return f

    return decorator
