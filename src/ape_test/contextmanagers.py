import re
from typing import Optional, Pattern, Type

from ape.exceptions import TransactionError


class RevertsContextManager:
    def __init__(self, message: Optional[str] = None, pattern: Optional[Pattern] = None):

        # Verify regex pattern
        if pattern:
            re.compile(pattern)

        self.message = message
        self.pattern = pattern

    def __enter__(self):
        pass

    def __exit__(self, exc_type: Type, exc_value: TransactionError, traceback) -> bool:
        if exc_type is None:
            raise AssertionError("Transaction did not revert")

        if exc_type is not TransactionError:
            raise

        if self.message or self.pattern:
            actual = str(exc_value)
            if (
                actual is None
                or (self.pattern and not re.fullmatch(self.pattern, actual))
                or (self.message and self.message != actual)
            ):
                raise AssertionError(f"Unexpected revert string '{actual}'.") from None

        return True
