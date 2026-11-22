"""Commands run with no step named, or with a wrong one."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

import pytest

from bike_safety_ca.cli import chosen_steps


def test_no_step_means_the_default_steps() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("steps", nargs="*")
    assert chosen_steps(parser, parser.parse_args([]).steps, ["a", "b", "c"]) == ["a", "b", "c"]
    assert chosen_steps(parser, [], ["a", "b", "c"], ["b"]) == ["b"]
    assert chosen_steps(parser, ["c", "a"], ["a", "b", "c"]) == ["c", "a"]


def test_an_unknown_step_is_an_error(capsys: pytest.CaptureFixture[str]) -> None:
    parser = argparse.ArgumentParser()
    with pytest.raises(SystemExit):
        chosen_steps(parser, ["merg"], ["tims", "merge"])
    assert "unknown step 'merg'" in capsys.readouterr().err


def test_bare_make_lists_the_targets_and_changes_no_file() -> None:
    if shutil.which("make") is None:
        pytest.skip("make is not installed")
    root = Path(__file__).resolve().parents[1]
    # -n prints what would run: only the help line, not the formatter.
    planned = subprocess.run(["make", "-n"], cwd=root, capture_output=True, text=True, check=True)
    assert "ruff" not in planned.stdout and "awk" in planned.stdout
    shown = subprocess.run(["make"], cwd=root, capture_output=True, text=True, check=True).stdout
    assert (
        shown
        == subprocess.run(
            ["make", "help"], cwd=root, capture_output=True, text=True, check=True
        ).stdout
    )
    for target in ("help", "format", "lint", "typecheck", "test", "check", "demo", "walkthrough"):
        assert f"make {target} " in shown
