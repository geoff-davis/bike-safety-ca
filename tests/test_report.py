from __future__ import annotations

import itertools
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, box

from bike_safety_ca import ADULT, CAR, CHILD
from bike_safety_ca import config as settings
from bike_safety_ca.network import names
from bike_safety_ca.report import codes, diagram, movement, summary
from bike_safety_ca.report.crashes import describe

CONFIG = settings.load(Path("config/los_altos.yaml"))
CRS = 26910
ORIGIN = (580_000.0, 4_137_000.0)  # somewhere in UTM zone 10N


def _at(x: float, y: float) -> tuple[float, float]:
    return (ORIGIN[0] + x, ORIGIN[1] + y)


STREETS = gpd.GeoDataFrame(
    {
        "highway": ["secondary", "residential", "footway"],
        "name": ["Main Street", "Oak Avenue", None],
    },
    geometry=[
        LineString([_at(-300, -30), _at(300, 30)]),  # runs a little north of east
        LineString([_at(0, -300), _at(0, 300)]),
        LineString([_at(-300, 280), _at(300, -280)]),  # a path cutting across
    ],
    crs=CRS,
)

# Made-up crashes: (id, year, group, date, hour, city, cause code, collision type, x, y)
_ROWS = [
    ("a", 2019, CHILD, "2019-03-05", 8, "Los Altos", "05", "D", 100, 10),
    ("b", 2021, ADULT, "2021-07-10", 18, "Elsewhere", "09", "B", 0, 150),
    ("c", 2021, CAR, "2021-01-12", None, "Los Altos", "03", "C", -100, -10),
]
CRASHES = gpd.GeoDataFrame(
    {
        "merged_id": [r[0] for r in _ROWS],
        "year": [r[1] for r in _ROWS],
        "group": [r[2] for r in _ROWS],
        "PRIMARY_RD": ["MAIN ST", "OAK AV", "MAIN ST"],
        "SECONDARY_RD": ["OAK AV", None, None],
    },
    geometry=[Point(_at(r[8], r[9])) for r in _ROWS],
    crs=CRS,
)
DETAIL = pd.DataFrame(
    {
        "merged_id": [r[0] for r in _ROWS],
        "CASE_ID": ["a", "b", "c"],
        "ccrs_collision_id": [None, None, None],
        "collision_date": [r[3] for r in _ROWS],
        "collision_hour": pd.array([r[4] for r in _ROWS], dtype="Int64"),
        "CITY": [r[5] for r in _ROWS],
        "PCF_VIOL_CATEGORY": [r[6] for r in _ROWS],
        "TYPE_OF_COLLISION": [r[7] for r in _ROWS],
    }
)
# (crash, number, party type, at fault, age, direction, movement, vehicle type)
_PARTIES = [
    ("a", 1, "4", "Y", "12", "W", "B", "L"),
    ("a", 2, "1", "N", "40", "E", "D", "A"),
    ("b", 1, "4", "N", "30", "N", "B", "L"),
    ("b", 2, "3", "N", "998", "-", "-", "A"),
    ("c", 1, "1", "Y", "50", "E", "B", "A"),
]
PARTIES = pd.DataFrame(
    _PARTIES,
    columns=[
        "CASE_ID",
        "PARTY_NUMBER",
        "PARTY_TYPE",
        "AT_FAULT",
        "PARTY_AGE",
        "DIR_OF_TRAVEL",
        "MOVE_PRE_ACC",
        "STWD_VEHICLE_TYPE",
    ],  # fmt: skip
).assign(ccrs_collision_id=None, source="tims")


@pytest.fixture(scope="module")
def crashes() -> gpd.GeoDataFrame:
    return describe(CRASHES, DETAIL, CONFIG)


def test_describe_adds_cause_commute_and_city(crashes: gpd.GeoDataFrame) -> None:
    by_id = crashes.set_index("merged_id")
    assert by_id.cause.tolist() == ["Wrong side of road", codes.CAUSES["09"], "Unsafe speed"]
    assert by_id.commute.tolist() == [True, False, False]  # a term-time weekday at 8 am
    assert by_id.in_city.tolist() == [True, False, True]


