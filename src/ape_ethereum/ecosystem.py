import json
import re
from typing import Any, Optional

from eth_abi import decode_abi as abi_decode
from eth_abi import encode_abi as abi_encode
from eth_abi.exceptions import InsufficientDataBytes
from eth_account import Account as EthAccount  # type: ignore
from eth_account._utils.legacy_transactions import (
    encode_transaction,
    serializable_unsigned_transaction_from_dict,
)
from eth_utils import keccak, to_bytes, to_int
from hexbytes import HexBytes

from ape.api import ContractLog, EcosystemAPI, ReceiptAPI, TransactionAPI, TransactionStatusEnum
from ape.exceptions import (
    DecodingError,
    OutOfGasError,
    SignatureError,
    TransactionError,
    VirtualMachineError,
)
from ape.types import ABI, AddressType

NETWORKS = {
    # chain_id, network_id
    "mainnet": (1, 1),
    "ropsten": (3, 3),
    "kovan": (42, 42),
    "rinkeby": (4, 4),
    "goerli": (420, 420),
}


class EthereumVirtualMachineError(VirtualMachineError):
    """
    Use this error in your Ethereum providers and raise
    when detecting internal faults from the EVM or
    contract-defined reverts such as from assert statements.
    """

    def __init__(self, revert_message: str):
        super().__init__(revert_message)

    @classmethod
    def from_error(cls, err: Exception):
        """
        Creates an instance of ``EthereumVirtualMachineError`` from
        a web3 raised ``ValueError`.

        Raises other ``TransactionError`` instances if it notices
        the error is gas-related.
        """

        if not isinstance(err, ValueError) or not hasattr(err, "args") or len(err.args) < 1:
            return None

        err_data = err.args[0]
        if not isinstance(err_data, dict):
            return None

        message = err_data.get("message", json.dumps(err_data))
        code = err_data.get("code")

        if re.match(r"(.*)out of gas(.*)", message.lower()):
            raise OutOfGasError(code=code)

        # Try not to raise ``EthereumVirtualMachineError`` for any gas-related
        # issues. This is to keep the ``EthereumVirtualMachineError`` more focused
        # on contract-application specific faults.
        other_gas_error_patterns = (
            r"(.*)exceeds \w*?[ ]?gas limit(.*)",
            r"(.*)requires at least \d* gas(.*)",
        )
        for pattern in other_gas_error_patterns:
            if re.match(pattern, message.lower()):
                raise TransactionError(message, code=code)

        return cls(message)


# TODO: Fix this to add support for TypedTransaction
class Transaction(TransactionAPI):
    def is_valid(self) -> bool:
        return False

    def as_dict(self) -> dict:
        data = super().as_dict()

        # Clean up data to what we expect
        data["chainId"] = data.pop("chain_id")

        receiver = data.pop("receiver")
        if receiver:
            data["to"] = receiver

        data["gas"] = data.pop("gas_limit")
        data["gasPrice"] = data.pop("gas_price")

        # NOTE: Don't publish signature or sender
        data.pop("signature")
        data.pop("sender")

        return {key: value for key, value in data.items() if value is not None}

    def encode(self) -> bytes:
        if not self.signature:
            raise SignatureError("The transaction is not signed.")

        txn_data = self.as_dict()
        unsigned_txn = serializable_unsigned_transaction_from_dict(txn_data)
        signature = (self.signature.v, to_int(self.signature.r), to_int(self.signature.s))

        signed_txn = encode_transaction(unsigned_txn, signature)

        if self.sender and EthAccount.recover_transaction(signed_txn) != self.sender:
            raise SignatureError("Recovered Signer doesn't match sender!")

        return signed_txn


class Receipt(ReceiptAPI):
    @classmethod
    def decode(cls, data: dict) -> ReceiptAPI:
        return cls(  # type: ignore
            txn_hash=data["hash"],
            status=TransactionStatusEnum(data["status"]),
            block_number=data["blockNumber"],
            gas_used=data["gasUsed"],
            gas_price=data["gasPrice"],
            logs=data["logs"],
            contract_address=data["contractAddress"],
        )


class Ethereum(EcosystemAPI):
    transaction_class = Transaction
    receipt_class = Receipt
    virtual_machine_error_class = EthereumVirtualMachineError

    def encode_calldata(self, abi: ABI, *args) -> bytes:
        if abi.inputs:
            input_types = [i.canonical_type for i in abi.inputs]
            return abi_encode(input_types, args)

        else:
            return HexBytes(b"")

    def decode_calldata(self, abi: ABI, raw_data: bytes) -> Any:
        output_types = [o.canonical_type for o in abi.outputs]
        try:
            return abi_decode(output_types, raw_data)

        except InsufficientDataBytes as err:
            raise DecodingError() from err

    def encode_deployment(
        self, deployment_bytecode: bytes, abi: Optional[ABI], *args, **kwargs
    ) -> Transaction:
        txn = Transaction(**kwargs)  # type: ignore
        txn.data = deployment_bytecode

        # Encode args, if there are any
        if abi:
            txn.data += self.encode_calldata(abi, *args)

        return txn

    def encode_transaction(
        self,
        address: AddressType,
        abi: ABI,
        *args,
        **kwargs,
    ) -> Transaction:
        txn = Transaction(receiver=address, **kwargs)  # type: ignore

        # Add method ID
        txn.data = keccak(to_bytes(text=abi.selector))[:4]
        txn.data += self.encode_calldata(abi, *args)

        return txn

    def decode_event(self, abi: ABI, receipt: "ReceiptAPI") -> "ContractLog":
        filter_id = keccak(to_bytes(text=abi.selector))
        event_data = next(log for log in receipt.logs if log["filter_id"] == filter_id)
        return ContractLog(  # type: ignore
            name=abi.name,
            inputs={i.name: event_data[i.name] for i in abi.inputs},
        )
