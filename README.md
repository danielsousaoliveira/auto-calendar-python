# Automatic Calendar in Python

Automatically schedule tasks from github into google calendar, using Python

## Setup

1. Clone this repository and create a virtual environment

```bash
$ git clone
$ cd cal-auto-python
$ python3 -m venv venv
$ . venv/bin/activate
```

2. Install dependencies and packages

```bash
$ (venv) pip install -r requirements.txt
```

## Run

1. Copy `auth/credentials.example.json` to `auth/credentials.json` and fill it in with your Google OAuth client credentials (downloaded from the Google Cloud Console).

2. Copy `auth/ghub.example.json` to `auth/ghub.json` and fill it in with your GitHub token and project ID:

```bash
{
    "token": "xxxxxxxxxxx",
    "project_id": "PVT_xxxxxxxxxx"
}
```

3. Copy `.env.example` to `.env` and fill in the same GitHub token and project ID if you prefer using environment variables.

4. Run the script

```bash
$ (venv) python3 src/main.py
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
