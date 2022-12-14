import json
import re
from dataclasses import dataclass
from statistics import mean, median
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from eth_abi.exceptions import InsufficientDataBytes
from evm_trace import CallType
from evm_trace.base import CallTreeNode as EvmCallTreeNode
from evm_trace.display import TreeRepresentation
from pydantic import ValidationError
from rich.box import SIMPLE
from rich.table import Table
from rich.tree import Tree

from ape.exceptions import DecodingError
from ape.utils.abi import _get_method_abi

if TYPE_CHECKING:
    from ape.types import CallTreeNode, GasReport
    from ape.types.trace import TraceStyles


_DEFAULT_TRACE_GAS_PATTERN = re.compile(r"\[\d* gas]")


def parse_call_tree(root: "CallTreeNode") -> Tree:
    address = root.provider.network.ecosystem.decode_address(root["address"])

    # Collapse pre-compile address calls
    address_int = int(address, 16)
    if 1 <= address_int <= 9:
        if len(root.sub_trees) == 1:
            return parse_call_tree(root.sub_trees[0])

        intermediary_node = Tree(f"{address_int}")
        for sub_tree_node in root.sub_trees:
            sub_tree = parse_call_tree(sub_tree_node)
            intermediary_node.add(sub_tree)

        return intermediary_node

    contract_type = root.chain_manager.contracts.get(address)
    selector = root["calldata"][:4]
    call_signature = ""

    if contract_type:
        contract_id = root._get_contract_id(address, contract_type=contract_type)
        method_abi = _get_method_abi(selector, contract_type)

        if method_abi:
            raw_calldata = root["calldata"][4:]
            arguments = root._decode_calldata(method_abi, raw_calldata)

            # The revert-message appears at the top of the trace output.
            try:
                return_value = root._decode_returndata(method_abi) if not root["failed"] else None
            except (DecodingError, InsufficientDataBytes):
                return_value = "<?>"

            method_id = method_abi.name or f"<{selector.hex()}>"
            call_signature = str(
                _MethodTraceSignature(
                    root,
                    contract_id,
                    method_id,
                    arguments,
                    return_value,
                )
            )
            if root["gas_cost"]:
                call_signature += f" [{root.colors.GAS_COST}][{root['gas_cost']} gas][/]"

            if root.verbose:
                extra_info = {
                    "address": address,
                    "value": root["value"],
                    "gas_limit": root["gas_limit"],
                    "call_type": root["call_type"].value,
                }
                call_signature += f" {json.dumps(extra_info, indent=root.indent)}"
        elif contract_type.name and contract_id == contract_type.name:
            # The case where we know the contract name but couldn't decipher the method ID,
            #  such as an unsupported proxy or fallback.

            call_tree_node = None
            try:
                # Attempt default EVM-style trace
                call_tree_node = EvmCallTreeNode.construct(**root.raw_tree)
            except ValidationError:
                pass

            if call_tree_node is not None:
                call_signature = next(TreeRepresentation.make_tree(call_tree_node)).title
                call_signature = call_signature.replace(address, contract_id)
                call_signature = _dim_default_gas(root, call_signature)
    else:
        call_tree_node = None
        try:
            # Attempt default EVM-style trace
            call_tree_node = EvmCallTreeNode(**root.raw_tree)
        except ValidationError:
            pass

        if call_tree_node is not None:
            next_node = next(TreeRepresentation.make_tree(call_tree_node), None)
            if next_node:
                call_signature = _dim_default_gas(root, next_node.title)
            else:
                # Only for mypy's sake. May never get here.
                call_signature = f"{address}.<{selector.hex()}>"
                if root["gas_cost"]:
                    call_signature = (
                        f"{call_signature} [{root.colors.GAS_COST}]" f"[{root['gas_cost']} gas][/]"
                    )

    if root["value"]:
        eth_value = round(root["value"] / 10**18, 8)
        if eth_value:
            call_signature += f" [{root.colors.VALUE}][{eth_value} value][/]"

    parent = Tree(call_signature, guide_style="dim")
    for sub_call in root["calls"]:
        parent.add(str(sub_call))

    return parent


def parse_gas_table(report: "GasReport") -> List[Table]:
    tables: List[Table] = []

    for contract_id, method_calls in report.items():
        title = f"{contract_id} Gas"
        table = Table(title=title, box=SIMPLE)
        table.add_column("Method")
        table.add_column("Times called", justify="right")
        table.add_column("Min.", justify="right")
        table.add_column("Max.", justify="right")
        table.add_column("Mean", justify="right")
        table.add_column("Median", justify="right")

        has_at_least_1_row = False
        for method_call, gases in method_calls.items():
            if not gases:
                continue

            has_at_least_1_row = True
            table.add_row(
                method_call,
                f"{len(gases)}",
                f"{min(gases)}",
                f"{max(gases)}",
                f"{int(round(mean(gases)))}",
                f"{int(round(median(gases)))}",
            )

        if has_at_least_1_row:
            tables.append(table)

    return tables


