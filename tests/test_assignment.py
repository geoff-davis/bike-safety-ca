from __future__ import annotations

import pytest

from bike_safety_ca.checks import assignment
from bike_safety_ca.checks.assignment import FINAL_TEST, SELECTION, assign, position, which_set

# position() of the made-up codes 00001 to 00003 under the fixed salt, as first computed.
EXPECTED = [0.286788, 0.837203, 0.392629]


def test_a_unit_goes_where_its_smallest_place_code_does() -> None:
    alone = position(["00123"])
    assert position(["45678", "00123", "99000"]) == alone
    assert position([" 123 "]) == alone  # padded and trimmed to five digits
    assert position(["00124"]) != alone
    assert 0 <= alone < 1


def test_the_set_follows_the_position_and_the_salt() -> None:
    codes = [str(n).zfill(5) for n in range(3000)]
    sets = [which_set([code]) for code in codes]
    assert set(sets) == {SELECTION, FINAL_TEST}
    for code, chosen in zip(codes[:50], sets[:50], strict=True):
        assert (position([code]) < assignment.SELECTION_SHARE) == (chosen == SELECTION)
    # about a third are selection
    assert sets.count(SELECTION) / len(sets) == pytest.approx(1 / 3, abs=0.03)
    # another salt is another split
    assert [which_set([code], salt="other") for code in codes] != sets


def test_the_fixed_salt_gives_the_same_split_every_time() -> None:
    # Made-up place codes; written down so that a changed salt or hash fails here.
    assert [round(position([code]), 6) for code in ("00001", "00002", "00003")] == EXPECTED


def test_assign_names_each_unit_and_refuses_a_city_in_two_units() -> None:
    units = {"a": ["00010", "00020"], "b": ["00030"]}
    assert assign(units) == {"a": which_set(["00010"]), "b": which_set(["00030"])}
    with pytest.raises(ValueError, match="00020"):
        assign(units | {"c": ["20"]})
    with pytest.raises(ValueError, match="at least one"):
        position([])
    with pytest.raises(ValueError, match="at least one"):
        assign({"empty": []})
    # codes given as a generator are read once
    lazy = {"a": (code for code in ["00010", "00020"]), "b": iter(["00030"])}
    assert assign(lazy) == assign(units)
