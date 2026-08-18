"""Fail if the pushed tag does not match pyproject.toml's declared version."""

import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(tag: str) -> int:
    if not tag.startswith("v"):
        print(f"Tag {tag!r} does not start with 'v'", file=sys.stderr)
        return 1
    tag_version = tag[1:]

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    package_version = pyproject["project"]["version"]

    if tag_version != package_version:
        print(
            f"Tag version {tag_version!r} does not match pyproject.toml version "
            f"{package_version!r}",
            file=sys.stderr,
        )
        return 1

    print(f"Tag {tag!r} matches pyproject.toml version {package_version!r}")
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"version={package_version}\n")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: check_tag_version.py <tag>", file=sys.stderr)
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
