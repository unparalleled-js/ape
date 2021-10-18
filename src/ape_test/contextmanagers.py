from typing import Optional, Type

from ape.exceptions import TransactionError, VirtualMachineError


class RevertsContextManager:
    def __init__(self, expected_message: Optional[str] = None):
        self.expected_message = expected_message

    def __enter__(self):
        pass

    def __exit__(self, exc_type: Type, exc_value: Exception, traceback) -> bool:
        if exc_type is None:
            raise AssertionError("Transaction did not revert.")

        if not isinstance(exc_value, VirtualMachineError):
            raise AssertionError(
                f"Transaction did not revert.\n"
                f"However, exception occurred: {exc_value}"
            ) from exc_value

        if (
            self.expected_message is not None
            and self.expected_message not in exc_value.revert_message
        ):
            raise AssertionError(
                f"'{self.expected_message}' not found in revert message '{exc_value.revert_message}'."
            )

        return True  # Assertion passes
