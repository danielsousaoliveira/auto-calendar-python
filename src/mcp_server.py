"""MCP server exposing this tool's capabilities to an assistant."""

from __future__ import annotations

import asyncio
from pydantic import BaseModel

from mcp.server.fastmcp import FastMCP

from .settings import Settings

SERVER_NAME = "auto-calendar"


class IntegrationStatus(BaseModel):
    github_configured: bool
    google_calendar_configured: bool
    google_calendar_authorized: bool


def build_server(settings: Settings) -> FastMCP:
    server = FastMCP(SERVER_NAME)

    @server.tool(
        name="status",
        description=(
            "Report which integrations are configured and whether Google Calendar "
            "authorisation is present. Reveals no secrets."
        ),
    )
    async def status() -> IntegrationStatus:
        return await asyncio.to_thread(_check_status, settings)

    return server


def _check_status(settings: Settings) -> IntegrationStatus:
    return IntegrationStatus(
        github_configured=bool(settings.github_token and settings.github_project_id),
        google_calendar_configured=settings.google_credentials_file.exists(),
        google_calendar_authorized=settings.google_token_file.exists(),
    )
