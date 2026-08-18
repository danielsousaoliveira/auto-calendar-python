from importlib.metadata import version

import pytest

from src.main import build_parser


def test_version_flag_reports_the_installed_package_version(capsys):
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--version"])

    assert version("cal-auto-python") in capsys.readouterr().out
