import pytest
from ape_ethereum.ecosystem import EthereumVirtualMachineError, Transaction

from ape.exceptions import TransactionError


class TestEthereumVirtualMachineError:
    @pytest.mark.parametrize(
        "error_dict",
        (
            {"message": "The transaction ran out of gas", "code": -32000},
            {"message": "Base limit exceeds gas limit", "code": -32603},
            {"message": "Exceeds block gas limit", "code": -32603},
            {"message": "Transaction requires at least 12345 gas"},
        ),
    )
    def test_when_gas_related_does_not_create(self, error_dict):
        test_err = ValueError(error_dict)
        with pytest.raises(TransactionError) as err:
            EthereumVirtualMachineError.from_error(test_err)

        assert type(err.value) != EthereumVirtualMachineError

    def test_from_dict(self):
        test_err = ValueError({"message": "Test Action Reverted!"})
        actual = EthereumVirtualMachineError.from_error(test_err)
        assert type(actual) == EthereumVirtualMachineError


class TestTransaction:
    def test_as_dict_excludes_none_values(self):
        txn = Transaction()
        txn.value = 1000000
        actual = txn.as_dict()
        assert "value" in actual
        txn.value = None
        actual = txn.as_dict()
        assert "value" not in actual
