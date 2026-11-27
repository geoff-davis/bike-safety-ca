from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, box

from bike_safety_ca.network import junctions as jn

CRS = 26910
AREA = box(-1000, -1000, 1000, 1000)


def _ways(rows: list[tuple[str, str | None, str | None, list[tuple[float, float]]]]):
    """Ways from (highway, name, lanes, coordinates); vertices at the same place share a node."""
    node_of: dict[tuple[float, float], int] = {}
    records = []
    for osm_id, (highway, name, lanes, coords) in enumerate(rows, 1):
        ids = [node_of.setdefault(xy, len(node_of) + 1) for xy in coords]
        records.append(
            {
                "osm_id": osm_id,
                "highway": highway,
                "name": name,
                "lanes": lanes,
                "node_ids": json.dumps(ids),
                "geometry": LineString(coords),
            }
        )
    return gpd.GeoDataFrame(records, crs=CRS)


def _tags(rows: list[tuple[str, str | None, tuple[float, float]]]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"highway": [r[0] for r in rows], "stop": [r[1] for r in rows]},
        geometry=[Point(r[2]) for r in rows],
        crs=CRS,
    )


def _points(*xy: tuple[float, float]) -> gpd.GeoSeries:
    return gpd.GeoSeries([Point(p) for p in xy], crs=CRS)


def test_crossing_takes_its_classes_lanes_and_name_from_the_roads_that_meet() -> None:
    ways = _ways(
        [
            ("secondary", "Main Street", "4", [(-200, 0), (0, 0), (200, 0)]),
            ("residential", "Oak Avenue", None, [(0, -200), (0, 0), (0, 200)]),
        ]
    )
    found, streets = jn.build_junctions(ways, AREA)
    assert len(found) == 1
    row = found.iloc[0]
    assert (row.major, row.minor, row.lanes) == ("Arterial", "Local", "4+")
    assert row["name"] == "Main Street / Oak Avenue"
    # Street keys keep the type, so that Main Street is not Main Avenue.
    assert streets.iloc[0] == {"MAIN STREET", "OAK AVENUE"}
    assert row.geometry.distance(Point(0, 0)) < 1e-6


def test_a_bend_or_dead_end_is_not_an_intersection() -> None:
    ways = _ways([("residential", "Oak Avenue", None, [(0, 0), (100, 0), (100, 100)])])
    found, _ = jn.build_junctions(ways, AREA)
    assert found.empty


def test_street_split_into_two_ways_counts_as_one_road() -> None:
    # Main Street changes OSM way at the junction: still one road, so the second
    # road is the local side street, not Main Street again.
    ways = _ways(
        [
            ("secondary", "Main Street", None, [(-200, 0), (0, 0)]),
            ("secondary", "Main Street", None, [(0, 0), (200, 0)]),
            ("residential", "Oak Avenue", None, [(0, 0), (0, 200)]),
        ]
    )
    found, _ = jn.build_junctions(ways, AREA)
    assert (found.major.iloc[0], found.minor.iloc[0]) == ("Arterial", "Local")


def test_on_and_off_halves_of_an_unnamed_ramp_are_one_road() -> None:
    ways = _ways(
        [
            ("trunk_link", None, None, [(-200, 50), (0, 0)]),
            ("trunk_link", None, None, [(0, 0), (200, 50)]),
            ("residential", "Bridge Street", None, [(0, 0), (0, -200)]),
        ]
    )
    found, _ = jn.build_junctions(ways, AREA)
    assert (found.major.iloc[0], found.minor.iloc[0]) == ("Arterial", "Local")


def test_divided_road_meeting_a_cross_street_is_one_intersection() -> None:
    ways = _ways(
        [
            ("primary", "Big Road", "2", [(-200, 20), (0, 20), (200, 20)]),
            ("primary", "Big Road", "2", [(200, -20), (0, -20), (-200, -20)]),
            ("residential", "Side Street", None, [(0, -200), (0, -20), (0, 20), (0, 200)]),
        ]
    )
    found, _ = jn.build_junctions(ways, AREA)
    assert len(found) == 1
    assert found.geometry.iloc[0].distance(Point(0, 0)) < 1


def test_signal_beats_stop_signs_and_yield_counts_as_minor_road_stop() -> None:
    points = _points((0, 0), (500, 0), (1000, 0))
    tags = _tags(
        [
            ("traffic_signals", None, (0, 20)),
            ("stop", "all", (0, -10)),
            ("give_way", None, (500, 10)),
        ]
    )
    control = jn.osm_control(points, tags)
    assert control.tolist() == [jn.SIGNAL, jn.MINOR_STOP, jn.NO_CONTROL]


