from typing import Iterator, Optional

from eth_account import Account as EthAccount  # type: ignore
from eth_account.messages import SignableMessage

from ape.api import AccountAPI, AccountContainerAPI, TransactionAPI
from ape.convert import to_address
from ape.types import AddressType, MessageSignature, TransactionSignature


def _get_alias(account_index: int) -> str:
    return f"HardhatTestAccount_{account_index}"


# TODO: replace with `accounts` from hardhat once that exists
class HardhatAccountContainer(AccountContainerAPI):
    _addresses = ["0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"]
    _private_keys = ["0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"]

    def aliases(self) -> Iterator[str]:
        for index in range(0, len(self)):
            yield _get_alias(index)

    def __len__(self) -> int:
        return min(len(self._addresses), len(self._private_keys))

    def __iter__(self) -> Iterator[AccountAPI]:
        for index in range(0, len(self)):
            yield HardhatAccount(
                self, index, self._addresses[index], self._private_keys[index]
            )  # type: ignore


class HardhatAccount(AccountAPI):
    _account_index: int
    _address: str
    _private_key: str

    @property
    def alias(self) -> str:
        return _get_alias(self._account_index)

    @property
    def address(self) -> AddressType:
        return to_address(self._address)

    def sign_message(self, msg: SignableMessage) -> Optional[MessageSignature]:
        signed_msg = EthAccount.sign_message(msg, self._private_key)
        return MessageSignature(v=signed_msg.v, r=signed_msg.r, s=signed_msg.s)  # type: ignore

    def sign_transaction(self, txn: TransactionAPI) -> Optional[TransactionSignature]:
        signed_txn = EthAccount.sign_transaction(txn.as_dict(), self._private_key)
        return TransactionSignature(v=signed_txn.v, r=signed_txn.r, s=signed_txn.s)  # type: ignore