def test_summary_tables_are_totals(crashes: gpd.GeoDataFrame) -> None:
    found = summary.tables(crashes, PARTIES, CONFIG.child_max_age)
    years = found["crashes_by_year"]
    assert years.loc["All years"].to_dict() == {
        CHILD: 1,
        ADULT: 1,
        "Cyclist, age not recorded": 0,
        CAR: 1,
        "Other": 0,
    }
    assert found["cyclist_crashes_by_cause"]["All cyclists"].sum() == 2
    hours = found["cyclist_crashes_by_hour"]
    assert hours.loc["6-9 am", CHILD] == 1 and hours.loc["School-commute hours", CHILD] == 1
    ages = found["cyclists_by_age"]
    assert list(ages.loc["11-13"]) == [1, 1] and list(ages.loc["25-44"]) == [1, 0]


def test_arrows_turn_to_the_street_and_ignore_paths() -> None:
    near = movement.Bearings(STREETS).near(Point(_at(100, 10)))
    assert sorted(round(b, 1) for b in near) == [84.3, 264.3]  # Main Street only
    assert movement.snap(90.0, near) == (pytest.approx(84.3, abs=0.05), True)
    assert movement.snap(0.0, near) == (0.0, False)  # no street runs north here


def test_streets_are_as_wide_as_their_lanes() -> None:
    roads = gpd.GeoDataFrame(
        {
            "highway": ["primary", "residential", "service"],
            "name": ["Wide Road", "Quiet Lane", None],
            "lanes": ["6", None, "1"],
        },
        geometry=[LineString([_at(0, 0), _at(100, 0)])] * 3,
        crs=CRS,
    )
    assert movement.half_widths(roads).round(2).tolist() == [11.9, 5.8, 2.15]


def test_a_corner_knows_the_width_of_each_street() -> None:
    legs = movement.Bearings(STREETS).legs(Point(_at(0, 0)))
    assert [[round(b), h] for b, h in legs] == [[0, 5.8], [84, 8.6], [180, 5.8], [264, 8.6]]


def test_a_street_ending_at_a_corner_leaves_it_one_way() -> None:
    tee = gpd.GeoDataFrame(
        {"highway": ["residential", "residential"], "name": ["Cross Street", "Stem Way"]},
        geometry=[
            LineString([_at(-200, 0), _at(200, 0)]),
            LineString([_at(0, 0), _at(30, 200)]),  # leaves north-north-east only
        ],
        crs=CRS,
    )
    legs = movement.Bearings(tee).legs(Point(_at(0, 0)))
    assert [b for b, _ in legs] == [8.5, 90.0, 270.0]


def test_a_street_that_bends_past_a_corner_takes_the_way_it_goes() -> None:
    bent = gpd.GeoDataFrame(
        {"highway": ["residential", "residential"], "name": ["Cross Street", "Bent Way"]},
        geometry=[
            LineString([_at(-200, 0), _at(200, 0)]),
            LineString([_at(0, 0), _at(0, 5), _at(100, 105)]),  # north for 5 m, then north-east
        ],
        crs=CRS,
    )
    legs = movement.Bearings(bent).legs(Point(_at(0, 0)))
    assert 35 < legs[0][0] < 45 and [b for b, _ in legs[1:]] == [90.0, 270.0]


def test_a_street_mapped_in_short_pieces_still_leaves_the_corner() -> None:
    north = [LineString([_at(0, y), _at(0, y + 8)]) for y in range(0, 40, 8)]  # 8 m pieces to 40 m
    pieces = gpd.GeoDataFrame(
        {"highway": "residential", "name": ["Cross Street"] * 2 + ["Long Way"] * 6},
        geometry=[
            LineString([_at(-200, 0), _at(0, 0)]),
            LineString([_at(0, 0), _at(200, 0)]),
            *north,
            LineString([_at(0, 40), _at(0, 300)]),
        ],
        crs=CRS,
    )
    legs = movement.Bearings(pieces).legs(Point(_at(0, 0)))
    assert legs == [[0.0, 5.8], [90.0, 5.8], [270.0, 5.8]]


def test_unnamed_ways_and_closed_streets_have_their_legs() -> None:
    ways = gpd.GeoDataFrame(
        {"highway": ["residential"] * 3, "name": ["Cross Street", pd.NA, "Loop Court"]},
        geometry=[
            LineString([_at(-200, 0), _at(200, 0)]),
            LineString([_at(0, -200), _at(0, 0)]),  # unnamed, south only
            LineString(
                [_at(0, 0), _at(0, 100), _at(100, 100), _at(100, 0.5), _at(0, 0)]
            ),  # seam here
        ],
        crs=CRS,
    )
    legs = movement.Bearings(ways).legs(Point(_at(0, 0)))
    assert {round(b) for b, _ in legs} == {0, 90, 180, 270}  # north and east from the loop


