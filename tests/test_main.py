import os
from importlib.metadata import PackageNotFoundError, version

import pytest

from src import main as main_module
from src.main import build_parser, main, package_version


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


@pytest.mark.parametrize("command", ["authorize", "server", "sync"])
def test_env_file_flag_is_accepted_by_every_command(command):
    args = build_parser().parse_args([command, "--env-file", "config.env"])

    assert args.env_file == "config.env"


def test_env_file_is_loaded_before_the_command_runs(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("CAL_AUTO_ENV_MARKER=abc\n")
    seen = {}

    def fake_server(_args):
        seen["marker"] = os.environ.get("CAL_AUTO_ENV_MARKER")
        return 0

    monkeypatch.delenv("CAL_AUTO_ENV_MARKER", raising=False)
    monkeypatch.setattr(main_module, "run_server", fake_server)

    assert main(["server", "--env-file", str(env_file)]) == 0
    assert seen["marker"] == "abc"


def test_missing_env_file_exits_with_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "run_server", lambda _args: 0)

    assert main(["server", "--env-file", str(tmp_path / "absent.env")]) == 1