def test_all_way_needs_a_tag_or_three_untagged_stop_signs() -> None:
    points = _points((0, 0), (500, 0), (1000, 0), (1500, 0))
    tags = _tags(
        [
            ("stop", "all", (0, 10)),  # tagged all-way
            ("stop", None, (500, 10)),  # three untagged signs
            ("stop", None, (500, -10)),
            ("stop", None, (510, 0)),
            ("stop", None, (1000, 10)),  # two untagged signs
            ("stop", None, (1000, -10)),
            ("stop", "minor", (1500, 10)),  # three signs, but tagged minor
            ("stop", None, (1500, -10)),
            ("stop", None, (1510, 0)),
        ]
    )
    control = jn.osm_control(points, tags)
    assert control.tolist() == [jn.ALL_WAY, jn.ALL_WAY, jn.MINOR_STOP, jn.MINOR_STOP]


def test_osm_control_with_no_tagged_nodes() -> None:
    control = jn.osm_control(_points((0, 0)), _tags([]))
    assert control.tolist() == [jn.NO_CONTROL]


def test_school_distance_bands() -> None:
    schools = gpd.GeoDataFrame({"school": ["Almond"]}, geometry=[Point(0, 0)], crs=CRS)
    near = jn.nearest_school(_points((300, 0), (600, 0), (900, 0)), schools)
    assert near.school_band.tolist() == ["<400 m", "400–800 m", ">800 m"]
    assert near.school_m.tolist() == [300, 600, 900]


def _crashes(rows: list[tuple[str, tuple[float, float], object, object, str, object]]):
    return gpd.GeoDataFrame(
        {
            "merged_id": [r[0] for r in rows],
            "PRIMARY_RD": [r[2] for r in rows],
            "SECONDARY_RD": [r[3] for r in rows],
            "INTERSECTION": [r[4] for r in rows],
            "DISTANCE": [r[5] for r in rows],
        },
        geometry=[Point(r[1]) for r in rows],
        crs=CRS,
    )


def test_crash_goes_to_the_named_intersection_before_the_nearest_one() -> None:
    points = _points((0, 0), (80, 0))
    streets = pd.Series([{"MAIN", "OAK"}, {"MAIN", "ELM"}])
    crashes = _crashes(
        [
            ("near", (10, 0), "MAIN ST", "PINE ST", "N", 300),  # within 35 m of the first
            ("named", (60, 0), "MAIN ST", "OAK AVE", "Y", 0),  # nearer the second, coded at first
            ("coded_far", (250, 0), "MAIN ST", "OAK AVE", "Y", 0),  # over 100 m away
            ("midblock", (40, 60), "PINE ST", "", "N", 500),  # at no intersection
        ]
    )
    hits = jn.assign_crashes(crashes, points, streets)
    assert hits.site.to_dict() == {"near": 0, "named": 0}
    assert jn.count_at(hits, points.index).tolist() == [2, 0]


def test_one_coded_street_is_not_enough_for_a_name_match() -> None:
    points = _points((0, 0), (160, 0))
    streets = pd.Series([{"MAIN", "OAK"}, {"MAIN", "ELM"}])
    crashes = _crashes(
        [
            ("blank", (60, 0), "MAIN ST", "", "Y", 0),  # second street missing
            ("same", (70, 0), "MAIN ST", "MAIN ST", "Y", 0),  # same street twice
            ("close", (20, 0), "MAIN ST", "", "Y", 0),  # still within 35 m of the first
        ]
    )
    hits = jn.assign_crashes(crashes, points, streets)
    assert hits.site.to_dict() == {"close": 0}


def test_a_crash_put_at_a_corner_for_want_of_a_direction_counts_only_if_it_was_close() -> None:
    points = _points((0, 0))
    streets = pd.Series([{"MAIN", "OAK"}])
    crashes = _crashes(
        [
            ("far", (0, 0), "MAIN ST", "OAK AVE", "N", 400),  # 122 m away, direction unknown
            ("close", (0, 0), "MAIN ST", "OAK AVE", "N", 60),  # 18 m away
            ("known", (0, 0), "MAIN ST", "OAK AVE", "N", 400),  # really located at the corner
            ("flagged", (0, 0), "MAIN ST", "OAK AVE", "Y", 400),  # far, though marked "at"
        ]
    ).assign(
        offset_direction_missing=[True, True, False, True],
        reported_offset_m=[121.9, 18.3, float("nan"), 121.9],
    )
    hits = jn.assign_crashes(crashes, points, streets)
    assert sorted(hits.index) == ["close", "known"]
    plain = jn.assign_crashes(crashes.drop(columns="offset_direction_missing"), points, streets)
    assert len(plain) == 4  # tables without the marker behave as before


