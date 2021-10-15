from typing import Optional, Type

from ape.exceptions import VirtualMachineError


class RevertsContextManager:
    def __init__(self, expected_message: Optional[str] = None):
        self.expected_message = expected_message

    def __enter__(self):
        pass

    def __exit__(self, exc_type: Type, exc_value: Exception, traceback) -> bool:
        if exc_type is None:
            raise AssertionError("Transaction did not revert")

        if exc_type is not VirtualMachineError:
            raise

        actual = str(exc_value) or ""
        if self.expected_message is None or self.expected_message in actual:
            return True

        raise AssertionError(f"Unexpected revert string '{actual}'.")
