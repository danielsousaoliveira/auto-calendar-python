"""Fail if server.json's declared version drifts from pyproject.toml's package version."""

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    package_version = pyproject["project"]["version"]

    manifest = json.loads((ROOT / "server.json").read_text())
    manifest_version = manifest["version"]
    package_versions = {package["version"] for package in manifest["packages"]}

    mismatches = {manifest_version, *package_versions} - {package_version}
    if mismatches:
        print(
            f"server.json version(s) {sorted(mismatches)} do not match "
            f"pyproject.toml version {package_version!r}",
            file=sys.stderr,
        )
        return 1

    print(f"server.json matches pyproject.toml version {package_version!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