def _divided(lanes_a: str | None, lanes_b: str | None, gap: float = 12.0) -> gpd.GeoDataFrame:
    ways = _ways(
        [
            ("primary", "Grand Road", lanes_a, [(-200, 0), (0, 0), (200, 0)]),
            ("primary", "Grand Road", lanes_b, [(200, gap), (0, gap), (-200, gap)]),
            ("residential", "Oak Avenue", None, [(0, -200), (0, 0), (0, gap), (0, 200)]),
        ]
    )
    return ways.assign(oneway=["yes", "yes", None])


def test_divided_road_lanes_are_the_two_halves_together() -> None:
    ways = _divided("2", "3")
    assert jn.road_lanes(ways).tolist()[:2] == [5.0, 5.0]
    found, _ = jn.build_junctions(ways, AREA)
    assert found.lanes.tolist() == ["4+"]


def test_divided_road_with_one_half_untagged_doubles_the_tagged_half() -> None:
    lanes = jn.road_lanes(_divided("2", None))
    assert lanes.iloc[0] == 4.0
    assert pd.isna(lanes.iloc[1])


def test_one_way_street_without_an_opposing_half_keeps_its_lanes() -> None:
    far = _divided("2", "2", gap=80.0)
    assert jn.road_lanes(far).tolist()[:2] == [2.0, 2.0]
    same_direction = _ways(
        [
            ("primary", "Grand Road", "2", [(-200, 0), (200, 0)]),
            ("primary", "Grand Road", "2", [(-200, 12), (200, 12)]),
        ]
    ).assign(oneway="yes")
    assert jn.road_lanes(same_direction).tolist() == [2.0, 2.0]


def test_lanes_without_a_oneway_column_are_the_tags() -> None:
    ways = _divided("2", "3").drop(columns="oneway")
    assert jn.road_lanes(ways).tolist()[:2] == [2.0, 3.0]


def test_a_short_widened_piece_does_not_decide_the_lane_group() -> None:
    ways = _ways(
        [
            ("secondary", "Main Street", "2", [(-200, 0), (-20, 0)]),
            ("secondary", "Main Street", "5", [(-20, 0), (0, 0), (20, 0)]),
            ("secondary", "Main Street", "2", [(20, 0), (200, 0)]),
            ("residential", "Oak Avenue", None, [(0, -200), (0, 0), (0, 200)]),
        ]
    )
    found, _ = jn.build_junctions(ways, AREA)
    assert found.lanes.tolist() == [jn.NOT_WIDE]


def test_three_lanes_is_not_wide() -> None:
    ways = _ways(
        [
            ("secondary", "Main Street", "3", [(-200, 0), (0, 0), (200, 0)]),
            ("residential", "Oak Avenue", None, [(0, -200), (0, 0), (0, 200)]),
        ]
    )
    found, _ = jn.build_junctions(ways, AREA)
    assert found.lanes.tolist() == [jn.NOT_WIDE]


def test_a_mostly_untagged_road_is_not_wide() -> None:
    ways = _ways(
        [
            ("secondary", "Main Street", None, [(-200, 0), (-20, 0)]),
            ("secondary", "Main Street", "5", [(-20, 0), (0, 0), (20, 0)]),
            ("secondary", "Main Street", None, [(20, 0), (200, 0)]),
            ("residential", "Oak Avenue", None, [(0, -200), (0, 0), (0, 200)]),
        ]
    )
    found, _ = jn.build_junctions(ways, AREA)
    assert found.lanes.tolist() == [jn.NOT_WIDE]


