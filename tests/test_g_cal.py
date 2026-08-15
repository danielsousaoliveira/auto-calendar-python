import pytest
from google.auth.exceptions import RefreshError
from src.errors import (
    AuthorizationError,
    AuthorizationExpiredError,
    SchedulingError,
)
from src.g_cal import *
from src.dtos.work_item import Priority, Size
from src.settings import load_settings
from src.scheduler import schedule
from src.dtos.schedule import ScheduleWindow, ScheduledBlock
from datetime import datetime


def schedule_events_from_project_items(
    start_date, end_date, start_hour, end_hour, events, tasks, settings=None
):
    if not isinstance(start_date, str) or not isinstance(end_date, str):
        raise SchedulingError("Invalid schedule window", "Provide valid dates.")
    window = ScheduleWindow(
        datetime.fromisoformat(f"{start_date}T{start_hour}:00+00:00"),
        datetime.fromisoformat(f"{end_date}T{end_hour}:00+00:00"),
    )
    busy_blocks = [
        ScheduledBlock(
            title=item["summary"],
            start=datetime.fromisoformat(item["start"]["dateTime"]),
            end=datetime.fromisoformat(item["end"]["dateTime"]),
        )
        for item in events
        if "dateTime" in item.get("start", {}) and "dateTime" in item.get("end", {})
    ]
    return schedule(tasks, busy_blocks, window).scheduled


def backlog(title, size="S", estimate=2, priority="P1"):
    return WorkItem(
        title=title,
        size=Size[size],
        estimate=estimate,
        priority=Priority[priority],
        status="Backlog",
    )


def event(summary, start, end):
    return {
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }


def placements(tasks):
    return [(task.title, task.start.isoformat(), task.end.isoformat()) for task in tasks]


def test_scheduler_leaves_empty_backlog_empty():
    assert (
        schedule_events_from_project_items("2024-01-01", "2024-01-01", "09:00", "17:00", [], [])
        == []
    )  # correct behaviour


def test_scheduler_places_single_item_that_fits():
    result = schedule_events_from_project_items(
        "2024-01-01", "2024-01-01", "09:00", "17:00", [], [backlog("A", estimate=2)]
    )
    assert placements(result) == [
        ("A", "2024-01-01T09:00:00+00:00", "2024-01-01T11:00:00+00:00")
    ]  # correct behaviour


def test_scheduler_splits_item_around_existing_commitment():
    result = schedule_events_from_project_items(
        "2024-01-01",
        "2024-01-01",
        "09:00",
        "17:00",
        [event("Meeting", "2024-01-01T11:00:00+00:00", "2024-01-01T13:00:00+00:00")],
        [backlog("A", estimate=6)],
    )
    assert placements(result) == [
        ("A", "2024-01-01T09:00:00+00:00", "2024-01-01T11:00:00+00:00"),
        ("A", "2024-01-01T13:00:00+00:00", "2024-01-01T17:00:00+00:00"),
    ]  # correct behaviour


def test_scheduler_swaps_second_large_item_for_smaller_item():
    result = schedule_events_from_project_items(
        "2024-01-01",
        "2024-01-01",
        "09:00",
        "17:00",
        [],
        [backlog("Large 1", "L", 2), backlog("Large 2", "L", 2), backlog("Small", "S", 2)],
    )
    assert [task.title for task in result] == [
        "Large 1",
        "Small",
    ]  # deliberate fix: the second large item is reported as unscheduled


def test_scheduler_advances_when_no_smaller_item_can_be_swapped_in():
    result = schedule_events_from_project_items(
        "2024-01-01",
        "2024-01-02",
        "09:00",
        "17:00",
        [],
        [backlog("Large 1", "L", 2), backlog("Large 2", "L", 2)],
    )
    assert placements(result) == [
        ("Large 1", "2024-01-01T09:00:00+00:00", "2024-01-01T11:00:00+00:00"),
        ("Large 2", "2024-01-02T09:00:00+00:00", "2024-01-02T11:00:00+00:00"),
    ]  # deliberate fix: advancing preserves the next day


def test_scheduler_rolls_over_an_item_across_days():
    result = schedule_events_from_project_items(
        "2024-01-01", "2024-01-02", "09:00", "17:00", [], [backlog("A", estimate=10)]
    )
    assert placements(result) == [
        ("A", "2024-01-01T09:00:00+00:00", "2024-01-01T17:00:00+00:00"),
        ("A", "2024-01-02T09:00:00+00:00", "2024-01-02T11:00:00+00:00"),
    ]  # correct behaviour


def test_scheduler_does_not_place_item_when_window_cannot_fit_it():
    result = schedule_events_from_project_items(
        "2024-01-01", "2024-01-01", "09:00", "17:00", [], [backlog("A", estimate=9)]
    )
    assert placements(result) == [
        ("A", "2024-01-01T09:00:00+00:00", "2024-01-01T17:00:00+00:00")
    ]  # deliberate fix: the remaining work is returned as unscheduled


def test_scheduler_uses_size_when_estimate_is_missing():
    result = schedule_events_from_project_items(
        "2024-01-01", "2024-01-01", "09:00", "17:00", [], [backlog("A", "M", None)]
    )
    assert placements(result) == [
        ("A", "2024-01-01T09:00:00+00:00", "2024-01-01T13:00:00+00:00")
    ]  # correct behaviour


def test_scheduler_sorts_existing_commitments_before_finding_slot():
    result = schedule_events_from_project_items(
        "2024-01-01",
        "2024-01-01",
        "09:00",
        "17:00",
        [
            event("Late", "2024-01-01T13:00:00+00:00", "2024-01-01T14:00:00+00:00"),
            event("Early", "2024-01-01T10:00:00+00:00", "2024-01-01T11:00:00+00:00"),
        ],
        [backlog("A", estimate=2)],
    )
    assert placements(result) == [
        ("A", "2024-01-01T09:00:00+00:00", "2024-01-01T10:00:00+00:00"),
        ("A", "2024-01-01T11:00:00+00:00", "2024-01-01T12:00:00+00:00"),
    ]


