from ape import plugins

from .accounts import HardhatAccount, HardhatAccountContainer


# TODO: Remove when ape-hardhat has accounts
@plugins.register(plugins.AccountPlugin)
def account_types():
    return HardhatAccountContainer, HardhatAccount