def test_nearness_does_not_count_when_both_coded_streets_are_elsewhere() -> None:
    points = _points((0, 0))
    streets = pd.Series([{"MAIN", "OAK"}])
    crashes = _crashes(
        [
            ("freeway", (10, 0), "RT 85", "FREMONT AVE", "N", 900),  # above the corner
            ("one_street", (10, 0), "MAIN ST", "PINE ST", "N", 300),  # on one of its streets
            ("unnamed", (10, 0), "MAIN ST", "", "N", 300),
            ("nan", (10, 0), "PINE ST", float("nan"), "N", 300),  # a missing name is no name
            ("na", (10, 0), "PINE ST", pd.NA, "N", 300),
            ("none", (10, 0), None, "PINE ST", "N", 300),
            ("minus", (60, 0), "MAIN ST", "OAK AVE", "N", -5),  # a negative distance is no match
        ]
    )
    kept = ["na", "nan", "none", "one_street", "unnamed"]
    assert sorted(jn.assign_crashes(crashes, points, streets).index) == kept
    loose = jn.assign_crashes(crashes, points, streets, check_names=False)
    assert sorted(loose.index) == sorted(["freeway", *kept])


def test_a_row_of_close_corners_can_be_kept_apart() -> None:
    # Four T-junctions 20 m apart along Main Street, each with its own side street.
    main = LineString([(-50, 0), (0, 0), (20, 0), (40, 0), (60, 0), (110, 0)])
    sides = [LineString([(x, 0), (x, 80)]) for x in (0, 20, 40, 60)]
    ways = gpd.GeoDataFrame(
        {
            "osm_id": range(5),
            "highway": "residential",
            "name": ["Main Street", "A Street", "B Street", "C Street", "D Street"],
            "lanes": None,
            "node_ids": [
                json.dumps([100, 1, 2, 3, 4, 101]),
                *[json.dumps([i + 1, 200 + i]) for i in range(4)],
            ],
        },
        geometry=[main, *sides],
        crs=CRS,
    )
    area = box(-100, -100, 200, 200)
    chained, _ = jn.build_junctions(ways, area)
    assert len(chained) == 1 and chained.span_m.iloc[0] == pytest.approx(60)
    assert chained.nodes.iloc[0] == 4
    apart, _ = jn.build_junctions(ways, area, max_cluster_m=25)
    assert len(apart) == 2 and apart.span_m.max() <= 25


def test_span_is_the_greatest_distance_between_joined_nodes() -> None:
    grid = jn._widest(np.array([(x, y) for x in (0, 20, 40) for y in (0, 20, 40)], dtype=float))
    assert grid == pytest.approx(40 * 2**0.5)  # corner to corner, not the side
    assert jn._widest(np.array([(3.0, 4.0)])) == 0.0


def test_a_crash_goes_to_the_nearest_intersection_it_could_describe() -> None:
    points = _points((0, 0), (30, 0))
    streets = pd.Series([{"MAIN", "OAK"}, {"ELM", "PINE"}])
    crashes = _crashes(
        [
            ("second", (10, 0), "ELM ST", "PINE ST", "N", 300),  # nearest is Main/Oak
            ("first", (10, 0), "MAIN ST", "PINE ST", "N", 300),
            ("neither", (10, 0), "RT 85", "FREMONT AVE", "N", 300),
        ]
    )
    assert jn.assign_crashes(crashes, points, streets).site.to_dict() == {"second": 1, "first": 0}
    loose = jn.assign_crashes(crashes, points, streets, check_names=False)
    assert loose.site.to_dict() == {"second": 0, "first": 0, "neither": 0}


def test_a_street_named_by_a_direction_or_a_type_word_keeps_its_name() -> None:
    keys = {n: jn.road_key(n) for n in ("South Street", "N Street", "North Avenue", "West Lane")}
    assert keys == {
        "South Street": "SOUTH",
        "N Street": "N",
        "North Avenue": "NORTH",
        "West Lane": "WEST",
    }
    assert jn.road_key("SOUTH ST") == "SOUTH" and jn.road_key("Court Street") == "COURT"
    assert jn.road_key("N Court St") == "COURT"
    # A direction or type beside a real name is still dropped.
    assert jn.road_key("N Main St") == jn.road_key("Main Street") == "MAIN"
    assert jn.road_key("N/B") == jn.road_key("") == jn.road_key(None) == ""
    # A leading ST before a name is Saint: not Francis Drive.
    assert jn.street_key("St Francis Drive") == jn.street_key("SAINT FRANCIS DR")
    assert jn.street_key("St Francis Drive") != jn.street_key("Francis Drive")
    assert jn.street_key("St Francis") == "SAINT FRANCIS"
    ways = _ways(
        [
            ("secondary", "South Street", None, [(-200, 0), (0, 0), (200, 0)]),
            ("residential", "Oak Avenue", None, [(0, -200), (0, 0), (0, 200)]),
        ]
    )
    found, streets = jn.build_junctions(ways, AREA)
    assert streets.iloc[0] == {"SOUTH STREET", "OAK AVENUE"}
    # Coded at the corner but 60 to 80 m off it: only the street names place them.
    crashes = _crashes(
        [
            ("first", (60, 0), "SOUTH ST", "OAK AVE", "Y", 0),
            ("second", (0, 78), "OAK AV", "SOUTH STREET", "Y", 0),
        ]
    )
    hits = jn.assign_crashes(crashes, found.geometry, streets)
    assert hits.site.to_dict() == {"first": found.index[0], "second": found.index[0]}


