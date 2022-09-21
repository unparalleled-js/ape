from typing import List

from ape.api import ReceiptAPI
from ape.utils import ManagerAccessMixin


class Reporter(ManagerAccessMixin):
    receipts: List[ReceiptAPI] = []


reporter = Reporter()
