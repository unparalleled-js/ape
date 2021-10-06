from typing import Any, Callable

import click as c

from ape import networks
from ape.cli.options import ape_cli_context, network_option


def command_with_cli_context(*args, **kwargs) -> Callable[[Callable[..., Any]], c.Command]:
    """
    A command that automatically has the ``
    """

    def decorator(f):
        f = ape_cli_context()(f)
        f = c.command(*args, **kwargs)(f)
        return f

    return decorator


def command_using_network_option(*args, **kwargs):
    """
    A command that automatically has the ``network_option`` and
    the base CLI context. The command executes entirely in the context of the
    given network.
    """

    def decorator(f):
        cls = kwargs.pop("cls", NetworkBoundCommand)
        f = c.command(cls=cls, *args, **kwargs)(f)
        f = network_option(f)
        return f

    return decorator


class NetworkBoundCommand(c.Command):
    """A command that uses the network option.
    It will automatically set the network for the duration of the command execution.
    """

    def invoke(self, ctx: c.Context) -> Any:
        with networks.parse_network_choice(ctx.params["network"]):
            super().invoke(ctx)
