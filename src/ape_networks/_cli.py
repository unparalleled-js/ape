from ape import networks
from ape.cli import ape_group


@ape_group(short_help="Manage networks")
def cli():
    """
    Command-line helper for managing networks.
    """


@cli.command_with_cli_context(name="list", short_help="List registered networks")
def _list(cli_ctx):
    cli_ctx.echo(networks.networks_yaml)
