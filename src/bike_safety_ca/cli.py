"""Shared command-line helpers."""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def chosen_steps(
    parser: argparse.ArgumentParser,
    given: Sequence[str],
    allowed: Sequence[str],
    default: Sequence[str] | None = None,
) -> list[str]:
    """The steps named on the command line, or the default when none is named.

    Checked here, not with argparse's ``choices``: an optional list of
    positional choices with an empty default is rejected by Python 3.12."""
    unknown = [step for step in given if step not in allowed]
    if unknown:
        parser.error(f"unknown step {unknown[0]!r}; choose from: {', '.join(allowed)}")
    return list(given) or list(default if default is not None else allowed)