def test_party_kinds() -> None:
    assert movement.party_kind("4", "-") == codes.BICYCLE
    assert movement.party_kind("1", "C") == codes.MOTORCYCLE
    assert movement.party_kind("1", "-") == codes.CAR
    assert movement.party_kind("2", "-") == codes.PEDESTRIAN


def test_crash_rows_and_wrong_side_pattern(crashes: gpd.GeoDataFrame) -> None:
    rows = movement.crash_rows(crashes, PARTIES, STREETS, CONFIG.child_max_age)
    assert len(rows) == 2  # the motor-vehicle-only crash is not on the map
    first, second = rows
    assert first["child"] and first["la"] and first["com"] and first["wc"]
    # Streets are named as the map names them, where it has one name for the street.
    assert first["st"] == "Main Street / Oak Avenue" and first["ym"] == "Mar 2019"
    assert first["cs"] == ["Main Street"] and not first["wu"]
    bike, car = first["p"]
    assert (bike["k"], bike["a"], bike["f"], bike["b"]) == ("bicycle", "18 or under", True, 264.3)
    assert first["ws"] == "car turning right met an oncoming cyclist"
    assert second["p"][1]["m"] == "O" and second["p"][1]["b"] is None  # parked car
    assert second["ws"] == "" and not second["wc"]
    # How the movements fit is stored for the page and the tables: the parked car has no direction.
    assert second["fit"] == "fits"
    assert first["p"][0]["wr"] and "wr" not in first["p"][1]  # the code moves the cyclist only
    assert first["fit"] == diagram.fit(first["p"], first.get("w") or [], True, False)


def test_page_is_filled_and_carries_the_warning(crashes: gpd.GeoDataFrame, tmp_path: Path) -> None:
    out = movement.build(crashes, PARTIES, STREETS, CONFIG, tmp_path / "map.html")
    html = out.read_text()
    assert "/*" not in html.replace("/*!", "")
    assert "Individual police records. Keep this file on your own computer" in html
    assert '<option value="la">Los Altos</option>' in html and "Main Street" in html


def test_the_summer_break_comes_from_the_config() -> None:
    from dataclasses import replace

    from bike_safety_ca.report.crashes import school_commute

    whole_year = replace(CONFIG, summer_break=((1, 1), (12, 31)))
    assert describe(CRASHES, DETAIL, CONFIG).commute.any()
    assert not describe(CRASHES, DETAIL, whole_year).commute.any()

    days = pd.Series(pd.to_datetime(["2024-06-07", "2024-06-10", "2024-08-14", "2024-08-15"]))
    hour = pd.Series([8.0] * 4)  # a Friday, Monday, Wednesday and Thursday at 8 am
    assert school_commute(days, hour).tolist() == [True, False, False, True]
    late = ((6, 20), (8, 31))
    assert school_commute(days, hour, late).tolist() == [True, True, False, False]


def test_an_arrow_with_no_street_that_way_is_marked() -> None:
    party = pd.Series(
        {
            "PARTY_TYPE": "1",
            "STWD_VEHICLE_TYPE": "A",
            "DIR_OF_TRAVEL": "N",
            "MOVE_PRE_ACC": "B",
            "PARTY_AGE": 40,
            "AT_FAULT": "N",
        }
    )
    assert movement.party_entry(party, [2.0, 182.0], 18)["s"] is True
    assert movement.party_entry(party, [90.0, 270.0], 18)["s"] is False


def test_text_from_a_record_cannot_close_the_maps_script_block(
    crashes: gpd.GeoDataFrame, tmp_path: Path
) -> None:
    nasty = "</script><script>example()</script><!--"
    streets = STREETS.assign(name=[nasty] * len(STREETS))
    crashes = crashes.assign(PRIMARY_RD=nasty)
    html = movement.build(crashes, PARTIES, streets, CONFIG, tmp_path / "map.html").read_text()
    assert (
        "example()" in html
        and "<script>example()" not in html
        and "<!--" not in html.split("const DATA=")[1].split("\n")[0]
    )