def test_streets_that_share_a_name_are_apart_and_reports_match_them_by_name() -> None:
    assert jn.street_key("Park Avenue") == jn.street_key("N PARK AV") == "PARK AVENUE"
    kinds = ("Park Avenue", "Park Place", "Park Way", "Park")
    assert len({jn.street_key(n) for n in kinds}) == 4
    assert jn.street_key("1st Street") != jn.street_key("1st Avenue")
    assert jn.street_key("Avenue 12") != jn.street_key("Road 12")
    assert jn.street_key("Foothill Expy") == jn.street_key("FOOTHILL EXPRESSWAY")
    assert jn.street_key("El Camino Real") == jn.street_key("RT 82")
    # Reports are matched by the name inside the key.
    for name in (*kinds, "South Street", "Court Street", "El Camino Real", "Avenue 12"):
        assert jn.road_key(jn.street_key(name)) == jn.road_key(name) != ""
    ways = _ways(
        [
            ("residential", "Oak Avenue", None, [(-300, 0), (-80, 0), (80, 0), (300, 0)]),
            ("residential", "Park Avenue", None, [(-80, -200), (-80, 0), (-80, 200)]),
            ("residential", "Park Place", None, [(80, -200), (80, 0), (80, 200)]),
        ]
    )
    found, streets = jn.build_junctions(ways, AREA)
    site = {round(x): int(str(i)) for i, x in found.geometry.x.items()}
    assert streets[site[-80]] == {"OAK AVENUE", "PARK AVENUE"}
    assert streets[site[80]] == {"OAK AVENUE", "PARK PLACE"}
    # Police drop and abbreviate types, so a report fits either corner whatever
    # type it gives, and goes to the nearer one within 100 m.
    crashes = _crashes(
        [
            ("untyped", (30, 0), "PARK", "OAK AVE", "Y", 0),
            ("typed", (-30, 0), "PARK PL", "OAK AVE", "Y", 0),
        ]
    )
    hits = jn.assign_crashes(crashes, found.geometry, streets)
    assert hits.site.to_dict() == {"untyped": site[80], "typed": site[-80]}


def test_opposing_one_way_streets_of_one_name_and_two_types_are_not_one_divided_road() -> None:
    ways = _ways(
        [
            ("secondary", "Park Avenue", "2", [(-200, 0), (0, 0), (200, 0)]),
            ("secondary", "Park Place", "2", [(200, 20), (0, 20), (-200, 20)]),
            ("residential", "Oak Lane", None, [(0, -200), (0, 0), (0, 20), (0, 200)]),
        ]
    ).assign(oneway=["yes", "yes", None])
    assert jn.road_lanes(ways).tolist()[:2] == [2.0, 2.0]
    found, _ = jn.build_junctions(ways, AREA)
    assert found.lanes.tolist() == [jn.NOT_WIDE]


def test_crossing_streets_of_one_name_and_two_types_are_two_roads() -> None:
    ways = _ways(
        [
            ("secondary", "Park Avenue", None, [(-200, 0), (0, 0), (200, 0)]),
            ("tertiary", "Park Place", None, [(0, -200), (0, 0), (0, 200)]),
        ]
    )
    found, _ = jn.build_junctions(ways, AREA)
    assert (found.major.iloc[0], found.minor.iloc[0]) == ("Arterial", "Collector")


