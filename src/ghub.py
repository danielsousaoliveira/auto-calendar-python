from typing import Iterable, List, Optional

import requests

from .providers.task_source import TaskSource
from .utils.utils import parse_response_to_list
from .settings import Settings, load_settings, legacy_auth_dir, warn_legacy_auth
from .errors import IntegrationError
from .dtos.work_item import WorkItem


url = "https://api.github.com/graphql"

# The query below requests a single page of 100 items with no pagination. A board with more than
# 100 items will silently lose the overflow. Revisit if boards regularly exceed this size.
PAGE_SIZE = 100


def get_github_auth(settings: Settings | None = None):
    settings = settings or load_settings()
    legacy = legacy_auth_dir() / "ghub.json"
    if legacy.exists():
        warn_legacy_auth(legacy)
    token, project_id = settings.require_github()
    return token, project_id


def get_github_query(projectID):

    return f"""
    query{{
    node(id: "{projectID}") {{
        ... on ProjectV2 {{
            items(first: {PAGE_SIZE}) {{
            nodes{{
                id
                fieldValues(first: 100) {{
                nodes{{                
                    ... on ProjectV2ItemFieldTextValue {{
                    text
                    field {{
                        ... on ProjectV2FieldCommon {{
                        name
                        }}
                    }}
                    }}
                    ... on ProjectV2ItemFieldDateValue {{
                    date
                    field {{
                        ... on ProjectV2FieldCommon {{
                        name
                        }}
                    }}
                    }}
                    ... on ProjectV2ItemFieldSingleSelectValue {{
                    name
                    field {{
                        ... on ProjectV2FieldCommon {{
                        name
                        }}
                    }}
                    }}
                    ... on ProjectV2ItemFieldNumberValue {{
                    number
                    }}
                }}              
                }}
                content{{              
                ... on DraftIssue {{
                    title
                    body
                }}
                ...on Issue {{
                    title
                    body
                    assignees(first: 10) {{
                    nodes{{
                        login
                    }} 
                    }}
                }}
                ...on PullRequest {{
                    title
                    body
                    assignees(first: 10) {{
                    nodes{{
                        login
                    }}
                    }}
                }}
                }}
            }}
            }}
        }}
        }}
    }}
    """


def get_github_headers(token):

    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_github_project_items(token, projectID):

    query = get_github_query(projectID)
    headers = get_github_headers(token)

    try:
        response = requests.post(url, json={"query": query}, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data.get("errors"):
            raise IntegrationError(
                f"GitHub returned errors for the project query: {data['errors']}",
                hint="Check that GITHUB_TOKEN has access to GITHUB_PROJECT_ID and the query is valid.",
            )
        return parse_response_to_list(data)

    except requests.exceptions.RequestException as e:
        raise IntegrationError(
            f"Failed to fetch project items from GitHub: {e}",
            hint="Check your network connection and that GITHUB_TOKEN has access to the project.",
        ) from e


class GitHubProjectsTaskSource(TaskSource):
    def __init__(self, token: str, project_id: str):
        self.token = token
        self.project_id = project_id

    def list_work_items(self, statuses: Optional[Iterable[str]] = None) -> List[WorkItem]:
        items = get_github_project_items(self.token, self.project_id)
        if statuses is None:
            return items
        wanted = set(statuses)
        return [item for item in items if item.status in wanted]
