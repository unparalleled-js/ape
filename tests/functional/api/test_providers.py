import pytest

from ape.api import TransactionType, Web3Provider

_TEST_TXN_DATA = {"test": -1}


class _Provider(Web3Provider):
    def __init__(self, mocker):
        self.mock_web3 = mocker.MagicMock()
        super().__init__(
            network=mocker.MagicMock(),
            name="test",
            _web3=self.mock_web3,
            config=mocker.MagicMock(),
            provider_settings={},
            data_folder="",
            request_header={},
        )

    def connect(self):
        pass

    def disconnect(self):
        pass


@pytest.fixture
def mock_transaction(mocker):
    txn = mocker.MagicMock()
    txn.as_dict.return_value = _TEST_TXN_DATA
    txn.type = TransactionType.DYNAMIC.value
    return txn


class TestWeb3Provider:
    def test_set_defaults_estimating_gas(self, mocker, mock_transaction):
        provider = _Provider(mocker)
        mock_transaction.gas_limit = None  # Done just to be explicit
        provider.set_defaults(mock_transaction)
        provider.mock_web3.eth.estimate_gas.assert_called_once_with(_TEST_TXN_DATA)