def test_a_template_mark_in_a_record_is_left_as_text(
    crashes: gpd.GeoDataFrame, tmp_path: Path
) -> None:
    mark = "Elm /*DARK*/ /*CITY*/ Street"
    streets = STREETS.assign(name=[mark] * len(STREETS))
    html = movement.build(crashes, PARTIES, streets, CONFIG, tmp_path / "map.html").read_text()
    assert mark in html and 'const DARK=["C","D","E"];' in html


def test_the_page_knows_which_patterns_have_no_other_party(
    crashes: gpd.GeoDataFrame, tmp_path: Path
) -> None:
    html = movement.build(crashes, PARTIES, STREETS, CONFIG, tmp_path / "map.html").read_text()
    assert f'const SOLO="{movement.NO_OTHER}";' in html
    assert movement.pattern([_entry(codes.BICYCLE, "N", "B")]).endswith(movement.NO_OTHER)


def test_an_offline_map_carries_its_own_map_library(
    crashes: gpd.GeoDataFrame, tmp_path: Path
) -> None:
    online = movement.build(crashes, PARTIES, STREETS, CONFIG, tmp_path / "a.html").read_text()
    offline = movement.build(
        crashes, PARTIES, STREETS, CONFIG, tmp_path / "b.html", offline=True
    ).read_text()
    assert movement.LEAFLET_JS in online and movement.LEAFLET_CSS in online
    assert "https://cdnjs" not in offline and "https://unpkg" not in offline
    assert "Leaflet 1.9.4" in offline and ".leaflet-container" in offline
    # The rest of the page is the same.
    assert offline.split("const DATA=")[1] == online.split("const DATA=")[1]


def test_a_city_with_no_cyclist_crashes_still_gets_a_map(
    crashes: gpd.GeoDataFrame, tmp_path: Path
) -> None:
    cars = crashes[crashes.group.eq(CAR)]
    html = movement.build(cars, PARTIES, STREETS, CONFIG, tmp_path / "map.html").read_text()
    assert "const DATA=[];" in html and "Main Street" in html


def _entry(kind: str, direction: str, move: str) -> dict[str, object]:
    return {"k": kind, "d": direction, "m": move}


def test_the_pattern_names_the_cyclist_and_how_the_other_party_came() -> None:
    bike, car = codes.BICYCLE, codes.CAR
    hook = [_entry(bike, "N", "B"), _entry(car, "N", "D")]
    assert movement.pattern(hook) == (
        "cyclist going straight; car or truck right turn, same direction"
    )
    cross = [_entry(bike, "N", "B"), _entry(car, "E", "B")]
    assert movement.pattern(cross).endswith("from the cyclist's left")
    assert movement.pattern([_entry(bike, "N", "B"), _entry(car, "W", "B")]).endswith(
        "from the cyclist's right"
    )
    assert movement.pattern([_entry(bike, "S", "B"), _entry(car, "N", "E")]).endswith(
        "left turn, opposite direction"
    )
    unknown = [_entry(bike, "", "B"), _entry(car, "E", "B")]
    assert movement.pattern(unknown) == (
        "cyclist, direction not stated, going straight; car or truck going straight,"
        " direction not stated"
    )
    assert movement.pattern([_entry(bike, "E", "B")]).endswith("; no other party")
    assert movement.pattern([_entry(car, "E", "B")]) == ""  # no cyclist
    two = [_entry(bike, "E", "B"), _entry(car, "E", "B"), _entry(car, "W", "E")]
    assert movement.pattern(two).endswith("; 2 other parties")


def _network() -> gpd.GeoDataFrame:
    """Main Street (east-west) and Oak Avenue (north-south) crossing at the origin."""
    coords = {
        "Main Street": [_at(-300, 0), _at(0, 0), _at(300, 0)],
        "Oak Avenue": [_at(0, -300), _at(0, 0), _at(0, 300)],
    }
    node_of: dict[tuple[float, float], int] = {}
    records = []
    for osm_id, (name, line) in enumerate(coords.items(), 1):
        ids = [node_of.setdefault(xy, len(node_of) + 1) for xy in line]
        records.append(
            {
                "osm_id": osm_id,
                "highway": "secondary" if name == "Main Street" else "residential",
                "name": name,
                "lanes": None,
                "node_ids": json.dumps(ids),
                "geometry": LineString(line),
            }
        )
    return gpd.GeoDataFrame(records, crs=CRS)