def test_a_way_mapped_without_its_type_is_the_one_typed_street_of_that_name() -> None:
    # Two halves of one divided road, one mapped as "Main": still a pair.
    ways = _ways(
        [
            ("secondary", "Main St", "2", [(-200, 0), (200, 0)]),
            ("secondary", "Main", "2", [(200, 20), (-200, 20)]),
        ]
    ).assign(oneway="yes")
    assert jn.road_lanes(ways).tolist() == [4.0, 4.0]
    # A spur mapped as "Main" is Main Street again, not a second road.
    spur = _ways(
        [
            ("secondary", "Main Street", None, [(-200, 0), (0, 0), (200, 0)]),
            ("secondary", "Main", None, [(0, 0), (0, 200)]),
        ]
    )
    found, _ = jn.build_junctions(spur, AREA)
    assert (found.major.iloc[0], found.minor.iloc[0]) == ("Arterial", "Local")


def test_an_untyped_name_with_two_typed_streets_stays_on_its_own() -> None:
    keys = {"PARK AVENUE", "PARK PLACE", "PARK", "OAK", "OAK LANE"}
    assert jn._joined(keys) == {
        "PARK AVENUE": "PARK AVENUE",
        "PARK PLACE": "PARK PLACE",
        "PARK": "PARK",
        "OAK": "OAK LANE",
        "OAK LANE": "OAK LANE",
    }
    ways = _ways(
        [
            ("secondary", "Park Avenue", None, [(-200, 0), (0, 0), (200, 0)]),
            ("tertiary", "Park Place", None, [(0, -200), (0, 0)]),
            ("tertiary", "Park", None, [(0, 0), (0, 200)]),
        ]
    )
    found, _ = jn.build_junctions(ways, AREA)
    assert (found.major.iloc[0], found.minor.iloc[0]) == ("Arterial", "Collector")
    opposing = _ways(
        [
            ("secondary", "Park Avenue", "2", [(-200, 0), (200, 0)]),
            ("secondary", "Park Place", "2", [(200, 20), (-200, 20)]),
        ]
    ).assign(oneway="yes")
    assert jn.road_lanes(opposing).tolist() == [2.0, 2.0]


def test_a_crash_just_outside_the_area_counts_at_an_intersection_inside_it() -> None:
    # Main Street crosses Oak 5 m inside the area's east edge and Elm 35 m beyond it.
    ways = _ways(
        [
            ("secondary", "Main Street", None, [(-400, 0), (0, 0), (40, 0), (400, 0)]),
            ("residential", "Oak Avenue", None, [(0, -200), (0, 0), (0, 200)]),
            ("residential", "Elm Street", None, [(40, -200), (40, 0), (40, 200)]),
        ]
    )
    area = box(-300, -300, 5, 300)
    sites, streets = jn.build_junctions(ways, area)
    assert len(sites) == 1  # Oak; Elm is outside
    oak = sites.index[0]
    crashes = _crashes(
        [
            ("inside", (-3, 0), "MAIN ST", "PINE ST", "N", 300),
            ("just_outside", (12, 0), "MAIN ST", "PINE ST", "N", 300),  # 12 m from Oak
            ("at_the_next_corner", (33, 0), "MAIN ST", "PINE ST", "N", 300),  # nearer Elm
            ("named", (70, 0), "MAIN ST", "OAK AVE", "Y", 0),  # coded at Oak, 70 m off
            ("too_far", (200, 0), "MAIN ST", "OAK AVE", "Y", 0),  # beyond the edge reach
        ]
    )
    hits = jn.assign_in_area(crashes, sites.geometry, streets, ways, area)
    assert hits.site.to_dict() == {"inside": oak, "just_outside": oak, "named": oak}
    # Cut to the area first, as before, only the crash inside is counted.
    inside = crashes[crashes.geometry.within(area)]
    assert jn.assign_crashes(inside, sites.geometry, streets).site.to_dict() == {"inside": oak}
    # With every crash inside the area the two agree.
    assert jn.assign_in_area(inside, sites.geometry, streets, ways, area).equals(
        jn.assign_crashes(inside, sites.geometry, streets)
    )


def test_a_crash_beyond_the_edge_goes_to_a_better_match_farther_out() -> None:
    # Oak Avenue meets Main Street twice: 1 m inside the area and 110 m beyond
    # its edge.  A report coded at Main and Oak, 90 m beyond the edge, is 91 m
    # from the first and 20 m from the second, which lies past the edge reach.
    ways = _ways(
        [
            ("secondary", "Main Street", None, [(-400, 0), (-1, 0), (110, 0), (400, 0)]),
            ("residential", "Oak Avenue", None, [(-1, -200), (-1, 0), (-1, 200)]),
            ("residential", "Oak Avenue", None, [(110, -200), (110, 0), (110, 200)]),
        ]
    )
    area = box(-300, -300, 0, 300)
    sites, streets = jn.build_junctions(ways, area)
    assert len(sites) == 1
    crashes = _crashes([("coded", (90, 0), "MAIN ST", "OAK AVE", "Y", 0)])
    assert jn.assign_in_area(crashes, sites.geometry, streets, ways, area).empty


