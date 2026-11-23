"""The command-line entry points, run on a made-up town with nothing fetched.

The town is a grid of nine streets by nine avenues.  Its west side is the city
of Alder and its east side the city of Birch; every crash, party and outline
here is invented.
"""

from __future__ import annotations

import json
import runpy
import shutil
import sys
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import geopandas as gpd
import httpx
import pandas as pd
import pytest
import shapely
import yaml
from shapely.geometry import Point, Polygon, box

from bike_safety_ca import CAR, config, demo
from bike_safety_ca.checks import holdout, reporting, sensitivity
from bike_safety_ca.crashes import __main__ as crashes_command
from bike_safety_ca.crashes import groups, merge
from bike_safety_ca.crashes.locate import streets_as_centerlines
from bike_safety_ca.download import arcgis, ccrs, census, osm, schools
from bike_safety_ca.network import __main__ as network_command
from bike_safety_ca.network import area, streets
from bike_safety_ca.report import __main__ as report_command
from bike_safety_ca.report import movement

# pandas announces what it will stop accepting as a warning first; a new one
# raised by these runs fails the test instead of scrolling past.
pytestmark = pytest.mark.filterwarnings("error::DeprecationWarning", "error::FutureWarning")

Bounds = tuple[float, float, float, float]

CRS = "EPSG:26910"
SIZE = 9
WEST, SOUTH, STEP_X, STEP_Y = -122.0, 37.0, 0.002, 0.0015  # degrees; blocks of about 170 m
STREETS = ["Aardvark", "Badger", "Capybara", "Dingo", "Echidna", "Ferret", "Gecko", "Heron", "Ibis"]
AVENUES = ["Kumquat", "Lychee", "Mango", "Nectarine", "Olive", "Papaya", "Quince", "Rhubarb", "Yam"]
ALDER_AVENUES = 5  # the first five avenues are in Alder, the rest in Birch
POLICE = {"ALDER": "0101", "BIRCH": "0102"}  # made-up agency codes

SETTINGS: dict[str, object] = {
    "city": "Alder",
    "county": "Made Up",
    "crash_source": "tims+ccrs",
    "first_year": 2014,
    "child_max_age": 15,
    "holdout_windows": [[2018, 2019, 2022], [2020, 2021, 2022], [2022, 2023, None]],
    "crs": CRS,
    "ccrs_county_code": 99,
    "ccrs_cities": ["Alder", "Birch"],
    "latitude": [36.9, 37.1],
    "longitude": [-122.1, -121.9],
}


def _corner(street: int, avenue: int) -> tuple[float, float]:
    """Longitude and latitude where a street (running east) meets an avenue (running north)."""
    return (WEST + avenue * STEP_X, SOUTH + street * STEP_Y)


def _block(first_avenue: float, last_avenue: float) -> Polygon:
    """The town between two avenues, half a block beyond the streets at either end."""
    return box(
        WEST + first_avenue * STEP_X,
        SOUTH - 0.5 * STEP_Y,
        WEST + last_avenue * STEP_X,
        SOUTH + (SIZE - 0.5) * STEP_Y,
    )


ALDER, BIRCH = _block(-0.5, ALDER_AVENUES - 0.5), _block(ALDER_AVENUES - 0.5, SIZE - 0.5)
TOWN = _block(-0.5, SIZE - 0.5)


def _overpass() -> dict[str, list[dict[str, object]]]:
    """The town's streets as an Overpass reply: one way per street, crossing at shared nodes."""

    def node(street: int, avenue: int) -> int:
        return 1000 + street * SIZE + avenue

    def way(number: int, name: str, nodes: list[int]) -> dict[str, object]:
        kind = "secondary" if number % 4 == 0 else "residential"
        return {
            "type": "way",
            "id": number,
            "nodes": nodes,
            "tags": {"highway": kind, "name": name},
        }

    elements: list[dict[str, object]] = []
    for i, name in enumerate(STREETS):
        elements.append(way(i, f"{name} Street", [node(i, j) for j in range(SIZE)]))
    for j, name in enumerate(AVENUES):
        elements.append(way(100 + j, f"{name} Avenue", [node(i, j) for i in range(SIZE)]))
    for i in range(SIZE):
        for j in range(SIZE):
            lon, lat = _corner(i, j)
            elements.append({"type": "node", "id": node(i, j), "lon": lon, "lat": lat})
    return {"elements": elements}


def _census_zips(folder: Path) -> dict[str, Path]:
    """Made-up place and county outlines, zipped under the names the Census files have."""
    layers = {
        "places": gpd.GeoDataFrame(
            {"NAME": ["Alder", "Birch"], "LSAD": "25", "STATEFP": "06"},
            geometry=[ALDER, BIRCH],
            crs=4326,
        ),
        "counties": gpd.GeoDataFrame(
            {"NAME": ["Made Up"], "LSAD": "06", "STATEFP": "06"},
            geometry=[TOWN.buffer(0.05)],
            crs=4326,
        ),
    }
    written = {}
    for kind, stem in census.names().items():
        parts = folder / "parts" / kind
        parts.mkdir(parents=True, exist_ok=True)
        layers[kind].to_file(parts / f"{stem}.shp")
        written[kind] = folder / f"{stem}.zip"
        with zipfile.ZipFile(written[kind], "w") as archive:
            for part in sorted(parts.iterdir()):
                archive.write(part, part.name)
    return written


def _settings(folder: Path, **changes: object) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "alder.yaml"
    path.write_text(yaml.safe_dump(SETTINGS | changes))
    return path


def _outline(path: Path, shape: Polygon) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(geometry=[shape], crs=4326).to_file(path, driver="GeoJSON")
    return path


def _run(monkeypatch: pytest.MonkeyPatch, main: Callable[[], None], *arguments: object) -> None:
    monkeypatch.setattr(sys, "argv", ["command", *(str(argument) for argument in arguments)])
    main()


def _run_as_script(monkeypatch: pytest.MonkeyPatch, module: ModuleType, *arguments: object) -> None:
    """Run a command's file the way ``python -m`` does."""
    assert module.__file__ is not None
    monkeypatch.setattr(sys, "argv", ["command", *(str(argument) for argument in arguments)])
    runpy.run_path(module.__file__, run_name="__main__")


# --- python -m bike_safety_ca.network ---------------------------------------------------------


