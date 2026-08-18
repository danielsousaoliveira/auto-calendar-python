import argparse
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from googleapiclient.errors import HttpError

from .auth import authorize_credentials
from .dtos.schedule import ScheduleWindow
from .errors import AutoCalendarError
from .integrations import build_integrations
from .logger import logger
from .mcp_server import build_server
from .settings import Settings, load_settings
from .sync import SyncResult, run_sync


def build_window(
    settings: Settings, start_date: str | None, end_date: str | None
) -> ScheduleWindow:
    tz = ZoneInfo(settings.timezone)
    start = (
        datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else datetime.now(tz).date()
    )
    end = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else start + timedelta(days=2)
    return ScheduleWindow(
        start=datetime.combine(
            start, datetime.strptime(settings.working_day_start, "%H:%M").time(), tz
        ),
        end=datetime.combine(end, datetime.strptime(settings.working_day_end, "%H:%M").time(), tz),
    )


def report_sync_result(result: SyncResult) -> None:
    for block in result.plan.scheduled:
        logger.info(
            f"Task '{block.title}' planned from {block.start} to {block.end} "
            f"with priority {block.priority} and size {block.size}, estimate: {block.estimate} hours."
        )
    for item in result.unscheduled:
        logger.info(f"Could not place '{item.work_item.title}': {item.reason}")
    if result.applied:
        for block in result.created:
            logger.info(f"Created '{block.title}'.")
        for block in result.skipped:
            logger.info(f"Skipped '{block.title}': already scheduled.")
    else:
        logger.info("Dry run: nothing was written. Pass --apply to create these events.")


def run_authorize(args: argparse.Namespace) -> int:
    settings = load_settings()
    authorize_credentials(settings)
    logger.info("Google Calendar/Tasks authorisation complete.")
    return 0


def run_server(args: argparse.Namespace) -> int:
    settings = load_settings()
    server = build_server(settings, host=args.host, port=args.port)
    if args.transport == "http":
        logger.info(
            f"Serving over HTTP on http://{args.host}:{args.port} — single-user, local use only. "
            "This exposes the configured Google account's calendar to anyone who can reach this "
            "address; do not expose it on a shared or public network."
        )
        server.run(transport="streamable-http")
    else:
        server.run(transport="stdio")
    return 0


def run_sync_command(args: argparse.Namespace) -> int:
    settings = load_settings()
    overrides = {}
    if args.working_day_start:
        overrides["working_day_start"] = args.working_day_start
    if args.working_day_end:
        overrides["working_day_end"] = args.working_day_end
    if overrides:
        settings = replace(settings, **overrides)

    window = build_window(settings, args.start, args.end)
    task_source, calendar_sink = build_integrations(settings)
    result = run_sync(task_source, calendar_sink, window, settings, apply=args.apply)
    report_sync_result(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cal-auto-python")
    subparsers = parser.add_subparsers(dest="command", required=True)

    authorize_parser = subparsers.add_parser(
        "authorize", help="Run the one-off Google Calendar/Tasks authorisation flow."
    )
    authorize_parser.set_defaults(func=run_authorize)

    server_parser = subparsers.add_parser("server", help="Run the MCP server.")
    server_parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help=(
            "Transport to serve over. 'http' is single-user and intended for local use only: "
            "the server has no notion of separate users and no per-endpoint authorisation, so "
            "anyone who can reach the address gets the configured Google account's calendar."
        ),
    )
    server_parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind when --transport http is used."
    )
    server_parser.add_argument(
        "--port", type=int, default=8000, help="Port to bind when --transport http is used."
    )
    server_parser.set_defaults(func=run_server)

    sync_parser = subparsers.add_parser(
        "sync", help="Fetch work items, plan a schedule, and create calendar events/tasks."
    )
    sync_parser.add_argument("--start", help="First day to schedule, as YYYY-MM-DD.")
    sync_parser.add_argument("--end", help="Last day to schedule, as YYYY-MM-DD.")
    sync_parser.add_argument("--working-day-start", help="Working day start time, as HH:MM.")
    sync_parser.add_argument("--working-day-end", help="Working day end time, as HH:MM.")
    sync_parser.add_argument(
        "--apply",
        action="store_true",
        help="Create the planned events and tasks. Without this flag, sync only previews the plan.",
    )
    sync_parser.set_defaults(func=run_sync_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except HttpError as error:
        logger.error(f"An error occurred: {error}")
    except AutoCalendarError as error:
        logger.error(f"{error.args[0]} Hint: {error.hint}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
