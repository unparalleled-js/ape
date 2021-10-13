from pathlib import Path

import pytest
from ape_http import EthereumProvider

from ape.api import ReceiptAPI, TransactionStatusEnum
from ape.exceptions import TransactionError


def _create_mock_receipt_class(status, gas_used):
    class MockReceipt(ReceiptAPI):
        @classmethod
        def decode(cls, data: dict) -> "ReceiptAPI":
            return MockReceipt(
                txn_hash="test-hash",  # type: ignore
                status=status,  # type: ignore
                gas_used=gas_used,  # type: ignore
                gas_price="60000000000",  # type: ignore
                block_number=0,  # type: ignore
            )

    return MockReceipt


class TestEthereumProvider:
    def test_send_when_web3_error_raises_transaction_error(
        self, mock_web3, mock_network_api, mock_config_item, mock_transaction
    ):
        provider = EthereumProvider(
            name="test",
            network=mock_network_api,
            config=mock_config_item,
            provider_settings={},
            data_folder=Path("."),
            request_header="",
        )
        provider._web3 = mock_web3
        mock_receipt_class = _create_mock_receipt_class(TransactionStatusEnum.NO_ERROR, 0)
        mock_network_api.ecosystem.receipt_class = mock_receipt_class
        web3_error_text = (
            "{'code': -32000, 'message': 'Transaction gas limit is "
            "100000000 and exceeds block gas limit of 30000000'}"
        )
        mock_web3.eth.wait_for_transaction_receipt.side_effect = ValueError(web3_error_text)
        with pytest.raises(TransactionError) as err:
            provider.send_transaction(mock_transaction)

        assert web3_error_text in str(err.value)