class Fetched:
    """Stand-ins for the downloads: each writes a made-up file and notes how it was called."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[tuple[str, object]] = []
        self.streets_asked: list[tuple[Bounds, str | None]] = []
        self.own_limit: Polygon | None = ALDER
        self.real_arcgis = arcgis.download
        monkeypatch.setattr(census, "download", self.census)
        monkeypatch.setattr(arcgis, "download", self.arcgis)
        monkeypatch.setattr(schools, "download", self.schools)
        monkeypatch.setattr(osm, "download", self.osm)

    def census(self, out: Path, year: int = 2023, overwrite: bool = False) -> dict[str, Path]:
        self.calls.append(("census", overwrite))
        return _census_zips(out)

    def arcgis(self, layer_url: str, dest: Path, overwrite: bool = False) -> Path:
        self.calls.append(("arcgis", layer_url))
        if self.own_limit is None:
            raise httpx.ConnectError("the made-up city's server is down")
        return _outline(dest, self.own_limit)

    def schools(self, dest: Path, overwrite: bool = False) -> Path:
        self.calls.append(("schools", dest.name))
        lon, lat = _corner(4, 7)  # a school in Birch
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            "CDSCode\tStatusType\tDistrict\tSchool\tLatitude\tLongitude\n"
            f"1\tActive\tMade Up Unified\tTapir Elementary\t{lat}\t{lon}\n",
            encoding="latin-1",
        )
        return dest

    def osm(
        self,
        bounds: Bounds,
        out: Path,
        overwrite: bool = False,
        date: str | None = None,
    ) -> Path:
        self.calls.append(("osm", overwrite))
        self.streets_asked.append((bounds, date))
        out.mkdir(parents=True, exist_ok=True)
        (out / "overpass_streets.json").write_text(json.dumps(_overpass()))
        return out / "overpass_streets.json"


@pytest.fixture
def fetched(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Fetched:
    monkeypatch.chdir(tmp_path)  # so a default path can never reach the repository's data
    return Fetched(monkeypatch)


def test_the_network_command_builds_the_outlines_and_the_street_table(
    fetched: Fetched, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(tmp_path, osm_date="2031-01-01T00:00:00Z")
    raw, out = tmp_path / "raw", tmp_path / "processed"
    _run(monkeypatch, network_command.main, "--config", settings, "--raw", raw, "--out", out)

    built = area.paths(out / "boundaries", CRS)
    outline, limit = gpd.read_parquet(built["area"]), gpd.read_parquet(built["city_limit"])
    whole = gpd.GeoSeries([TOWN, ALDER], crs=4326).to_crs(CRS)
    assert outline.area.iloc[0] == pytest.approx(whole.area.iloc[0], rel=1e-6)
    assert limit.area.iloc[0] == pytest.approx(whole.area.iloc[1], rel=1e-6)
    assert limit.name.tolist() == ["Alder"]
    # The streets are asked for inside the outline just built, as of the config's date.
    ((bounds, date),) = fetched.streets_asked
    assert bounds == pytest.approx(TOWN.bounds) and date == "2031-01-01T00:00:00Z"
    assert [call for call, _ in fetched.calls] == ["census", "osm"]  # no limit layer, no schools
    table = gpd.read_parquet(streets.path(out / "network", CRS))
    assert len(table) == 2 * SIZE and table.crs == CRS
    assert {"Aardvark Street", "Yam Avenue"} <= set(table.name)


def test_the_citys_own_limit_and_school_circles_replace_the_census_outlines(
    fetched: Fetched, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(
        tmp_path,
        city_limit_url="https://example.org/made-up/limit/0",
        area_schools=[{"school": "Tapir Elementary", "district": "Made Up Unified"}],
        area_buffer_m=100.0,
    )
    fetched.own_limit = _block(-0.5, 1.5)  # narrower than the Census outline of Alder
    raw, out = tmp_path / "raw", tmp_path / "processed"
    arguments = ["--config", settings, "--raw", raw, "--out", out, "--overwrite"]
    _run(monkeypatch, network_command.main, "area", *arguments)

    assert fetched.calls == [
        ("census", True),
        ("arcgis", "https://example.org/made-up/limit/0"),
        ("schools", "pubschls.txt"),
    ]
    built = area.paths(out / "boundaries", CRS)
    limit, outline = gpd.read_parquet(built["city_limit"]), gpd.read_parquet(built["area"])
    own = gpd.GeoSeries([fetched.own_limit], crs=4326).to_crs(CRS)
    assert limit.area.iloc[0] == pytest.approx(own.area.iloc[0], rel=1e-6)
    # The area is the city's own limit and a 100 m circle around the school, apart from it.
    assert shapely.get_num_geometries(outline.geometry.iloc[0]) == 2
    assert not (out / "network").exists()  # only the step named was run

    # When the city's layer cannot be fetched the Census outline of the city is used.
    fetched.own_limit = None
    _run(monkeypatch, network_command.main, "area", *arguments)
    census_limit = gpd.GeoSeries([ALDER], crs=4326).to_crs(CRS)
    again = gpd.read_parquet(built["city_limit"])
    assert again.area.iloc[0] == pytest.approx(census_limit.area.iloc[0], rel=1e-6)


def test_a_saved_limit_from_another_address_stops_the_network_command(
    fetched: Fetched,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _settings(tmp_path, city_limit_url="https://example.org/made-up/limit/0")
    raw, out = tmp_path / "raw", tmp_path / "processed"
    saved = _outline(raw / "boundaries" / "city_limit.geojson", BIRCH)
    saved.with_name(saved.name + ".source.txt").write_text("https://example.org/another/limit/3\n")
    monkeypatch.setattr(arcgis, "download", fetched.real_arcgis)  # the cache rule itself
    arguments = ["area", "--config", settings, "--raw", raw, "--out", out]
    # The refusal is not a failed fetch: the Census outline must not quietly stand in.
    with pytest.raises(ValueError, match="was fetched from .* pass --overwrite"):
        _run(monkeypatch, network_command.main, *arguments)
    assert not out.exists()

    # A reply that is not a usable layer is a failed fetch: the Census outline is used, and
    # the warning says what was wrong with the reply.
    square = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
    replies = {
        "the layer is empty": {"type": "FeatureCollection", "features": []},
        "cut-short layer was not saved": {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": square}],
            "exceededTransferLimit": True,
        },
    }
    for reason, body in replies.items():
        reply = type("Reply", (), {"text": json.dumps(body), "raise_for_status": lambda self: None})
        monkeypatch.setattr(arcgis.httpx, "get", lambda url, reply=reply, **kwargs: reply())
        caplog.clear()
        _run(monkeypatch, network_command.main, *arguments, "--overwrite")
        (warning,) = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert reason in warning and "using the Census outline" in warning
        limit = gpd.read_parquet(area.paths(out / "boundaries", CRS)["city_limit"])
        census_limit = gpd.GeoSeries([ALDER], crs=4326).to_crs(CRS)
        assert limit.area.iloc[0] == pytest.approx(census_limit.area.iloc[0], rel=1e-6)


def test_a_ready_made_street_extract_or_outline_is_used_in_place_of_a_download(
    fetched: Fetched, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "streets.json").write_text(json.dumps(_overpass()))
    with_extract = _settings(tmp_path / "extract", streets_file="../streets.json")
    out = tmp_path / "processed"
    arguments = ["--raw", tmp_path / "raw", "--out", out]
    _run(
        monkeypatch, network_command.main, "download", "build", "--config", with_extract, *arguments
    )
    assert fetched.calls == []  # nothing fetched: the config names the streets to use
    assert len(gpd.read_parquet(streets.path(out / "network", CRS))) == 2 * SIZE

    own = _outline(tmp_path / "own.geojson", BIRCH)
    plain = _settings(tmp_path / "plain")
    _run(
        monkeypatch, network_command.main, "download", "--config", plain, "--area", own, *arguments
    )
    ((bounds, date),) = fetched.streets_asked
    assert bounds == pytest.approx(BIRCH.bounds) and date is None


def test_a_regional_extract_is_cut_in_place_of_a_download(
    fetched: Fetched, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cuts = []
    monkeypatch.setattr(
        network_command.osm_extract,
        "cut",
        lambda pbf, bounds, out, overwrite: cuts.append((pbf, bounds, out, overwrite)),
    )
    own = _outline(tmp_path / "own.geojson", BIRCH)
    raw = tmp_path / "raw"
    arguments = ["download", "--area", own, "--raw", raw, "--out", tmp_path / "processed"]
    pbf = tmp_path / "region.osm.pbf"
    _run(
        monkeypatch,
        network_command.main,
        *arguments,
        "--config",
        _settings(tmp_path / "plain"),
        "--extract",
        pbf,
    )
    ((cut_from, bounds, out, overwrite),) = cuts
    assert cut_from == pbf and out == raw / "osm" and not overwrite
    assert bounds == pytest.approx(BIRCH.bounds)
    assert fetched.streets_asked == []  # Overpass is not asked

    # An extract holds the map of its own date, so a config asking for another is refused.
    dated = _settings(tmp_path / "dated", osm_date="2031-01-01T00:00:00Z")
    with pytest.raises(SystemExit):
        _run(monkeypatch, network_command.main, *arguments, "--config", dated, "--extract", pbf)
    assert len(cuts) == 1


def test_the_network_command_rejects_a_step_it_does_not_have(
    fetched: Fetched,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        _run_as_script(monkeypatch, network_command, "biuld", "--config", _settings(tmp_path))
    assert stopped.value.code == 2 and fetched.calls == []
    assert "unknown step 'biuld'; choose from: area, download, build" in capsys.readouterr().err


# --- python -m bike_safety_ca.crashes ---------------------------------------------------------

# Made-up police reports.  Each is at a corner of the grid: (street, avenue).
#   80000101  a child cyclist, in TIMS with a point and in CCRS as report 101
#   80000102  an adult cyclist in Birch, in TIMS only
#   80000107  two cars, in TIMS with a point and in CCRS as report 107
#   7000003   two cars, in TIMS without a point; CCRS report 203 is the same crash, with one
#   7000004   one car, in TIMS without a point and before CCRS starts
#   301       an adult cyclist, in CCRS only, with a point
#   302       two cars and no injury, in CCRS only, without a point
#   303       a report marked deleted
#   304, 305  one report filed twice; 305 is the later version
#   306       the sheriff's report of the crash that Birch police filed as 80000102
_TIMS_CRASHES = [
    # case, date, time, severity, bicycle, corner, has a point, cause section, cause category
    ("80000101", "2022-03-08", "0810", "3", "Y", (1, 1), True, "21453", "12"),
    ("80000102", "2023-05-10", "1730", "4", "Y", (2, 6), True, "22350", "03"),
    ("7000003", "2021-09-14", "1200", "4", "", (3, 2), False, "21453", "12"),
    ("7000004", "2020-02-03", "0900", "4", "", (4, 3), False, "22350", "03"),
    ("80000107", "2022-10-05", "2215", "4", "", (6, 3), True, "22350", "03"),
]
_TIMS_PARTIES = [
    # case, number, type, at fault, sex, age, direction, movement, statewide and CHP vehicle type
    ("80000101", "1", "4", "Y", "M", "12", "E", "B", "L", "04"),
    ("80000101", "2", "1", "N", "F", "40", "N", "D", "A", "01"),
    ("80000102", "1", "4", "N", "F", "33", "W", "B", "L", "04"),
    ("80000102", "2", "1", "Y", "M", "51", "S", "E", "A", "01"),
    ("7000003", "1", "1", "Y", "M", "60", "E", "B", "A", "01"),
    ("7000003", "2", "1", "N", "F", "25", "W", "B", "A", "01"),
    ("7000004", "1", "1", "Y", "F", "70", "N", "B", "A", "01"),
    ("80000107", "1", "1", "Y", "F", "29", "S", "B", "A", "01"),
    ("80000107", "2", "1", "N", "M", "47", "E", "A", "A", "01"),
]
_CCRS_CRASHES = [
    # collision id, report number, version, date and time, corner, has a point, deleted
    (101, "FAKE-101", 1, "2022-03-08T08:10:00", (1, 1), True, False),
    (107, "FAKE-107", 1, "2022-10-05T22:15:00", (6, 3), True, False),
    (203, "FAKE-203", 1, "2021-09-14T12:00:00", (3, 2), True, False),
    (301, "FAKE-301", 1, "2024-06-04T16:20:00", (5, 1), True, False),
    (302, "FAKE-302", 1, "2023-11-20T07:05:00", (6, 2), False, False),
    (303, "FAKE-303", 1, "2023-12-01T10:00:00", (7, 1), True, True),
    (304, "FAKE-304", 1, "2023-01-15T13:00:00", (7, 3), True, False),
    (305, "FAKE-304", 2, "2023-01-15T13:00:00", (7, 3), True, False),
    (306, "FAKE-306", 1, "2023-05-10T17:35:00", (2, 6), True, False),
]
SHERIFF = "9900"  # filed report 306
SHERIFF_REPORTS: tuple[int, ...] = (306,)
_CCRS_PARTIES = [
    # party id, collision id, number, type, at fault, sex, age, speed limit
    (1, 101, 1, "Bicyclist", "True", "M", "12", None),
    (2, 101, 2, "Driver", "False", "F", "40", "25"),
    (3, 203, 1, "Driver", "True", "M", "60", "35"),
    (4, 203, 2, "Driver", "False", "F", "25", "35"),
    (5, 301, 1, "Bicyclist", "False", "F", "30", None),
    (6, 301, 2, "Driver", "True", "M", "44", "30"),
    (7, 302, 1, "Driver", "True", "F", "52", "25"),
    (8, 302, 2, "Driver", "False", "M", "19", "25"),
    (9, 305, 1, "Driver", "True", "M", "38", "25"),
    (10, 306, 1, "Driver", "True", "M", "51", "40"),
    (11, 306, 2, "Bicyclist", "False", "F", "34", None),
    (12, 107, 1, "Driver", "True", "F", "29", "45"),
    (13, 107, 2, "Driver", "False", "M", "47", "45"),
]
_CCRS_INJURED = [
    # person id, collision id, party number, witness only, kind of person, injury, sex, age
    (1, 101, 1, "False", "Bicyclist", "SuspectMinor", "M", "12"),
    (2, 203, 2, "False", "Driver", "PossibleInjury", "F", "25"),
    (3, 301, 1, "False", "Bicyclist", "SuspectMinor", "F", "30"),
    (4, 302, 1, "True", None, None, "M", "61"),  # a witness, not hurt
    (5, 306, 2, "False", "Bicyclist", "PossibleInjury", "F", "34"),
    (6, 107, 1, "False", "Driver", "PossibleInjury", "F", "29"),
]


def _city(avenue: int) -> str:
    return "ALDER" if avenue < ALDER_AVENUES else "BIRCH"


def _roads(street: int, avenue: int) -> tuple[str, str]:
    return (f"{STREETS[street].upper()} ST", f"{AVENUES[avenue].upper()} AV")


def _write_tims(folder: Path) -> None:
    """A hand-made TIMS export of the made-up reports, in one batch folder."""
    batch = folder / "2020-2023_final"
    batch.mkdir(parents=True)
    rows = []
    for case, date, time, severity, bicycle, corner, located, section, category in _TIMS_CRASHES:
        lon, lat = _corner(*corner)
        primary, secondary = _roads(*corner)
        rows.append(
            {
                "CASE_ID": case,
                "COLLISION_DATE": date,
                "COLLISION_TIME": time,
                "COLLISION_SEVERITY": severity,
                "PEDESTRIAN_ACCIDENT": "",
                "BICYCLE_ACCIDENT": bicycle,
                "POINT_X": lon if located else "",
                "POINT_Y": lat if located else "",
                "JURIS": POLICE[_city(corner[1])],
                "CITY": _city(corner[1]),
                "PRIMARY_RD": primary,
                "SECONDARY_RD": secondary,
                "DISTANCE": "0",
                "DIRECTION": "",
                "INTERSECTION": "Y",
                "PCF_VIOLATION": section,
                "PCF_VIOL_CATEGORY": category,
                "TYPE_OF_COLLISION": "D",
            }
        )
    pd.DataFrame(rows).to_csv(batch / "Crashes.csv", index=False)
    parties = pd.DataFrame(
        _TIMS_PARTIES,
        columns=[
            "CASE_ID",
            "PARTY_NUMBER",
            "PARTY_TYPE",
            "AT_FAULT",
            "PARTY_SEX",
            "PARTY_AGE",
            "DIR_OF_TRAVEL",
            "MOVE_PRE_ACC",
            "STWD_VEHICLE_TYPE",
            "CHP_VEH_TYPE_TOWING",
        ],
    ).assign(VEHICLE_MAKE="")
    parties.to_csv(batch / "Parties.csv", index=False)
    victims = parties[["CASE_ID", "PARTY_NUMBER"]].drop_duplicates("CASE_ID")
    victims.assign(VICTIM_NUMBER="1", VICTIM_DEGREE_OF_INJURY="4").to_csv(
        batch / "Victims.csv", index=False
    )


def _write_ccrs(
    settings: config.Config, out: Path, overwrite: bool = False, leave_out: int = 0
) -> None:
    """Stands in for ``ccrs.download``: the made-up reports as one year's files, with their list.

    ``leave_out`` is the collision id of a report to leave out of every file, if any."""
    out.mkdir(parents=True, exist_ok=True)
    crashes = []
    for number, report, version, when, corner, located, deleted in _CCRS_CRASHES:
        if number == leave_out:
            continue
        lon, lat = _corner(*corner)
        primary, secondary = _roads(*corner)
        crashes.append(
            {
                "Collision Id": number,
                "Report Number": report,
                "Report Version": version,
                "NCIC Code": SHERIFF if number in SHERIFF_REPORTS else POLICE[_city(corner[1])],
                "Crash Date Time": when,
                "Crash Time Description": when[11:13] + when[14:16],
                "ModifiedDate": f"2025-01-0{version}T00:00:00",
                "IsDeleted": str(deleted),
                "County Code": settings.ccrs_county_code,
                "City Name": _city(corner[1]).title(),
                "PrimaryRoad": primary,
                "SecondaryRoad": secondary,
                "SecondaryDistance": "0",
                "SecondaryUnitOfMeasure": "F",
                "Latitude": lat if located else None,
                "Longitude": lon if located else None,
                "NumberInjured": 1 if number in (101, 107, 203, 301, 306) else 0,
                "NumberKilled": 0,
                "Primary Collision Factor Violation": "21453",
            }
        )
    blank = [
        "Beat",
        "SecondaryDirection",
        "Collision Type Code",
        "Primary Collision Factor Code",
        "LightingCode",
        "MotorVehicleInvolvedWithCode",
        "PedestrianActionCode",
        "RoadwaySurfaceCode",
        "TrafficControlDeviceCode",
        "Weather 1",
        "HitRun",
    ]
    pd.DataFrame(crashes).assign(**dict.fromkeys(blank)).to_csv(
        out / "Crashes_2024.csv", index=False
    )
    parties = pd.DataFrame(
        _CCRS_PARTIES,
        columns=[
            "PartyId",
            "CollisionId",
            "PartyNumber",
            "PartyType",
            "IsAtFault",
            "GenderCode",
            "StatedAge",
            "SpeedLimit",
        ],
    )
    parties["Vehicle1TypeId"] = parties.PartyType.map({"Driver": "1", "Bicyclist": "4"})
    parties = parties[parties.CollisionId.ne(leave_out)].reindex(columns=merge.PARTY_COLUMNS)
    parties.to_csv(out / "Parties_2024.csv", index=False)
    injured = pd.DataFrame(_CCRS_INJURED, columns=merge.INJURED_COLUMNS)
    injured = injured[injured.CollisionId.ne(leave_out)]
    injured.to_csv(out / "InjuredWitnessPassengers_2024.csv", index=False)
    wanted = {"County Code": settings.ccrs_county_code, "City Name": list(settings.ccrs_cities)}
    files = ["Crashes_2024.csv", "Parties_2024.csv", "InjuredWitnessPassengers_2024.csv"]
    manifest = {"filter": wanted, "files": {name: {"overwrite": overwrite} for name in files}}
    (out / "ccrs_manifest.json").write_text(json.dumps(manifest))


class Town:
    """Where the made-up town's files are, laid out as the commands' defaults expect."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.settings = _settings(root)
        self.raw, self.processed = root / "data" / "raw", root / "data" / "processed"
        self.crashes = self.processed / "crashes"


