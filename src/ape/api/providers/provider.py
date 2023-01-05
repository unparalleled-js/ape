from pathlib import Path
from typing import Any, Iterator, List, Optional, cast

from eth_utils import is_hex
from hexbytes import HexBytes
from pydantic import Field, root_validator, validator
from web3.exceptions import ContractLogicError as Web3ContractLogicError

from ape.api.config import PluginConfig
from ape.api.networks import NetworkAPI
from ape.api.query import BlockTransactionQuery
from ape.api.transactions import ReceiptAPI, TransactionAPI
from ape.exceptions import (
    APINotImplementedError,
    ContractLogicError,
    TransactionError,
    VirtualMachineError,
)
from ape.logging import logger
from ape.types import (
    AddressType,
    BlockID,
    CallTreeNode,
    ContractCode,
    ContractLog,
    LogFilter,
    SnapshotID,
    TraceFrame,
)
from ape.utils import EMPTY_BYTES32, BaseInterfaceModel, abstractmethod, cached_property, raises_not_implemented


class BlockAPI(BaseInterfaceModel):
    """
    An abstract class representing a block and its attributes.
    """

    # NOTE: All fields in this class (and it's subclasses) should not be `Optional`
    #       except the edge cases noted below

    num_transactions: int = 0
    hash: Optional[Any] = None  # NOTE: pending block does not have a hash
    number: Optional[int] = None  # NOTE: pending block does not have a number
    parent_hash: Any = Field(
        EMPTY_BYTES32, alias="parentHash"
    )  # NOTE: genesis block has no parent hash
    size: int
    timestamp: int

    @root_validator(pre=True)
    def convert_parent_hash(cls, data):
        parent_hash = data.get("parent_hash", data.get("parentHash")) or EMPTY_BYTES32
        data["parentHash"] = parent_hash
        return data

    @validator("hash", "parent_hash", pre=True)
    def validate_hexbytes(cls, value):
        # NOTE: pydantic treats these values as bytes and throws an error
        if value and not isinstance(value, HexBytes):
            raise ValueError(f"Hash `{value}` is not a valid Hexbytes.")

        return value

    @cached_property
    def transactions(self) -> List[TransactionAPI]:
        query = BlockTransactionQuery(columns=["*"], block_id=self.hash)
        return cast(List[TransactionAPI], list(self.query_manager.query(query)))


