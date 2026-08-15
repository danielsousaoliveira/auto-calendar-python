import pytest
import requests

from src.dtos.work_item import Priority, WorkItem
from src.errors import ConfigurationError, IntegrationError
from src.ghub import GitHubProjectsTaskSource, get_github_project_items
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


def test_get_github_project_items_raises_integration_error_on_non_success_status(mocker):
    response = mocker.Mock()
    response.raise_for_status.side_effect = requests.exceptions.HTTPError("401 Unauthorized")
    mocker.patch("src.ghub.requests.post", return_value=response)

    with pytest.raises(IntegrationError, match="Failed to fetch project items from GitHub"):
        get_github_project_items("token", "project-id")


def test_get_github_project_items_raises_integration_error_on_graphql_errors(mocker):
    response = mocker.Mock()
    response.json.return_value = {
        "data": {"node": None},
        "errors": [{"message": "Could not resolve to a node with the global id"}],
    }
    mocker.patch("src.ghub.requests.post", return_value=response)

    with pytest.raises(IntegrationError, match="GitHub returned errors"):
        get_github_project_items("token", "project-id")


def test_get_github_project_items_returns_empty_list_for_empty_board(mocker):
    response = mocker.Mock()
    response.json.return_value = {"data": {"node": {"items": {"nodes": []}}}}
    mocker.patch("src.ghub.requests.post", return_value=response)

    assert get_github_project_items("token", "project-id") == []


def test_get_github_project_items_maps_response_to_work_items(mocker):
    response = mocker.Mock()
    response.json.return_value = {
        "data": {
            "node": {
                "items": {
                    "nodes": [
                        {
                            "id": "item-1",
                            "fieldValues": {
                                "nodes": [
                                    {"text": "Task A", "field": {"name": "Title"}},
                                    {"name": "P1", "field": {"name": "Priority"}},
                                    {"name": "Backlog", "field": {"name": "Status"}},
                                ]
                            },
                            "content": {
                                "title": "Task A",
                                "body": "",
                                "assignees": {"nodes": [{"login": "userA"}]},
                            },
                        }
                    ]
                }
            }
        }
    }
    mocker.patch("src.ghub.requests.post", return_value=response)

    items = get_github_project_items("token", "project-id")

    assert items == [
        WorkItem(
            id="item-1",
            title="Task A",
            assignee="userA",
            priority=Priority.P1,
            status="Backlog",
        )
    ]


class TestGitHubProjectsTaskSource:
    def test_list_work_items_returns_everything_without_a_status_filter(self, mocker):
        mocker.patch(
            "src.ghub.get_github_project_items",
            return_value=[
                WorkItem(id="1", status="Backlog"),
                WorkItem(id="2", status="Done"),
            ],
        )

        source = GitHubProjectsTaskSource("token", "project-id")

        assert [item.id for item in source.list_work_items()] == ["1", "2"]

    def test_list_work_items_filters_by_status(self, mocker):
        mocker.patch(
            "src.ghub.get_github_project_items",
            return_value=[
                WorkItem(id="1", status="Backlog"),
                WorkItem(id="2", status="Done"),
            ],
        )

        source = GitHubProjectsTaskSource("token", "project-id")

        assert [item.id for item in source.list_work_items(statuses=["Backlog"])] == ["1"]

    def test_list_work_items_propagates_integration_errors(self, mocker):
        mocker.patch(
            "src.ghub.get_github_project_items",
            side_effect=IntegrationError("boom", hint="check the board"),
        )

        source = GitHubProjectsTaskSource("token", "project-id")

        with pytest.raises(IntegrationError, match="boom"):
            source.list_work_items()