def _placed_crashes() -> gpd.GeoDataFrame:
    """A cyclist crash at the corner and one mid-block, with severity and light."""
    rows = gpd.GeoDataFrame(
        {
            "merged_id": ["a", "b"],
            "year": [2022, 2023],
            "group": [ADULT, CHILD],
            "PRIMARY_RD": ["MAIN ST", "MAIN ST"],
            "SECONDARY_RD": ["OAK AV", None],
            "INTERSECTION": ["Y", "N"],
            "DISTANCE": ["0", "500"],
            "COLLISION_SEVERITY": ["2", "4"],
        },
        geometry=[Point(_at(6, 4)), Point(_at(180, 2))],
        crs=CRS,
    )
    detail = DETAIL.iloc[:2].assign(merged_id=["a", "b"], LIGHTING=["C", "A"])
    return describe(rows, detail, CONFIG)


def test_crashes_are_placed_at_their_intersection_and_mid_block_ones_are_not(
    tmp_path: Path,
) -> None:
    ways, crashes = _network(), _placed_crashes()
    area = box(*_at(-1000, -1000), *_at(1000, 1000))
    at, sites = movement.place(crashes, ways, area)
    assert list(at.index) == ["a"] and len(sites) == 1
    assert sites[0]["n"] == "Main Street / Oak Avenue" and sites[0]["i"] == at["a"]
    rows = movement.crash_rows(crashes, PARTIES, ways, CONFIG.child_max_age, at)
    corner, mid = rows
    assert corner["si"] == at["a"] and mid["si"] is None
    assert (corner["sv"], corner["lt"], mid["sv"], mid["lt"]) == ("2", "C", "4", "A")
    assert (
        corner["pk"].startswith("cyclist going straight; car or truck right turn")
        and corner["pd"] == "westbound"
    )
    assert {round(b) for b, _ in sites[0]["w"]} == {0, 90, 180, 270}
    assert "w" not in corner and mid["w"]  # a corner's streets are on its site entry
    # Parties at a corner turn to the corner's streets, not to those near the reported point.
    skewed = {at["a"]: [[10.0, 5.8], [100.0, 8.6], [190.0, 5.8], [280.0, 8.6]]}
    turned = movement.crash_rows(crashes, PARTIES, ways, CONFIG.child_max_age, at, skewed)
    assert {p["b"] for p in turned[0]["p"] if p["b"] is not None} <= {10.0, 100.0, 190.0, 280.0}
    assert [p["b"] for p in turned[1]["p"]] == [p["b"] for p in mid["p"]]
    # A fit is stored only where the diagram's streets are known: not for a corner given without them.
    assert "fit" not in corner and "fit" in mid and "fit" in turned[0]
    html = movement.build(crashes, PARTIES, ways, CONFIG, tmp_path / "map.html", area=area)
    page = html.read_text()
    assert '"n":"Main Street / Oak Avenue"' in page.split("const SITES=")[1].split(";")[0]
    assert 'id="print"' in page and "Transportation Injury Mapping System (TIMS)" in page


def test_rows_without_severity_or_light_leave_them_blank(crashes: gpd.GeoDataFrame) -> None:
    rows = movement.crash_rows(crashes, PARTIES, STREETS, CONFIG.child_max_age)
    assert all(r["sv"] == "" and r["lt"] == "" and r["si"] is None for r in rows)


def test_a_copy_for_city_staff_says_so_in_its_banner(
    crashes: gpd.GeoDataFrame, tmp_path: Path
) -> None:
    who = "City of Example <traffic> staff"
    page = movement.build(
        crashes, PARTIES, STREETS, CONFIG, tmp_path / "map.html", prepared_for=who
    ).read_text()
    assert "Prepared for City of Example &lt;traffic&gt; staff. Confidential" in page
    assert movement.REAL_NOTICE[0] not in page and "<traffic>" not in page


def test_the_pattern_is_relative_and_the_approach_is_kept_apart() -> None:
    bike, car = codes.BICYCLE, codes.CAR
    north = [_entry(bike, "N", "B"), _entry(car, "N", "D")]
    south = [_entry(bike, "S", "B"), _entry(car, "S", "D")]
    assert movement.pattern(north) == movement.pattern(south)
    assert movement.approach(north) == "northbound"
    assert movement.approach(south) == "southbound"
    assert movement.approach([_entry(bike, "", "B")]) == ""