def test_scheduler_preserves_offset_event_clock_as_utc():
    result = schedule_events_from_project_items(
        "2024-01-01",
        "2024-01-01",
        "09:00",
        "17:00",
        [event("Meeting", "2024-01-01T10:00:00+01:00", "2024-01-01T12:00:00+01:00")],
        [backlog("A", estimate=2)],
    )
    assert placements(result) == [("A", "2024-01-01T11:00:00+00:00", "2024-01-01T13:00:00+00:00")]


@pytest.fixture
def mock_service(mocker):
    # Mock the Google Calendar service
    service_mock = mocker.Mock()
    mocker.patch("src.g_cal.get_calendar_service", return_value=service_mock)
    return service_mock


@pytest.mark.parametrize(
    "mock_response, expected_events, expected_len",
    [
        # Test case 1: No events
        ({"items": []}, [], 0),
        # Test case 2: Multiple events
        (
            {
                "items": [
                    {"summary": "Event 1", "start": {"dateTime": "2024-08-28T09:00:00Z"}},
                    {"summary": "Event 2", "start": {"dateTime": "2024-08-29T10:00:00Z"}},
                ]
            },
            [
                {"summary": "Event 1", "start": {"dateTime": "2024-08-28T09:00:00Z"}},
                {"summary": "Event 2", "start": {"dateTime": "2024-08-29T10:00:00Z"}},
            ],
            2,
        ),
        # Test case 3: Event with only date
        (
            {"items": [{"summary": "All Day Event", "start": {"date": "2024-08-30"}}]},
            [{"summary": "All Day Event", "start": {"date": "2024-08-30"}}],
            1,
        ),
    ],
)
def test_list_all_google_events(mock_service, mock_response, expected_events, expected_len):
    # Mock the response
    mock_service.events.return_value.list.return_value.execute.return_value = mock_response

    # Call the function
    events = list_all_google_events(mock_service)

    # Assertions
    assert len(events) == expected_len
    assert events == expected_events
    mock_service.events().list().execute.assert_called_once()


def test_list_all_google_tasks_succeeds_when_a_task_has_no_due_date(mocker):
    service_mock = mocker.Mock()
    service_mock.tasks.return_value.list.return_value.execute.return_value = {
        "items": [
            {"title": "With due date", "id": "1", "due": "2024-08-30T00:00:00Z"},
            {"title": "No due date", "id": "2"},
        ]
    }

    items = list_all_google_tasks(service_mock)

    assert [item["id"] for item in items] == ["1", "2"]


def test_load_credentials_requires_authorization_when_token_file_missing(tmp_path):
    settings = load_settings({"CAL_AUTO_CONFIG_DIR": str(tmp_path)})

    with pytest.raises(AuthorizationError, match="cal-auto-python authorize"):
        load_credentials(settings)


def test_load_credentials_requires_one_off_authorization_without_network(tmp_path, mocker):
    settings = load_settings({"CAL_AUTO_CONFIG_DIR": str(tmp_path)})
    request = mocker.patch("src.g_cal.Request")
    browser = mocker.patch("src.g_cal.InstalledAppFlow")

    with pytest.raises(AuthorizationError, match="cal-auto-python authorize"):
        load_credentials(settings)

    request.assert_not_called()
    browser.assert_not_called()


def test_load_credentials_reports_refresh_failure_separately(tmp_path, mocker):
    settings = load_settings({"CAL_AUTO_CONFIG_DIR": str(tmp_path)})
    settings.google_token_file.write_text("token")
    settings.google_token_file.chmod(0o600)
    credentials = mocker.Mock(valid=False, expired=True, refresh_token="refresh")
    mocker.patch("src.g_cal.Credentials.from_authorized_user_file", return_value=credentials)
    credentials.refresh.side_effect = RefreshError("expired")

    with pytest.raises(AuthorizationExpiredError, match="could not be refreshed"):
        load_credentials(settings)


def test_load_credentials_rejects_token_readable_by_group(tmp_path):
    settings = load_settings({"CAL_AUTO_CONFIG_DIR": str(tmp_path)})
    settings.google_token_file.write_text("token")
    settings.google_token_file.chmod(0o640)

    with pytest.raises(AuthorizationError, match="readable by other users"):
        load_credentials(settings)


def test_authorize_credentials_is_the_only_browser_flow(tmp_path, mocker):
    settings = load_settings({"CAL_AUTO_CONFIG_DIR": str(tmp_path)})
    settings.google_credentials_file.write_text("credentials")
    flow = mocker.patch("src.g_cal.InstalledAppFlow.from_client_secrets_file")
    credentials = mocker.Mock()
    credentials.to_json.return_value = "token"
    flow.return_value.run_local_server.return_value = credentials

    authorize_credentials(settings)

    flow.assert_called_once()
    assert settings.google_token_file.read_text() == "token"
    assert settings.google_token_file.stat().st_mode & 0o777 == 0o600


def test_list_all_google_tasks_returns_empty_list_when_no_tasks(mocker):
    service_mock = mocker.Mock()
    service_mock.tasks.return_value.list.return_value.execute.return_value = {"items": []}

    items = list_all_google_tasks(service_mock)

    assert items == []


def test_scheduler_raises_scheduling_error_on_non_string_date():
    with pytest.raises(SchedulingError, match="Invalid schedule window"):
        schedule_events_from_project_items(None, "2024-01-01", "09:00", "17:00", [], [])
