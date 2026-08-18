# Automatic Calendar in Python

mcp-name: io.github.danielsousaoliveira/cal-auto-python

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

## Run as an MCP server

```bash
$ uv run cal-auto-python server
```

By default this speaks the MCP protocol over standard input/output, for clients that launch it as
a child process. Some clients — web-based ones in particular, or anyone wanting to run the server
on one machine and talk to it from another — cannot do that. For them, pass `--transport http`:

```bash
$ uv run cal-auto-python server --transport http --host 127.0.0.1 --port 8000
```

**HTTP mode is single-user and intended for local use only.** The server reads one person's stored
Google Calendar authorisation from disk and has no notion of separate users; it does not add any
authorisation of its own on top of the HTTP endpoint. Exposing it on a shared or public network
would hand everyone who can reach it access to that one calendar, so only bind it to `127.0.0.1`
or a private, trusted network. Every capability behaves identically regardless of which transport
you connect over.

## Roadmap

[x] ~~Retrieve project data from github~~ \
[x] ~~Add events and tasks to google calendar~~ \
[x] ~~Schedule based on priority~~ \
[x] ~~Fix duplicated events and tasks~~ \
[x] ~~Replace the hardcoded entry point with a real CLI~~ \
[x] ~~Run as an MCP server (`cal-auto-python server`)~~ \
[ ] Optimize event distribution \
[ ] Update or move an event when the plan changes

## References

[Google Calendar API](https://developers.google.com/calendar/api/quickstart/python) \
[Github Projects API](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects?tool=curl)
