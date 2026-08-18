"""Verify the installed package by running a real MCP client handshake against it.

Run against a `cal-auto-python` installed from a built artifact (sdist or wheel) into an
environment with no development dependencies, not against the source tree.
"""

import asyncio
import os
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> int:
    executable = Path(sys.executable).parent / "cal-auto-python"
    if not executable.exists():
        print(f"{executable} not found; is the built artifact installed?", file=sys.stderr)
        return 1

    expected_version = version("cal-auto-python")

    with tempfile.TemporaryDirectory() as config_dir:
        env = {
            **os.environ,
            "CAL_AUTO_CONFIG_DIR": config_dir,
            "CAL_AUTO_TIMEZONE": "UTC",
        }
        params = StdioServerParameters(command=str(executable), args=["server"], env=env)
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    result = await asyncio.wait_for(session.initialize(), timeout=30)
        except TimeoutError:
            print(
                "Timed out waiting for the installed server to complete initialize", file=sys.stderr
            )
            return 1

    if result.serverInfo.version != expected_version:
        print(
            f"Server reported version {result.serverInfo.version!r}, "
            f"expected installed package version {expected_version!r}",
            file=sys.stderr,
        )
        return 1

    print(f"Handshake succeeded with {result.serverInfo.name} {result.serverInfo.version}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