def _town(root: Path) -> Town:
    """The town with its outlines, street table and TIMS export, and no crash tables yet."""
    town = Town(root)
    loaded = config.load(town.settings)
    area.build(_census_zips(town.raw / "boundaries"), town.processed / "boundaries", loaded)
    (town.raw / "osm").mkdir(parents=True)
    (town.raw / "osm" / "overpass_streets.json").write_text(json.dumps(_overpass()))
    streets.build(town.raw / "osm" / "overpass_streets.json", town.processed / "network", CRS)
    _write_tims(town.raw / "crashes" / "tims")
    return town


@pytest.fixture(scope="module")
def town(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Town]:
    """The town after ``python -m bike_safety_ca.crashes download tims merge``."""
    built = _town(tmp_path_factory.mktemp("town"))
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(built.root)
        patch.setattr(ccrs, "download", _write_ccrs)
        arguments = ["--config", built.settings, "--raw", built.raw / "crashes"]
        _run(patch, crashes_command.main, "download", "tims", "merge", *arguments, "--overwrite")
    yield built


def test_the_crashes_command_downloads_reads_and_merges(town: Town) -> None:
    manifest = json.loads((town.raw / "crashes" / "ccrs" / "ccrs_manifest.json").read_text())
    assert manifest["files"]["Crashes_2024.csv"] == {"overwrite": True}  # the flag was passed on
    assert len(gpd.read_parquet(town.crashes / "crashes_4326.parquet")) == 5  # the tims step

    links = pd.read_csv(town.crashes / "ccrs_tims_links.csv", dtype={"CASE_ID": str})
    assert links.set_index("CASE_ID").link_method.to_dict() == {
        "80000101": "case_id",
        "80000102": "unlinked",
        "7000003": "attributes",
        "7000004": "unlinked",
        "80000107": "case_id",
    }
    superseded = pd.read_csv(town.crashes / "ccrs_superseded.csv")
    assert superseded[["ccrs_collision_id", "superseded_by"]].values.tolist() == [[304, 305]]

    merged = gpd.read_parquet(town.crashes / f"crashes_merged_{CRS[5:]}.parquet")
    by_id = merged.set_index("merged_id")
    # Every TIMS crash, then the CCRS reports TIMS lacks; not the deleted or the superseded one.
    assert sorted(by_id.index) == [
        "7000003",
        "7000004",
        "80000101",
        "80000102",
        "80000107",
        "CCRS-301",
        "CCRS-302",
        "CCRS-305",
        "CCRS-306",
    ]
    assert by_id.geometry_source.to_dict() == {
        "80000101": "tims",
        "80000102": "tims",
        "80000107": "tims",
        "7000003": "ccrs",  # the point of the CCRS report it was linked to
        "7000004": "intersection_centerline",  # placed from its street names
        "CCRS-301": "ccrs",
        "CCRS-302": "intersection_centerline",
        "CCRS-305": "ccrs",
        "CCRS-306": "ccrs",
    }
    corners = gpd.GeoSeries([Point(_corner(4, 3)), Point(_corner(6, 2))], crs=4326).to_crs(CRS)
    placed = by_id.loc[["7000004", "CCRS-302"]].geometry
    apart = placed.distance(corners, align=False)  # metres; missing if a point is empty
    assert apart.notna().all() and apart.max() < 1.0
    assert by_id.injury_crash.to_dict() == {
        "80000101": True,
        "80000102": True,
        "80000107": True,
        "7000003": True,
        "7000004": True,
        "CCRS-301": True,
        "CCRS-302": False,
        "CCRS-305": False,
        "CCRS-306": True,
    }
    assert by_id.posted_speed_limit_mph.dropna().to_dict() == {
        "80000101": 25.0,
        "80000107": 45.0,
        "7000003": 35.0,
        "CCRS-301": 30.0,
        "CCRS-302": 25.0,
        "CCRS-305": 25.0,
        "CCRS-306": 40.0,
    }
    # Two agencies filed the cyclist's crash in Birch: the CCRS-only report is the one marked.
    assert by_id.reporting_agency[["80000102", "CCRS-306"]].tolist() == ["0102", SHERIFF]
    assert by_id.possible_duplicate_of.dropna().to_dict() == {"CCRS-306": "80000102"}
    pairs = pd.read_csv(town.crashes / "crashes_duplicate_reports.csv", dtype=str)
    assert pairs[["keep", "duplicate", "minutes_apart"]].values.tolist() == [
        ["80000102", "CCRS-306", "5"]
    ]

    parties = pd.read_parquet(town.crashes / "parties_merged.parquet")
    assert parties.groupby("source").size().to_dict() == {"tims": 9, "ccrs": 7}
    from_ccrs = parties[parties.source.eq("ccrs")]
    assert set(from_ccrs.CASE_ID) == {"CCRS-301", "CCRS-302", "CCRS-305", "CCRS-306"}
    # The statewide vehicle type of a CHP code is learned from the three drivers in both sources;
    # one cyclist is too few to learn from.
    assert set(zip(from_ccrs.PARTY_TYPE, from_ccrs.STWD_VEHICLE_TYPE)) == {("1", "A"), ("4", "-")}
    victims = pd.read_parquet(town.crashes / "victims_merged.parquet")
    assert victims.CASE_ID[victims.source.eq("ccrs")].tolist() == ["CCRS-301", "CCRS-306"]

    report = json.loads((town.crashes / "crashes_merge_report.json").read_text())
    assert report["placed_from"] == "street table" and report["merged_rows"] == 9
    assert report["superseded_resubmissions"] == 1 and report["deleted_rows_dropped"] == 1
    assert report["ccrs_only_injury_crashes_by_year"] == {"2023": 1, "2024": 1}
    assert report["duplicate_report_pairs_cross_agency"] == 1
    assert report["duplicate_pairs_by_source"] == {"tims+ccrs": 1}
    assert report["chp_to_statewide_vehicle_type"] == {"01": "A"}
    assert report["built_for"] == {
        "city": "Alder",
        "county_code": 99,
        "ccrs_cities": ["Alder", "Birch"],
    }
    assert report["location_recovery_status"] == {"recovered_unique_centerline_intersection": 2}