def test_a_corner_joined_with_a_node_across_the_edge_keeps_its_crashes() -> None:
    # Oak is 5 m inside the edge and Elm 15 m beyond it, 20 m apart: one
    # intersection when both are in view, centred outside the area.  The area's
    # own intersection is Oak alone, and a crash between the two counts there.
    ways = _ways(
        [
            ("secondary", "Main Street", None, [(-400, 0), (0, 0), (20, 0), (400, 0)]),
            ("residential", "Oak Avenue", None, [(0, -200), (0, 0), (0, 200)]),
            ("residential", "Elm Street", None, [(20, -200), (20, 0), (20, 200)]),
        ]
    )
    area = box(-300, -300, 5, 300)
    sites, streets = jn.build_junctions(ways, area)
    wider, _ = jn.build_junctions(ways, area.buffer(2 * jn.EDGE_REACH_M))
    assert len(sites) == 1 and len(wider) == 1
    assert not wider.geometry.iloc[0].within(area)  # the joined centre is outside
    crashes = _crashes([("between", (12, 0), "MAIN ST", "PINE ST", "N", 300)])
    hits = jn.assign_in_area(crashes, sites.geometry, streets, ways, area)
    assert hits.site.to_dict() == {"between": sites.index[0]}


def test_a_long_chain_across_the_edge_is_still_the_areas_own_corner() -> None:
    # Cross streets every 20 m from Oak, 5 m inside the edge, to 160 m beyond:
    # in the wider view they chain into one intersection centred 80 m out,
    # farther from Oak than any fixed distance would allow for.
    cross = [(0.0, "Oak Avenue")] + [(float(x), f"Lane {x} Street") for x in range(20, 180, 20)]
    main: list[tuple[float, float]] = [(-400, 0), *[(x, 0.0) for x, _ in cross], (400, 0)]
    rows: list[tuple[str, str | None, str | None, list[tuple[float, float]]]] = [
        ("secondary", "Main Street", None, main)
    ]
    rows += [("residential", name, None, [(x, -200), (x, 0), (x, 200)]) for x, name in cross]
    ways = _ways(rows)
    area = box(-300, -300, 5, 300)
    sites, streets = jn.build_junctions(ways, area)
    wider, _ = jn.build_junctions(ways, area.buffer(2 * jn.EDGE_REACH_M))
    assert len(sites) == 1 and len(wider) == 1
    assert wider.geometry.iloc[0].distance(sites.geometry.iloc[0]) > 60
    crashes = _crashes([("coded", (70, 0), "MAIN ST", "OAK AVE", "Y", 0)])
    hits = jn.assign_in_area(crashes, sites.geometry, streets, ways, area)
    assert hits.site.to_dict() == {"coded": sites.index[0]}


def test_a_separate_corner_beyond_the_edge_with_the_same_streets_keeps_its_crash() -> None:
    # Main and Oak meet 5 m inside the edge; 40 m on, outside, Main meets Elm
    # where another piece of Oak ends.  The two are separate intersections
    # (their street names differ), and a crash 10 m from the second is its own.
    ways = _ways(
        [
            ("secondary", "Main Street", None, [(-400, 0), (0, 0), (40, 0), (400, 0)]),
            ("residential", "Oak Avenue", None, [(0, -200), (0, 0), (0, 200)]),
            ("residential", "Oak Avenue", None, [(40, 0), (40, 200)]),
            ("residential", "Elm Street", None, [(40, -200), (40, 0)]),
        ]
    )
    area = box(-300, -300, 5, 300)
    sites, streets = jn.build_junctions(ways, area)
    wider, _ = jn.build_junctions(ways, area.buffer(2 * jn.EDGE_REACH_M))
    assert len(sites) == 1 and len(wider) == 2
    crashes = _crashes([("at_elm", (30, 0), "MAIN ST", "ELM ST", "N", 300)])
    assert jn.assign_in_area(crashes, sites.geometry, streets, ways, area).empty
