import pytest

from ape.api import AccountContainerAPI, NetworkAPI, ProviderAPI, ReceiptAPI, TransactionStatusEnum

TEST_ADDRESS = "0x0A78AAAAA2122100000b9046f0A085AB2E111113"


@pytest.fixture
def mock_account_container_api(mocker):
    return mocker.MagicMock(spec=AccountContainerAPI)


@pytest.fixture
def mock_provider_api(mocker, mock_network_api):
    mock = mocker.MagicMock(spec=ProviderAPI)
    mock.network = mock_network_api
    return mock


@pytest.fixture
def mock_network_api(mocker):
    return mocker.MagicMock(spec=NetworkAPI)


@pytest.fixture
def mock_failing_transaction_receipt(mocker):
    mock = mocker.MagicMock(spec=ReceiptAPI)
    mock.status = TransactionStatusEnum.failing
    mock.gas_used = 0
    return mock
