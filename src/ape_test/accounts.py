from typing import Iterator, Optional

from eth_account.messages import SignableMessage
from eth_tester import EthereumTester

from ape.convert import to_address
from ape.api import AccountContainerAPI, AccountAPI, TransactionAPI
from ape.types import AddressType, MessageSignature, TransactionSignature


def _create_test_alias(index: int) -> str:
    return f"EthTesterAccount{index}"


class TestAccountContainer(AccountContainerAPI):
    def __post_init__(self):
        self._eth_tester = EthereumTester()

    @property
    def aliases(self) -> Iterator[str]:
        for i in range(0, len(self)):
            yield _create_test_alias(i)

    def __len__(self) -> int:
        return len(self._eth_tester.get_accounts())

    def __iter__(self) -> Iterator[AccountAPI]:
        accounts = self._eth_tester.get_accounts()
        for i in range(0, len(accounts)):
            yield TestAccount(self, i, accounts[i])


class TestAccount(AccountAPI):
    _account_index: int
    _address: str

    @property
    def alias(self) -> Optional[str]:
        return _create_test_alias(self._account_index)

    @property
    def address(self) -> AddressType:
        return to_address(self._address)

    def sign_message(self, msg: SignableMessage) -> Optional[MessageSignature]:
        raise AttributeError("TestAccounts cannot sign messages.")

    def sign_transaction(self, txn: TransactionAPI) -> Optional[TransactionSignature]:
        raise AttributeError("TestAccounts cannot sign transactions.")
