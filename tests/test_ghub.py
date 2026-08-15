import pytest
import requests

from src.errors import ConfigurationError, IntegrationError
from src.ghub import get_github_project_items
from src.settings import load_settings


def test_get_github_auth_raises_configuration_error_when_credentials_missing(tmp_path):
    settings = load_settings({"CAL_AUTO_CONFIG_DIR": str(tmp_path)})

    with pytest.raises(ConfigurationError, match="GITHUB_TOKEN"):
        settings.require_github()


def test_get_github_project_items_raises_integration_error_on_request_failure(mocker):
    mocker.patch(
        "src.ghub.requests.post",
        side_effect=requests.exceptions.ConnectionError("boom"),
    )

    with pytest.raises(IntegrationError, match="Failed to fetch project items from GitHub"):
        get_github_project_items("token", "project-id")
