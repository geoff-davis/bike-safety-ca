"""Corridor forecast and hold-out, on made-up streets and crashes."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, box

from bike_safety_ca import CAR, CHILD
from bike_safety_ca.checks import corridors as check
from bike_safety_ca.model import corridors as model
from bike_safety_ca.model.crash_history import MIN_CRASHES

ADULT_GROUP = next(g for g in check.OUTCOMES["All cyclists"] if g != CHILD)


def test_lengths_group_spellings_and_skip_unnamed_streets() -> None:
    ways = gpd.GeoDataFrame(
        {"name": ["Foothill Expy", "FOOTHILL EXPRESSWAY", None, "Grant Rd"]},
        geometry=[
            LineString([(0, 0), (500, 0)]),
            LineString([(500, 0), (800, 0)]),
            LineString([(0, 0), (0, 900)]),
            LineString([(0, 0), (0, 200)]),
        ],
        crs="EPSG:26910",
    )
    km = model.corridor_lengths(ways)
    assert km.to_dict() == {"Foothill": 0.8, "Grant": 0.2}
    clipped = model.corridor_lengths(ways, box(-1, -1, 400, 1000))
    assert round(clipped["Foothill"], 3) == 0.4


def test_a_corner_is_on_every_street_through_it() -> None:
    corners = model.corridor_corners({2: {"GRANT RD", "Foothill Expy"}, 1: {"Foothill Expressway"}})
    assert corners == {"Foothill": [1, 2], "Grant": [2]}


def test_a_crash_counts_at_a_corner_or_between_never_both() -> None:
    crashes = pd.DataFrame({"corridor": ["Foothill", "Foothill", ""]}, index=["a", "b", "c"])
    at = pd.Series({"a": 7})
    site, between = check.split(
        crashes, at, pd.Series(True, index=crashes.index), pd.Index([7]), pd.Index(["Foothill"])
    )
    assert site.to_dict() == {7: 1.0}
    assert between.to_dict() == {"Foothill": 1.0}
    assert site.sum() + between.sum() == 2  # the crash with no road is in neither


def _street_grid() -> tuple[dict[int, set[str]], dict[Any, list[Any]], pd.Series]:
    streets = {1: {"A St", "X St"}, 2: {"A St", "Y St"}, 3: {"B St", "X St"}}
    return (
        streets,
        model.corridor_corners(streets),
        pd.Series({"A": 1.0, "B": 2.0, "X": 0.5, "Y": 0.4}),
    )


def test_too_few_crashes_falls_back_to_past_crashes_and_says_so() -> None:
    streets, corners, km = _street_grid()
    bike = pd.Series({1: 2.0, 2: 1.0, 3: 0.0})
    result = model.score_corridors(
        bike, bike * 0, streets, corners, pd.Series({"B": 3.0}), pd.Series(dtype=float), km
    )
    table = result["table"]
    assert result["corner_method"] == result["between_method"] == model.PAST
    assert len(result["reasons"]) == 2
    assert table.past.to_dict() == {"A": 3.0, "B": 3.0, "X": 2.0, "Y": 1.0}
    assert table.expected.equals(table.past)
    # Corner 1 is on A and X, so the corridors add up to more than the 6 crashes.
    assert table.past.sum() > bike.sum() + 3


def test_between_corners_fit_ranks_by_length_and_blends_own_count() -> None:
    rng = np.random.default_rng(4)
    names = [f"S{i:03d}" for i in range(300)]
    km = pd.Series(rng.uniform(0.2, 5, len(names)), index=names)
    car = pd.Series(rng.poisson(km * 3), index=names).astype(float)
    bike = pd.Series(rng.poisson(km * 0.6), index=names).astype(float)
    assert bike.sum() >= MIN_CRASHES
    fit = model.fit_between(bike, car, km)
    assert fit.predicted.corr(km) > 0.8
    # The blend lies between the corridor's own count and the fitted mean.
    low = np.minimum(fit.observed, fit.predicted) - 1e-9
    high = np.maximum(fit.observed, fit.predicted) + 1e-9
    assert ((fit.eb >= low) & (fit.eb <= high)).all()


def test_city_pieces_split_a_street_at_the_limit() -> None:
    key = check.piece("Los Altos")
    corners, lost = check.pieces(
        pd.Index([1, 2]), {1: {"Foothill Expy"}, 2: {"FOOTHILL EXPY"}}, pd.Series({1: True}), key
    )
    assert corners == {"Foothill (Los Altos)": [1], "Foothill (elsewhere)": [2]}
    assert lost == 0
    assert check.piece(None)("Foothill", True) == "Foothill"


def _crashes(
    rng: np.random.Generator, km: pd.Series, sites: list[int]
) -> tuple[pd.DataFrame, pd.Series]:
    rows, at = [], {}
    for n, name in enumerate(km.index):
        for year in range(2014, 2025):
            for _ in range(rng.poisson(km[name] * 0.25)):
                rows.append({"year": year, "group": ADULT_GROUP, "corridor": name})
            for _ in range(rng.poisson(km[name] * 4)):
                rows.append({"year": year, "group": CAR, "corridor": name})
            for _ in range(rng.poisson(0.1 * (n % 4))):
                at[len(rows)] = sites[n % len(sites)]
                rows.append({"year": year, "group": ADULT_GROUP, "corridor": name})
    return pd.DataFrame(rows), pd.Series(at)


def test_holdout_scores_every_ranking_and_leaves_length_out_of_rates() -> None:
    rng = np.random.default_rng(7)
    names = [f"S{i:03d}" for i in range(120)]
    km = pd.Series(rng.uniform(0.1, 4, len(names)), index=names)
    sites = list(range(120))
    streets = {s: {f"{names[s]} St"} for s in sites}
    crashes, at = _crashes(rng, km, sites)
    table = check.holdout(
        crashes,
        at,
        pd.Index(sites),
        streets,
        model.corridor_corners(streets),
        km,
        windows=((2019, 2020, 2022),),
        min_later=5,
    )
    adults = table[table.outcome == "All cyclists"]
    assert set(adults.ranking) == {check.PAST, check.LENGTH, check.MODEL}
    assert adults.loc[adults.ranking == check.LENGTH, "rate correlation"].isna().all()
    assert adults.loc[adults.ranking != check.LENGTH, "rate correlation"].notna().all()
    assert adults.scored.all()
    assert adults["count correlation"].notna().all()
    model_row = adults[adults.ranking == check.MODEL].iloc[0]
    assert "between: length and car crash model" in model_row.method
    # No child crashes at all: too few later crashes, so nothing is scored.
    children = table[table.outcome == "Cyclists 18 or under"]
    assert children["rank score"].isna().all() and not children.scored.any()
    assert check.ALL_CYCLISTS in set(children.ranking)


def test_a_window_where_every_corridor_has_a_later_crash_is_not_scored() -> None:
    km = pd.Series({"A": 1.0, "B": 2.0, "C": 3.0})
    crashes = pd.DataFrame(
        [
            {"year": y, "group": ADULT_GROUP, "corridor": c}
            for y in (2018, 2020)
            for c, n in zip("ABC", (2, 5, 8), strict=True)
            for _ in range(n)
        ]
    )
    table = check.holdout(
        crashes,
        pd.Series(dtype=float),
        pd.Index([]),
        {},
        {},
        km,
        windows=((2018, 2019, None),),
        min_later=5,
    )
    row = table[(table.outcome == "All cyclists") & (table.ranking == check.PAST)].iloc[0]
    assert row["later crashes"] == 15 and not row.scored
    assert np.isfinite(row["count correlation"])  # still scored by correlation


def test_the_forecast_table_gives_no_rate_for_a_short_stub() -> None:
    table = pd.DataFrame(
        {"km": [0.03, 2.0], "past": [3.0, 4.0], "corners": [4.0, 3.0], "between": [0.0, 1.0]},
        index=["Stub", "Long"],
    )
    table["expected"] = table.corners + table.between
    table["per_km"] = table.expected / table.km
    out = check.forecast_table({"table": table}, table.index)
    assert out.loc["Long", "expected per km"] == 2.0
    assert out["expected per km"].isna().to_dict() == {"Long": False, "Stub": True}


def test_streets_that_differ_only_in_type_are_separate_corridors() -> None:
    names = [
        *["Distel Circle", "Distel Drive", "DISTEL DR", "Saint Francis Drive"],
        *["Park Avenue", "Park Place", "Park Way", "1st Street", "1st Avenue", "South Street"],
    ]
    lines = gpd.GeoDataFrame(
        {"name": names},
        geometry=[LineString([(0, 10 * i), (100 + 100 * i, 10 * i)]) for i in range(len(names))],
        crs="EPSG:26910",
    )
    labels = check.street_labels(lines["name"])
    assert sorted(labels.values()) == [
        *["1st Avenue", "1st Street", "Distel", "Distel Circle", "Park", "Park Place"],
        *["Park Way", "Saint Francis", "South Street"],
    ]
    km = check.piece_lengths(lines, box(-1, -1, 2000, 200), None, labels, check.piece(None))
    assert km.round(3).to_dict() == {
        "1st Avenue": 0.9,
        "1st Street": 0.8,
        "Distel": 0.5,  # two spellings of Distel Drive
        "Distel Circle": 0.1,
        "Park": 0.5,
        "Park Place": 0.6,
        "Park Way": 0.7,
        "Saint Francis": 0.4,
        "South Street": 1.0,
    }
    from bike_safety_ca.network.junctions import street_key

    corners, lost = check.pieces(
        pd.Index([1, 2]),
        {1: {street_key("Park Avenue"), street_key("1st Street")}, 2: {street_key("Park Place")}},
        pd.Series(dtype=bool),
        check.piece(None),
        lambda name: labels.get(name, ""),
        km.index,
    )
    assert corners == {"1st Street": [1], "Park": [1], "Park Place": [2]} and lost == 0
    # A report is matched by name; its type decides between streets when it names
    # one of them, and otherwise the longest street of that name takes it.
    by_name = check.streets_by_name(lines)
    reported = {
        text: labels.get(check.reported_street(text, by_name), "")
        for text in ("PARK PL", "PARK AV", "PARK", "PARK RD", "1ST ST", "S DISTEL DR", "SOUTH ST")
    }
    assert reported == {
        "PARK PL": "Park Place",
        "PARK AV": "Park",
        "PARK": "Park Way",
        "PARK RD": "Park Way",
        "1ST ST": "1st Street",
        "S DISTEL DR": "Distel",
        "SOUTH ST": "South Street",
    }
    assert check.reported_street("ELM ST", by_name) == check.reported_street(None, by_name) == ""
    # A street mapped without a type is not preferred by a report that gives none.
    bare = {"PARK": ["PARK AVENUE", "PARK"]}  # longest first
    assert check.reported_street("PARK", bare) == check.reported_street("PARK RD", bare)
    assert check.reported_street("N PARK", bare) == "PARK AVENUE"
    assert check.reported_street("PARK", {"PARK": ["PARK"]}) == "PARK"


def test_the_floor_and_the_reported_totals_count_a_corner_crash_once() -> None:
    # Every crash is at corner 1, where A and X cross, so each is on two corridors.
    km = pd.Series({"A": 1.0, "B": 1.0, "X": 1.0, "Y": 1.0})
    corners = {"A": [1], "B": [2], "X": [1], "Y": [2]}
    streets = {1: {"A St", "X St"}, 2: {"B St", "Y St"}}
    years = [2018] * 12 + [2020] * 20
    crashes = pd.DataFrame({"year": years, "group": ADULT_GROUP, "corridor": ""})
    at = pd.Series(1, index=crashes.index)
    table = check.holdout(
        crashes, at, pd.Index([1, 2]), streets, corners, km, windows=((2018, 2019, None),)
    )
    rows = table[table.outcome == "All cyclists"]
    assert set(rows["later crashes"]) == {20} and set(rows["training crashes"]) == {12}
    # 20 crashes are under the floor of 30, though the corridor sums come to 40.
    assert rows["rank score"].isna().all() and not rows.scored.any()
    assert "0 of 0 with 30+ later crashes" in check.report(table)
    scored = check.holdout(
        crashes,
        at,
        pd.Index([1, 2]),
        streets,
        corners,
        km,
        windows=((2018, 2019, None),),
        min_later=20,
    )
    assert scored.loc[scored.outcome == "All cyclists", "rank score"].notna().all()


def test_a_boundary_street_is_counted_once_and_a_boundary_corner_moves_to_its_street() -> None:
    limit = box(0, 0, 100, 100)
    lines = gpd.GeoDataFrame(
        {"name": ["Edge Rd", "Cross St"]},
        geometry=[LineString([(0, 0), (0, 100)]), LineString([(-50, 50), (50, 50)])],
        crs="EPSG:26910",
    )
    labels = check.street_labels(lines["name"])
    key = check.piece("Town")
    km = check.piece_lengths(lines, box(-100, -100, 200, 200), limit, labels, key)
    assert km.to_dict() == {"Cross (Town)": 0.05, "Cross (elsewhere)": 0.05, "Edge (Town)": 0.1}
    from bike_safety_ca.network.junctions import street_key

    corners, lost = check.pieces(
        pd.Index([1, 2]),
        {1: {street_key("Edge Rd")}, 2: {street_key("Nowhere Ln")}},
        pd.Series({1: False, 2: False}),  # corner 1 judged outside, but Edge is mapped only inside
        key,
        lambda name: labels.get(name, ""),
        km.index,
    )
    assert corners == {"Edge (Town)": [1]}
    assert lost == 1


def test_the_synthetic_command_prints_the_check_and_writes_the_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["corridors", "--synthetic", "--out", str(tmp_path)])
    check.main()
    printed = capsys.readouterr().out
    assert "Corridor hold-out (synthetic city)" in printed and "windows scored" in printed
    assert check.NOTE in printed
    methods = pd.read_csv(tmp_path / "corridor_forecast_methods.csv")
    # The made-up city has no crashes between corners, so that part falls back and says so.
    assert set(methods["between corners"]) == {model.PAST}
    assert methods["fallback reasons"].str.contains("between corners").all()
    table = pd.read_csv(tmp_path / "corridor_forecast_cyclists_all.csv", index_col=0)
    assert table.expected.is_monotonic_decreasing
    assert (tmp_path / "corridor_holdout.csv").exists()


def test_loading_a_real_area_splits_at_the_limit_and_counts_what_has_no_street(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shapely.geometry import Point

    from bike_safety_ca.crashes import groups
    from bike_safety_ca.network import junctions

    crs = "EPSG:26910"
    lines = gpd.GeoDataFrame(
        {"name": ["Main St", "Oak Ave"]},
        geometry=[LineString([(0, 50), (200, 50)]), LineString([(50, 0), (50, 100)])],
        crs=crs,
    )
    sites = gpd.GeoDataFrame(geometry=[Point(50, 50), Point(150, 50)], index=[1, 2], crs=crs)
    streets = pd.Series(
        {
            1: {junctions.street_key("Main St"), junctions.street_key("Oak Ave")},
            2: {junctions.street_key("Main St")},
        }
    )
    crashes = gpd.GeoDataFrame(
        {
            "merged_id": list("abcde"),
            "group": [ADULT_GROUP] * 4 + [CAR],
            "year": [2020] * 5,
            "PRIMARY_RD": ["MAIN ST", "MAIN ST", "MAIN", "NOWHERE RD", "OAK AV"],
        },
        geometry=[Point(50, 50), Point(20, 50), Point(180, 50), Point(30, 30), Point(50, 20)],
        crs=crs,
    )
    monkeypatch.setattr(gpd, "read_parquet", lambda *args, **kwargs: lines)
    monkeypatch.setattr(junctions, "build_junctions", lambda *args, **kwargs: (sites, streets))
    monkeypatch.setattr(groups, "load", lambda *args, **kwargs: crashes)
    monkeypatch.setattr(
        junctions, "assign_crashes", lambda *args, **kwargs: pd.DataFrame({"site": {"a": 1}})
    )
    config = SimpleNamespace(crs=crs, child_max_age=18, first_year=2014, city="Town")
    data = check.load(
        config, Path("crashes"), Path("ways"), box(0, 0, 200, 100), box(0, 0, 100, 100)
    )
    assert data["km"].round(3).to_dict() == {
        "Main (Town)": 0.1,
        "Main (elsewhere)": 0.1,
        "Oak (Town)": 0.1,
    }
    assert data["corners"] == {"Main (Town)": [1], "Main (elsewhere)": [2], "Oak (Town)": [1]}
    assert list(data["crashes"].corridor) == [
        "Main (Town)",
        "Main (Town)",
        "Main (elsewhere)",
        "",
        "Oak (Town)",
    ]
    assert data["at"].to_dict() == {0: 1}
    assert list(data["areas"]["Town"]) == ["Main (Town)", "Oak (Town)"]
    assert data["unplaced"] == {
        "intersections on no mapped corridor": 0,
        "cyclist crashes between corners on no mapped corridor": 1,
        "cyclist crashes between corners": 3,
    }


def test_the_corner_part_of_a_corridor_keeps_the_fitted_spread_power(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bike_safety_ca.model import corridors

    class Seen(Exception):
        pass

    def stub(*_: object, **options: object) -> dict:
        raise Seen(options)

    monkeypatch.setattr(corridors, "rank_intersections", stub)
    empty = pd.Series(dtype=float)
    with pytest.raises(Seen) as seen:
        corridors.score_corridors(empty, empty, {}, {}, empty, empty, empty)
    # ``None`` fits the power: the corridor table was not part of the comparison at power 1.
    assert seen.value.args[0] == {"spread_power": None}