def test_corridor_groups_the_ways_a_street_is_written() -> None:
    assert names.corridor("FOOTHILL EXPY") == names.corridor("Foothill Expressway")
    assert names.corridor("N SAN ANTONIO RD") == "San Antonio"
    assert names.corridor("RT 82") == names.corridor("El Camino Real") == "El Camino Real"
    assert names.corridor("Distel Drive") != names.corridor("Distel Circle")
    assert names.corridor("NORTH") == "North"
    assert names.corridor("nan") == names.corridor("") == ""
    assert names.corridor("W El Camino Real") == "El Camino Real"
    assert names.corridor("EL CAMINO DEL MAR") == "El Camino Del Mar"
    assert names.corridor("ST FRANCIS DR") == names.corridor("Saint Francis Drive")
    assert names.corridor("ST FRANCIS DR") != names.corridor("FRANCIS DR")
    assert names.corridor("STEVENS CREEK BL") == "Stevens Creek"
    assert names.corridor("1ST ST") == "1st"
    assert names.corridor("W 22ND AVE") == "22nd"
    assert names.corridor("Distel Cir") == names.corridor("DISTEL CIRCLE")
    # A street named by a compass word alone keeps it, with its type written out.
    assert names.corridor("South Street") == names.corridor("SOUTH ST") == "South Street"
    assert names.corridor("N Street") == names.corridor("N ST") == "N Street"
    assert names.corridor("North Avenue") == "North Avenue"
    assert names.corridor("WEST LN") == names.corridor("West Lane") == "West Lane"
    assert names.corridor("N Main St") == names.corridor("Main Street") == "Main"


def _party(kind: str, move: str, bearing: float | None) -> dict:
    return {"k": kind, "m": move, "b": bearing}


@pytest.mark.parametrize(
    ("parties", "coded", "expected"),
    [
        ([("bicycle", "B", 0), ("car or truck", "D", 0)], False, "fits"),  # right hook
        ([("bicycle", "B", 180), ("car or truck", "D", 270)], False, "against"),
        ([("bicycle", "B", 180), ("car or truck", "D", 270)], True, "fits"),
        ([("bicycle", "B", 90), ("car or truck", "A", 180)], False, "nomeet"),
        ([("bicycle", "B", 0), ("car or truck", "L", 0)], False, "fits"),  # pulls out from the kerb
        ([("bicycle", "B", 90)], False, "fits"),
        ([("bicycle", "B", None), ("car or truck", "B", 0)], False, None),
    ],
)
def test_how_movements_fit(parties: list, coded: bool, expected: str | None) -> None:
    made = [_party(*p) for p in parties]
    if coded:  # the cyclist is coded as riding on the wrong side
        made[0]["wr"] = True
    assert diagram.fit(made, [], False, not coded) == expected


def _fault(cyclist: str, driver: str, move: str = "B") -> pd.DataFrame:
    """The made-up parties with crash "a" (cause: wrong side of road) refaulted."""
    parties = PARTIES.copy()
    first = parties.CASE_ID.eq("a")
    parties.loc[first & parties.PARTY_NUMBER.eq(1), ["AT_FAULT", "MOVE_PRE_ACC"]] = [cyclist, move]
    parties.loc[first & parties.PARTY_NUMBER.eq(2), "AT_FAULT"] = driver
    return parties


@pytest.mark.parametrize(
    ("cyclist", "driver", "move", "riding", "unclear"),
    [
        ("Y", "N", "B", True, False),  # the cyclist is the party at fault for the wrong side
        ("N", "Y", "B", False, True),  # the driver is: not the cyclist's wrong-side riding
        ("N", "N", "B", False, True),  # nobody is marked at fault
        ("N", "Y", "Q", True, False),  # the cyclist's own movement is "travelling wrong way"
    ],
)
def test_a_wrong_side_cause_counts_against_the_cyclist_only_when_at_fault(
    crashes: gpd.GeoDataFrame, cyclist: str, driver: str, move: str, riding: bool, unclear: bool
) -> None:
    parties = _fault(cyclist, driver, move)
    first = movement.crash_rows(crashes, parties, STREETS, CONFIG.child_max_age)[0]
    assert first["cause"] == "Wrong side of road"
    assert (first["wc"], first["wu"]) == (riding, unclear)
    # The code puts a cyclist against traffic only when it is that cyclist's; cited with the
    # party unclear, nothing does: not the movements' suggestion, nor making the paths meet.
    assert bool(first["p"][0].get("wr")) == (riding and move != "Q")
    if unclear:
        assert first["ws"] == "" and first["fit"] in ("fits", "nomeet")
        assert not diagram.against(first["p"][0], bool(first["ws"]))
    assert movement.wrong_side(first) == ("coded" if riding else "unclear")


