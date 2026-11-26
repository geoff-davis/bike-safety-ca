"""Which evaluation set a city falls in, from a hash of its Census place code.

New cities are held back to test the ranking.  Each is put in the selection
set (where a model may be chosen) or the final test set (scored once, after
the choice is frozen) by a rule that looks at nothing but its Census place
code, so the split cannot follow the crashes.  Cities that share a police
agency are one unit and go together: a unit takes the smallest place code
among its cities.

The salt is fixed.  Changing it after any city's crashes have been seen
would be choosing the split.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping

SALT = "bike-safety-ca evaluation, 24 November 2026"
SELECTION, FINAL_TEST = "selection", "final test"
# A unit whose hash falls under this share of the hash's range is selection.
SELECTION_SHARE = 1 / 3


def _codes(place_codes: Iterable[str]) -> list[str]:
    """The codes as five-digit text, each once, smallest first; at least one."""
    codes = sorted({str(code).strip().zfill(5) for code in place_codes})
    if not codes:
        raise ValueError("a unit needs at least one place code")
    return codes


def position(place_codes: Iterable[str], salt: str = SALT) -> float:
    """Where a unit's hash falls between 0 and 1.

    ``place_codes`` are the five-digit Census place codes of the unit's
    cities, as text; the smallest stands for the unit.
    """
    codes = _codes(place_codes)
    digest = hashlib.sha256(f"{salt}:{codes[0]}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def which_set(place_codes: Iterable[str], salt: str = SALT) -> str:
    """``SELECTION`` or ``FINAL_TEST`` for a unit of one or more cities."""
    return SELECTION if position(place_codes, salt) < SELECTION_SHARE else FINAL_TEST


def assign(units: Mapping[str, Iterable[str]], salt: str = SALT) -> dict[str, str]:
    """The set of each named unit; ``units`` maps a name to its cities' place codes.

    No place code may be in two units: a city has one agency group.  Each
    unit's codes are read once, so a generator will do.
    """
    read = {name: _codes(codes) for name, codes in units.items()}
    seen: dict[str, str] = {}
    for name, codes in read.items():
        for code in codes:
            if code in seen:
                raise ValueError(f"place {code} is in both {seen[code]} and {name}")
            seen[code] = name
    return {name: which_set(codes, salt) for name, codes in read.items()}
