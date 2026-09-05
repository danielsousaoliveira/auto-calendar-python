# Architecture

## Layers

```
src/
  dtos/         plain @dataclass models — WorkItem, ScheduledBlock, EventDTO, TaskDTO, ...
  providers/    the two integration interfaces: TaskSource, CalendarSink
  ghub.py       GitHubProjectsTaskSource — the only TaskSource implementation today
  google_calendar_sink.py / auth.py
                GoogleCalendarSink — the only CalendarSink implementation today
  scheduler.py  schedule() — pure function, work items + busy blocks + a window in,
                a SchedulePlan out
  sync.py       run_sync() — orchestrates: fetch from a TaskSource, schedule, write to
                a CalendarSink, skipping items already present
  integrations.py
                build_task_source() / build_calendar_sink() — wires concrete
                implementations from Settings; the one place that knows both concrete
                types exist
  mcp_server.py / main.py
                MCP tools and CLI commands, calling sync.py and scheduler.py
```

Each layer only talks to the layer(s) named above it in this list. `scheduler.py` sits
at the bottom: it imports nothing from `providers/`, `ghub.py`, or
`google_calendar_sink.py`.

## The two integration interfaces

### `TaskSource` (`src/providers/task_source.py`)

```python
class TaskSource(ABC):
    @abstractmethod
    def list_work_items(self, statuses: Optional[Iterable[str]] = None) -> List[WorkItem]:
        """Return work items, optionally restricted to the given statuses."""
```

A conforming implementation returns `WorkItem` instances (`src/dtos/work_item.py`) with
whatever subset of these fields the tracker can supply: `id`, `source` (a short constant
string identifying the tracker, e.g. `"github"`), `title`, `assignee`, `priority`
(`Priority` enum, `P0`–`P4`), `status`, `size` (`Size` enum, `XL`–`XS`), `estimate`
(hours, a `float`), `description`, `tasks` (a list of markdown-checkbox strings — each
becomes one Google Task). `status` filtering, if `statuses` is given, must match the
tracker's own status vocabulary; nothing above this layer normalizes status names.

### `CalendarSink` (`src/providers/calendar_sink.py`)

```python
class CalendarSink(ABC):
    def list_busy_blocks(self, window: ScheduleWindow) -> List[ScheduledBlock]: ...
    def list_entries(self, window: ScheduleWindow) -> List[CalendarEntryDTO]: ...
    def list_outstanding_todos(self) -> List[TodoItemDTO]: ...
    def create_event(self, event: EventDTO) -> dict: ...
    def create_todo(self, task: TaskDTO) -> dict: ...
    def find_scheduled_events(self, source: str, source_id: str) -> List[dict]: ...
    def update_event(self, event_id: str, event: EventDTO) -> dict: ...
    def list_scheduled_todo_markers(self) -> Set[str]: ...
```

`find_scheduled_events` and `list_scheduled_todo_markers` are what make re-running sync
idempotent: they let `sync.py` tell "this block already has an event" from "this is
new," per `source`/`source_id` pair, without either side going back to the tracker.

Only one `CalendarSink` (Google) exists today, so this seam is less proven than
`TaskSource`. A second `TaskSource` is the cheaper way to test whether the split is in
the right place.

## The load-bearing rule

**`scheduler.py` imports nothing from `providers/`, `ghub.py`, or
`google_calendar_sink.py`.** `schedule()` takes a `list[WorkItem]`, a `list[ScheduledBlock]`
(busy time), and a `ScheduleWindow`, and returns a `SchedulePlan` — all plain DTOs, no
network calls, no knowledge of GitHub or Google.

This is why `plan_week` (an MCP tool) can plan a week from data handed to it directly,
with no configured account at all, and why `scheduler.py` has unit tests that never touch
a fake HTTP client. If adding a second `TaskSource` ever means changing `scheduler.py`,
the seam has failed — the point of the interface split is that scheduling logic is
identical no matter which tracker or calendar backs it.

## Walkthrough: adding a second task tracker (e.g. Jira)

This is a paper exercise — no code below is meant to be copied verbatim, but it should
be enough to start from.

1. **Implement `TaskSource`.** Create `src/jira.py` with a `JiraTaskSource` class:

   ```python
   class JiraTaskSource(TaskSource):
       def __init__(self, base_url: str, email: str, api_token: str, jql: str): ...

       def list_work_items(self, statuses: Optional[Iterable[str]] = None) -> List[WorkItem]:
           issues = self._search_issues(statuses)
           return [self._to_work_item(issue) for issue in issues]
   ```

   `_to_work_item` maps Jira's issue fields onto `WorkItem`: `summary` → `title`,
   `priority.name` → `Priority`, story points or a custom field → `Size`/`estimate`,
   `assignee.displayName` → `assignee`, the issue key → `id`, `"jira"` → `source`. Any
   field Jira doesn't have stays `None` — every `WorkItem` field is optional.

2. **Add settings.** `src/settings.py` already resolves `GITHUB_TOKEN` /
   `GITHUB_PROJECT_ID`; add the Jira equivalents (`JIRA_BASE_URL`, `JIRA_EMAIL`,
   `JIRA_API_TOKEN`, `JIRA_JQL`, or similar) the same way, with a `require_jira()`
   accessor mirroring `require_github()`.

3. **Wire it in `integrations.py`.** Add a `build_task_source` variant, or extend the
   existing one to pick a tracker based on which settings are present:

   ```python
   def build_task_source(settings: Settings) -> TaskSource:
       if settings.jira_base_url:
           return JiraTaskSource(*settings.require_jira())
       token, project_id = get_github_auth(settings)
       return GitHubProjectsTaskSource(token, project_id)
   ```

4. **Nothing else changes.** `scheduler.py`, `sync.py`, and `mcp_server.py` already
   operate on `TaskSource` and `WorkItem`; they do not know or care that a second
   implementation now exists. If step 4 turns out to require touching any of those
   files, that is the signal the interface is missing something.

5. **Test it.** Follow the pattern in `tests/test_ghub.py`: unit-test
   `JiraTaskSource.list_work_items` against a fake HTTP response, and add it to
   `tests/test_providers.py`'s conformance checks if one exists for `TaskSource`.

A second `CalendarSink` (e.g. Outlook) follows the same shape against
`src/providers/calendar_sink.py` instead, with `find_scheduled_events` /
`list_scheduled_todo_markers` as the two methods that need the most thought, since
they're what keeps re-sync idempotent.
