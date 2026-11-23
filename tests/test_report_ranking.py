"""The model's top corners for the crash map and the one-pager, on a made-up ranking."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from bike_safety_ca.report import movement, ranking


def _ranking(path: Path) -> Path:
    pd.DataFrame(
        {
            "rank": [1, 2, 3, 4],
            "streets": ["Elm Street / Oak Avenue", "Far Road / Main Street", "Ash Lane", "B / C"],
            "major": ["Major arterial", "Arterial", "Collector", "Local"],
            "minor": ["Arterial", "Arterial", None, "Local"],
            "in_city": [True, False, True, True],
            "expected_bike_crashes": [4.25, 3.0, None, 1.0],
            "observed_bike_crashes": [1, 5, 2, 0],
            "car_crashes": [16, 3, 1, 1],
            "method": "street-length model",
            "longitude": [-118.05, -118.06, -118.04, -118.03],
            "latitude": [34.05, 34.06, 34.04, 34.03],
        }
    ).to_csv(path, index=False)
    return path


def test_the_top_corners_are_the_citys_highest_ranked(tmp_path: Path) -> None:
    top = ranking.top(_ranking(tmp_path / "r.csv"), 2)
    assert top["rank"].tolist() == [1, 3]  # rank 2 lies outside the city


def test_a_city_limit_with_no_corners_inside_keeps_none(tmp_path: Path) -> None:
    path = _ranking(tmp_path / "r.csv")
    table = pd.read_csv(path)
    table.assign(in_city=False).to_csv(path, index=False)
    assert ranking.top(path, 2).empty
    # No city limit: the model leaves the column empty; the whole area is kept.
    table.assign(in_city=None).to_csv(path, index=False)
    assert ",," in path.read_text()
    assert ranking.top(path, 2)["rank"].tolist() == [1, 2]
    table.drop(columns="in_city").to_csv(path, index=False)
    assert ranking.top(path, 2)["rank"].tolist() == [1, 2]


def test_each_corner_says_what_the_model_saw(tmp_path: Path) -> None:
    top = ranking.top(_ranking(tmp_path / "r.csv"), 3)
    assert ranking.why(top.iloc[0]) == (
        "A major arterial meets an arterial. 1 bike crash and 16 car-only crashes recorded; "
        "the model expects about 4.2 bike crashes."
    )
    # No expected count (the blend) and no second road class.
    assert (
        ranking.why(top.iloc[1]) == "Collectors meet. 2 bike crashes and 1 car-only crash recorded."
    )
    marks = ranking.markers(top)
    assert marks[0] == {
        "r": 1,
        "n": "Elm Street / Oak Avenue",
        "lat": 34.05,
        "lon": -118.05,
        "w": ranking.why(top.iloc[0]),
    }


def test_the_one_pager_lists_the_corners_with_the_credits(tmp_path: Path) -> None:
    top = ranking.top(_ranking(tmp_path / "r.csv"), 3)
    (written,) = ranking.write(top, "Example", (2015, 2024), tmp_path / "out", pdf=False)
    text = written.read_text()
    assert text.startswith("# Where the crash model ranks highest: Example")
    assert "| 1 | Elm Street / Oak Avenue |" in text and "| 4 | B / C |" in text
    assert "Far Road" not in text and "2015–2024" in text and "TIMS" in text and "CCRS" in text


def test_the_map_carries_the_corners_and_a_switch_only_when_given() -> None:
    from bike_safety_ca import config as settings

    config = settings.load(Path("config/los_altos.yaml"))
    marks = [{"r": 1, "n": "A </script> B", "lat": 34.0, "lon": -118.0, "w": "why"}]
    plain = movement.page([], {k: [] for k in "MTLSP"}, [], config, (34.0, -118.0), [])
    ranked = movement.page(
        [], {k: [] for k in "MTLSP"}, [], config, (34.0, -118.0), [], ranked=marks
    )
    assert "const RANKED=[];" in plain
    assert '"r":1' in ranked and "</script> B" not in ranked  # script-safe
    assert '<label id="rkw" hidden>' in ranked  # shown by the page's script when there are corners
