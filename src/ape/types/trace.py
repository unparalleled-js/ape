import fnmatch
from functools import cached_property
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, Union, cast

from eth_typing import Hash32
from eth_utils import humanize_hash, is_hex_address
from ethpm_types import ContractType, HexBytes
from ethpm_types.abi import MethodABI
from evm_trace.gas import merge_reports
from rich.table import Table
from rich.tree import Tree

from ape.exceptions import ContractError, DecodingError
from ape.utils import ZERO_ADDRESS, BaseInterfaceModel, Struct, parse_call_tree, parse_gas_table
from ape.utils.abi import _get_method_abi

if TYPE_CHECKING:
    from ape.types import AddressType, ContractFunctionPath, GasReport


_DEFAULT_WRAP_THRESHOLD = 50
_DEFAULT_INDENT = 2
_BASE_TRANSFER = "Transferring {}"


class TraceStyles:
    """
    Colors to use when displaying a call trace.
    Each item in the class points to the part of
    the trace it colors.
    """

    CONTRACTS = "#ff8c00"
    """Contract type names."""

    METHODS = "bright_green"
    """Method names; not including arguments or return values."""

    INPUTS = "bright_magenta"
    """Method arguments."""

    OUTPUTS = "bright_blue"
    """Method return values."""

    DELEGATE = "#d75f00"
    """The part '(delegate)' that appears before delegate calls."""

    VALUE = "#00afd7"
    """The transaction value, when it's > 0."""

    GAS_COST = "dim"
    """The gas used of the call."""


class TraceFrame(BaseInterfaceModel):
    pc: int
    op: str
    gas: int
    gas_cost: int
    depth: int


