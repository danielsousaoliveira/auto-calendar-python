import pytest
from google.auth.exceptions import RefreshError

from src.auth import authorize_credentials, load_credentials
from src.errors import AuthorizationError, AuthorizationExpiredError
from src.settings import load_settings


def test_load_credentials_requires_authorization_when_token_file_missing(tmp_path):
    settings = load_settings({"CAL_AUTO_CONFIG_DIR": str(tmp_path), "CAL_AUTO_TIMEZONE": "UTC"})

    with pytest.raises(AuthorizationError, match="cal-auto-python authorize"):
        load_credentials(settings)


def test_load_credentials_requires_one_off_authorization_without_network(tmp_path, mocker):
    settings = load_settings({"CAL_AUTO_CONFIG_DIR": str(tmp_path), "CAL_AUTO_TIMEZONE": "UTC"})
    request = mocker.patch("src.auth.Request")
    browser = mocker.patch("src.auth.InstalledAppFlow")

    with pytest.raises(AuthorizationError, match="cal-auto-python authorize"):
        load_credentials(settings)

    request.assert_not_called()
    browser.assert_not_called()


def test_load_credentials_reports_refresh_failure_separately(tmp_path, mocker):
    settings = load_settings({"CAL_AUTO_CONFIG_DIR": str(tmp_path), "CAL_AUTO_TIMEZONE": "UTC"})
    settings.google_token_file.write_text("token")
    settings.google_token_file.chmod(0o600)
    credentials = mocker.Mock(valid=False, expired=True, refresh_token="refresh")
    mocker.patch("src.auth.Credentials.from_authorized_user_file", return_value=credentials)
    credentials.refresh.side_effect = RefreshError("expired")

    with pytest.raises(AuthorizationExpiredError, match="could not be refreshed"):
        load_credentials(settings)


def test_load_credentials_rejects_token_readable_by_group(tmp_path):
    settings = load_settings({"CAL_AUTO_CONFIG_DIR": str(tmp_path), "CAL_AUTO_TIMEZONE": "UTC"})
    settings.google_token_file.write_text("token")
    settings.google_token_file.chmod(0o640)

    with pytest.raises(AuthorizationError, match="readable by other users"):
        load_credentials(settings)


def test_load_credentials_reports_a_malformed_token_file_as_an_authorization_error(tmp_path):
    settings = load_settings({"CAL_AUTO_CONFIG_DIR": str(tmp_path), "CAL_AUTO_TIMEZONE": "UTC"})
    settings.google_token_file.write_text("not json")
    settings.google_token_file.chmod(0o600)

    with pytest.raises(AuthorizationError, match="could not be read"):
        load_credentials(settings)


def test_authorize_credentials_is_the_only_browser_flow(tmp_path, mocker):
    settings = load_settings({"CAL_AUTO_CONFIG_DIR": str(tmp_path), "CAL_AUTO_TIMEZONE": "UTC"})
    settings.google_credentials_file.write_text("credentials")
    flow = mocker.patch("src.auth.InstalledAppFlow.from_client_secrets_file")
    credentials = mocker.Mock()
    credentials.to_json.return_value = "token"
    flow.return_value.run_local_server.return_value = credentials

    authorize_credentials(settings)

    flow.assert_called_once()
    assert settings.google_token_file.read_text() == "token"
    assert settings.google_token_file.stat().st_mode & 0o777 == 0o600
