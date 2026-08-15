"""Application-specific error hierarchy.

Every error carries a ``hint`` describing what the caller should actually do next.
"""

from __future__ import annotations


class AutoCalendarError(Exception):
    def __init__(self, message: str, hint: str):
        super().__init__(message)
        self.hint = hint

    def __str__(self) -> str:
        return f"{super().__str__()} ({self.hint})"


class ConfigurationError(AutoCalendarError):
    """Required configuration is missing or invalid."""


class AuthorizationError(AutoCalendarError):
    """The calendar/tasks account has not been authorised."""


class AuthorizationExpiredError(AutoCalendarError):
    """A previously granted authorisation is no longer valid."""


class IntegrationError(AutoCalendarError):
    """A call to an upstream integration (e.g. the task tracker) failed."""


class SchedulingError(AutoCalendarError):
    """Events or tasks could not be scheduled."""
