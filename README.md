# Automatic Calendar in Python

mcp-name: io.github.danielsousaoliveira/cal-auto-python

An MCP server that connects your GitHub Projects backlog to Google Calendar and Google Tasks. Point
your assistant at it and ask it to show what's on your calendar, list your backlog, plan a week of
work into your free time, or turn that plan into real events and to-dos.

## Install

```bash
$ pip install cal-auto-python
```

This installs the `cal-auto-python` command, which runs both the CLI and the MCP server.

## One-off authorisation

Before the server can read or write your calendar, you authorise it once against your Google
account:

```bash
$ cal-auto-python authorize
```

This opens a browser window, asks you to sign in and grant calendar/tasks access, and stores the
resulting token on disk (`token.json` in the config directory below). Do this before starting the
server for the first time, and again any time authorisation expires — see
[Troubleshooting](#troubleshooting).

Authorisation needs a Google OAuth client:

1. In the [Google Cloud Console](https://console.cloud.google.com/), create a project (or reuse one)
   and enable the **Google Calendar API** and **Google Tasks API**.
2. Under **APIs & Services → Credentials**, create an OAuth client ID of type **Desktop app**, and
   download the resulting JSON.
3. Save it as `credentials.json` in the config directory (see [Configuration](#configuration) for
   where that is and how to change it).

## Connect it to your assistant

The server speaks MCP over stdio by default, which is what these clients expect. Every capability
behaves the same regardless of client.

### Claude Desktop / Claude Code

Add to `claude_desktop_config.json` (Desktop) or run `claude mcp add` (Claude Code), or paste this
into either client's MCP settings:

```json
{
  "mcpServers": {
    "auto-calendar": {
      "command": "cal-auto-python",
      "args": ["server"],
      "env": {
        "GITHUB_TOKEN": "your_github_token_here",
        "GITHUB_PROJECT_ID": "PVT_xxxxxxxxxx",
        "CAL_AUTO_TIMEZONE": "Europe/Lisbon"
      }
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json` in your project (or the global `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "auto-calendar": {
      "command": "cal-auto-python",
      "args": ["server"],
      "env": {
        "GITHUB_TOKEN": "your_github_token_here",
        "GITHUB_PROJECT_ID": "PVT_xxxxxxxxxx",
        "CAL_AUTO_TIMEZONE": "Europe/Lisbon"
      }
    }
  }
}
```

### Generic (any stdio-capable MCP client)

```json
{
  "command": "cal-auto-python",
  "args": ["server"],
  "env": {
    "GITHUB_TOKEN": "your_github_token_here",
    "GITHUB_PROJECT_ID": "PVT_xxxxxxxxxx",
    "CAL_AUTO_TIMEZONE": "Europe/Lisbon"
  }
}
```

Web-based clients, or anyone wanting to run the server on one machine and talk to it from another,
can't launch a stdio child process. For them, run the server over HTTP instead:

```bash
$ cal-auto-python server --transport http --host 127.0.0.1 --port 8000
```

**HTTP mode is single-user and intended for local use only.** The server reads one person's stored
Google authorisation from disk and has no notion of separate users; it adds no authorisation of its
own on top of the HTTP endpoint. Exposing it on a shared or public network would hand everyone who
can reach it access to that one calendar, so only bind it to `127.0.0.1` or a private, trusted
network.

## Prerequisites

- **A GitHub personal access token** with read access to the Projects V2 board you want to
  schedule from: a classic token with the `read:project` scope (plus `repo` if the board tracks
  items in private repositories), or a fine-grained token granted read access to Projects. Set it as
  `GITHUB_TOKEN`.
- **The board's Projects V2 node ID**, e.g. `PVT_xxxxxxxxxx`. Find it by querying the GitHub GraphQL
  API for the project, or from its URL and the
  [Projects API docs](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects?tool=curl).
  Set it as `GITHUB_PROJECT_ID`.
- **A Google OAuth client** (Desktop app type) as described in
  [One-off authorisation](#one-off-authorisation) above.

## Capabilities

| Tool | Arguments | What it does |
| --- | --- | --- |
| `status` | — | Reports which integrations are configured and whether Google authorisation is present. Reveals no secrets. |
| `list_calendar_entries` | `start`, `end` (`YYYY-MM-DD`, inclusive) | Lists calendar events and all-day items in the date range. |
| `list_todos` | — | Lists outstanding (not completed) items from the configured Google Tasks list. |
| `list_tracker_items` | `statuses` (optional list, e.g. `["Backlog", "In Progress"]`) | Lists work items from the GitHub Projects board, optionally filtered by status. Omit to list everything. |
| `plan_week` | `items`, `start_date`, `end_date`, `working_day_start`, `working_day_end`, `timezone` (optional), `commitments` (optional) | Plans work into free working-hour slots for the given items and existing commitments. Pure computation — does not touch any configured account. |
| `sync_backlog` | `start_date`, `end_date`, `apply` (default `false`) | Fetches the schedulable backlog, fits it around existing calendar commitments, and returns the result. Previews by default; pass `apply=true` to create the events and to-dos. Already-scheduled items are skipped. |
| `create_calendar_entry` | `summary`, `start`, `end`, `timezone`, `description` (optional), `attendees` (optional) | Creates one calendar event. Does not schedule or deduplicate. |
| `create_todo` | `title`, `note` (optional), `due` (optional) | Creates one Google Task. Does not deduplicate. |

The CLI exposes the same scheduling logic directly:

```bash
$ cal-auto-python sync --start 2026-08-17 --end 2026-08-21 --apply
```

`sync` previews by default; pass `--apply` to create events and tasks, and `--start`/`--end`
(`YYYY-MM-DD`) or `--working-day-start`/`--working-day-end` (`HH:MM`) to override the default
range (today plus the next two days) and working hours.

## Configuration

Every variable below is optional except `GITHUB_TOKEN`, `GITHUB_PROJECT_ID`, and
`CAL_AUTO_TIMEZONE`, which has no default and must be set. Copy `.env.example` to `.env` if you use
an environment loader.

| Variable | Default | Purpose |
| --- | --- | --- |
| `GITHUB_TOKEN` | *(required)* | GitHub token used to query the Projects board. |
| `GITHUB_PROJECT_ID` | *(required)* | GitHub Projects V2 node ID of the board to read. |
| `CAL_AUTO_TIMEZONE` | *(required)* | IANA timezone name used to schedule events, e.g. `Europe/Lisbon`. |
| `CAL_AUTO_CONFIG_DIR` | `%APPDATA%\cal-auto-python` (Windows), `$XDG_CONFIG_HOME/cal-auto-python`, or `~/.config/cal-auto-python` | Directory holding `credentials.json` and `token.json`. |
| `CAL_AUTO_WORKING_DAY_START` | `09:00` | Start of the working day, `HH:MM`. |
| `CAL_AUTO_WORKING_DAY_END` | `17:00` | End of the working day, `HH:MM`. |
| `CAL_AUTO_CALENDAR_ID` | `primary` | Google Calendar ID to schedule events into. |
| `CAL_AUTO_TASK_LIST_ID` | `@default` | Google Tasks list ID to create tasks in. |
| `CAL_AUTO_ATTENDEES` | *(none)* | Comma-separated email addresses to invite to scheduled events. |
| `CAL_AUTO_SCHEDULABLE_STATUSES` | `Backlog` | Comma-separated GitHub Project status names to schedule. Must match the board's status names exactly. |
| `CAL_AUTO_COUNT_ALL_DAY_EVENTS` | `false` | Whether all-day events count against free/busy slots. |

## Troubleshooting

**Authorisation error / "Google account has not been authorised"**
Run `cal-auto-python authorize` again. This also fixes an expired authorisation that couldn't be
refreshed automatically (Google revokes a refresh token after long inactivity or if access is
revoked from your Google Account settings) — the server reports this explicitly rather than
failing silently.

**Events show up at unexpected times**
Check `CAL_AUTO_TIMEZONE`. It must be a valid IANA name (e.g. `Europe/Lisbon`, not `CET` or a UTC
offset) and must match the timezone you actually work in — the scheduler places events using this
value, not your system timezone.

**`list_tracker_items` or `sync_backlog` return nothing, even though the board has cards**
`CAL_AUTO_SCHEDULABLE_STATUSES` (default `Backlog`) must match your board's status column names
exactly, including case. Open the board and copy the status name verbatim, or pass an explicit
`statuses` argument to `list_tracker_items` to confirm what the board actually reports.

## Roadmap

[x] ~~Retrieve project data from github~~ \
[x] ~~Add events and tasks to google calendar~~ \
[x] ~~Schedule based on priority~~ \
[x] ~~Fix duplicated events and tasks~~ \
[x] ~~Replace the hardcoded entry point with a real CLI~~ \
[x] ~~Run as an MCP server (`cal-auto-python server`)~~ \
[x] ~~Optimize event distribution~~ \
[ ] Update or move an event when the plan changes

## References

[Google Calendar API](https://developers.google.com/calendar/api/quickstart/python) \
[Github Projects API](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects?tool=curl)
