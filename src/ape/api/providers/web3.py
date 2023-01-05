import re
from abc import ABC
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterator, List, Optional, cast

from eth_abi.exceptions import InsufficientDataBytes
from eth_typing import HexStr
from eth_utils import add_0x_prefix, to_hex
from evm_trace import CallTreeNode as EvmCallTreeNode
from hexbytes import HexBytes
from web3 import Web3
from web3.eth import TxParams
from web3.exceptions import BlockNotFound, TimeExhausted
from web3.types import RPCEndpoint

from ape.api.networks import LOCAL_NETWORK_NAME
from ape.api.providers.provider import BlockAPI, ProviderAPI
from ape.api.transactions import ReceiptAPI, TransactionAPI
from ape.exceptions import (
    APINotImplementedError,
    BlockNotFoundError,
    ContractLogicError,
    ProviderError,
    ProviderNotConnectedError,
    TransactionError,
    TransactionNotFoundError,
    VirtualMachineError, DecodingError,
)
from ape.logging import logger
from ape.types import AddressType, BlockID, CallTreeNode, ContractCode, ContractLog, LogFilter
from ape.utils import cached_property, gas_estimation_error_message, run_until_complete

_DEFAULT_TRACE_GAS_PATTERN = re.compile(r"\[\d* gas]")
_DEFAULT_WRAP_THRESHOLD = 50
_DEFAULT_INDENT = 2
_ETH_TRANSFER = "Transferring ETH"


