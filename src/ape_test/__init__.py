from ape import plugins

from .accounts import HardhatAccount, HardhatAccountContainer
from .providers import LocalNetwork


# TODO: Remove when ape-hardhat has accounts
@plugins.register(plugins.AccountPlugin)
def account_types():
    return HardhatAccountContainer, HardhatAccount


@plugins.register(plugins.ProviderPlugin)
def providers():
    yield "ethereum", "development", LocalNetwork
