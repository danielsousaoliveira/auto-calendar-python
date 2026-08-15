# Automatic Calendar in Python

Automatically schedule tasks from github into google calendar, using Python

## Setup

1. Clone this repository

```bash
$ git clone
$ cd cal-auto-python
```

2. Install the pinned dependencies and package into uv's managed `.venv`

```bash
$ uv sync --locked
```

## Run

1. Put your Google OAuth client credentials in the platform configuration directory as `credentials.json` (downloaded from the Google Cloud Console). Set `CAL_AUTO_CONFIG_DIR` to choose a different directory; the default is `%APPDATA%\\cal-auto-python` on Windows, `$XDG_CONFIG_HOME/cal-auto-python` when `XDG_CONFIG_HOME` is set, or `~/.config/cal-auto-python` on Unix.

2. Set the GitHub token and project ID as environment variables:

```bash
export GITHUB_TOKEN=xxxxxxxxxxx
export GITHUB_PROJECT_ID=PVT_xxxxxxxxxx
```

3. Copy `.env.example` to `.env` if you use an environment loader. Configure optional calendar, attendee, timezone, working-hours, and schedulable-status values there.

4. Authorise the Google account once:

```bash
$ uv run cal-auto-python authorize
```

5. Preview the plan for the default date range (today plus the next two days):

```bash
$ uv run cal-auto-python sync
```

Previewing is the default: `sync` only fetches, plans, and reports what it would do. Pass `--apply`
to actually create the events and tasks, and `--start`/`--end` (as `YYYY-MM-DD`) or
`--working-day-start`/`--working-day-end` (as `HH:MM`) to override the date range and working
hours:

```bash
$ uv run cal-auto-python sync --start 2026-08-17 --end 2026-08-21 --apply
```

## Roadmap

[x] ~~Retrieve project data from github~~ \
[x] ~~Add events and tasks to google calendar~~ \
[x] ~~Schedule based on priority~~ \
[x] ~~Fix duplicated events and tasks~~ \
[x] ~~Replace the hardcoded entry point with a real CLI~~ \
[ ] Optimize event distribution \
[ ] Update or move an event when the plan changes \
[ ] Run as an MCP server (`cal-auto-python server`)

## References

[Google Calendar API](https://developers.google.com/calendar/api/quickstart/python) \
[Github Projects API](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects?tool=curl)
