import pytest

from ape.api import TransactionAPI
from ape.api.accounts import AccountAPI
from ape.exceptions import AccountsError, TransactionError
from ape.types import AddressType

from ..conftest import TEST_ADDRESS


class _TestAccountAPI(AccountAPI):
    can_sign: bool

    @property
    def address(self):
        return AddressType(TEST_ADDRESS)

    def sign_message(self, msg):
        return "test-signature" if self.can_sign else None

    def sign_transaction(self, txn):
        return "test-signature" if self.can_sign else None


@pytest.fixture
def test_account_api_no_sign(mock_account_container_api, mock_provider_api):
    account = _TestAccountAPI(mock_account_container_api, can_sign=False)
    account._provider = mock_provider_api
    return account


@pytest.fixture
def test_account_api_can_sign(mock_account_container_api, mock_provider_api):
    account = _TestAccountAPI(mock_account_container_api, can_sign=True)
    account._provider = mock_provider_api
    return account


class TestAccountAPI:
    def test_txn_nonce_less_than_accounts_raise_accounts_error(
        self, mocker, mock_provider_api, test_account_api_can_sign
    ):
        mock_transaction = mocker.MagicMock(spec=TransactionAPI)

        # Differing nonces
        mock_provider_api.get_nonce.return_value = 1
        mock_transaction.nonce = 0

        with pytest.raises(AccountsError) as err:
            test_account_api_can_sign.call(mock_transaction)

        assert str(err.value) == "Invalid nonce, will not publish"

    def test_not_enough_funds_raises_error(
        self, mocker, mock_provider_api, test_account_api_can_sign
    ):
        mock_transaction = mocker.MagicMock(spec=TransactionAPI)
        mock_provider_api.get_nonce.return_value = mock_transaction.nonce = 0

        # Transaction costs are greater than balance
        mock_transaction.transfer_value = 1000000
        mock_provider_api.get_balance.return_value = 0

        with pytest.raises(AccountsError) as err:
            test_account_api_can_sign.call(mock_transaction)

        expected = (
            "Transfer value meets or exceeds account balance (transfer_value=1000000, balance=0)"
        )
        assert str(err.value) == expected

    def test_transaction_not_signed_raises_error(
        self, mocker, mock_provider_api, test_account_api_no_sign
    ):
        mock_transaction = mocker.MagicMock(spec=TransactionAPI)
        mock_provider_api.get_nonce.return_value = mock_transaction.nonce = 0
        mock_transaction.transfer_value = mock_provider_api.get_balance.return_value = 1000000

        with pytest.raises(AccountsError) as err:
            test_account_api_no_sign.call(mock_transaction)

        assert str(err.value) == "The transaction was not signed"

    def test_transaction_web3_value_error_raises_transaction_error(
        self, mocker, mock_provider_api, test_account_api_can_sign
    ):
        mock_transaction = mocker.MagicMock(spec=TransactionAPI)
        mock_provider_api.get_nonce.return_value = mock_transaction.nonce = 0
        mock_transaction.transfer_value = mock_provider_api.get_balance.return_value = 1000000
        mock_transaction.signature.return_value = "test-signature"

        web3_error_text = (
            "{'code': -32000, 'message': 'Transaction gas limit is "
            "100000000 and exceeds block gas limit of 30000000'}"
        )
        mock_provider_api.send_transaction.side_effect = ValueError(web3_error_text)

        with pytest.raises(TransactionError) as err:
            test_account_api_can_sign.call(mock_transaction)

        assert web3_error_text in str(err.value)

    def test_transaction_failing_raises_transaction_error(
        self, mocker, mock_provider_api, test_account_api_can_sign, mock_failing_transaction_receipt
    ):
        mock_transaction = mocker.MagicMock(spec=TransactionAPI)
        mock_provider_api.get_nonce.return_value = mock_transaction.nonce = 0
        mock_transaction.transfer_value = mock_provider_api.get_balance.return_value = 1000000
        mock_transaction.signature.return_value = "test-signature"

        mock_provider_api.send_transaction.return_value = mock_failing_transaction_receipt

        with pytest.raises(TransactionError) as err:
            test_account_api_can_sign.call(mock_transaction)

        assert str(err.value) == "Transaction failing"

    def test_transaction_failing_out_of_gas_raises_transaction_error(
        self, mocker, mock_provider_api, test_account_api_can_sign, mock_failing_transaction_receipt
    ):
        mock_transaction = mocker.MagicMock(spec=TransactionAPI)
        mock_provider_api.get_nonce.return_value = mock_transaction.nonce = 0
        mock_transaction.transfer_value = mock_provider_api.get_balance.return_value = 1000000
        mock_transaction.signature.return_value = "test-signature"

        # Out of gas - used whole limit
        mock_transaction.gas_limit = 1000000
        mock_failing_transaction_receipt.gas_used = 1000000

        mock_provider_api.send_transaction.return_value = mock_failing_transaction_receipt

        with pytest.raises(TransactionError) as err:
            test_account_api_can_sign.call(mock_transaction)

        assert str(err.value) == "Transaction failing: Out of gas"

    def test_transaction_when_no_gas_limit_calls_estimate_gas_cost(
        self, mocker, mock_provider_api, test_account_api_can_sign
    ):
        mock_transaction = mocker.MagicMock(spec=TransactionAPI)
        mock_transaction.gas_limit = None  # Causes estimate_gas_cost to get called
        mock_provider_api.get_nonce.return_value = mock_transaction.nonce = 0
        mock_transaction.transfer_value = mock_provider_api.get_balance.return_value = 1000000
        mock_transaction.signature.return_value = "test-signature"
        test_account_api_can_sign.call(mock_transaction)
        mock_provider_api.estimate_gas_cost.assert_called_once_with(mock_transaction)
