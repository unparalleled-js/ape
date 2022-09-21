from typing import List, Optional
from rich.table import Table

from ape.api import ReceiptAPI
from ape.utils import CallTraceParser
from evm_trace.gas import merge_reports, GasReport


class Reporter:
    gas_report: Optional[GasReport] = None

    def add_gas_report(self, receipt: ReceiptAPI):
        tree_factory = CallTraceParser(receipt)
        gas_report = tree_factory.parse_as_gas_report(receipt.call_tree)
        self.gas_report = merge_reports(self.gas_report, *gas_report)

reporter = Reporter()
