class ApeException(Exception):
    """
    An exception raised by ape.
    """


class AccountsError(ApeException):
    """
    Raised when a problem occurs when using accounts.
    """


class AliasAlreadyInUseError(AccountsError):
    """
    Raised when attempting to add an account using an alias
    that already maps to another account.
    """

    def __init__(self, alias: str):
        self.alias = alias
        super().__init__(f"Account with alias '{alias}' already in use")


class ContractError(ApeException):
    """
    Raised when issues occur when interacting with a contract
    (calls or transactions).
    """


class ArgumentsLengthError(ContractError):
    """
    Raised when calling a contract method with the wrong number of arguments.
    """

    def __init__(self):
        message = "The number of the given arguments do not match what is defined in the ABI."
        super().__init__(message)


class TransactionError(ContractError):
    """
    Raised when issues occur that caused the transaction to
    revert in a virtual machine, such as gas-related issues.
    """


class SignatureError(AccountsError):
    """
    Raised when an transaction is not signed when it should be.
    """


class DecodingError(ContractError):
    """
    Raised when issues occur while decoding data from
    a contract call or transaction.
    """

    def __init__(self):
        super().__init__("Output corrupted")


class ContractDeployError(ApeException):
    """
    Raised when a problem occurs when deploying a contract.
    """


class NetworkError(ApeException):
    """
    Raised when a problem occurs when using blockchain networks.
    """


class NetworkNotFoundError(NetworkError):
    """
    Raised when the network with the given name was not found.
    """

    def __init__(self, network: str):
        self.network = network
        message = f"No network named '{network}'"
        super().__init__(message)


class CompilerError(ApeException):
    """
    Raised when unable to compile.
    """


class ProjectError(ApeException):
    """
    Raised when problems occur in a project.
    """


class ConversionError(ApeException):
    """
    Raised when unable to convert a value.
    """


class ProviderError(ApeException):
    """
    Raised when a problem occurs when using providers.
    """


class ConfigError(ApeException):
    """
    Raised when a problem occurs from the configuration file.
    """


class AddressError(ApeException):
    """
    Raised when a problem occurs regarding an address.
    """
