import json

from eth_account import Account as EthAccount  # type: ignore
from eth_utils import to_bytes

from ape import accounts
from ape.cli import ape_group, existing_alias_argument, non_existing_alias_argument, option
from ape_accounts import KeyfileAccount

# NOTE: Must used the instantiated version of `AccountsContainer` in `accounts`
container = accounts.containers["accounts"]


@ape_group(short_help="Manage local accounts")
def cli():
    """
    Command-line helper for managing local accounts. You can unlock local accounts from
    scripts or the console using the accounts.load() method.
    """


@cli.command_with_cli_context(name="list", short_help="List available local accounts")
@option("--all", help="Output accounts from all plugins", is_flag=True)
def _list(cli_ctx, all):
    accounts_to_output = accounts if all else accounts.containers.get("accounts", [])
    if len(accounts_to_output) == 0:
        cli_ctx.logger.warning("No accounts found.")
        return

    elif len(accounts_to_output) > 1:
        cli_ctx.echo(f"Found {len(accounts)} accounts:")

    else:
        cli_ctx.echo("Found 1 account:")

    for account in accounts_to_output:
        alias_display = f" (alias: '{account.alias}')" if account.alias else ""
        cli_ctx.echo(f"  {account.address}{alias_display}")


@cli.command_with_cli_context(short_help="Create a new keyfile account with a random private key")
@non_existing_alias_argument()
def generate(cli_ctx, alias):
    path = container.data_folder.joinpath(f"{alias}.json")
    extra_entropy = cli_ctx.prompt(
        "Add extra entropy for key generation...",
        hide_input=True,
    )
    account = EthAccount.create(extra_entropy)
    passphrase = cli_ctx.secure_prompt(
        "Create Passphrase",
        confirmation_prompt=True,
    )
    path.write_text(json.dumps(EthAccount.encrypt(account.key, passphrase)))
    cli_ctx.logger.success(
        f"A new account '{account.address}' has been added with the id '{alias}'"
    )


@cli.command_with_cli_context(
    name="import", short_help="Add a new keyfile account by entering a private key"
)
@non_existing_alias_argument()
def _import(cli_ctx, alias):
    path = container.data_folder.joinpath(f"{alias}.json")
    key = cli_ctx.secure_prompt("Enter Private Key")
    try:
        account = EthAccount.from_key(to_bytes(hexstr=key))
    except Exception as error:
        cli_ctx.abort(f"Key can't be imported: {error}")

    passphrase = cli_ctx.secure_prompt(
        "Create Passphrase",
        confirmation_prompt=True,
    )
    # noinspection PyUnboundLocalVariable
    path.write_text(json.dumps(EthAccount.encrypt(account.key, passphrase)))
    cli_ctx.logger.success(
        f"A new account '{account.address}' has been added with the id '{alias}'"
    )


@cli.command_with_cli_context(short_help="Change the password of an existing account")
@existing_alias_argument(account_type=KeyfileAccount)
def change_password(cli_ctx, alias):
    account = accounts.load(alias)
    account.change_password()
    cli_ctx.logger.success(f"Password has been changed for account '{alias}'")


@cli.command_with_cli_context(short_help="Delete an existing account")
@existing_alias_argument(account_type=KeyfileAccount)
def delete(cli_ctx, alias):
    account = accounts.load(alias)
    account.delete()
    cli_ctx.logger.success(f"Account '{alias}' has been deleted")