def _dim_default_gas(root: "CallTreeNode", call_sig: str) -> str:
    # Add style to default gas block so it matches nodes with contract types
    gas_part = re.findall(_DEFAULT_TRACE_GAS_PATTERN, call_sig)
    if gas_part:
        return f"{call_sig.split(gas_part[0])[0]} [{root.colors.GAS_COST}]{gas_part[0]}[/]"

    return call_sig


@dataclass()
class _MethodTraceSignature:
    root: "CallTreeNode"
    contract_name: str
    method_name: str
    arguments: Dict
    return_value: Any

    def __str__(self) -> str:
        contract = f"[{self.root.colors.CONTRACTS}]{self.contract_name}[/]"
        method = f"[{TraceStyles.METHODS}]{self.method_name}[/]"
        call_path = f"{contract}.{method}"
        call_type = self.root["call_type"].value

        if call_type in (CallType.DELEGATECALL.value,):
            call_path = f"[orange](delegate)[/] {call_path}"

        arguments_str = self._build_arguments_str()
        signature = f"{call_path}{arguments_str}"

        return_str = self._build_return_str()
        if return_str:
            signature = f"{signature} -> {return_str}"

        return signature

    def _build_arguments_str(self) -> str:
        if not self.arguments:
            return "()"

        return self._dict_to_str(self.arguments, TraceStyles.INPUTS)

    def _build_return_str(self) -> Optional[str]:
        if self.return_value in [None, [], (), {}]:
            return None

        elif isinstance(self.return_value, dict):
            return self._dict_to_str(self.return_value, TraceStyles.OUTPUTS)

        elif isinstance(self.return_value, (list, tuple)):
            return f"[{TraceStyles.OUTPUTS}]{self._list_to_str(self.return_value)}[/]"

        return f"[{TraceStyles.OUTPUTS}]{self.return_value}[/]"

    def _dict_to_str(self, dictionary: Dict, color: str) -> str:
        length = sum([len(str(v)) for v in [*dictionary.keys(), *dictionary.values()]])
        do_wrap = length > self.root.wrap_threshold

        index = 0
        end_index = len(dictionary) - 1
        kv_str = "(\n" if do_wrap else "("

        for key, value in dictionary.items():
            if do_wrap:
                kv_str += self.root.indent * " "

            if isinstance(value, (list, tuple)):
                value = self._list_to_str(value, 1 if do_wrap else 0)

            kv_str += (
                f"{key}=[{color}]{value}[/]"
                if key and not key.isnumeric()
                else f"[{color}]{value}[/]"
            )
            if index < end_index:
                kv_str += ", "

            if do_wrap:
                kv_str += "\n"

            index += 1

        return f"{kv_str})"

    def _list_to_str(self, ls: Union[List, Tuple], depth: int = 0) -> str:
        if not isinstance(ls, (list, tuple)) or len(str(ls)) < self.root.wrap_threshold:
            return str(ls)

        elif ls and isinstance(ls[0], (list, tuple)):
            # List of lists
            sub_lists = [self._list_to_str(i) for i in ls]

            # Use multi-line if exceeds threshold OR any of the sub-lists use multi-line
            extra_chars_len = (len(sub_lists) - 1) * 2
            use_multiline = len(str(sub_lists)) + extra_chars_len > self.root.wrap_threshold or any(
                ["\n" in ls for ls in sub_lists]
            )

            if not use_multiline:
                # Happens for lists like '[[0], [1]]' that are short.
                return f"[{', '.join(sub_lists)}]"

            value = "[\n"
            num_sub_lists = len(sub_lists)
            index = 0
            spacing = self.root.indent * " " * 2
            for formatted_list in sub_lists:
                if "\n" in formatted_list:
                    # Multi-line sub list. Append 1 more spacing to each line.
                    indented_item = f"\n{spacing}".join(formatted_list.split("\n"))
                    value = f"{value}{spacing}{indented_item}"
                else:
                    # Single line sub-list
                    value = f"{value}{spacing}{formatted_list}"

                if index < num_sub_lists - 1:
                    value = f"{value},"

                value = f"{value}\n"
                index += 1

            value = f"{value}{self.root.indent * ' '}]"
            return value

        return self._list_to_multiline_str(ls, depth=depth)

    def _list_to_multiline_str(self, value: Union[List, Tuple], depth: int = 0) -> str:
        spacing = self.root.indent * " "
        new_val = "[\n"
        num_values = len(value)
        for idx in range(num_values):
            ls_spacing = spacing * (depth + 1)
            new_val += f"{ls_spacing}{value[idx]}"
            if idx < num_values - 1:
                new_val += ","

            new_val += "\n"

        new_val += spacing * depth
        new_val += "]"
        return new_val
