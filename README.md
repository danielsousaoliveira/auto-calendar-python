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

1. Put your Google OAuth client credentials in the platform configuration directory as `credentials.json` (downloaded from the Google Cloud Console). Set `CAL_AUTO_CONFIG_DIR` to choose a different directory; the default is `$XDG_CONFIG_HOME/cal-auto-python` or `~/.config/cal-auto-python`.

2. Set the GitHub token and project ID as environment variables:

```bash
export GITHUB_TOKEN=xxxxxxxxxxx
export GITHUB_PROJECT_ID=PVT_xxxxxxxxxx
```

3. Copy `.env.example` to `.env` if you use an environment loader. Configure optional calendar, attendee, timezone, working-hours, and schedulable-status values there.

4. Run the script

```bash
$ uv run cal-auto-python
```

## Roadmap

[x] ~~Retrieve project data from github~~ \
[x] ~~Add events and tasks to google calendar~~ \
[x] ~~Schedule based on priority~~ \
[ ] Optimize event distribution \
[ ] Fix duplicated events and tasks

## References

[Google Calendar API](https://developers.google.com/calendar/api/quickstart/python) \
[Github Projects API](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects?tool=curl)
