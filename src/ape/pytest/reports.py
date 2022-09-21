from typing import List

from ape.api import ReceiptAPI
from ape.utils import CallTraceParser, ManagerAccessMixin


class Reporter(ManagerAccessMixin):
    receipts: List[ReceiptAPI] = []

    def build_gas_report(self):
        tables = []
        for receipt in self.receipts:
            tree_factory = CallTraceParser(receipt)
            tables.extend(tree_factory.parse_as_gas_report(receipt.call_tree))

        return tables


reporter = Reporter()
