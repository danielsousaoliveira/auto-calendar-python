import pytest
from src.g_cal import *

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
            {
                "items": [
                    {"summary": "All Day Event", "start": {"date": "2024-08-30"}}
                ]
            },
            [
                {"summary": "All Day Event", "start": {"date": "2024-08-30"}}
            ],
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
