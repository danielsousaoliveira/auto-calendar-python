# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.1] - Unreleased

### Added

- MCP server (`cal-auto-python server`) exposing `status`, `list_calendar_entries`,
  `list_todos`, `list_tracker_items`, `plan_week`, `sync_backlog`,
  `create_calendar_entry`, and `create_todo` tools, over stdio or HTTP.
- CLI (`cal-auto-python sync`, `cal-auto-python authorize`) built on the same
  `TaskSource`/`CalendarSink` seam as the MCP server.
- GitHub Projects V2 integration (`TaskSource`) and Google Calendar + Google Tasks
  integration (`CalendarSink`).
- Scheduling algorithm that packs backlog items into free calendar slots by priority
  and size, independent of either integration.
- Idempotent re-sync: re-running `sync_backlog` updates or skips already-scheduled
  events and to-dos instead of duplicating them.
- Release pipeline that publishes the package to PyPI as `cal-auto-python` and lists it
  on the MCP registry as `io.github.danielsousaoliveira/cal-auto-python`, on tag push.
