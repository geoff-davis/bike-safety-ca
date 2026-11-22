from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, box

from bike_safety_ca import ADULT, CAR, CHILD, UNKNOWN_AGE
from bike_safety_ca.crashes.groups import OTHER, group_crashes


def _crashes() -> gpd.GeoDataFrame:
    rows = [
        # id, injury, bike, ped, duplicate of, point
        ("child", True, True, False, None, Point(0, 0)),
        ("adult", True, True, False, None, Point(1, 0)),
        ("both", True, True, False, None, Point(2, 0)),
        ("unknown-age", True, True, False, None, Point(3, 0)),
        ("cars", True, False, False, None, Point(4, 0)),
        ("walker", True, False, True, None, Point(5, 0)),
        ("no-injury", False, False, False, None, Point(6, 0)),
        ("duplicate", True, False, False, "cars", Point(7, 0)),
        ("unlocated", True, False, False, None, None),
        ("empty", True, False, False, None, Point()),
        ("far", True, False, False, None, Point(500, 0)),
    ]
    return gpd.GeoDataFrame(
        {
            "merged_id": [r[0] for r in rows],
            "injury_crash": [r[1] for r in rows],
            "bike_involved": [r[2] for r in rows],
            "ped_involved": [r[3] for r in rows],
            "possible_duplicate_of": [r[4] for r in rows],
        },
        geometry=gpd.GeoSeries([r[5] for r in rows]),  # type: ignore[arg-type]
        crs=26910,
    )


PARTIES = pd.DataFrame(
    [
        ("child", "4", "12"),
        ("child", "1", "40"),
        ("adult", " 4 ", "19"),
        ("both", "4", "18"),
        ("both", "4", "50"),
        ("unknown-age", "4", "998"),
        ("cars", "1", "16"),
        ("walker", "2", "9"),
    ],
    columns=["CASE_ID", "PARTY_TYPE", "PARTY_AGE"],
)


def test_groups_follow_the_youngest_cyclist() -> None:
    out = group_crashes(_crashes(), PARTIES, area=box(-10, -10, 10, 10))
    assert out.set_index("merged_id").group.to_dict() == {
        "child": CHILD,
        "adult": ADULT,
        "both": CHILD,
        "unknown-age": UNKNOWN_AGE,
        "cars": CAR,
        "walker": OTHER,
    }


def test_a_negative_age_is_not_a_child() -> None:
    parties = pd.DataFrame([("child", "4", "-1")], columns=["CASE_ID", "PARTY_TYPE", "PARTY_AGE"])
    out = group_crashes(_crashes(), parties).set_index("merged_id")
    assert out.group["child"] == UNKNOWN_AGE


def test_the_child_age_comes_from_the_caller() -> None:
    out = group_crashes(_crashes(), PARTIES, child_max_age=17).set_index("merged_id")
    assert out.group["both"] == ADULT
    assert "far" in out.index