class Web3Provider(ProviderAPI, ABC):
    """
    A base provider mixin class that uses the
    `web3.py <https://web3py.readthedocs.io/en/stable/>`__ python package.
    """

    _web3: Optional[Web3] = None
    _client_version: Optional[str] = None

    @property
    def web3(self) -> Web3:
        """
        Access to the ``web3`` object as if you did ``Web3(HTTPProvider(uri))``.
        """

        if not self._web3:
            raise ProviderNotConnectedError()

        return self._web3

    @property
    def client_version(self) -> str:
        if not self._web3:
            return ""

        # NOTE: Gets reset to `None` on `connect()` and `disconnect()`.
        if self._client_version is None:
            self._client_version = self.web3.clientVersion

        return self._client_version

    @property
    def base_fee(self) -> int:
        block = self.get_block("latest")
        if not hasattr(block, "base_fee"):
            raise APINotImplementedError("No base fee found in block.")
        else:
            base_fee = block.base_fee  # type: ignore

        if base_fee is None:
            # Non-EIP-1559 chains or we time-travelled pre-London fork.
            raise APINotImplementedError("base_fee is not implemented by this provider.")

        return base_fee

    @property
    def is_connected(self) -> bool:
        if self._web3 is None:
            return False

        return run_until_complete(self._web3.is_connected())

    @property
    def max_gas(self) -> int:
        block = self.web3.eth.get_block("latest")
        return block["gasLimit"]

    @cached_property
    def supports_tracing(self) -> bool:
        try:
            self.get_call_tree(None)
        except APINotImplementedError:
            return False
        except Exception:
            return True

        return True

    def update_settings(self, new_settings: dict):
        self.disconnect()
        self.provider_settings.update(new_settings)
        self.connect()

    def estimate_gas_cost(self, txn: TransactionAPI, **kwargs) -> int:
        """
        Estimate the cost of gas for a transaction.

        Args:
            txn (:class:`~ape.api.transactions.TransactionAPI`):
                The transaction to estimate the gas for.
            kwargs:
                * ``block_identifier`` (:class:`~ape.types.BlockID`): The block ID
                  to use when estimating the transaction. Useful for
                  checking a past estimation cost of a transaction.
                * ``state_overrides`` (Dict): Modify the state of the blockchain
                  prior to estimation.

        Returns:
            int: The estimated cost of gas to execute the transaction
            reported in the fee-currency's smallest unit, e.g. Wei. If the
            provider's network has been configured with a gas limit override, it
            will be returned. If the gas limit configuration is "max" this will
            return the block maximum gas limit.
        """

        txn_dict = txn.dict()

        # NOTE: "auto" means to enter this method, so remove it from dict
        if "gas" in txn_dict and txn_dict["gas"] == "auto":
            txn_dict.pop("gas")
            # Also pop these, they are overriden by "auto"
            txn_dict.pop("maxFeePerGas", None)
            txn_dict.pop("maxPriorityFeePerGas", None)

        try:
            block_id = kwargs.pop("block_identifier", None)
            txn_params = cast(TxParams, txn_dict)
            return self.web3.eth.estimate_gas(txn_params, block_identifier=block_id)
        except ValueError as err:
            tx_error = self.get_virtual_machine_error(err)

            # If this is the cause of a would-be revert,
            # raise ContractLogicError so that we can confirm tx-reverts.
            if isinstance(tx_error, ContractLogicError):
                raise tx_error from err

            message = gas_estimation_error_message(tx_error)
            raise TransactionError(base_err=tx_error, message=message) from err

    @property
    def chain_id(self) -> int:
        default_chain_id = None
        if self.network.name not in (
            "adhoc",
            LOCAL_NETWORK_NAME,
        ) and not self.network.name.endswith("-fork"):
            # If using a live network, the chain ID is hardcoded.
            default_chain_id = self.network.chain_id

        try:
            if hasattr(self.web3, "eth"):
                return self.web3.eth.chain_id

        except ProviderNotConnectedError:
            if default_chain_id is not None:
                return default_chain_id

            raise  # Original error

        if default_chain_id is not None:
            return default_chain_id

        raise ProviderNotConnectedError()

    @property
    def gas_price(self) -> int:
        return self._web3.eth.generate_gas_price()  # type: ignore

    @property
    def priority_fee(self) -> int:
        return self.web3.eth.max_priority_fee

    def get_block(self, block_id: BlockID) -> BlockAPI:
        if isinstance(block_id, str) and block_id.isnumeric():
            block_id = int(block_id)

        try:
            block_data = dict(self.web3.eth.get_block(block_id))
        except BlockNotFound as err:
            raise BlockNotFoundError(block_id) from err

        return self.network.ecosystem.decode_block(block_data)

    def get_nonce(self, address: str, **kwargs) -> int:
        """
        Get the number of times an account has transacted.

        Args:
            address (str): The address of the account.
            kwargs:
                * ``block_identifier`` (:class:`~ape.types.BlockID`): The block ID
                  for checking a previous account nonce.

        Returns:
            int
        """

        block_id = kwargs.pop("block_identifier", None)
        return self.web3.eth.get_transaction_count(address, block_identifier=block_id)

    def get_balance(self, address: str) -> int:
        return self.web3.eth.get_balance(address)

    def get_code(self, address: AddressType) -> ContractCode:
        return self.web3.eth.get_code(address)

    def get_storage_at(self, address: str, slot: int, **kwargs) -> bytes:
        """
        Gets the raw value of a storage slot of a contract.

        Args:
            address (str): The address of the contract.
            slot (int): Storage slot to read the value of.
            kwargs:
                * ``block_identifier`` (:class:`~ape.types.BlockID`): The block ID
                  for checking previous contract storage values.

        Returns:
            bytes: The value of the storage slot.
        """

        block_id = kwargs.pop("block_identifier", None)
        try:
            return self.web3.eth.get_storage_at(address, slot, block_identifier=block_id)
        except ValueError as err:
            if "RPC Endpoint has not been implemented" in str(err):
                raise APINotImplementedError(str(err)) from err

            raise  # Raise original error

    def send_call(self, txn: TransactionAPI, **kwargs) -> bytes:
        """
        Execute a new transaction call immediately without creating a
        transaction on the block chain.

        Args:
            txn: :class:`~ape.api.transactions.TransactionAPI`
            kwargs:
                * ``block_identifier`` (:class:`~ape.types.BlockID`): The block ID
                  to use to send a call at a historical point of a contract.
                  checking a past estimation cost of a transaction.
                * ``state_overrides`` (Dict): Modify the state of the blockchain
                  prior to sending the call, for testing purposes.
                * ``show_trace`` (bool): Set to ``True`` to display the call's
                  trace. Defaults to ``False``.
                * ``show_gas_report (bool): Set to ``True`` to display the call's
                  gas report. Defaults to ``False``.
                * ``skip_trace`` (bool): Set to ``True`` to skip the trace no matter
                  what. This is useful if you are making a more background contract call
                  of some sort, such as proxy-checking, and you are running a global
                  call-tracer such as using the ``--gas`` flag in tests.

        Returns:
            str: The result of the transaction call.
        """
        skip_trace = kwargs.pop("skip_trace", False)
        if skip_trace:
            return self._send_call(txn, **kwargs)

        track_gas = self.chain_manager._reports.track_gas
        show_trace = kwargs.pop("show_trace", False)
        show_gas = kwargs.pop("show_gas_report", False)
        needs_trace = track_gas or show_trace or show_gas
        if not needs_trace or not self.provider.supports_tracing or not txn.receiver:
            return self._send_call(txn, **kwargs)

        # The user is requesting information related to a call's trace,
        # such as gas usage data.
        try:
            with self.chain_manager.isolate():
                return self._send_call_as_txn(
                    txn, track_gas=track_gas, show_trace=show_trace, show_gas=show_gas, **kwargs
                )

        except APINotImplementedError:
            return self._send_call(txn, **kwargs)

    def _send_call_as_txn(
        self,
        txn: TransactionAPI,
        track_gas: bool = False,
        show_trace: bool = False,
        show_gas: bool = False,
        **kwargs,
    ) -> bytes:
        account = self.account_manager.test_accounts[0]
        receipt = account.call(txn)
        call_tree = receipt.call_tree
        if not call_tree:
            return self._send_call(txn, **kwargs)

        if track_gas:
            receipt.track_gas()
        if show_trace:
            self.chain_manager._reports.show_trace(call_tree)
        if show_gas:
            self.chain_manager._reports.show_gas(call_tree)

        return call_tree.returndata

    def _send_call(self, txn: TransactionAPI, **kwargs) -> bytes:
        arguments = self._prepare_call(txn, **kwargs)
        return self._eth_call(arguments)

    def _eth_call(self, arguments: List) -> bytes:
        try:
            result = self._make_request("eth_call", arguments)
        except Exception as err:
            raise self.get_virtual_machine_error(err) from err

        return HexBytes(result)

    def _prepare_call(self, txn: TransactionAPI, **kwargs) -> List:
        txn_dict = txn.dict()
        fields_to_convert = ("data", "chainId", "value")
        for field in fields_to_convert:
            value = txn_dict.get(field)
            if value is not None and not isinstance(value, str):
                txn_dict[field] = to_hex(value)

        # Remove unneeded properties
        txn_dict.pop("gas", None)
        txn_dict.pop("gasLimit", None)
        txn_dict.pop("maxFeePerGas", None)
        txn_dict.pop("maxPriorityFeePerGas", None)

        block_identifier = kwargs.pop("block_identifier", "latest")
        if isinstance(block_identifier, int):
            block_identifier = to_hex(block_identifier)
        arguments = [txn_dict, block_identifier]
        if "state_override" in kwargs:
            arguments.append(kwargs["state_override"])

        return arguments

    def get_receipt(
        self, txn_hash: str, required_confirmations: int = 0, timeout: Optional[int] = None
    ) -> ReceiptAPI:
        """
        Get the information about a transaction from a transaction hash.

        Args:
            txn_hash (str): The hash of the transaction to retrieve.
            required_confirmations (int): The amount of block confirmations
              to wait before returning the receipt. Defaults to ``0``.
            timeout (Optional[int]): The amount of time to wait for a receipt
              before timing out. Defaults ``None``.

        Raises:
            :class:`~ape.exceptions.TransactionNotFoundError`: Likely the exception raised
              when the transaction receipt is not found (depends on implementation).

        Returns:
            :class:`~api.providers.ReceiptAPI`:
            The receipt of the transaction with the given hash.
        """

        if required_confirmations < 0:
            raise TransactionError(message="Required confirmations cannot be negative.")

        timeout = (
            timeout if timeout is not None else self.provider.network.transaction_acceptance_timeout
        )

        try:
            receipt_data = self.web3.eth.wait_for_transaction_receipt(
                HexBytes(txn_hash), timeout=timeout
            )
        except TimeExhausted as err:
            raise TransactionNotFoundError(txn_hash) from err

        txn = dict(self.web3.eth.get_transaction(HexStr(txn_hash)))
        receipt = self.network.ecosystem.decode_receipt(
            {
                "provider": self,
                "required_confirmations": required_confirmations,
                **txn,
                **receipt_data,
            }
        )
        return receipt.await_confirmations()

    def get_transactions_by_block(self, block_id: BlockID) -> Iterator:
        if isinstance(block_id, str):
            block_id = HexStr(block_id)

            if block_id.isnumeric():
                block_id = add_0x_prefix(block_id)

        block = cast(Dict, self.web3.eth.get_block(block_id, full_transactions=True))
        for transaction in block.get("transactions", []):
            yield self.network.ecosystem.create_transaction(**transaction)

    def block_ranges(self, start=0, stop=None, page=None):
        if stop is None:
            stop = self.chain_manager.blocks.height
        if page is None:
            page = self.block_page_size

        for start_block in range(start, stop + 1, page):
            stop_block = min(stop, start_block + page - 1)
            yield start_block, stop_block

    def get_contract_logs(self, log_filter: LogFilter) -> Iterator[ContractLog]:
        height = self.chain_manager.blocks.height
        start_block = log_filter.start_block
        stop_block_arg = log_filter.stop_block if log_filter.stop_block is not None else height
        stop_block = min(stop_block_arg, height)
        block_ranges = self.block_ranges(start_block, stop_block, self.block_page_size)

        def fetch_log_page(block_range):
            start, stop = block_range
            page_filter = log_filter.copy(update=dict(start_block=start, stop_block=stop))
            # eth-tester expects a different format, let web3 handle the conversions for it
            raw = "EthereumTester" not in self.client_version
            logs = self._get_logs(page_filter.dict(), raw)
            return self.network.ecosystem.decode_logs(logs, *log_filter.events)

        with ThreadPoolExecutor(self.concurrency) as pool:
            for page in pool.map(fetch_log_page, block_ranges):
                yield from page

    def _get_logs(self, filter_params, raw=True) -> List[Dict]:
        if not raw:
            return [vars(d) for d in self.web3.eth.get_logs(filter_params)]

        return self._make_request("eth_getLogs", [filter_params])

    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        try:
            txn_hash = self.web3.eth.send_raw_transaction(txn.serialize_transaction())
        except ValueError as err:
            vm_err = self.get_virtual_machine_error(err)

            if "nonce too low" in str(vm_err):
                # Add additional nonce information
                new_err_msg = f"Nonce '{txn.nonce}' is too low"
                raise VirtualMachineError(
                    base_err=vm_err.base_err, message=new_err_msg, code=vm_err.code
                )

            vm_err.txn = txn
            raise vm_err from err

        receipt = self.get_receipt(
            txn_hash.hex(),
            required_confirmations=(
                txn.required_confirmations
                if txn.required_confirmations is not None
                else self.network.required_confirmations
            ),
        )

        if receipt.failed:
            txn_dict = receipt.transaction.dict()
            txn_params = cast(TxParams, txn_dict)

            # Replay txn to get revert reason
            try:
                self.web3.eth.call(txn_params)
            except Exception as err:
                vm_err = self.get_virtual_machine_error(err)
                vm_err.txn = txn
                raise vm_err from err

        logger.info(f"Confirmed {receipt.txn_hash} (total fees paid = {receipt.total_fees_paid})")
        self.chain_manager.account_history.append(receipt)
        return receipt

    def enrich_call_tree(self, call: CallTreeNode) -> CallTreeNode:
        """
        Handles EVM-specific logic for creating a CallTreeNode.
        Called in EVM implementations of
        :class:`~ape.api.providers.ProviderAPI.get_call_tree`.
        """

        address = self.provider.network.ecosystem.decode_address(call.address)

        # Collapse pre-compile address calls
        address_int = int(address, 16)
        if 1 <= address_int <= 9:
            sub_trees = [self._get_call_tree_node(c) for c in call.calls]
            if len(sub_trees) == 1:
                return sub_trees[0]

            intermediary_node = CallTreeNode(address=str(address_int))
            for sub_tree in sub_trees:
                intermediary_node.add(sub_tree)

            return intermediary_node

        contract_type = self.chain_manager.contracts.get(address)
        selector = call.calldata[:4]
        call_signature = ""

        # def _dim_default_gas(call_sig: str) -> str:
        #     # Add style to default gas block so it matches nodes with contract types
        #     gas_part = re.findall(_DEFAULT_TRACE_GAS_PATTERN, call_sig)
        #     if gas_part:
        #         return f"{call_sig.split(gas_part[0])[0]} [{TraceStyles.GAS_COST}]{gas_part[0]}[/]"
        #
        #     return call_sig

        if contract_type:

            call = CallTreeNode

            contract_id = self._get_contract_id(address, contract_type=contract_type)
            method_abi = contract_type.methods[selector]

            if method_abi:
                raw_calldata = call.calldata[4:]
                arguments = {
                    k: .decode_value(v)
                    for k, v in self.decode_calldata(method_abi, raw_calldata).items()
                }

                # The revert-message appears at the top of the trace output.
                try:
                    return_value = (
                        self.decode_returndata(method_abi, call.returndata)
                        if not call.failed
                        else None
                    )
                except (DecodingError, InsufficientDataBytes):
                    return_value = "<?>"

                method_id = method_abi.name or f"<{selector.hex()}>"
                call_signature = str(
                    _MethodTraceSignature(
                        contract_id,
                        method_id,
                        arguments,
                        return_value,
                        call.call_type,
                        colors=self.colors,
                        _indent=self._indent,
                        _wrap_threshold=self._wrap_threshold,
                    )
                )
                if call.gas_cost:
                    call_signature += f" [{TraceStyles.GAS_COST}][{call.gas_cost} gas][/]"

                if self._verbose:
                    extra_info = {
                        "address": address,
                        "value": call.value,
                        "gas_limit": call.gas_limit,
                        "call_type": call.call_type.value,
                    }
                    call_signature += f" {json.dumps(extra_info, indent=self._indent)}"
            elif contract_type.name and contract_id == contract_type.name:
                # The case where we know the contract name but couldn't decipher the method ID,
                #  such as an unsupported proxy or fallback.
                call_signature = next(TreeRepresentation.make_tree(call)).title
                call_signature = call_signature.replace(address, contract_id)
                call_signature = _dim_default_gas(call_signature)
        else:
            next_node: Optional[TreeRepresentation] = None
            try:
                # Use default representation
                next_node = next(TreeRepresentation.make_tree(call))
            except StopIteration:
                pass

            if next_node:
                call_signature = _dim_default_gas(next_node.title)

            else:
                # Only for mypy's sake. May never get here.
                call_signature = f"{address}.<{selector.hex()}>"
                if call.gas_cost:
                    call_signature = (
                        f"{call_signature} [{TraceStyles.GAS_COST}][{call.gas_cost} gas][/]"
                    )

        if call.value:
            eth_value = round(call.value / 10**18, 8)
            if eth_value:
                call_signature += f" [{self.colors.VALUE}][{eth_value} value][/]"

    def _make_request(self, endpoint: str, parameters: List) -> Any:
        coroutine = self.web3.provider.make_request(RPCEndpoint(endpoint), parameters)
        result = run_until_complete(coroutine)

        if "error" in result:
            error = result["error"]
            message = (
                error["message"] if isinstance(error, dict) and "message" in error else str(error)
            )
            raise ProviderError(message)

        elif "result" in result:
            return result.get("result", {})

        return result