class CallTreeNode(BaseInterfaceModel):
    contract_address: "AddressType"
    method_id: str
    raw_tree: Dict
    transaction_hash: Optional[str] = None
    caller_address: Optional["AddressType"] = None

    # Display properties
    verbose: bool = False
    wrap_threshold: int = _DEFAULT_WRAP_THRESHOLD
    indent: int = _DEFAULT_INDENT
    colors: Union[TraceStyles, Type[TraceStyles]] = TraceStyles

    def __repr__(self) -> str:
        builder = ""
        call_type = self.raw_tree.get("call_type")
        builder += f"{call_type.value}:" if call_type else ""
        address = self.raw_tree.get("address")
        if address:
            try:
                checksum_address = self.provider.network.ecosystem.decode_address(address)
                builder += f" <{checksum_address}>"
            except Exception:
                builder += f" <{address}>"

        gas_cost = self.raw_tree.get("gas_cost", 0)
        builder += f" [{gas_cost} gas]"
        return builder

    def __getitem__(self, name: str) -> Any:
        return self.raw_tree[name]

    @cached_property
    def sub_trees(self) -> List["CallTreeNode"]:
        return [CallTreeNode(raw_tree=t, **self.dict()) for t in self.raw_tree.get("calls", [])]

    @cached_property
    def tree(self) -> Tree:
        return parse_call_tree(self)

    def _get_contract_id(
        self,
        address: "AddressType",
        contract_type: Optional[ContractType] = None,
        use_symbol: bool = True,
    ) -> str:
        if not contract_type:
            return self._get_contract_id_from_address(address)

        if use_symbol and "symbol" in contract_type.view_methods:
            # Use token symbol as name
            contract = self.chain_manager.contracts.instance_at(
                address, contract_type=contract_type, txn_hash=self.transaction_hash
            )

            try:
                symbol = contract.symbol()
                if symbol and str(symbol).strip():
                    return str(symbol).strip()

            except ContractError:
                pass

        contract_id = contract_type.name
        if contract_id:
            contract_id = contract_id.strip()
            if contract_id:
                return contract_id

        return self._get_contract_id(address)

    def _get_contract_id_from_address(self, address: "AddressType") -> str:
        if address in self.account_manager:
            return _BASE_TRANSFER.format(self.provider.network.ecosystem.fee_token_symbol)

        return address

    def _decode_calldata(self, method: MethodABI, raw_data: bytes) -> Dict:
        try:
            return self.provider.network.ecosystem.decode_calldata(method, raw_data)
        except DecodingError:
            return {i.name: "<?>" for i in method.inputs}

    def _decode_returndata(self, method: MethodABI) -> Any:
        raw_data = self.raw_tree["returndata"]
        values = [
            self._decode_value(v)
            for v in self.provider.network.ecosystem.decode_returndata(method, raw_data)
        ]

        if len(values) == 1:
            return values[0]

        return values

    def _decode_value(self, value):
        if isinstance(value, bytes):
            try:
                string_value = value.strip(b"\x00").decode("utf8")
                return f"'{string_value}'"
            except UnicodeDecodeError:
                # Truncate bytes if very long.
                if len(value) > 24:
                    return humanize_hash(cast(Hash32, value))

                hex_str = HexBytes(value).hex()
                if is_hex_address(hex_str):
                    return self._decode_value(hex_str)

                return hex_str

        elif isinstance(value, str) and is_hex_address(value):
            return self._decode_address(value)

        elif value and isinstance(value, str):
            # Surround non-address strings with quotes.
            return f'"{value}"'

        elif isinstance(value, (list, tuple)):
            return [self._decode_value(v) for v in value]

        elif isinstance(value, Struct):
            return {k: self._decode_value(v) for k, v in value.items()}

        return value

    def _decode_address(self, address: str) -> str:
        if address == ZERO_ADDRESS:
            return "ZERO_ADDRESS"

        elif self.caller_address is not None and address == self.caller_address:
            return "tx.origin"

        # Use name of known contract if possible.
        checksum_address = self.provider.network.ecosystem.decode_address(address)
        contract_type = self.chain_manager.contracts.get(checksum_address)
        if contract_type and contract_type.name:
            return contract_type.name

        return checksum_address

    @cached_property
    def gas_report(self) -> List[Table]:
        report = self.create_gas_report()
        return parse_gas_table(report)

    def create_gas_report(
        self, exclude: Optional[List["ContractFunctionPath"]] = None
    ) -> "GasReport":
        exclusions = exclude or []
        sub_calls = self.raw_tree.get("calls", [])
        this_method = self.create_gas_report
        exclude_arg = [exclusions for _ in sub_calls]
        address = self.provider.network.ecosystem.decode_address(self.raw_tree["address"])
        contract_type = self.chain_manager.contracts.get(address)
        selector = self.raw_tree["calldata"][:4]
        contract_id = self._get_contract_id(address, contract_type=contract_type, use_symbol=False)

        for exclusion in exclusions:
            if exclusion.method_name is not None:
                # Method-related excludes are handled below, even when contract also specified.
                continue

            if fnmatch.fnmatch(contract_id, exclusion.contract_name):
                # Skip this whole contract
                reports = list(map(this_method, exclude_arg))
                if len(reports) == 1:
                    return reports[0]
                elif len(reports) > 1:
                    return merge_reports(*reports)
                else:
                    return {}

        transfer_line = _BASE_TRANSFER.format(self.provider.network.ecosystem.fee_token_symbol)
        if contract_id == transfer_line and address in self.account_manager:
            receiver_id = self.account_manager[address].alias or address
            method_id = f"to:{receiver_id}"

        elif contract_id == transfer_line:
            method_id = f"to:{address}"

        elif contract_type:
            # NOTE: Use contract name when possible to distinguish between sources with the same
            #  symbol. Also, ape projects don't permit multiple contract types with the same name.
            method_abi = _get_method_abi(selector, contract_type)
            method_id = method_abi.name if method_abi else selector.hex()

            for exclusion in exclusions:
                if not exclusion.method_name:
                    # Full contract skips handled above.
                    continue

                elif not fnmatch.fnmatch(contract_id, exclusion.contract_name):
                    # Method may match, but contract does not match, so continue.
                    continue

                elif fnmatch.fnmatch(method_id, exclusion.method_name):
                    # Skip this report
                    reports = [r for r in map(this_method, exclude_arg)]
                    if len(reports) == 1:
                        return reports[0]
                    elif len(reports) > 1:
                        return merge_reports(*reports)
                    else:
                        return {}

        else:
            method_id = selector.hex()

        report = {
            contract_id: {
                method_id: [self.raw_tree["gas_cost"]]
                if self.raw_tree["gas_cost"] is not None
                else []
            }
        }
        reports = list(map(this_method, exclude_arg))
        if len(reports) >= 1:
            return merge_reports(report, *reports)

        return report
