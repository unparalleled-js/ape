from typing import List

import pytest

from ape import accounts, networks, project
from ape.api import AccountAPI, ProviderAPI
from ape.managers.project import ProjectManager


class PytestApeFixtures:
    @pytest.fixture(scope="session")
    def accounts(self) -> List[AccountAPI]:
        """Ape accounts container. Access to all loaded accounts."""
        accts = accounts.filter_by_plugin(["test"])
        accts.init_fixture()
        return list(accts)

    @pytest.fixture
    def provider(self) -> ProviderAPI:
        provider = networks.active_provider

        if not provider:
            raise ValueError("No active provider set!")

        return provider

    @pytest.fixture(scope="session")
    def project(self) -> ProjectManager:
        return project
