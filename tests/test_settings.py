import pytest

from src.errors import ConfigurationError
from src.settings import load_settings


def test_override_is_created_and_isolates_credentials(tmp_path):
    config = tmp_path / "config"
    settings = load_settings(
        {
            "CAL_AUTO_CONFIG_DIR": str(config),
            "GITHUB_TOKEN": "token",
            "GITHUB_PROJECT_ID": "project",
        }
    )

    assert settings.config_dir == config
    assert config.is_dir()
    assert settings.google_token_file == config / "token.json"
    assert settings.require_github() == ("token", "project")


def test_required_github_values_are_validated_on_use(tmp_path):
    settings = load_settings({"CAL_AUTO_CONFIG_DIR": str(tmp_path)})

    assert settings.timezone == "Europe/Lisbon"
    with pytest.raises(ConfigurationError, match="GitHub integration is not configured"):
        settings.require_github()


def test_all_optional_values_are_typed_and_configurable(tmp_path):
    settings = load_settings(
        {
            "CAL_AUTO_CONFIG_DIR": str(tmp_path),
            "CAL_AUTO_TIMEZONE": "UTC",
            "CAL_AUTO_WORKING_DAY_START": "08:30",
            "CAL_AUTO_WORKING_DAY_END": "16:30",
            "CAL_AUTO_CALENDAR_ID": "work",
            "CAL_AUTO_TASK_LIST_ID": "tasks",
            "CAL_AUTO_ATTENDEES": "a@example.com, b@example.com",
            "CAL_AUTO_SCHEDULABLE_STATUSES": "Backlog, Ready",
        }
    )

    assert settings.timezone == "UTC"
    assert settings.attendees == ("a@example.com", "b@example.com")
    assert settings.schedulable_statuses == frozenset({"Backlog", "Ready"})