class ProviderAPI(BaseInterfaceModel):
    """
    An abstraction of a connection to a network in an ecosystem. Example ``ProviderAPI``
    implementations include the `ape-infura <https://github.com/ApeWorX/ape-infura>`__
    plugin or the `ape-hardhat <https://github.com/ApeWorX/ape-hardhat>`__ plugin.
    """

    name: str
    """The name of the provider (should be the plugin name)."""

    network: NetworkAPI
    """A reference to the network this provider provides."""

    provider_settings: dict
    """The settings for the provider, as overrides to the configuration."""

    data_folder: Path
    """The path to the  ``.ape`` directory."""

    request_header: dict
    """A header to set on HTTP/RPC requests."""

    cached_chain_id: Optional[int] = None
    """Implementation providers may use this to cache and re-use chain ID."""

    block_page_size: int = 100
    """
    The amount of blocks to fetch in a response, as a default.
    This is particularly useful for querying logs across a block range.
    """

    concurrency: int = 4
    """
    How many parallel threads to use when fetching logs.
    """

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """
        ``True`` if currently connected to the provider. ``False`` otherwise.
        """

    @abstractmethod
    def connect(self):
        """
        Connect a to a provider, such as start-up a process or create an HTTP connection.
        """

    @abstractmethod
    def disconnect(self):
        """
        Disconnect from a provider, such as tear-down a process or quit an HTTP session.
        """

    @abstractmethod
    def update_settings(self, new_settings: dict):
        """
        Change a provider's setting, such as configure a new port to run on.
        May require a reconnect.

        Args:
            new_settings (dict): The new provider settings.
        """

    @property
    @abstractmethod
    def chain_id(self) -> int:
        """
        The blockchain ID.
        See `ChainList <https://chainlist.org/>`__ for a comprehensive list of IDs.
        """

    @abstractmethod
    def get_balance(self, address: str) -> int:
        """
        Get the balance of an account.

        Args:
            address (str): The address of the account.

        Returns:
            int: The account balance.
        """

    @abstractmethod
    def get_code(self, address: AddressType) -> ContractCode:
        """
        Get the bytes a contract.

        Args:
            address (``AddressType``): The address of the contract.

        Returns:
            :class:`~ape.types.ContractCode`: The contract bytecode.
        """

    @raises_not_implemented
    def get_storage_at(self, address: str, slot: int) -> bytes:  # type: ignore[empty-body]
        """
        Gets the raw value of a storage slot of a contract.

        Args:
            address (str): The address of the contract.
            slot (int): Storage slot to read the value of.

        Returns:
            bytes: The value of the storage slot.
        """

    @abstractmethod
    def get_nonce(self, address: AddressType) -> int:
        """
        Get the number of times an account has transacted.

        Args:
            address (``AddressType``): The address of the account.

        Returns:
            int
        """

    @abstractmethod
    def estimate_gas_cost(self, txn: TransactionAPI) -> int:
        """
        Estimate the cost of gas for a transaction.

        Args:
            txn (:class:`~ape.api.transactions.TransactionAPI`):
                The transaction to estimate the gas for.

        Returns:
            int: The estimated cost of gas to execute the transaction
            reported in the fee-currency's smallest unit, e.g. Wei.
        """

    @property
    @abstractmethod
    def gas_price(self) -> int:
        """
        The price for what it costs to transact
        (pre-`EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__).
        """

    @property
    def max_gas(self) -> int:
        """
        The max gas limit value you can use.
        """
        # TODO: Make abstract
        return 0

    @property
    def config(self) -> PluginConfig:
        """
        The provider's configuration.
        """
        return self.config_manager.get_config(self.name)

    @property
    def priority_fee(self) -> int:
        """
        A miner tip to incentivize them to include your transaction in a block.

        Raises:
            NotImplementedError: When the provider does not implement
              `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__ typed transactions.
        """
        raise APINotImplementedError("priority_fee is not implemented by this provider")

    @property
    def supports_tracing(self) -> bool:
        """
        ``True`` when the provider can provide transaction traces.
        """
        return False

    @property
    def base_fee(self) -> int:
        """
        The minimum value required to get your transaction included on the next block.
        Only providers that implement `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__
        will use this property.

        Raises:
            NotImplementedError: When this provider does not implement
              `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__.
        """
        raise APINotImplementedError("base_fee is not implemented by this provider")

    @abstractmethod
    def get_block(self, block_id: BlockID) -> BlockAPI:
        """
        Get a block.

        Args:
            block_id (:class:`~ape.types.BlockID`): The ID of the block to get.
                Can be ``"latest"``, ``"earliest"``, ``"pending"``, a block hash or a block number.

        Raises:
            :class:`~ape.exceptions.BlockNotFoundError`: Likely the exception raised when a block
              is not found (depends on implementation).

        Returns:
            :class:`~ape.types.BlockID`: The block for the given ID.
        """

    @abstractmethod
    def send_call(self, txn: TransactionAPI, **kwargs) -> bytes:  # Return value of function
        """
        Execute a new transaction call immediately without creating a
        transaction on the blockchain.

        Args:
            txn (:class:`~ape.api.transactions.TransactionAPI`): The transaction
              to send as a call.

        Returns:
            str: The result of the transaction call.
        """

    @abstractmethod
    def get_receipt(self, txn_hash: str) -> ReceiptAPI:
        """
        Get the information about a transaction from a transaction hash.

        Args:
            txn_hash (str): The hash of the transaction to retrieve.

        Returns:
            :class:`~api.providers.ReceiptAPI`:
            The receipt of the transaction with the given hash.
        """

    @abstractmethod
    def get_transactions_by_block(self, block_id: BlockID) -> Iterator[TransactionAPI]:
        """
        Get the information about a set of transactions from a block.

        Args:
            block_id (:class:`~ape.types.BlockID`): The ID of the block.

        Returns:
            Iterator[:class: `~ape.api.transactions.TransactionAPI`]
        """

    @abstractmethod
    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        """
        Send a transaction to the network.

        Args:
            txn (:class:`~ape.api.transactions.TransactionAPI`): The transaction to send.

        Returns:
            :class:`~ape.api.transactions.ReceiptAPI`
        """

    @abstractmethod
    def get_contract_logs(self, log_filter: LogFilter) -> Iterator[ContractLog]:
        """
        Get logs from contracts.

        Args:
            log_filter (:class:`~ape.types.LogFilter`): A mapping of event ABIs to
              topic filters. Defaults to getting all events.

        Returns:
            Iterator[:class:`~ape.types.ContractLog`]
        """

    @raises_not_implemented
    def snapshot(self) -> SnapshotID:  # type: ignore[empty-body]
        """
        Defined to make the ``ProviderAPI`` interchangeable with a
        :class:`~ape.api.providers.TestProviderAPI`, as in
        :class:`ape.managers.chain.ChainManager`.

        Raises:
            NotImplementedError: Unless overridden.
        """

    @raises_not_implemented
    def revert(self, snapshot_id: SnapshotID):  # type: ignore[empty-body]
        """
        Defined to make the ``ProviderAPI`` interchangeable with a
        :class:`~ape.api.providers.TestProviderAPI`, as in
        :class:`ape.managers.chain.ChainManager`.

        Raises:
            NotImplementedError: Unless overridden.
        """

    @raises_not_implemented
    def set_timestamp(self, new_timestamp: int):  # type: ignore[empty-body]
        """
        Defined to make the ``ProviderAPI`` interchangeable with a
        :class:`~ape.api.providers.TestProviderAPI`, as in
        :class:`ape.managers.chain.ChainManager`.

        Raises:
            NotImplementedError: Unless overridden.
        """

    @raises_not_implemented
    def mine(self, num_blocks: int = 1):  # type: ignore[empty-body]
        """
        Defined to make the ``ProviderAPI`` interchangeable with a
        :class:`~ape.api.providers.TestProviderAPI`, as in
        :class:`ape.managers.chain.ChainManager`.

        Raises:
            NotImplementedError: Unless overridden.
        """

    @raises_not_implemented
    def set_balance(self, address: AddressType, amount: int):  # type: ignore[empty-body]
        """
        Change the balance of an account.

        Args:
            address (AddressType): An address on the network.
            amount (int): The balance to set in the address.
        """

    def __repr__(self) -> str:
        try:
            chain_id = self.chain_id
        except Exception as err:
            logger.error(str(err))
            chain_id = None

        return f"<{self.name} chain_id={self.chain_id}>" if chain_id else f"<{self.name}>"

    @raises_not_implemented
    def set_code(  # type: ignore[empty-body]
        self, address: AddressType, code: ContractCode
    ) -> bool:
        """
        Change the code of a smart contract, for development purposes.
        Test providers implement this method when they support it.

        Args:
            address (AddressType): An address on the network.
            code (:class:`~ape.types.ContractCode`): The new bytecode.
        """

    @raises_not_implemented
    def unlock_account(self, address: AddressType) -> bool:  # type: ignore[empty-body]
        """
        Ask the provider to allow an address to submit transactions without validating
        signatures. This feature is intended to be subclassed by a
        :class:`~ape.api.providers.TestProviderAPI` so that during a fork-mode test,
        a transaction can be submitted by an arbitrary account or contract without a private key.

        Raises:
            NotImplementedError: When this provider does not support unlocking an account.

        Args:
            address (``AddressType``): The address to unlock.

        Returns:
            bool: ``True`` if successfully unlocked account and ``False`` otherwise.
        """

    @raises_not_implemented
    def get_transaction_trace(  # type: ignore[empty-body]
        self, txn_hash: str
    ) -> Iterator[TraceFrame]:
        """
        Provide a detailed description of opcodes.

        Args:
            txn_hash (str): The hash of a transaction to trace.

        Returns:
            Iterator(:class:`~ape.types.trace.TraceFrame`): Transaction execution
            trace object.
        """

    @raises_not_implemented
    def get_call_tree(self, txn_hash: str) -> CallTreeNode:  # type: ignore[empty-body]
        """
        Create a tree structure of calls for a transaction.

        Args:
            txn_hash (str): The hash of a transaction to trace.

        Returns:
            :class:`~ape.types.trace.CallTreeNode`: Transaction execution call-tree objects.
        """

    def prepare_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        """
        Set default values on the transaction.

        Raises:
            :class:`~ape.exceptions.TransactionError`: When given negative required confirmations.

        Args:
            txn (:class:`~ape.api.transactions.TransactionAPI`): The transaction to prepare.

        Returns:
            :class:`~ape.api.transactions.TransactionAPI`
        """

        # NOTE: Use "expected value" for Chain ID, so if it doesn't match actual, we raise
        txn.chain_id = self.network.chain_id

        from ape_ethereum.transactions import StaticFeeTransaction, TransactionType

        txn_type = TransactionType(txn.type)
        if (
            txn_type == TransactionType.STATIC
            and isinstance(txn, StaticFeeTransaction)
            and txn.gas_price is None
        ):
            txn.gas_price = self.gas_price
        elif txn_type == TransactionType.DYNAMIC:
            if txn.max_priority_fee is None:
                txn.max_priority_fee = self.priority_fee

            if txn.max_fee is None:
                txn.max_fee = self.base_fee + txn.max_priority_fee
            # else: Assume user specified the correct amount or txn will fail and waste gas

        gas_limit = txn.gas_limit or self.network.gas_limit
        if isinstance(gas_limit, str) and gas_limit.isnumeric():
            txn.gas_limit = int(gas_limit)
        elif isinstance(gas_limit, str) and is_hex(gas_limit):
            txn.gas_limit = int(gas_limit, 16)
        elif gas_limit == "max":
            txn.gas_limit = self.max_gas
        elif gas_limit in ("auto", None):
            txn.gas_limit = self.estimate_gas_cost(txn)
        else:
            txn.gas_limit = gas_limit

        assert txn.gas_limit not in ("auto", "max")
        # else: Assume user specified the correct amount or txn will fail and waste gas

        if txn.required_confirmations is None:
            txn.required_confirmations = self.network.required_confirmations
        elif not isinstance(txn.required_confirmations, int) or txn.required_confirmations < 0:
            raise TransactionError(message="'required_confirmations' must be a positive integer.")

        return txn

    def get_virtual_machine_error(self, exception: Exception) -> VirtualMachineError:
        """
        Get a virtual machine error from an error returned from your RPC.
        If from a contract revert / assert statement, you will be given a
        special :class:`~ape.exceptions.ContractLogicError` that can be
        checked in ``ape.reverts()`` tests.

        **NOTE**: The default implementation is based on ``geth`` output.
        ``ProviderAPI`` implementations override when needed.

        Args:
            exception (Exception): The error returned from your RPC client.

        Returns:
            :class:`~ape.exceptions.VirtualMachineError`: An error representing what
               went wrong in the call.
        """

        if isinstance(exception, Web3ContractLogicError):
            # This happens from `assert` or `require` statements.
            message = str(exception).split(":")[-1].strip()
            if message == "execution reverted":
                # Reverted without an error message
                raise ContractLogicError()

            return ContractLogicError(revert_message=message)

        if not len(exception.args):
            return VirtualMachineError(base_err=exception)

        err_data = exception.args[0] if (hasattr(exception, "args") and exception.args) else None
        if not isinstance(err_data, dict):
            return VirtualMachineError(base_err=exception)

        err_msg = err_data.get("message")
        if not err_msg:
            return VirtualMachineError(base_err=exception)

        return VirtualMachineError(message=str(err_msg), code=err_data.get("code"))

