import pytest

from ape.api import TransactionAPI
from ape.exceptions import TransactionError


class TestEthereumProvider:
    def test_transaction_web3_value_error_raises_transaction_error(
        self, mocker, mock_provider_api, test_account_api_can_sign
    ):
        mock_transaction = mocker.MagicMock(spec=TransactionAPI)
        mock_provider_api.get_nonce.return_value = mock_transaction.nonce = 0
        mock_transaction.total_transfer_value = mock_provider_api.get_balance.return_value = 1000000
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
        mock_transaction.total_transfer_value = mock_provider_api.get_balance.return_value = 1000000
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
        mock_transaction.total_transfer_value = mock_provider_api.get_balance.return_value = 1000000
        mock_transaction.signature.return_value = "test-signature"

        # Out of gas - used whole limit
        mock_transaction.gas_limit = 1000000
        mock_failing_transaction_receipt.gas_used = 1000000

        mock_provider_api.send_transaction.return_value = mock_failing_transaction_receipt

        with pytest.raises(TransactionError) as err:
            test_account_api_can_sign.call(mock_transaction)

        assert str(err.value) == "Transaction failing: Out of gas"
