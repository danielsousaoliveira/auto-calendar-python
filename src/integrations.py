"""Wiring for the real GitHub/Google integrations behind the provider seams."""

from __future__ import annotations

from .auth import get_calendar_service, get_tasks_service, load_credentials
from .ghub import GitHubProjectsTaskSource, get_github_auth
from .providers.calendar_sink import CalendarSink
from .providers.google_calendar_sink import GoogleCalendarSink
from .providers.task_source import TaskSource
from .settings import Settings


def build_task_source(settings: Settings) -> TaskSource:
    token, project_id = get_github_auth(settings)
    return GitHubProjectsTaskSource(token, project_id)


def build_calendar_sink(settings: Settings) -> CalendarSink:
    creds = load_credentials(settings)
    calendar_service = get_calendar_service(creds)
    tasks_service = get_tasks_service(creds)
    return GoogleCalendarSink(calendar_service, tasks_service, settings)


def build_integrations(settings: Settings) -> tuple[TaskSource, CalendarSink]:
    return build_task_source(settings), build_calendar_sink(settings)