class TestProviderAPI(ProviderAPI):
    """
    An API for providers that have development functionality, such as snapshotting.
    """

    @cached_property
    def test_config(self) -> PluginConfig:
        return self.config_manager.get_config("test")

    @abstractmethod
    def snapshot(self) -> SnapshotID:
        """
        Record the current state of the blockchain with intent to later
        call the method :meth:`~ape.managers.chain.ChainManager.revert`
        to go back to this point. This method is for local networks only.

        Returns:
            :class:`~ape.types.SnapshotID`: The snapshot ID.
        """

    @abstractmethod
    def revert(self, snapshot_id: SnapshotID):
        """
        Regress the current call using the given snapshot ID.
        Allows developers to go back to a previous state.

        Args:
            snapshot_id (str): The snapshot ID.
        """

    @abstractmethod
    def set_timestamp(self, new_timestamp: int):
        """
        Change the pending timestamp.

        Args:
            new_timestamp (int): The timestamp to set.

        Returns:
            int: The new timestamp.
        """

    @abstractmethod
    def mine(self, num_blocks: int = 1):
        """
        Advance by the given number of blocks.

        Args:
            num_blocks (int): The number of blocks allotted to mine. Defaults to ``1``.
        """


class UpstreamProvider(ProviderAPI):
    """
    A provider that can also be set as another provider's upstream.
    """

    @property
    @abstractmethod
    def connection_str(self) -> str:
        """
        The str used by downstream providers to connect to this one.
        For example, the URL for HTTP-based providers.
        """
