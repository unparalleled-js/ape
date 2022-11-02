import pytest

from ape.cli import Path
from ape.exceptions import ContractLogicError
from build.lib.ape_geth import GethProvider


@pytest.fixture(scope="module", autouse=True)
def geth(networks):
    with networks.ethereum.local.use_provider("geth") as provider:
        yield provider


@pytest.fixture
def mock_geth(geth, mock_web3):
    provider = GethProvider(
        name="geth",
        network=geth.network,
        provider_settings={},
        data_folder=Path("."),
        request_header="",
    )
    provider._web3 = mock_web3
    return provider


@pytest.fixture
def contract_on_geth(owner, contract_container):
    return owner.deploy(contract_container)


def test_did_start_local_process(geth):
    assert geth._process is not None
    assert geth._process.is_running


def test_uri(geth):
    assert geth.uri == "http://localhost:8545"


def test_uri_uses_value_from_config(geth, temp_config):
    config = {"geth": {"ethereum": {"local": {"uri": "value/from/config"}}}}
    with temp_config(config):
        assert geth.uri == "value/from/config"


def test_uri_uses_value_from_settings(geth, temp_config):
    # The value from the adhoc-settings is valued over the value from the config file.
    config = {"geth": {"ethereum": {"local": {"uri": "value/from/config"}}}}
    with temp_config(config):
        geth.provider_settings["uri"] = "value/from/settings"
        assert geth.uri == "value/from/settings"
        del geth.provider_settings["uri"]


def test_snapshot_and_revert(geth, contract_on_geth, owner):
    snapshot_id = geth.snapshot()
    start_nonce = owner.nonce
    contract_on_geth.setNumber(1, sender=owner)  # Advance block

    expected_nonce = start_nonce + 1
    expected_block_num = snapshot_id + 1
    assert owner.nonce == expected_nonce
    assert geth.get_block("latest").number == expected_block_num

    geth.revert(snapshot_id)

    assert geth.get_block("latest").number == snapshot_id
    assert owner.nonce == start_nonce


def test_revert(sender, contract_on_geth):
    # 'sender' is not the owner so it will revert (with a message)
    with pytest.raises(ContractLogicError, match="!authorized"):
        contract_on_geth.setNumber(5, sender=sender)


def test_revert_no_message(owner, contract_on_geth):
    # The Contract raises empty revert when setting number to 5.
    expected = "Transaction failed."  # Default message
    with pytest.raises(ContractLogicError, match=expected):
        contract_on_geth.setNumber(5, sender=owner)


#
#
# def test_get_call_tree(geth, contract_on_geth, owner):
#     receipt = contract_on_geth.setNumber(10, sender=owner)
#     result = geth.get_call_tree(receipt.txn_hash)
#     assert f"CALL: {contract_on_geth.address}.<0x3fb5c1cb> [51212 gas]" in repr(result)
#
#
# def test_get_call_tree_erigon(mock_web3, mock_geth, trace_response):
#     mock_web3.client_version = "erigon_MOCK"
#     mock_web3.provider.make_request.return_value = trace_response
#     result = mock_geth.get_call_tree("0x053cba5c12172654d894f66d5670bab6215517a94189a9ffc09bc40a589ec04d")
#     actual = repr(result)
#     expected = "CALL: 0xC17f2C69aE2E66FD87367E3260412EEfF637F70E.<0x96d373e5> [1401584 gas]"
#     assert expected in actual
