import click

from ape.cli.arguments import argument, existing_alias_argument, non_existing_alias_argument
from ape.cli.choices import Alias, PromptChoice
from ape.cli.commands import command_using_network_option, command_with_cli_context
from ape.cli.groups import ape_cli, ape_group
from ape.cli.options import (
    ape_cli_context,
    network_option,
    option,
    skip_confirmation_option,
    verbose_option,
)
from ape.cli.paramtype import AllFilePaths
from ape.cli.utils import Abort, ApeCliContext


def get_cli_context() -> ApeCliContext:
    return click.get_current_context().obj


__all__ = [
    "Abort",
    "Alias",
    "AllFilePaths",
    "ape_cli",
    "ape_cli_context",
    "argument",
    "ApeCliContext",
    "ape_group",
    "existing_alias_argument",
    "command_using_network_option",
    "command_with_cli_context",
    "get_cli_context",
    "network_option",
    "non_existing_alias_argument",
    "option",
    "PromptChoice",
    "skip_confirmation_option",
    "verbose_option",
]
