from typing import Optional, Type

from ape.exceptions import TransactionError


class RevertsContextManager:
    def __init__(self, expected_message: Optional[str] = None):
        self.expected_message = expected_message

    def __enter__(self):
        pass

    def __exit__(self, exc_type: Type, exc_value: TransactionError, traceback) -> bool:
        if exc_type is None:
            raise AssertionError("Transaction did not revert")

        if exc_type is not TransactionError:
            raise

        if self.expected_message is not None:
            actual = str(exc_value) or ""
            if self.expected_message not in actual:
                raise AssertionError(f"Unexpected revert string '{actual}'.") from None

        return True