def _copy_tims_tables(town: Town, out: Path) -> None:
    """The tables the tims step wrote, in a folder of their own for another merge."""
    out.mkdir(parents=True)
    for name in ("crashes_4326.parquet", "parties.parquet", "victims.parquet"):
        (out / name).write_bytes((town.crashes / name).read_bytes())


@pytest.mark.parametrize("absent", ["victims.parquet", "parties.parquet"])
def test_merging_stops_with_a_message_when_a_tims_table_is_absent(
    town: Town,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    absent: str,
) -> None:
    """The tims step writes each table only when the export held its CSV."""
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "processed" / "crashes"
    _copy_tims_tables(town, out)
    (out / absent).unlink()
    arguments = ["--config", town.settings, "--raw", town.raw / "crashes", "--out", out]
    with pytest.raises(SystemExit) as stopped:
        _run(monkeypatch, crashes_command.main, "merge", *arguments)
    assert stopped.value.code == 1
    assert f"TIMS tables missing ({absent})" in capsys.readouterr().out
    assert not (out / "crashes_merged_4326.parquet").exists()


def test_merging_with_no_streets_leaves_unlocated_crashes_where_they_are(
    town: Town, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    raw = tmp_path / "raw" / "crashes"
    out = tmp_path / "processed" / "crashes"  # no street table beside it
    _write_tims(raw / "tims")
    _write_ccrs(config.load(town.settings), raw / "ccrs", leave_out=306)  # no report filed twice
    (raw / "ccrs" / "ccrs_manifest.json").unlink()  # as files put there by hand would be
    arguments = ["--config", town.settings, "--raw", raw, "--out", out]
    _run(monkeypatch, crashes_command.main, "tims", *arguments)
    assert (out / "crashes_4326.parquet").exists()
    assert not list(out.glob("crashes_merged*"))  # only the step named was run

    _run(monkeypatch, crashes_command.main, "merge", *arguments)
    merged = gpd.read_parquet(out / "crashes_merged_4326.parquet").set_index("merged_id")
    assert merged.loc[["7000004", "CCRS-302"]].geometry.is_empty.all()
    assert not merged.geometry_is_approximate.any()
    assert merged.possible_duplicate_of.isna().all()
    assert pd.read_csv(out / "crashes_duplicate_reports.csv").empty
    report = json.loads((out / "crashes_merge_report.json").read_text())
    assert report["placed_from"] == "nothing" and report["merged_rows_without_geometry"] == 2
    assert report["merged_rows"] == 8 and report["duplicate_pairs_by_source"] == {}

    # The street table and outlines can be named instead of being found beside the folders.
    named = [
        "--streets",
        streets.path(town.processed / "network", CRS),
        "--boundaries",
        town.raw / "boundaries",
    ]
    _run(monkeypatch, crashes_command.main, "merge", *arguments, *named)
    report = json.loads((out / "crashes_merge_report.json").read_text())
    assert report["placed_from"] == "street table" and report["merged_rows_without_geometry"] == 0


def test_merging_with_a_centerline_file_places_crashes_from_it(
    town: Town, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "processed" / "crashes"
    _copy_tims_tables(town, out)
    # A centerline layer holding only Alder's part of two streets: one crash can be placed.
    table = gpd.read_parquet(streets.path(town.processed / "network", CRS))
    places = gpd.GeoDataFrame({"NAME": ["Alder"]}, geometry=[ALDER], crs=4326).to_crs(CRS)
    lines = streets_as_centerlines(table, places)
    lines = lines[lines.STNAME.isin(["Echidna Street", "Nectarine Avenue"])]
    lines[lines.MUNICIPALI.eq("ALDER")].to_parquet(tmp_path / "centerlines.parquet")
    arguments = ["--config", town.settings, "--raw", town.raw / "crashes", "--out", out]
    centerlines = ["--centerlines", tmp_path / "centerlines.parquet"]
    _run(monkeypatch, crashes_command.main, "merge", *arguments, *centerlines)
    merged = gpd.read_parquet(out / "crashes_merged_4326.parquet").set_index("merged_id")
    assert merged.geometry_source[["7000004", "CCRS-302"]].tolist() == [
        "intersection_centerline",
        "",
    ]
    report = json.loads((out / "crashes_merge_report.json").read_text())
    assert report["placed_from"] == "centerlines"
    assert report["location_recovery_status"] == {
        "recovered_unique_centerline_intersection": 1,
        "road_name_not_in_retained_centerlines": 1,
    }


def test_a_centerline_file_that_does_not_exist_stops_the_command_before_any_step(
    town: Town,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "processed" / "crashes"
    arguments = ["--config", town.settings, "--raw", town.raw / "crashes", "--out", out]
    with pytest.raises(SystemExit) as stopped:
        _run(monkeypatch, crashes_command.main, *arguments, "--centerlines", tmp_path / "typo.pq")
    assert stopped.value.code == 2
    assert "typo.pq does not exist" in capsys.readouterr().err
    assert not out.exists()  # the tims step was not run either


def test_a_report_whose_date_differs_from_its_tims_crash_is_not_counted_as_another_crash(
    town: Town, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    raw = tmp_path / "raw" / "crashes"
    out = tmp_path / "processed" / "crashes"
    _write_tims(raw / "tims")
    _write_ccrs(config.load(town.settings), raw / "ccrs")
    # The date of the child cyclist's crash was corrected in TIMS and not in CCRS.
    export = raw / "tims" / "2020-2023_final" / "Crashes.csv"
    rows = pd.read_csv(export, dtype=str)
    rows.loc[rows.CASE_ID.eq("80000101"), "COLLISION_DATE"] = "2022-03-05"
    rows.to_csv(export, index=False)
    arguments = ["--config", town.settings, "--raw", raw, "--out", out]
    _run(monkeypatch, crashes_command.main, *arguments)
    merged = gpd.read_parquet(out / "crashes_merged_4326.parquet").set_index("merged_id")
    assert merged.ccrs_link_method["80000101"] == "case_id_date_mismatch"
    # Both rows are kept; the CCRS one is marked so that counts take the crash once.
    assert _counted_duplicates(merged) == {"CCRS-101": "80000101", "CCRS-306": "80000102"}
    counted = merged[merged.bike_involved & merged.possible_duplicate_of.isna()]
    assert sorted(counted.index) == ["80000101", "80000102", "CCRS-301"]
    report = json.loads((out / "crashes_merge_report.json").read_text())
    assert report["ccrs_only_flagged_for_case_id_date_mismatch"] == 1
    assert report["case_id_date_mismatches_kept_as_two_crashes"] == 0
    assert report["case_id_date_mismatches_kept_because_tims_row_incomplete"] == 0
    assert report["rows_flagged_possible_duplicate"] == 2


def _mismatched_town(town: Town, raw: Path, **changes: str) -> None:
    """The made-up reports, with ``changes`` made to the child cyclist's row in the TIMS export."""
    _write_tims(raw / "tims")
    _write_ccrs(config.load(town.settings), raw / "ccrs")
    export = raw / "tims" / "2020-2023_final" / "Crashes.csv"
    rows = pd.read_csv(export, dtype=str)
    for column, value in changes.items():
        rows.loc[rows.CASE_ID.eq("80000101"), column] = value
    rows.to_csv(export, index=False)


def test_a_case_id_used_again_for_a_different_crash_does_not_hide_that_crash(
    town: Town, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    raw, out = tmp_path / "raw" / "crashes", tmp_path / "processed" / "crashes"
    # TIMS 80000101 is a crash days earlier at another corner, a kilometre from report 101's.
    lon, lat = _corner(8, 7)
    primary, secondary = _roads(8, 7)
    elsewhere = {"PRIMARY_RD": primary, "SECONDARY_RD": secondary}
    place = {"POINT_X": str(lon), "POINT_Y": str(lat), "CITY": "BIRCH", "JURIS": POLICE["BIRCH"]}
    _mismatched_town(town, raw, COLLISION_DATE="2022-03-05", **elsewhere, **place)
    arguments = ["--config", town.settings, "--raw", raw, "--out", out]
    _run(monkeypatch, crashes_command.main, *arguments)
    merged = gpd.read_parquet(out / "crashes_merged_4326.parquet").set_index("merged_id")
    assert merged.ccrs_link_method["80000101"] == "case_id_date_mismatch"
    assert _counted_duplicates(merged) == {"CCRS-306": "80000102"}
    report = json.loads((out / "crashes_merge_report.json").read_text())
    assert report["ccrs_only_flagged_for_case_id_date_mismatch"] == 0
    assert report["case_id_date_mismatches_kept_as_two_crashes"] == 1
    grouped = groups.load(out, CRS, 15)
    assert {"80000101", "CCRS-101"} <= set(grouped.merged_id)


def _counted_duplicates(merged: gpd.GeoDataFrame) -> dict[str, str]:
    """Each marked row and the row it repeats, which must be there and not marked itself."""
    marked = {str(k): str(v) for k, v in merged.possible_duplicate_of.dropna().items()}
    assert set(marked.values()) <= set(merged.index) - set(marked)
    return marked


def _crash_filed_under_two_numbers(
    monkeypatch: pytest.MonkeyPatch, first: tuple[Any, ...], second: tuple[Any, ...], report: str
) -> None:
    """Report 100 filed again as 101 (at Echidna and Olive), and TIMS rows carrying each number."""
    here = sys.modules[__name__]
    filed = [(n, "FAKE-101", n - 100, report, (4, 4), True, False) for n in (100, 101)]
    monkeypatch.setattr(here, "_CCRS_CRASHES", [*filed, *_CCRS_CRASHES[1:]])
    rows = [
        (case, date, "0810", "3", "Y", corner, True, "21453", "12")
        # The later number first: the order of the export must not decide which row is kept.
        for case, (date, corner) in (("80000101", second), ("80000100", first))
    ]
    monkeypatch.setattr(here, "_TIMS_CRASHES", [*rows, *_TIMS_CRASHES[1:]])
    people = [("80000100", *party[1:]) for party in _TIMS_PARTIES if party[0] == "80000101"]
    monkeypatch.setattr(here, "_TIMS_PARTIES", [*people, *_TIMS_PARTIES])


def test_two_different_tims_crashes_that_fit_one_refused_report_are_all_kept(
    town: Town, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    # Two crashes a week and 1.4 km apart on the street the report names, each 700 m from it.
    _crash_filed_under_two_numbers(
        monkeypatch, ("2022-03-01", (4, 0)), ("2022-03-08", (4, 8)), "2022-03-20T08:10:00"
    )
    raw, out = tmp_path / "raw" / "crashes", tmp_path / "processed" / "crashes"
    _mismatched_town(town, raw)
    _run(monkeypatch, crashes_command.main, "--config", town.settings, "--raw", raw, "--out", out)
    links = pd.read_csv(out / "ccrs_tims_links.csv", dtype={"CASE_ID": str}).set_index("CASE_ID")
    assert links.date_mismatch_corroborated[["80000100", "80000101"]].all()
    merged = gpd.read_parquet(out / "crashes_merged_4326.parquet").set_index("merged_id")
    assert _counted_duplicates(merged) == {"CCRS-306": "80000102"}
    three = ["80000100", "80000101", "CCRS-101"]
    grouped = groups.load(out, CRS, 15)
    assert sorted(grouped.merged_id[grouped.merged_id.isin(three)]) == three
    counted = reporting.load(out, CRS, 2014)
    assert sorted(counted.merged_id[counted.merged_id.isin(three)]) == three
    report = json.loads((out / "crashes_merge_report.json").read_text())
    assert report["case_id_date_mismatches_with_several_tims_rows_kept"] == 1
    assert report["ccrs_only_flagged_for_case_id_date_mismatch"] == 0


def test_one_crash_twice_in_tims_and_refused_by_its_report_is_counted_once_downstream(
    town: Town, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    same = ("2022-03-05", (4, 4))
    _crash_filed_under_two_numbers(monkeypatch, same, same, "2022-03-08T08:10:00")
    raw, out = tmp_path / "raw" / "crashes", tmp_path / "processed" / "crashes"
    _mismatched_town(town, raw)
    _run(monkeypatch, crashes_command.main, "--config", town.settings, "--raw", raw, "--out", out)
    merged = gpd.read_parquet(out / "crashes_merged_4326.parquet").set_index("merged_id")
    # The two TIMS rows are one agency's duplicate reports; the CCRS report repeats the one kept.
    assert _counted_duplicates(merged) == {
        "80000101": "80000100",
        "CCRS-101": "80000100",
        "CCRS-306": "80000102",
    }
    three = ["80000100", "80000101", "CCRS-101"]
    grouped = groups.load(out, CRS, 15)
    assert grouped.merged_id[grouped.merged_id.isin(three)].tolist() == ["80000100"]
    counted = reporting.load(out, CRS, 2014)
    assert counted.merged_id[counted.merged_id.isin(three)].tolist() == ["80000100"]
    report = json.loads((out / "crashes_merge_report.json").read_text())
    assert report["case_id_date_mismatches_with_several_tims_rows_kept"] == 0
    assert report["ccrs_only_flagged_for_case_id_date_mismatch"] == 1


@pytest.mark.parametrize(
    ("changes", "located", "dated"),
    [
        # No point in TIMS, no date in TIMS, neither: the report knows what the TIMS row lacks.
        ({"COLLISION_DATE": "2022-03-05", "POINT_X": "0", "POINT_Y": "0"}, False, True),
        ({"COLLISION_DATE": ""}, True, False),
        ({"COLLISION_DATE": "", "POINT_X": "0", "POINT_Y": "0"}, False, False),
    ],
)
def test_a_refused_report_is_kept_when_its_tims_row_lacks_what_the_report_has(
    town: Town,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    changes: dict[str, str],
    located: bool,
    dated: bool,
) -> None:
    monkeypatch.chdir(tmp_path)
    # No street table beside the output: a crash with no point cannot be placed from its streets.
    raw, out = tmp_path / "raw" / "crashes", tmp_path / "processed" / "crashes"
    _mismatched_town(town, raw, **changes)
    arguments = ["--config", town.settings, "--raw", raw, "--out", out]
    _run(monkeypatch, crashes_command.main, *arguments)
    merged = gpd.read_parquet(out / "crashes_merged_4326.parquet").set_index("merged_id")
    links = pd.read_csv(out / "ccrs_tims_links.csv", dtype={"CASE_ID": str}).set_index("CASE_ID")
    assert links.date_mismatch_corroborated["80000101"]
    assert _counted_duplicates(merged) == {"CCRS-306": "80000102"}
    # The TIMS row is as it was exported: nothing is copied to it from the report.
    assert merged.geometry_source["80000101"] == ("tims" if located else "")
    assert pd.isna(merged.year["80000101"]) is not dated
    pair = ["80000101", "CCRS-101"]
    grouped = groups.load(out, CRS, 15)
    assert sorted(grouped.merged_id[grouped.merged_id.isin(pair)]) == pair[1 - located :]
    counted = reporting.load(out, CRS, 2014)
    assert sorted(counted.merged_id[counted.merged_id.isin(pair)]) == pair[1 - dated :]
    report = json.loads((out / "crashes_merge_report.json").read_text())
    assert report["case_id_date_mismatches_kept_because_tims_row_incomplete"] == 1
    assert report["ccrs_only_flagged_for_case_id_date_mismatch"] == 0


def test_a_refused_report_with_no_point_either_is_marked_as_the_tims_rows_duplicate(
    town: Town, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    here = sys.modules[__name__]
    unplaced = (*_CCRS_CRASHES[0][:5], False, False)
    monkeypatch.setattr(here, "_CCRS_CRASHES", [unplaced, *_CCRS_CRASHES[1:]])
    raw, out = tmp_path / "raw" / "crashes", tmp_path / "processed" / "crashes"
    _mismatched_town(town, raw, COLLISION_DATE="2022-03-05", POINT_X="0", POINT_Y="0")
    _run(monkeypatch, crashes_command.main, "--config", town.settings, "--raw", raw, "--out", out)
    merged = gpd.read_parquet(out / "crashes_merged_4326.parquet").set_index("merged_id")
    assert _counted_duplicates(merged) == {"CCRS-101": "80000101", "CCRS-306": "80000102"}
    counted = reporting.load(out, CRS, 2014)
    assert counted.merged_id[counted.merged_id.isin(["80000101", "CCRS-101"])].tolist() == [
        "80000101"
    ]


def test_a_report_that_repeats_a_refused_report_is_marked_against_the_row_kept(
    town: Town, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    here = sys.modules[__name__]
    # Another agency's report of the child cyclist's crash, five minutes off report 101's time.
    again = (111, "FAKE-111", 1, "2022-03-08T08:15:00", (1, 1), True, False)
    monkeypatch.setattr(here, "_CCRS_CRASHES", [*_CCRS_CRASHES, again])
    monkeypatch.setattr(here, "SHERIFF_REPORTS", (306, 111))
    raw, out = tmp_path / "raw" / "crashes", tmp_path / "processed" / "crashes"
    _mismatched_town(town, raw, COLLISION_DATE="2022-03-05")
    _run(monkeypatch, crashes_command.main, "--config", town.settings, "--raw", raw, "--out", out)
    pairs = pd.read_csv(out / "crashes_duplicate_reports.csv", dtype=str)
    assert ["CCRS-101", "CCRS-111"] in pairs[["keep", "duplicate"]].values.tolist()
    merged = gpd.read_parquet(out / "crashes_merged_4326.parquet").set_index("merged_id")
    assert _counted_duplicates(merged) == {
        "CCRS-101": "80000101",
        "CCRS-111": "80000101",  # not CCRS-101, which is itself marked
        "CCRS-306": "80000102",
    }


def test_a_duplicate_marked_against_a_row_that_is_not_there_stops_the_merge(
    town: Town, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    found = merge.duplicate_reports

    def with_a_stray_pair(crashes: gpd.GeoDataFrame, crs: str) -> pd.DataFrame:
        pairs = found(crashes, crs)
        stray = pairs.iloc[:1].assign(keep="NOT-A-ROW", duplicate="CCRS-301")
        return pd.concat([pairs, stray], ignore_index=True)

    monkeypatch.setattr(merge, "duplicate_reports", with_a_stray_pair)
    out = tmp_path / "processed" / "crashes"
    _copy_tims_tables(town, out)
    arguments = ["--config", town.settings, "--raw", town.raw / "crashes", "--out", out]
    with pytest.raises(AssertionError, match="1 possible_duplicate_of values name a row"):
        _run(monkeypatch, crashes_command.main, "merge", *arguments)
    assert not list(out.glob("crashes_merged_*.parquet"))


def test_an_incomplete_tims_row_does_not_displace_the_rows_other_duplicates_point_at(
    town: Town, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    here = sys.modules[__name__]
    # Report 202 is in TIMS under two case numbers, at the place and minute of report 101.
    when = "2022-01-10T08:00:00"
    reports = [(101, "FAKE-101", 1, when, (1, 1), True, False), *_CCRS_CRASHES[1:]]
    monkeypatch.setattr(
        here, "_CCRS_CRASHES", [*reports, (202, "FAKE-202", 1, when, (1, 1), True, False)]
    )
    twice = [
        (case, "2022-01-10", "0800", "4", "", (1, 1), True, "21453", "12")
        for case in ("80000202", "90000202")
    ]
    monkeypatch.setattr(here, "_TIMS_CRASHES", [*_TIMS_CRASHES, *twice])
    drivers = [
        (case, number, "1", fault, "M", age, "E", "B", "A", "01")
        for case in ("80000202", "90000202")
        for number, fault, age in (("1", "Y", "36"), ("2", "N", "58"))
    ]
    monkeypatch.setattr(here, "_TIMS_PARTIES", [*_TIMS_PARTIES, *drivers])
    raw, out = tmp_path / "raw" / "crashes", tmp_path / "processed" / "crashes"
    # TIMS 80000101 has the report's streets and neither a date nor a point.
    blank = {"COLLISION_DATE": "", "COLLISION_TIME": "0800", "POINT_X": "0", "POINT_Y": "0"}
    _mismatched_town(town, raw, **blank)
    _run(monkeypatch, crashes_command.main, "--config", town.settings, "--raw", raw, "--out", out)
    merged = gpd.read_parquet(out / "crashes_merged_4326.parquet").set_index("merged_id")
    assert _counted_duplicates(merged) == {"90000202": "80000202", "CCRS-306": "80000102"}
    assert merged.geometry_source["80000101"] == "" and pd.isna(merged.year["80000101"])
    counted = reporting.load(out, CRS, 2014)
    assert {"CCRS-101", "80000202"} <= set(counted.merged_id)
    report = json.loads((out / "crashes_merge_report.json").read_text())
    assert report["case_id_date_mismatches_kept_because_tims_row_incomplete"] == 1


def test_the_crashes_command_stops_with_an_error_when_a_step_has_nothing_to_read(
    town: Town,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    empty = ["--config", town.settings, "--raw", tmp_path / "raw", "--out", tmp_path / "out"]
    with pytest.raises(SystemExit) as stopped:
        _run(monkeypatch, crashes_command.main, *empty)  # no step named: tims, then merge
    assert stopped.value.code == 1
    assert "No TIMS exports found" in capsys.readouterr().out
    assert not (tmp_path / "out").exists()  # the merge was not tried

    # A CCRS download with no TIMS tables to merge it with.
    with_ccrs = [
        "--config",
        town.settings,
        "--raw",
        town.raw / "crashes",
        "--out",
        tmp_path / "out",
    ]
    with pytest.raises(SystemExit) as stopped:
        _run(monkeypatch, crashes_command.main, "merge", *with_ccrs)
    assert stopped.value.code == 1
    assert "CCRS download or TIMS crash tables missing" in capsys.readouterr().out

    with pytest.raises(SystemExit) as stopped:
        _run_as_script(monkeypatch, crashes_command, "merg", *empty)
    assert stopped.value.code == 2
    assert "unknown step 'merg'; choose from: download, tims, merge" in capsys.readouterr().err


def test_a_ccrs_folder_fetched_for_other_cities_is_not_merged(
    town: Town, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    elsewhere = _settings(tmp_path, ccrs_cities=["Alder"])
    arguments = ["--config", elsewhere, "--raw", town.raw / "crashes", "--out", tmp_path / "out"]
    with pytest.raises(ValueError, match="not for this config"):
        _run(monkeypatch, crashes_command.main, "merge", *arguments)


# --- python -m bike_safety_ca.report ----------------------------------------------------------


def _map_rows(page: str) -> list[dict[str, object]]:
    """The crashes written into the map page."""
    rows, _ = json.JSONDecoder().raw_decode(page.split("const DATA=")[1])
    assert isinstance(rows, list)
    return rows


def test_the_report_command_writes_the_summaries_and_the_map(
    town: Town,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(town.root)  # the crash tables and outlines are where the defaults look
    out = tmp_path / "output"
    _run(monkeypatch, report_command.main, "--config", town.settings, "--out", out)

    written = sorted(path.name for path in (out / "summary").iterdir())
    names = [
        "crashes_by_year",
        "cyclist_crashes_by_cause",
        "cyclist_crashes_by_hour",
        "cyclists_by_age",
    ]
    assert written == sorted(f"{scope}_{name}.csv" for scope in ("alder", "area") for name in names)
    child = "Cyclist 15 or under"  # the config's child age, not the 18 of the fixed names
    years = pd.read_csv(out / "summary" / "area_crashes_by_year.csv", index_col=0)
    assert years[[child, "Cyclist over 15", CAR]].to_dict("index") == {
        "2020": {child: 0, "Cyclist over 15": 0, CAR: 1},
        "2021": {child: 0, "Cyclist over 15": 0, CAR: 1},
        "2022": {child: 1, "Cyclist over 15": 0, CAR: 1},
        "2023": {child: 0, "Cyclist over 15": 1, CAR: 0},
        "2024": {child: 0, "Cyclist over 15": 1, CAR: 0},
        "All years": {child: 1, "Cyclist over 15": 2, CAR: 3},
    }
    # The city's own tables leave out the cyclist in Birch.
    city = pd.read_csv(out / "summary" / "alder_crashes_by_year.csv", index_col=0)
    assert list(city.loc["All years"][[child, "Cyclist over 15", CAR]]) == [1, 1, 3]
    hours = pd.read_csv(out / "summary" / "alder_cyclist_crashes_by_hour.csv", index_col=0)
    assert hours.loc["School-commute hours", child] == 1  # 8:10 on a Tuesday in March
    ages = pd.read_csv(out / "summary" / "area_cyclists_by_age.csv", index_col=0)
    assert ages.cyclists.to_dict() == {
        "0-10": 0,
        "11-13": 1,
        "14-15": 0,
        "16-24": 0,
        "25-44": 2,
        "45-64": 0,
        "65-100": 0,
        "not recorded": 0,
    }
    printed = capsys.readouterr().out
    assert "area: crashes by year" in printed and "alder: cyclists by age" in printed

    page = (out / "crash_movement_map.html").read_text()
    assert movement.SYNTHETIC_NOTICE[0] not in page and '<div class="warn">' not in page
    data = _map_rows(page)
    assert sorted(str(row["st"]) for row in data) == [
        "Badger Street / Lychee Avenue",
        "Capybara Street / Quince Avenue",
        "Ferret Street / Lychee Avenue",
    ]


def test_the_report_command_runs_one_step_on_the_callers_own_area(
    town: Town, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    own = _outline(tmp_path / "birch.geojson", BIRCH)
    arguments = ["--config", town.settings, "--crashes", town.crashes, "--area", own]
    placed = ["--processed", town.processed, "--out", tmp_path / "output"]
    _run(monkeypatch, report_command.main, "map", *arguments, *placed)
    assert not (tmp_path / "output" / "summary").exists()
    page = (tmp_path / "output" / "crash_movement_map.html").read_text()
    data = _map_rows(page)
    # The one crash in Birch, its streets named as the map names them.
    assert [row["st"] for row in data] == ["Capybara Street / Quince Avenue"]

    _run(monkeypatch, report_command.main, "summary", *arguments, "--out", tmp_path / "tables")
    assert not (tmp_path / "tables" / "crash_movement_map.html").exists()
    years = pd.read_csv(tmp_path / "tables" / "summary" / "area_crashes_by_year.csv", index_col=0)
    assert years.loc["All years"].sum() == 1


def test_the_report_command_draws_the_streets_alone_with_no_crashes(
    town: Town, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # No crash in the area: the map is the streets alone, with or without a ranking.
    load = report_command.crash_table.load
    monkeypatch.setattr(report_command.crash_table, "load", lambda *a: load(*a).iloc[:0])
    ranked = tmp_path / "ranking.csv"
    pd.DataFrame(
        {
            "rank": [1],
            "streets": ["A / B"],
            "major": ["Arterial"],
            "minor": ["Local"],
            "in_city": [True],
            "expected_bike_crashes": [2.0],
            "observed_bike_crashes": [0],
            "car_crashes": [1],
            "method": ["street-length model"],
            "longitude": [-118.0],
            "latitude": [34.0],
        }
    ).to_csv(ranked, index=False)
    arguments = [
        "--config",
        town.settings,
        "--crashes",
        town.crashes,
        "--processed",
        town.processed,
    ]
    for extra, out in (([], tmp_path / "plain"), (["--ranking", ranked], tmp_path / "ranked")):
        _run(monkeypatch, report_command.main, "map", *arguments, *extra, "--out", out)
        assert _map_rows((out / "crash_movement_map.html").read_text()) == []
    assert "| 1 | A / B |" in (tmp_path / "ranked" / "top_corners.md").read_text()


def test_the_report_command_prints_the_risk_view_and_the_corners(
    town: Town, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Chrome is stood in for: each print is recorded and leaves an empty file.
    from bike_safety_ca.hospital import pdf

    printed: list[list[str]] = []

    def chrome(command: list[str], **_: object) -> None:
        printed.append(command)
        target = next(a for a in command if a.startswith("--print-to-pdf="))
        Path(target.split("=", 1)[1]).write_bytes(b"%PDF")

    monkeypatch.setattr(pdf.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(pdf.subprocess, "run", chrome)
    ranked = tmp_path / "ranking.csv"
    pd.DataFrame(
        {
            "rank": [1],
            "streets": ["A / B"],
            "major": ["Arterial"],
            "minor": ["Local"],
            "in_city": [True],
            "expected_bike_crashes": [2.0],
            "observed_bike_crashes": [0],
            "car_crashes": [1],
            "method": ["street-length model"],
            "longitude": [-118.0],
            "latitude": [34.0],
        }
    ).to_csv(ranked, index=False)
    out = tmp_path / "out"
    arguments = [
        "--config",
        town.settings,
        "--crashes",
        town.crashes,
        "--processed",
        town.processed,
    ]
    _run(
        monkeypatch,
        report_command.main,
        "map",
        *arguments,
        "--ranking",
        ranked,
        "--pdf",
        "--out",
        out,
    )

    assert (out / "predicted_risk.pdf").exists() and (out / "top_corners.pdf").exists()
    risk = next(c for c in printed if c[-1].endswith("crash_movement_map.html?view=risk"))
    assert "--virtual-time-budget=15000" in risk  # the map draws itself before printing
    profiles = [a for c in printed for a in c if a.startswith("--user-data-dir=")]
    assert len(set(profiles)) == len(printed) == 2  # a fresh profile for each print

    # With no ranked corner in the city the page has no risk view, so none is printed.
    printed.clear()
    (out / "predicted_risk.pdf").unlink()
    _run(
        monkeypatch,
        report_command.main,
        "map",
        *arguments,
        "--ranking",
        ranked,
        "--pdf",
        "--top",
        "0",
        "--out",
        out,
    )
    assert not (out / "predicted_risk.pdf").exists()
    assert not any(c[-1].endswith("?view=risk") for c in printed)

    # Without --pdf, or without a ranking, nothing is printed.
    printed.clear()
    _run(monkeypatch, report_command.main, "map", *arguments, "--ranking", ranked, "--out", out)
    _run(monkeypatch, report_command.main, "map", *arguments, "--pdf", "--out", out)
    assert printed == []


def test_the_report_command_rejects_a_step_it_does_not_have(
    town: Town,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as stopped:
        _run_as_script(monkeypatch, report_command, "maps", "--config", town.settings)
    assert stopped.value.code == 2
    assert "unknown step 'maps'; choose from: summary, map" in capsys.readouterr().err
    assert not (tmp_path / "output").exists()


# --- python -m bike_safety_ca.checks.holdout and .sensitivity ---------------------------------


class Invented:
    """The town with crash tables invented by ``bike_safety_ca.demo``."""

    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "streets.json").write_text(json.dumps(_overpass()))
        _outline(root / "town.geojson", TOWN)
        _outline(root / "alder.geojson", ALDER)
        self.settings = _settings(
            root,
            synthetic=True,
            streets_file="streets.json",
            area_file="town.geojson",
            city_limit_file="alder.geojson",
        )
        written = demo.build(config.load(self.settings), root / "data")
        self.processed = root / "data" / "processed"
        self.crashes, self.ways = written["crashes"].parent, written["streets"]
        self.boundaries = root / "data" / "raw" / "boundaries"
        _census_zips(self.boundaries)


@pytest.fixture(scope="module")
def invented(tmp_path_factory: pytest.TempPathFactory) -> Invented:
    return Invented(tmp_path_factory.mktemp("invented"))


def test_the_holdout_command_scores_the_city_and_saves_the_table(
    invented: Invented,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(invented.root)  # the crash tables and streets are where the defaults look
    saved = tmp_path / "tables" / "holdout.csv"
    _run(monkeypatch, holdout.main, "--config", invented.settings, "--out", saved)
    printed = capsys.readouterr().out
    assert printed.startswith("Rank score on later bike crashes (Alder)")
    assert f"wrote {saved}" in printed and "compared with" not in printed
    table = pd.read_csv(saved)
    assert set(table.area) == {"All intersections", "Alder"}  # the config's city limit
    assert set(table.outcome) == {"All cyclists", "Cyclists 15 or under"}  # the config's age
    assert set(table["tested on"]) == {"2019–2022", "2021–2022", "2023–latest"}
    everywhere = table[table.area.eq("All intersections")]
    in_city = table[table.area.eq("Alder")]
    assert (in_city["later crashes"].to_numpy() < everywhere["later crashes"].to_numpy()).all()
    # A row is scored only on enough later crashes; the others keep the count alone.
    scored = table["later crashes"].ge(holdout.MIN_LATER)
    figures = ["rank score", "found in top 25", "found in top 50", "found in top 100"]
    assert scored.any() and not scored.all()
    assert table.loc[scored, "rank score"].between(0.5, 1).all()
    assert table.loc[~scored, figures].isna().all().all()
    assert table.loc[scored, figures].notna().all().all()
    assert "too few (" in printed

    # The same run matches the table just saved; with another city limit it does not.
    arguments = ["--config", invented.settings, "--expect", saved]
    _run(monkeypatch, holdout.main, *arguments)
    assert f"compared with {saved}: every figure matches" in capsys.readouterr().out
    birch = _outline(tmp_path / "birch.geojson", BIRCH)
    other = tmp_path / "other.csv"
    with pytest.raises(SystemExit) as stopped:
        _run(monkeypatch, holdout.main, *arguments, "--city-limit", birch, "--out", other)
    assert stopped.value.code == 1 and not other.exists()  # stopped before the table was written
    assert "later crashes differs by up to" in capsys.readouterr().out


def test_the_holdout_command_takes_the_callers_own_outlines(
    invented: Invented,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    own = _outline(tmp_path / "alder.geojson", ALDER)
    half = _outline(tmp_path / "half.geojson", _block(-0.5, 2.5))
    saved = tmp_path / "holdout.csv"
    placed = ["--crashes", invented.crashes, "--ways", invented.ways, "--area", own]
    limits = ["--city-limit", half, "--out", saved]
    _run(monkeypatch, holdout.main, "--config", invented.settings, *placed, *limits)
    table = pd.read_csv(saved)
    later = table.groupby("area")["later crashes"].max()
    assert 0 < later["Alder"] < later["All intersections"]
    assert "Rank score on later bike crashes (Alder)" in capsys.readouterr().out


def test_the_holdout_command_runs_on_the_synthetic_city_or_asks_for_a_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _run(monkeypatch, holdout.main, "--synthetic", "--out", tmp_path / "synthetic.csv")
    assert "Rank score on later bike crashes (synthetic city)" in capsys.readouterr().out
    table = pd.read_csv(tmp_path / "synthetic.csv")
    # Three windows and two areas; five rankings for all cyclists and, with the
    # all-cyclist ranking added, six for children.
    assert set(table.area) == {"All intersections", "City"} and len(table) == 3 * 2 * (5 + 6)

    with pytest.raises(SystemExit) as stopped:
        _run_as_script(monkeypatch, holdout)
    assert stopped.value.code == 2 and "give --synthetic or --config" in capsys.readouterr().err


def test_the_sensitivity_command_writes_both_tables(
    invented: Invented,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    alder = _outline(tmp_path / "alder.geojson", ALDER)  # the area as the caller draws it
    arguments = ["--config", invented.settings, "--crashes", invented.crashes, "--area", alder]
    placed = ["--processed", invented.processed, "--boundaries", invented.boundaries]
    # Copies under their own names, so a run that ignored either option and fell
    # back on the default street table would be seen.
    other, wide = tmp_path / "other_date.parquet", tmp_path / "wide_area.parquet"
    shutil.copy(invented.ways, other)
    shutil.copy(invented.ways, wide)
    read: list[Path] = []
    real = sensitivity.placed

    def watched(settings: Any, crash_folder: Path, ways: Path, *rest: Any, **named: Any) -> Any:
        read.append(ways)
        return real(settings, crash_folder, ways, *rest, **named)

    monkeypatch.setattr(sensitivity, "placed", watched)
    asked: list[Any] = []
    real_severity = sensitivity.by_severity

    def watched_severity(windows: Any, sites: Any, streets: Any, hits: Any) -> Any:
        asked.append((windows, len(sites), "COLLISION_SEVERITY" in hits))
        return real_severity(windows, sites, streets, hits)

    monkeypatch.setattr(sensitivity, "by_severity", watched_severity)
    others = ["--other-ways", other, "--wide-ways", wide, "--leave-out", "Birch"]
    out = tmp_path / "tables"
    _run(monkeypatch, sensitivity.main, *arguments, *placed, *others, "--out", out)
    assert read.count(other) == 1 and read.count(wide) == 2  # wide: once for each table
    assert set(read) == {invented.ways, other, wide}

    table = pd.read_csv(out / "sensitivity.csv", index_col=0)
    assert table.index.tolist() == [
        "As configured",
        "Leaving out intersections wider than 40 m",
        "Nearness counts whatever streets the report names",
        "Chains of close corners split at 25 m",
        "Census city limit",
        "Area built from the city list",
        "Streets of another date",
    ]
    sites = table.intersections.to_dict()
    assert sites["Streets of another date"] == sites["As configured"]  # the same street table
    assert sites["Area built from the city list"] > sites["As configured"]  # Birch as well
    assert table["All intersections, All cyclists"].between(0.5, 1).all()
    assert "Alder, Cyclists 15 or under" in table.columns

    split = pd.read_csv(out / "sensitivity_by_place.csv", index_col=0)
    count = split.intersections.to_dict()
    assert count["All intersections"] == sites["Area built from the city list"]
    assert count["Inside the configured area"] == sites["As configured"]
    assert count["Inside the configured area"] + count["Outside it"] == count["All intersections"]
    assert count["Outside it, without Birch"] == 0  # everything outside Alder is in Birch
    assert 0.5 < float(split["All cyclists"][sensitivity.WITHIN]) <= 1
    # The severity table is asked for the config's windows on the configured area.
    windows = config.load(Path(invented.settings)).holdout_windows
    assert len(windows) > 0 and asked == [(windows, sites["As configured"], True)]
    by_severity = pd.read_csv(out / "sensitivity_by_severity.csv", index_col=0)
    assert by_severity.index.tolist() == [
        "Trained on all injury crashes",
        "Trained on visible injury and worse",
    ]
    printed = capsys.readouterr().out
    assert "With and without complaint-of-pain crashes" in printed
    assert "Street-length model, mean rank score over the test windows (Alder)" in printed
    assert "Area built from the city list, trained through 2022, tested on 2023–latest" in printed
    assert f"wrote the tables to {out}" in printed


def test_the_sensitivity_command_needs_the_census_outlines_for_the_wide_area(
    invented: Invented,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    arguments = ["--config", invented.settings, "--crashes", invented.crashes]
    placed = ["--processed", invented.processed, "--boundaries", tmp_path / "none"]
    with pytest.raises(SystemExit) as stopped:
        _run_as_script(monkeypatch, sensitivity, *arguments, *placed, "--wide-ways", invented.ways)
    assert stopped.value.code == 2
    assert "--wide-ways needs the Census outlines" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())  # stopped before anything was worked out or written


def test_the_sensitivity_command_runs_with_no_city_limit_and_no_wide_area(
    invented: Invented, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    # A config that names no outlines, with the caller's own area: there is no city limit.
    no_limit = _settings(tmp_path / "settings", synthetic=True)
    alder = _outline(tmp_path / "alder.geojson", ALDER)
    arguments = ["--config", no_limit, "--crashes", invented.crashes, "--area", alder]
    placed = ["--processed", invented.processed, "--boundaries", invented.boundaries]
    out = tmp_path / "tables"
    _run(monkeypatch, sensitivity.main, *arguments, *placed, "--out", out)
    table = pd.read_csv(out / "sensitivity.csv", index_col=0)
    assert len(table) == 5 and table.index[-1] == "Census city limit"
    # Only the row that brings the Census limit has figures for the city on its own.
    assert table["Alder, All cyclists"].notna().tolist() == [False, False, False, False, True]
    assert table["All intersections, All cyclists"].between(0.5, 1).all()
    assert not (out / "sensitivity_by_place.csv").exists()  # that table needs --wide-ways


# --- python -m bike_safety_ca.checks.cities ---------------------------------------------------


def test_the_cities_command_runs_each_built_city_and_names_the_ones_left_out(
    invented: Invented,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from bike_safety_ca.checks import cities

    # The layout the command expects: <processed>/<config name>/crashes, network, boundaries.
    configs, processed = tmp_path / "configs", tmp_path / "processed"
    configs.mkdir()
    processed.mkdir()
    for name in ["alder", "birch", "cedar", "pool_both"]:
        text = Path(invented.settings).read_text()
        # The outlines are named relative to the config, so point at them where they are.
        text = text.replace("town.geojson", str(invented.root / "town.geojson"))
        text = text.replace("alder.geojson", str(invented.root / "alder.geojson"))
        text = text.replace("streets.json", str(invented.root / "streets.json"))
        (configs / f"{name}.yaml").write_text(text)
    (processed / "alder").symlink_to(invented.processed, target_is_directory=True)
    (processed / "cedar").symlink_to(invented.processed, target_is_directory=True)
    (processed / "pool_both").symlink_to(invented.processed, target_is_directory=True)
    # Fir is fitted on the same town, but its own limit lies outside it: a city, and not
    # a member of the pooled area.
    far = _outline(tmp_path / "far.geojson", _block(SIZE + 5, SIZE + 10))
    alder_limit = str(invented.root / "alder.geojson")
    fir = (configs / "alder.yaml").read_text().replace(alder_limit, str(far))
    assert str(far) in fir
    (configs / "fir.yaml").write_text(fir)
    (processed / "fir").symlink_to(invented.processed, target_is_directory=True)
    # Gum counts children to another age than the pooled area: not compared with it either.
    gum = (configs / "alder.yaml").read_text().replace("child_max_age: 15", "child_max_age: 12")
    assert "child_max_age: 12" in gum
    (configs / "gum.yaml").write_text(gum)
    (processed / "gum").symlink_to(invented.processed, target_is_directory=True)
    # A config naming a file that is gone is listed, not fatal.
    (configs / "elm.yaml").write_text(
        Path(invented.settings).read_text().replace("streets.json", "gone.json")
    )
    ran: dict[str, int] = {"steps": 0, "severity": 0}
    real_steps, real_windows = cities.reporting.level_steps, cities.severity_windows

    def counted_steps(crashes: pd.DataFrame) -> pd.DataFrame:
        ran["steps"] += len(crashes) > 0  # the empty call only asks for the column names
        return real_steps(crashes)

    def counted_windows(*given: Any) -> Any:
        ran["severity"] += 1
        return real_windows(*given)

    monkeypatch.setattr(cities.reporting, "level_steps", counted_steps)
    monkeypatch.setattr(cities, "severity_windows", counted_windows)

    out = tmp_path / "tables"
    arguments = ["--configs", configs, "--processed", processed, "--skip", "pool_*"]
    _run(monkeypatch, cities.main, *arguments)
    printed = capsys.readouterr().out
    assert "left out pool_both: skipped by name" in printed
    assert "pooled areas" not in printed and "Fitted alone and inside" not in printed

    arguments = ["--configs", configs, "--processed", processed, "--pool", "pool_*"]
    _run(monkeypatch, cities.main, *arguments, "--out", out)
    printed = capsys.readouterr().out
    assert "1 pooled areas: pool_both" in printed
    assert "left out birch: no crash table at" in printed
    assert "left out elm: config not usable: " in printed and "not found" in printed
    assert "\n4 cities: alder, cedar, fir, gum\n" in printed
    assert ran == {"steps": 8, "severity": 8}  # each check, once for each city, in both runs

    tested = pd.read_csv(out / "holdout_windows.csv")
    assert tested.city.value_counts().to_dict() == dict.fromkeys(
        ["alder", "cedar", "fir", "gum"], len(tested) // 4
    )
    assert tested["rank score"].notna().any() and tested.intersections.gt(0).all()
    by_city = pd.read_csv(out / "holdout_by_city.csv", index_col=0)
    assert sorted(by_city.index) == ["alder", "cedar", "fir", "gum"]
    assert by_city["windows scored"].gt(0).all() and by_city["rank score"].between(0.5, 1).all()
    assert by_city["rank score"].gt(by_city["history alone"]).all()
    children = pd.read_csv(out / "child_ranking.csv", index_col=0)
    model = tested[tested.ranking.eq(cities.MODEL)]
    scored_child = model[model.outcome.eq(cities.CHILDREN) & model.area.eq(cities.WHOLE)]
    assert int(children.windows.sum()) == int(scored_child["rank score"].notna().sum())

    # The pooled area is the same made-up town, so inside its own limit each member
    # scores what it scores when fitted alone.  Fir's limit is elsewhere: not a member.
    together = pd.read_csv(out / "pooled_windows.csv")
    assert set(together.pool) == {"pool_both"} and set(together.city) == {"alder", "cedar"}
    every = model[model.outcome.eq(cities.EVERYONE)]
    in_pool = together[together.ranking.eq(cities.MODEL) & together.outcome.eq(cities.EVERYONE)]
    for city in ["alder", "cedar"]:
        whole = every[every.city.eq(city) & every.area.eq(cities.WHOLE)]
        limit = every[every.city.eq(city) & every.area.eq(cities.LIMIT)]
        member = in_pool[in_pool.city.eq(city)]
        assert member["later crashes"].tolist() == limit["later crashes"].tolist()
        assert member["rank score"].round(3).tolist() == limit["rank score"].round(3).tolist()
        assert member["rank score"].notna().any()
        # The limit holds only part of the town, so this is not the whole pool's score.
        assert member["later crashes"].sum() < whole["later crashes"].sum()
    pools = pd.read_csv(out / "pooled_by_city.csv")
    assert pools[["pool", "city"]].to_numpy().tolist() == [
        ["pool_both", "alder"],
        ["pool_both", "cedar"],
    ]
    assert pools[f"{cities.EVERYONE}, pooled, windows"].gt(0).all()
    assert pools[f"{cities.EVERYONE}, pooled"].equals(pools[f"{cities.EVERYONE}, alone"])

    found = pd.read_csv(out / "level_steps.csv")
    assert list(found.columns[:3]) == ["city", "reporting_agency", "measure"]
    assert set(found.city) <= {"alder", "cedar", "fir", "gum"}
    # The two cities are the same made-up town, so they contribute the same rows.
    assert found[found.city.eq("alder")].shape == found[found.city.eq("cedar")].shape
    counts = pd.read_csv(out / "level_step_counts.csv", index_col=0)
    assert int(counts.to_numpy().sum()) == len(found)
    scored = pd.read_csv(out / "severity_windows.csv")
    assert list(scored.columns) == [
        "city", "trained", "target", "window", "fitted", "training", "later", "score",
    ]  # fmt: skip
    assert int(scored.city.eq("alder").sum()) == int(scored.city.eq("cedar").sum())
    summary = pd.read_csv(out / "severity_summary.csv", index_col=0)
    assert summary.index.tolist()[:2] == [cities.ALL_WINDOWS, cities.BOTH_FITTED]
    assert int(summary.windows[cities.ALL_WINDOWS]) == len(scored) // 4

    with pytest.raises(SystemExit):
        _run(
            monkeypatch, cities.main, "--configs", configs, "--processed", processed, "--skip", "*"
        )
    assert "no built city found" in capsys.readouterr().err
