from typing import List

import pytest
from ape_test import HardhatAccount

from ape import accounts, networks, project
from ape.api import AccountAPI, ProviderAPI
from ape.managers.project import ProjectManager
from ape_accounts import KeyfileAccount


class PytestApeFixtures:
    @pytest.fixture
    def accounts(self, provider) -> List[AccountAPI]:
        """
        Returns test accounts based on the active provider.
        """
        account_type_by_provider = {
            "hardhat": HardhatAccount,
        }
        account_type = account_type_by_provider.get(provider.name, KeyfileAccount)
        return accounts.get_accounts_by_type(account_type)

    @pytest.fixture
    def provider(self) -> ProviderAPI:
        provider = networks.active_provider

        if not provider:
            raise ValueError("No active provider set!")

        return provider

    @pytest.fixture(scope="session")
    def project(self) -> ProjectManager:
        return project
