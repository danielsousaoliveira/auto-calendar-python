from importlib.metadata import PackageNotFoundError, version

import pytest

from src.main import build_parser, package_version


def test_version_flag_reports_the_installed_package_version(capsys):
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--version"])

    assert version("cal-auto-python") in capsys.readouterr().out


def test_package_version_falls_back_when_not_installed(monkeypatch):
    def raise_not_found(_name):
        raise PackageNotFoundError

    monkeypatch.setattr("src.main.version", raise_not_found)

    assert package_version() == "0+unknown"
