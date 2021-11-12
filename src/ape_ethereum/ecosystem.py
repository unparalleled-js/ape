from typing import Any, Optional, Tuple, Type

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

from ape.api import (
    ContractLog,
    EcosystemAPI,
    ProviderAPI,
    ReceiptAPI,
    TransactionAPI,
    TransactionStatusEnum,
)
from ape.exceptions import DecodingError, OutOfGasError, SignatureError, TransactionError
from ape.types import ABI, AddressType

NETWORKS = {
    # chain_id, network_id
    "mainnet": (1, 1),
    "ropsten": (3, 3),
    "kovan": (42, 42),
    "rinkeby": (4, 4),
    "goerli": (420, 420),
}


class BaseTransaction(TransactionAPI):
    type: str = None  # type: ignore

    def set_defaults(self, provider: ProviderAPI):
        """
        Sets ``gas_limit`` if it is None.
        Sub-classes should likely should call this method.
        """
        if self.gas_limit is None:
            self.gas_limit = provider.estimate_gas_cost(self)
        # else: Assume user specified the correct amount or txn will fail and waste gas

    def is_valid(self) -> bool:
        return False

    def as_dict(self) -> dict:
        data = super().as_dict()

        # Clean up data to what we expect
        data["chainId"] = data.pop("chain_id")

        receiver = data.pop("receiver")
        if receiver:
            data["to"] = receiver

        # NOTE: sender is needed sometimes for estimating gas
        # but is it no needed during publish (and may error if included).
        sender = data.pop("sender")
        if sender:
            data["from"] = sender

        data["gas"] = data.pop("gas_limit")

        # NOTE: Don't include signature
        data.pop("signature")

        return {key: value for key, value in data.items() if value is not None}

    def encode(self) -> bytes:
        if not self.signature:
            raise SignatureError("The transaction is not signed.")

        txn_data = self.as_dict()

        # Don't publish from
        if "from" in txn_data:
            del txn_data["from"]

        unsigned_txn = serializable_unsigned_transaction_from_dict(txn_data)
        signature = (self.signature.v, to_int(self.signature.r), to_int(self.signature.s))

        signed_txn = encode_transaction(unsigned_txn, signature)

        if self.sender and EthAccount.recover_transaction(signed_txn) != self.sender:
            raise SignatureError("Recovered Signer doesn't match sender!")

        return signed_txn


class StaticFeeTransaction(BaseTransaction):
    """
    Transactions that are pre-EIP-1559 and use the ``gasPrice`` field.
    """

    gas_price: int = None  # type: ignore
    type: str = "0x0"

    @property
    def max_fee(self) -> int:
        return (self.gas_limit or 0) * (self.gas_price or 0)

    def set_defaults(self, provider: ProviderAPI):
        if self.gas_price is None:
            self.gas_price = provider.gas_price

        super().set_defaults(provider)

    def as_dict(self):
        data = super().as_dict()
        if "gas_price" in data:
            data["gasPrice"] = data.pop("gas_price")

        data.pop("type")

        return data


class DynamicFeeTransaction(BaseTransaction):
    """
    Transactions that are post-EIP-1559 and use the ``maxFeePerGas``
    and ``maxPriorityFeePerGas`` fields.
    """

    max_fee: int = None  # type: ignore
    max_priority_fee: int = None  # type: ignore
    type: str = "0x2"

    def set_defaults(self, provider: ProviderAPI):
        if self.max_priority_fee is None:
            self.max_priority_fee = provider.priority_fee

        if self.max_fee is None:
            self.max_fee = provider.base_fee + self.max_priority_fee
        # else: Assume user specified the correct amount or txn will fail and waste gas

        super().set_defaults(provider)

    def as_dict(self):
        data = super().as_dict()
        if "max_fee" in data:
            data["maxFeePerGas"] = data.pop("max_fee")
        if "max_priority_fee" in data:
            data["maxPriorityFeePerGas"] = data.pop("max_priority_fee")

        return data


class Receipt(ReceiptAPI):
    def raise_for_status(self, txn: TransactionAPI):
        """
        Raises :class`~ape.exceptions.OutOfGasError` when the
        transaction failed and consumed all the gas.

        Raises :class:`~ape.exceptions.TransactionError`
        when the transaction has a failing status otherwise.
        """
        if not isinstance(txn, BaseTransaction):
            return

        gas_limit = txn.gas_limit
        if gas_limit and self.ran_out_of_gas(gas_limit):
            raise OutOfGasError()
        elif self.status != TransactionStatusEnum.NO_ERROR:
            txn_hash = HexBytes(self.txn_hash).hex()
            raise TransactionError(message=f"Transaction '{txn_hash}' failed.")

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
    transaction_class_map = {
        "0x0": StaticFeeTransaction,
        "0x2": DynamicFeeTransaction,
    }
    receipt_class = Receipt

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
    ) -> BaseTransaction:
        kwargs["type"], txn_type = self._extract_transaction_type(**kwargs)
        txn = txn_type(**kwargs)  # type: ignore
        txn.data = deployment_bytecode

        # Encode args, if there are any
        if abi:
            txn.data += self.encode_calldata(abi, *args)

        return txn  # type: ignore

    def encode_transaction(
        self,
        address: AddressType,
        abi: ABI,
        *args,
        **kwargs,
    ) -> BaseTransaction:
        kwargs["type"], txn_type = self._extract_transaction_type(**kwargs)
        txn = txn_type(receiver=address, **kwargs)  # type: ignore

        # Add method ID
        txn.data = keccak(to_bytes(text=abi.selector))[:4]
        txn.data += self.encode_calldata(abi, *args)

        return txn  # type: ignore

    def _extract_transaction_type(self, **kwargs) -> Tuple[str, Type[TransactionAPI]]:
        if "type" in kwargs:
            txn_type_code = str(kwargs["type"])
            # Allows non 0x-prefixed transaction type IDs
            if not txn_type_code.startswith("0x"):
                txn_type_code = kwargs["type"] = f"0x{txn_type_code}"
        elif "gas_price" in kwargs:
            txn_type_code = "0x0"
        else:
            txn_type_code = "0x2"

        return txn_type_code, self.transaction_class_map[txn_type_code]

    def decode_event(self, abi: ABI, receipt: "ReceiptAPI") -> "ContractLog":
        filter_id = keccak(to_bytes(text=abi.selector))
        event_data = next(log for log in receipt.logs if log["filter_id"] == filter_id)
        return ContractLog(  # type: ignore
            name=abi.name,
            inputs={i.name: event_data[i.name] for i in abi.inputs},
        )
