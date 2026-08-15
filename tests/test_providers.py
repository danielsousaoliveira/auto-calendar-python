import pytest

from src.providers.calendar_sink import CalendarSink
from src.providers.task_source import TaskSource


def test_task_source_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        TaskSource()


def test_calendar_sink_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        CalendarSink()
