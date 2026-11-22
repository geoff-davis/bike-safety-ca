"""``python -m bike_safety_ca.model``: the intersection ranking, on the demo city."""

from __future__ import annotations

import json
import runpy
import sys
from dataclasses import replace
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from pyproj import Transformer
from shapely.geometry import LineString, Point, box

from bike_safety_ca import config, demo
from bike_safety_ca.io import read_shapes
from bike_safety_ca.model import __main__ as command
from bike_safety_ca.model import crash_history, ranking

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "demo_claremont.yaml"
SETTINGS = config.load(CONFIG)


@pytest.fixture(scope="module")
def processed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The demo city's built tables: real streets, made-up crashes."""
    return demo.build(SETTINGS, tmp_path_factory.mktemp("demo"))["crashes"].parents[1]


@pytest.fixture(scope="module")
def small_area(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """An outline with under 100 made-up child crashes at its intersections."""
    assert SETTINGS.area_file is not None
    centre = read_shapes(SETTINGS.area_file).to_crs(SETTINGS.crs).union_all().centroid
    path = tmp_path_factory.mktemp("outline") / "small.geojson"
    gpd.GeoDataFrame(geometry=[centre.buffer(900)], crs=SETTINGS.crs).to_file(path)
    return path


def _run(monkeypatch: pytest.MonkeyPatch, processed: Path, *arguments: object) -> None:
    argv = ["model", "--config", CONFIG, "--processed", processed]
    argv += ["--crashes", processed / "crashes", *arguments]
    monkeypatch.setattr(sys, "argv", [str(argument) for argument in argv])
    command.main()


def test_the_command_writes_the_ranking_as_a_table_and_a_map_file(
    processed: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _run(monkeypatch, processed, "--out", tmp_path)
    table = pd.read_csv(tmp_path / "intersection_ranking.csv")
    assert list(table.columns) == ranking.COLUMNS
    assert len(table) > 1000 and table.intersection.is_unique
    assert list(table["rank"]) == list(range(1, len(table) + 1))
    assert table.score.is_monotonic_decreasing and table.score.iloc[0] > table.score.iloc[-1]
    assert set(table.method) == {"street-length model"} and table.fallback_reason.isna().all()
    # The model's score is its expected count, given beside the count on record.
    assert (table.expected_bike_crashes == table.score).all()
    assert table.observed_bike_crashes.sum() > 100 and table.car_crashes.sum() > 100
    assert table.streets.str.contains(" / ").any() and table.in_city.any()
    assert table.street_keys.str.contains("; ").mean() > 0.5  # most corners join two streets
    assert not table.in_city.all()

    points = gpd.read_file(tmp_path / "intersection_ranking.geojson")
    assert len(points) == len(table) and set(points.geom_type) == {"Point"}
    assert list(points["rank"]) == list(table["rank"])
    assert points.geometry.x.between(-118.5, -117.0).all()  # longitude and latitude
    assert (points.geometry.x.round(6) == table.longitude).all()

    said = capsys.readouterr().out
    crashes = int(table.observed_bike_crashes.sum())
    assert f"Method: street-length model, fitted on {crashes:,} bike crashes" in said
    assert "intersection_ranking.csv" in said and "intersection_ranking.geojson" in said


def test_top_keeps_only_the_highest_ranked(
    processed: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _run(monkeypatch, processed, "--out", tmp_path, "--top", 7)
    assert list(pd.read_csv(tmp_path / "intersection_ranking.csv")["rank"]) == list(range(1, 8))
    assert len(gpd.read_file(tmp_path / "intersection_ranking.geojson")) == 7
    with pytest.raises(SystemExit) as stopped:
        _run(monkeypatch, processed, "--out", tmp_path, "--top", 0)
    assert stopped.value.code == 2


def test_a_child_ranking_goes_to_files_of_its_own(
    processed: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _run(monkeypatch, processed, "--out", tmp_path, "--children")
    children = pd.read_csv(tmp_path / "intersection_ranking_children.csv")
    assert (tmp_path / "intersection_ranking_children.geojson").exists()
    assert not (tmp_path / "intersection_ranking.csv").exists()
    _run(monkeypatch, processed, "--out", tmp_path)
    everyone = pd.read_csv(tmp_path / "intersection_ranking.csv")
    assert 100 <= children.observed_bike_crashes.sum() < everyone.observed_bike_crashes.sum()
    assert children.car_crashes.sum() == everyone.car_crashes.sum()


def test_too_few_child_crashes_are_refused_unless_forced(
    processed: Path,
    small_area: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments = ["--area", small_area, "--out", tmp_path, "--children"]
    with pytest.raises(SystemExit) as stopped:
        _run(monkeypatch, processed, *arguments)
    message = str(stopped.value.code)
    assert "fewer than 100" in message and "--force" in message and "all-cyclist" in message
    assert not list(tmp_path.iterdir())

    _run(monkeypatch, processed, *arguments, "--force")
    table = pd.read_csv(tmp_path / "intersection_ranking_children.csv")
    crashes = int(table.observed_bike_crashes.sum())
    assert 0 < crashes < 100
    # Too few to fit: the blend is used, and the file and the terminal both say so and why.
    assert set(table.method) == {"hand-built blend"}
    assert set(table.fallback_reason) == {f"{crashes} bike crashes, fewer than 100"}
    assert table.expected_bike_crashes.isna().all() and table.score.is_monotonic_decreasing
    said = capsys.readouterr().out
    assert f"Method: hand-built blend ({crashes} bike crashes, fewer than 100)" in said
    assert "fitted on" not in said


# --- a made-up town small enough to work the ranking out by hand -------------------------------

X0, Y0 = 430_000.0, 3_773_000.0  # metres, in the demo config's coordinate system
CORNERS = {
    "Ash Street / First Avenue": (0.0, 0.0),
    "Ash Street / Second Avenue": (300.0, 0.0),
    "Birch Street / First Avenue": (0.0, 300.0),
    "Birch Street / Second Avenue": (300.0, 300.0),
}
TOWN = replace(SETTINGS, city="Alder", first_year=2016, area_file=None, city_limit_file=None)
# One made-up crash: id, year, where (metres from the town's corner), cyclist ages
# (none: motor vehicles only), and the report it may duplicate.
Crash = tuple[str, int, tuple[float, float], tuple[int, ...], str | None]


def _town(folder: Path, crashes: list[Crash]) -> tuple[Path, Path, Path]:
    """Write a two-by-two grid of streets, an outline and crash tables; return their paths."""
    lines = {
        "Ash Street": [(-150, 0), (0, 0), (300, 0), (450, 0)],
        "Birch Street": [(-150, 300), (0, 300), (300, 300), (450, 300)],
        "First Avenue": [(0, -150), (0, 0), (0, 300), (0, 450)],
        "Second Avenue": [(300, -150), (300, 0), (300, 300), (300, 450)],
    }
    nodes: dict[tuple[int, int], int] = {}
    ways = gpd.GeoDataFrame(
        {
            "osm_id": range(1, len(lines) + 1),
            "highway": "residential",
            "name": list(lines),
            "lanes": None,
            "oneway": None,
            "node_ids": [
                json.dumps([nodes.setdefault(xy, len(nodes) + 1) for xy in line])
                for line in lines.values()
            ],
        },
        geometry=[LineString([(X0 + x, Y0 + y) for x, y in line]) for line in lines.values()],
        crs=TOWN.crs,
    )
    ways_path = folder / "streets.parquet"
    ways.to_parquet(ways_path)
    # The outline ends 20 m east of Second Avenue.
    area_path = folder / "area.geojson"
    outline = box(X0 - 100, Y0 - 100, X0 + 320, Y0 + 400)
    gpd.GeoDataFrame(geometry=[outline], crs=TOWN.crs).to_file(area_path)
    table = gpd.GeoDataFrame(
        {
            "merged_id": [c[0] for c in crashes],
            "year": [c[1] for c in crashes],
            "injury_crash": True,
            "bike_involved": [bool(c[3]) for c in crashes],
            "ped_involved": False,
            "possible_duplicate_of": [c[4] for c in crashes],
            "INTERSECTION": None,
            "DISTANCE": None,
            "PRIMARY_RD": None,
            "SECONDARY_RD": None,
        },
        geometry=[Point(X0 + c[2][0], Y0 + c[2][1]) for c in crashes],
        crs=TOWN.crs,
    )
    crash_folder = folder / "crashes"
    crash_folder.mkdir()
    table.to_parquet(crash_folder / "crashes_merged_26911.parquet")
    parties = [(c[0], "4", str(age)) for c in crashes for age in c[3]]
    parties += [(c[0], "1", "40") for c in crashes]  # a driver in every crash
    pd.DataFrame(parties, columns=["CASE_ID", "PARTY_TYPE", "PARTY_AGE"]).to_parquet(
        crash_folder / "parties_merged.parquet"
    )
    return crash_folder, ways_path, area_path


def test_a_small_town_is_ranked_as_worked_out_by_hand(tmp_path: Path) -> None:
    crashes: list[Crash] = [
        ("child-1", 2018, (3, 4), (12,), None),
        ("child-2", 2020, (-5, 0), (18, 44), None),  # the youngest cyclist decides
        ("adult-1", 2021, (0, 6), (19,), None),
        ("car-1", 2019, (2, 2), (), None),
        ("adult-2", 2017, (304, 0), (30,), None),
        ("adult-3", 2022, (0, 296), (51,), None),
        ("car-2", 2016, (300, 305), (), None),
        ("car-3", 2023, (297, 300), (), None),
        # Not counted: a second report of adult-2, a crash before the first year,
        # and one 25 m from Ash and Second but outside the outline.
        ("duplicate", 2017, (303, 1), (30,), "adult-2"),
        ("too-early", 2015, (300, -4), (25,), None),
        ("outside", 2020, (325, 0), (33,), None),
    ]
    crash_folder, ways, area = _town(tmp_path, crashes)
    table, summary = ranking.rank(TOWN, crash_folder, ways, area)

    by_name = table.set_index("streets")
    assert set(by_name.index) == set(CORNERS)
    assert by_name.observed_bike_crashes.to_dict() == dict(zip(CORNERS, (3, 1, 1, 0)))
    assert by_name.car_crashes.to_dict() == dict(zip(CORNERS, (1, 0, 0, 2)))
    assert summary["bike_crashes"] == 5 and summary["car_crashes"] == 3

    # Five bike crashes: the blend.  Each count is blended with the mean of its two
    # streets' averages (weight 1 for bikes, 0.5 for cars), and the score is the
    # product of one plus each.  Street averages, bike then car:
    # Ash 2 and 0.5, First 2 and 0.5, Second 0.5 and 1, Birch 0.5 and 1.
    expected = {
        "Ash Street / First Avenue": (1 + (3 + 2) / 2) * (1 + (1 + 0.5 * 0.5) / 1.5),
        "Ash Street / Second Avenue": (1 + (1 + 1.25) / 2) * (1 + (0 + 0.5 * 0.75) / 1.5),
        "Birch Street / First Avenue": (1 + (1 + 1.25) / 2) * (1 + (0 + 0.5 * 0.75) / 1.5),
        "Birch Street / Second Avenue": (1 + (0 + 0.5) / 2) * (1 + (2 + 0.5 * 1) / 1.5),
    }
    assert by_name.score.to_dict() == pytest.approx(expected, abs=5e-5)
    assert set(table.method) == {"hand-built blend"}
    assert set(table.fallback_reason) == {"5 bike crashes, fewer than 100"}
    assert table.expected_bike_crashes.isna().all()
    # The two middle corners tie: the lower intersection number comes first.
    tied = by_name.loc[["Ash Street / Second Avenue", "Birch Street / First Avenue"]]
    assert tied.score.nunique() == 1
    first, second = tied.sort_values("intersection").index
    assert list(table.streets) == [
        "Ash Street / First Avenue",
        "Birch Street / Second Avenue",
        first,
        second,
    ]
    assert list(table["rank"]) == [1, 2, 3, 4]

    # Children only: the two crashes with a cyclist of 18 or under, both at one corner.
    children = ranking.rank(TOWN, crash_folder, ways, area, children=True, force=True)[0]
    counts = children.set_index("streets").observed_bike_crashes.to_dict()
    assert counts == dict(zip(CORNERS, (2, 0, 0, 0)))

    # The GeoJSON holds longitude, latitude in EPSG:4326, at each corner's own place.
    written = ranking.write(table, tmp_path / "out")
    text = json.loads(written["geojson"].read_text())
    points = gpd.read_file(written["geojson"])
    assert points.crs == "EPSG:4326" and list(points.streets) == list(table.streets)
    to_degrees = Transformer.from_crs(TOWN.crs, "EPSG:4326", always_xy=True)
    for feature in text["features"]:
        x, y = CORNERS[feature["properties"]["streets"]]
        longitude, latitude = to_degrees.transform(X0 + x, Y0 + y)
        assert -118 < longitude < -117 and 34 < latitude < 35
        assert feature["geometry"]["type"] == "Point"
        assert feature["geometry"]["coordinates"] == pytest.approx([longitude, latitude], abs=1e-6)
        assert feature["properties"]["longitude"] == pytest.approx(longitude, abs=1e-6)
        assert feature["properties"]["latitude"] == pytest.approx(latitude, abs=1e-6)


def test_a_child_ranking_is_refused_at_99_crashes_and_made_at_100(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The command has no number of its own: the floor is the model's.
    assert crash_history.MIN_CRASHES == 100
    spots = list(CORNERS.values())

    def town(name: str, count: int) -> tuple[Path, Path, Path]:
        crashes: list[Crash] = [
            (f"child-{i}", 2016 + i % 8, spots[i % 7 % 4], (9 + i % 10,), None)
            for i in range(count)
        ]
        crashes += [(f"car-{i}", 2016 + i % 8, spots[i % 3], (), None) for i in range(30)]
        folder = tmp_path / name
        folder.mkdir()
        return _town(folder, crashes)

    # Four corners are too few to fit anything, so the fit is stood in for: what
    # matters here is at which count the model is tried.
    tried: list[int] = []

    def fit(bike: pd.Series, car: pd.Series, streets: object) -> dict[str, object]:
        tried.append(int(bike.sum()))
        raise RuntimeError("four corners")

    monkeypatch.setattr(crash_history, "fit_street_model", fit)

    short = town("short", 99)
    with pytest.raises(ranking.RankingError, match="99 crashes .* fewer than 100.*--force"):
        ranking.rank(TOWN, *short, children=True)
    forced = ranking.rank(TOWN, *short, children=True, force=True)[1]
    # Forced, it is the blend for the model's own reason, with no fit tried: the same floor.
    assert forced["bike_crashes"] == 99 and forced["method"] == "hand-built blend"
    assert forced["reason"] == "99 bike crashes, fewer than 100" and tried == []

    table, enough = ranking.rank(TOWN, *town("enough", 100), children=True)
    assert enough["bike_crashes"] == 100 and int(table.observed_bike_crashes.sum()) == 100
    # At 100 it is not refused and the model is tried.
    assert tried == [100] and enough["reason"] == "fit failed: four corners"
    assert set(table.fallback_reason) == {"fit failed: four corners"}


def test_a_missing_input_stops_with_a_message_naming_it(
    processed: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with pytest.raises(SystemExit) as stopped:
        _run(monkeypatch, tmp_path / "nowhere", "--out", tmp_path / "out")
    message = str(stopped.value.code)
    assert stopped.value.code not in (0, None) and message.startswith("error: ")
    for name in ("street table", "crash table", "party table"):
        assert f"{name} not found" in message
    assert "python -m bike_safety_ca.network" in message
    assert "python -m bike_safety_ca.crashes" in message
    assert not (tmp_path / "out").exists()

    # The street table is there and the crash tables are not: only those are named.
    argv = ["model", "--config", CONFIG, "--processed", processed, "--crashes", tmp_path / "no"]
    monkeypatch.setattr(sys, "argv", [str(argument) for argument in argv])
    with pytest.raises(SystemExit) as stopped:
        command.main()
    message = str(stopped.value.code)
    assert "crash table not found" in message and "street table" not in message


def test_built_outlines_that_are_absent_are_named(tmp_path: Path) -> None:
    plain = config.load(ROOT / "config" / "davis.yaml")  # no outline files of its own
    with pytest.raises(ranking.RankingError, match="area outline not found.*city limit not found"):
        ranking.inputs(plain, tmp_path, tmp_path)


def test_the_command_runs_as_a_script(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert command.__file__ is not None
    monkeypatch.setattr(sys, "argv", ["model", "--config", str(CONFIG), "--processed", "x"])
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(command.__file__, run_name="__main__")
    assert "street table not found: x/network" in str(stopped.value.code)