def test_wrong_side_needs_the_cause_or_the_cyclists_own_movement() -> None:
    bike = {"k": codes.BICYCLE, "m": "B", "f": True}
    car = {"k": codes.CAR, "m": "Q", "f": True}
    assert movement.wrong_side_coded("Unsafe speed", [bike, car]) == (False, False)
    assert movement.wrong_side_coded("Wrong side of road", []) == (False, True)


def test_a_mid_block_crash_counts_for_its_own_street_only() -> None:
    ways = _network()
    crashes = _placed_crashes().assign(SECONDARY_RD="OAK AV")  # the nearest cross street
    area = box(*_at(-1000, -1000), *_at(1000, 1000))
    at, _ = movement.place(crashes, ways, area)
    corner, mid = movement.crash_rows(crashes, PARTIES, ways, CONFIG.child_max_age, at)
    assert corner["si"] is not None and corner["cs"] == ["Main Street", "Oak Avenue"]
    assert mid["si"] is None and mid["cs"] == ["Main Street"]
    assert mid["st"] == "Main Street / Oak Avenue"  # the pop-up still names the cross street


def test_tables_name_a_street_as_the_map_does() -> None:
    # (mapped name, metres)
    mapped = [
        ("Foothill Boulevard", 500),
        ("East Foothill Boulevard", 500),  # the same street: a compass word aside
        ("Distel Drive", 500),
        ("Distel Avenue", 400),  # two streets of one name: the short name stays
        ("Mountain Avenue", 2000),
        ("Mountain Drive", 100),  # nearly all of the corridor is the avenue
        (None, 500),
    ]
    ways = gpd.GeoDataFrame(
        {"highway": "residential", "name": [name for name, _ in mapped]},
        geometry=[LineString([_at(0, i), _at(m, i)]) for i, (_, m) in enumerate(mapped)],
        crs=CRS,
    )
    assert movement.street_names(ways) == {
        "Foothill": "Foothill Boulevard",
        "Mountain": "Mountain Avenue",
    }
    assert movement.street_names(ways.drop(columns="name")) == {}


@pytest.mark.parametrize(("age", "band"), [(0, "18 or under"), (100, "adult"), (105, "")])
def test_the_pop_ups_age_band_uses_the_ages_the_crash_group_does(age: int, band: str) -> None:
    party = pd.Series(
        {
            "PARTY_TYPE": "4",
            "STWD_VEHICLE_TYPE": "L",
            "DIR_OF_TRAVEL": "N",
            "MOVE_PRE_ACC": "B",
            "PARTY_AGE": age,
            "AT_FAULT": "N",
        }
    )
    assert movement.party_entry(party, [], 18)["a"] == band
    # The crash group (and so the age filter) draws the line at the same ages.
    from bike_safety_ca.crashes.groups import MAX_AGE

    assert (band != "") == (0 <= age <= MAX_AGE)


RELATIONS = (0, 90, 180, 270)  # the other party's heading less the cyclist's
CROSS = [(0, 8.6), (90, 5.8), (180, 8.6), (270, 5.8)]  # a wide street crossing a narrow one


def test_a_pattern_sorts_the_same_from_every_compass_direction() -> None:
    # Every pair of movements, the other party coming each way, on bearings that used to
    # sit on a knife edge; with and without mapped streets turned to the same bearing.
    odd = []
    for bike_move, other_move, turn in itertools.product(codes.MOVES, codes.MOVES, RELATIONS):
        for streets in (False, True):
            found = set()
            for bearing in (0, 90, 180, 270, 45, 200, 90.1):
                legs = [[(bearing + a) % 360, h] for a, h in CROSS] if streets else []
                parties = [
                    _party("bicycle", bike_move, bearing),
                    _party("car or truck", other_move, (bearing + turn) % 360),
                ]
                found.add(diagram.fit(parties, legs, False, False))
            if len(found) > 1:
                odd.append((bike_move, other_move, turn, streets, sorted(map(str, found))))
    assert odd == []
