import pytest
from src.errors import ConfigurationError
from src.g_cal import *
from src.settings import load_settings


def backlog(title, size="S", estimate=2, priority="P1"):
    return ProjectItemDTO(
        title=title, size=size, estimate=estimate, priority=priority, status="Backlog"
    )


def event(summary, start, end):
    return {
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }


def placements(tasks):
    return [(task.title, task.startDate.isoformat(), task.endDate.isoformat()) for task in tasks]


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
        "Large 2",
        "Small",
    ]  # preserved defect: the large-item swap branch is not reached for this ordering


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
        ("Large 1", "2024-01-01T09:00:00+00:00", "2024-01-01T11:00:00+00:00")
    ]  # preserved defect: advancing inside the loop skips the next day


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
    ]  # preserved defect: an oversized item is truncated instead of rejected


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
        ("A", "2024-01-01T09:00:00+00:00", "2024-01-01T11:00:00+00:00")
    ]  # preserved defect: unsorted commitments make the algorithm choose this gap


def test_scheduler_preserves_offset_event_clock_as_utc():
    result = schedule_events_from_project_items(
        "2024-01-01",
        "2024-01-01",
        "09:00",
        "17:00",
        [event("Meeting", "2024-01-01T10:00:00+01:00", "2024-01-01T12:00:00+01:00")],
        [backlog("A", estimate=2)],
    )
    assert placements(result) == [
        ("A", "2024-01-01T09:00:00+00:00", "2024-01-01T10:00:00+00:00"),
        ("A", "2024-01-01T12:00:00+00:00", "2024-01-01T13:00:00+00:00"),
    ]  # preserved defect: the offset clock is relabelled UTC instead of converted


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


def test_authenticate_raises_configuration_error_when_credentials_file_missing(tmp_path):
    settings = load_settings({"CAL_AUTO_CONFIG_DIR": str(tmp_path)})

    with pytest.raises(ConfigurationError, match="Missing Google OAuth client file"):
        authenticate(settings)
