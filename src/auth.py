import os

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .errors import AuthorizationError, AuthorizationExpiredError, ConfigurationError
from .settings import Settings, legacy_auth_dir, load_settings, warn_legacy_auth

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/tasks"]


def _check_token_permissions(token_path):
    mode = os.stat(token_path).st_mode & 0o777
    if mode & 0o077:
        raise AuthorizationError(
            f"Google token file {token_path} is readable by other users",
            hint=f"Run chmod 600 {token_path}.",
        )


def _save_credentials(creds, token_path):
    with open(token_path, "w", opener=lambda path, flags: os.open(path, flags, 0o600)) as token:
        token.write(creds.to_json())
    os.chmod(token_path, 0o600)


def load_credentials(settings: Settings | None = None):
    settings = settings or load_settings()
    creds = None
    token_path = settings.google_token_file
    legacy = legacy_auth_dir()
    if (legacy / "credentials.json").exists() or (legacy / "token.json").exists():
        warn_legacy_auth(legacy)

    if token_path.exists():
        _check_token_permissions(token_path)
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except (ValueError, OSError) as exc:
            raise AuthorizationError(
                f"Google token file {token_path} could not be read",
                hint="Run cal-auto-python authorize to re-authorise the account.",
            ) from exc

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                raise AuthorizationExpiredError(
                    "Stored Google authorisation could not be refreshed",
                    hint="Run cal-auto-python authorize to authorise the account again.",
                ) from exc
        else:
            raise AuthorizationError(
                "Google account has not been authorised",
                hint="Run cal-auto-python authorize before starting the server.",
            )

        _save_credentials(creds, token_path)

    return creds


def authorize_credentials(settings: Settings | None = None):
    settings = settings or load_settings()
    credentials_path = settings.google_credentials_file
    if not credentials_path.exists():
        raise ConfigurationError(
            f"Missing Google OAuth client file: {credentials_path}",
            hint=(
                "Download an OAuth client ID (Desktop app) from the Google Cloud "
                f"Console and save it to {credentials_path}."
            ),
        )
    try:
        flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
        creds = flow.run_local_server(port=0)
    except Exception as exc:
        raise AuthorizationError(
            "Google Calendar/Tasks authorisation was not completed",
            hint="Rerun cal-auto-python authorize and grant access in the browser window that opens.",
        ) from exc
    _save_credentials(creds, settings.google_token_file)
    return creds


authenticate = load_credentials


def get_calendar_service(creds: Credentials):
    return build("calendar", "v3", credentials=creds)


def get_tasks_service(creds: Credentials):
    return build("tasks", "v1", credentials=creds)
