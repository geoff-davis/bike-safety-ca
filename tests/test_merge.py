"""CCRS cleaning, TIMS linkage and duplicate-report checks (crashes.merge)."""

import geopandas as gpd
import pandas as pd
import pytest

from bike_safety_ca.config import Reassignment
from bike_safety_ca.crashes import merge as ccrs
from bike_safety_ca.crashes.locate import locate_reported_intersections
from bike_safety_ca.crashes.tims import reporting_agency

CRS = "EPSG:26910"
RULES = (Reassignment(filed_as="4312", agency="4305", beat_prefix="LA", city="Los Altos"),)


def _raw_crash(cid, report, version, ncic="4316", when="2024-05-01T08:30:00", **extra):
    row = {
        "Collision Id": str(cid),
        "Report Number": report,
        "Report Version": str(version),
        "NCIC Code": ncic,
        "Crash Date Time": when,
        "ModifiedDate": f"2025-01-0{version}T00:00:00",
        "IsDeleted": "False",
        "City Name": "Sunnyvale",
        "PrimaryRoad": "MATHILDA AV",
        "SecondaryRoad": "EVELYN AV",
    }
    return row | extra


def test_resubmission_keeps_latest_version_and_report_numbers_are_per_agency():
    raw = pd.DataFrame(
        [
            _raw_crash(1, "CR24-1", 1),
            _raw_crash(2, "CR24-1", 2, when="2024-05-01T09:30:00"),  # corrected resubmission
            _raw_crash(3, "24-0421", 1, ncic="4307"),
            _raw_crash(4, "24-0421", 1, ncic="4304"),  # same number, another agency
            _raw_crash(5, "CR24-9", 1, when="2024-01-01T00:00:00"),
            _raw_crash(6, "CR24-9", 2, when="2024-11-01T00:00:00"),  # too far apart to merge
            _raw_crash(7, "ZZ24-7", 1, IsDeleted="True"),
        ]
    )
    kept, superseded, stats = ccrs.clean_crashes(raw)
    assert sorted(kept.ccrs_collision_id) == [2, 3, 4, 5, 6]
    assert superseded.set_index("ccrs_collision_id").superseded_by.to_dict() == {1: 2}
    assert stats["deleted_rows_dropped"] == 1
    assert kept.set_index("ccrs_collision_id").report_number_conflict.to_dict() == {
        2: False,
        3: False,
        4: False,
        5: True,
        6: True,
    }


def test_ccrs_id_is_embedded_in_ccrs_era_tims_case_ids():
    ids = ccrs.ccrs_id_from_case_id(pd.Series(["81000011", "90100022", "9100033", "8100044"]))
    assert ids.tolist()[:2] == [1000011, 100022]
    assert ids.iloc[2:].isna().all()  # legacy 7-digit SWITRS ids


def test_road_key_unifies_state_route_spellings():
    assert ccrs._road_key("SR -82 (El Camino Real)") == ccrs._road_key("RT 82")
    assert ccrs._road_key("EL CAMINO REAL") == "RT 82"
    assert ccrs._road_key("US-101 S/B") == ccrs._road_key("RT 101")
    assert ccrs._road_key("WOLFE RD") == "WOLFE"


def _tims(rows):
    frame = pd.DataFrame(rows, columns=["CASE_ID", "JURIS", "date", "time", "pr", "sr"])
    return gpd.GeoDataFrame(
        {
            "CASE_ID": frame.CASE_ID,
            "JURIS": frame.JURIS,
            "collision_date": pd.to_datetime(frame.date),
            "year": pd.to_datetime(frame.date).dt.year,
            "collision_time": frame.time,
            "PRIMARY_RD": frame.pr,
            "SECONDARY_RD": frame.sr,
            "POINT_X": pd.NA,
            "POINT_Y": pd.NA,
        }
    )


def _ccrs(rows):
    frame = pd.DataFrame(rows, columns=["ccrs_collision_id", "JURIS", "date", "time", "pr", "sr"])
    return pd.DataFrame(
        {
            "ccrs_collision_id": pd.array(frame.ccrs_collision_id, dtype="Int64"),  # type: ignore[call-overload]
            "JURIS": frame.JURIS,
            "collision_date": pd.to_datetime(frame.date),
            "year": pd.to_datetime(frame.date).dt.year,
            "collision_time": frame.time,
            "PRIMARY_RD": frame.pr,
            "SECONDARY_RD": frame.sr,
            "LATITUDE": float("nan"),
            "LONGITUDE": float("nan"),
        }
    )


def test_link_by_embedded_id_then_by_attributes_one_to_one():
    tims = _tims(
        [
            ("81000011", "4316", "2024-01-08", "15:40", "FIRST AV", "OAK AV"),
            ("8100055", "4316", "2019-03-04", "18:30", "S ELM ST", "PINE ST"),
            ("8100056", "4316", "2019-03-04", "18:30", "S MAPLE AV", "E PINE AV"),
            ("8100088", "4316", "2019-03-05", "10:00", "MATHILDA AV", "EVELYN AV"),
            ("81000099", "4316", "2024-02-01", "10:00", "MARY AV", "EVELYN AV"),
        ]
    )
    ccrs_rows = _ccrs(
        [
            (1000011, "4316", "2024-01-08", "15:40", "FIRST AV", "OAK AV"),
            (3000016, "4316", "2019-03-04", "18:30", "S ELM ST", "PINE ST"),
            (3000019, "4316", "2019-03-04", "18:30", "S MAPLE AV", "E PINE AV"),
            # A third crash on Olive a minute later must not make the others ambiguous.
            (3000030, "4316", "2019-03-04", "18:31", "E PINE AV", "CEDAR AV"),
            # Two different crashes equally good for one TIMS crash: ambiguous.
            (3000041, "4316", "2019-03-05", "10:00", "MATHILDA AV", "WOLFE RD"),
            (3000042, "4316", "2019-03-05", "10:00", "MATHILDA AV", "FAIR OAKS AV"),
            # Embedded id exists but on another date: rejected.
            (1000099, "4316", "2024-03-15", "10:00", "MARY AV", "EVELYN AV"),
        ]
    )
    links = ccrs.link_tims(
        tims, ccrs_rows, pd.DataFrame(columns=["ccrs_collision_id", "superseded_by"]), CRS
    )
    by_case = links.set_index("CASE_ID")
    assert by_case.link_method.to_dict() == {
        "81000011": "case_id",
        "8100055": "attributes",
        "8100056": "attributes",
        "8100088": "attributes_ambiguous",
        "81000099": "case_id_date_mismatch",
    }
    assert by_case.loc["8100055", "ccrs_collision_id"] == 3000016
    assert by_case.loc["8100056", "ccrs_collision_id"] == 3000019
    # With nothing left to match by attributes the distance columns still exist.
    direct = ccrs.link_tims(
        tims.iloc[:1],
        ccrs_rows.iloc[:1],
        pd.DataFrame(columns=["ccrs_collision_id", "superseded_by"]),
        CRS,
    )
    assert direct.link_method.tolist() == ["case_id"] and direct.metres_apart.isna().all()


def test_same_parties_tolerates_one_year_age_difference_and_unknown_ages():
    assert ccrs.same_parties("1:F:62,1:M:55,1:M:88", "1:F:998,1:M:998,1:M:998")
    assert ccrs.same_parties("1:M:33,4:F:12", "1:M:34,4:F:12")
    assert not ccrs.same_parties("1:M:33,4:F:12", "1:M:40,4:F:12")
    assert not ccrs.same_parties("1:M:33,1:F:20", "1:M:33")  # chain crash: other parties
    assert not ccrs.same_parties("", "1:M:33")


def test_duplicate_reports_needs_same_people_for_same_agency():
    points = gpd.points_from_xy([-122.0500, -122.0498, -122.0500, -122.0208], [37.3500] * 4)
    crashes = gpd.GeoDataFrame(
        {
            "merged_id": ["8100077", "CCRS-3000077", "CCRS-9", "CCRS-10"],
            "reporting_agency": ["4316", "4316", "4316", "9340"],
            "collision_date": pd.to_datetime(["2018-10-01"] * 4),
            "collision_time": ["09:10", "09:10", "09:11", "09:14"],
            "PRIMARY_RD": ["MAIN ST", "MAIN ST", "MAIN ST", "MAIN ST"],
            "SECONDARY_RD": ["SECOND AV"] * 4,
            "_priority": [0, 4, 4, 5],
            "_party_signature": [
                "1:F:40,1:M:50,1:M:60",
                "1:F:998,1:M:998,1:M:998",
                "1:M:30,1:M:41",  # chain-reaction crash: different people
                "1:F:40,1:M:50,1:M:60",  # another agency, 2.6 km away
            ],
        },
        geometry=points,
        crs="EPSG:4326",
    )
    pairs = ccrs.duplicate_reports(crashes, CRS)
    assert pairs[["keep", "duplicate"]].values.tolist() == [["8100077", "CCRS-3000077"]]


def test_los_altos_crashes_under_palo_alto_code_are_reassigned_by_city_too():
    crashes = pd.DataFrame(
        {
            "JURIS": ["4312", "4312", "4312"],
            "BEAT_NUMBER": ["2", "2", "LA1"],
            "CITY": ["LOS ALTOS", "PALO ALTO", "PALO ALTO"],
        }
    )
    assert reporting_agency(crashes, RULES).tolist() == ["4305", "4312", "4305"]


def _centerlines():
    from shapely.geometry import LineString

    lines = [
        ("ALMOND AVE", LineString([(0, 0), (450, 0)])),
        ("GORDON WAY", LineString([(200, -300), (200, 300)])),
        # A divided road: two carriageways 20 m apart crossing Almond.
        ("SAN ANTONIO RD", LineString([(390, -300), (390, 300)])),
        ("SAN ANTONIO RD", LineString([(410, -300), (410, 300)])),
        ("PINE LN", LineString([(-50, 50), (450, 50)])),
    ]
    return gpd.GeoDataFrame(
        {
            "STNAME": [name for name, _ in lines],
            "FULLNAME": [name for name, _ in lines],
            "MUNICIPALI": "LOS ALTOS",
        },
        geometry=[line for _, line in lines],
        crs="EPSG:26910",
    )


def test_reported_intersection_and_offset_are_placed_on_centerlines():
    crashes = pd.DataFrame(
        [
            ("ALMOND AV", "N GORDON WY", 0, None),  # at the intersection
            ("ALMOND AV", "GORDON WY", 100, "N"),  # 100 ft north, along Gordon
            ("9999 ALMOND AVE", "GORDON WAY", None, None),  # house number stripped
            ("ALMOND AV", "SAN ANTONIO RD", 0, None),  # divided road: one intersection
            ("ALMOND AV", "GORDON WY", 600, "N"),  # beyond 500 ft: not placed
            ("ALMOND AVE", "9998 ALMOND AVE", None, None),  # same road: not placed
            ("PINE LN", "GORDON WY", 0, "E"),  # direction without distance is fine
            ("GORDON WY", "MERCEDES AV", 0, None),  # unknown road
        ],
        columns=["PRIMARY_RD", "SECONDARY_RD", "DISTANCE", "DIRECTION"],
    ).assign(CITY="LOS ALTOS")
    found = locate_reported_intersections(crashes, _centerlines())
    xy = [(round(p.x), round(p.y)) if p is not None else None for p in found.geometry]
    assert xy[:4] == [(200, 0), (200, 30), (200, 0), (400, 0)]
    assert found.recovery_status.tolist()[3:] == [
        "recovered_divided_road_intersection",
        "reported_offset_too_far",
        "same_normalized_road_name_is_ambiguous",
        "recovered_unique_centerline_intersection",
        "road_name_not_in_retained_centerlines",
    ]
    other_city = locate_reported_intersections(crashes.assign(CITY="SUNNYVALE"), _centerlines())
    assert other_city.geometry.isna().all()


def test_ccrs_secondary_distance_in_miles_becomes_feet():
    raw = pd.DataFrame(
        [
            _raw_crash(1, "A", 1, SecondaryDistance="0.1", SecondaryUnitOfMeasure="M"),
            _raw_crash(2, "B", 1, SecondaryDistance="150", SecondaryUnitOfMeasure="F"),
            _raw_crash(3, "C", 1, SecondaryDistance="0", SecondaryUnitOfMeasure="F"),
        ]
    )
    for column in ccrs_required_columns():
        raw[column] = raw.get(column, pd.Series(pd.NA, index=raw.index))
    kept, _, _ = ccrs.clean_crashes(raw)
    empty = pd.DataFrame(
        columns=["CollisionId", "IsWitnessOnly", "ExtentOfInjuryCode", "PartyType"]
    )
    out = ccrs.ccrs_crash_columns(kept, empty, empty)
    assert out.set_index("ccrs_collision_id").DISTANCE.to_dict() == {1: 528.0, 2: 150.0, 3: 0.0}
    assert out.set_index("ccrs_collision_id").INTERSECTION.to_dict() == {1: "N", 2: "N", 3: "Y"}


def ccrs_required_columns():
    return [
        "Beat",
        "Crash Time Description",
        "SecondaryDirection",
        "Collision Type Code",
        "Primary Collision Factor Code",
        "Primary Collision Factor Violation",
        "LightingCode",
        "MotorVehicleInvolvedWithCode",
        "PedestrianActionCode",
        "RoadwaySurfaceCode",
        "TrafficControlDeviceCode",
        "Weather 1",
        "HitRun",
        "NumberInjured",
        "NumberKilled",
        "Latitude",
        "Longitude",
    ]


def test_posted_speed_limit_is_highest_plausible_driver_value():
    parties = pd.DataFrame(
        {
            "ccrs_collision_id": [1, 1, 1, 2, 3],
            "PARTY_TYPE": ["1", "1", "4", "1", "1"],
            "SPEED_LIMIT": ["25", "35", "45", "0", None],
        }
    )
    assert ccrs.posted_speed_limits(parties).to_dict() == {1: 35.0}


def test_an_offset_with_a_blank_direction_is_placed_at_the_corner_not_to_the_north():
    crashes = pd.DataFrame(
        {
            "PRIMARY_RD": ["ALMOND AV", "ALMOND AV"],
            "SECONDARY_RD": ["GORDON WY", "GORDON WY"],
            "DISTANCE": [100, 0],
            "DIRECTION": [float("nan"), float("nan")],  # how a blank reads from a merged table
            "CITY": "LOS ALTOS",
        }
    )
    found = locate_reported_intersections(crashes, _centerlines())
    assert found.recovery_status.iloc[0] == "recovered_at_intersection_offset_direction_missing"
    assert (round(found.geometry.iloc[0].x), round(found.geometry.iloc[0].y)) == (200, 0)
    assert (round(found.geometry.iloc[1].x), round(found.geometry.iloc[1].y)) == (200, 0)


def test_a_report_deleted_in_its_latest_row_does_not_survive_through_an_older_row():
    raw = pd.DataFrame(
        [
            _raw_crash(1, "CR24-1", 1),  # live in an earlier file
            _raw_crash(1, "CR24-1", 2, IsDeleted="True"),  # deleted later
            _raw_crash(2, "CR24-2", 1),
        ]
    )
    kept, _, stats = ccrs.clean_crashes(raw)
    assert kept.ccrs_collision_id.tolist() == [2]
    assert stats["repeated_collision_ids_dropped"] == 1 and stats["deleted_rows_dropped"] == 1
    # The same when the older, live row has no modified date.
    undated = raw.copy()
    undated.loc[0, "ModifiedDate"] = None
    assert ccrs.clean_crashes(undated)[0].ccrs_collision_id.tolist() == [2]


def test_same_parties_needs_an_unknown_age_for_each_age_left_unpaired():
    assert not ccrs.same_parties("1:M:20,1:M:998", "1:M:80,1:M:90")  # 80 and 90 cannot both fit
    assert ccrs.same_parties("1:M:20,1:M:998", "1:M:21,1:M:90")  # 20~21, 90 takes the unknown
    assert ccrs.same_parties("1:M:20,1:M:50", "1:M:51,1:M:998")
    assert not ccrs.same_parties("1:M:20,1:M:50", "1:M:30,1:M:998")


def test_one_shared_street_does_not_link_reports_far_apart_or_without_times():
    tims = _tims(
        [
            ("8100061", "4316", "2019-05-01", "10:00", "MAIN ST", "OAK AV"),  # far from its match
            ("8100062", "4316", "2019-05-02", "10:00", "MAIN ST", "OAK AV"),  # both streets: linked
            ("8100063", "4316", "2019-05-03", None, "MAIN ST", "OAK AV"),  # no time on either
            ("8100064", "4316", "2019-05-04", "10:00", "MAIN ST", "OAK AV"),  # one street, close
        ]
    ).assign(POINT_X=-122.10, POINT_Y=37.38)
    ccrs_rows = _ccrs(
        [
            (3000061, "4316", "2019-05-01", "10:00", "MAIN ST", "ELM ST"),
            (3000062, "4316", "2019-05-02", "10:00", "MAIN ST", "OAK AV"),
            (3000063, "4316", "2019-05-03", None, "MAIN ST", "ELM ST"),
            (3000064, "4316", "2019-05-04", "10:00", "MAIN ST", "ELM ST"),
        ]
    ).assign(LATITUDE=[37.43, 37.43, float("nan"), 37.3805], LONGITUDE=-122.10)  # 37.43: 5 km north
    links = ccrs.link_tims(
        tims, ccrs_rows, pd.DataFrame(columns=["ccrs_collision_id", "superseded_by"]), CRS
    )
    assert links.set_index("CASE_ID").link_method.to_dict() == {
        "8100061": "unlinked",
        "8100062": "attributes",
        "8100063": "unlinked",
        "8100064": "attributes",
    }


def test_the_merged_table_marks_crashes_put_at_the_corner_for_want_of_a_direction():
    merged = gpd.GeoDataFrame(
        {
            "merged_id": ["no-direction", "north", "at-corner"],
            "source": "tims",
            "injury_crash": True,
            "CITY": "LOS ALTOS",
            "PRIMARY_RD": "ALMOND AV",
            "SECONDARY_RD": "GORDON WY",
            "DISTANCE": [100, 100, 0],
            "DIRECTION": [float("nan"), "N", float("nan")],
            "geometry_source": "",
        },
        geometry=gpd.GeoSeries([None, None, None]),  # type: ignore[arg-type]
        crs=CRS,
    )
    placed, audit = ccrs.place_unlocated(merged, _centerlines(), CRS)
    by_id = placed.set_index("merged_id")
    assert by_id.offset_direction_missing.to_dict() == {
        "no-direction": True,
        "north": False,
        "at-corner": False,
    }
    assert by_id.geometry_is_approximate.all()
    assert by_id.geometry.x["no-direction"] == 200 and by_id.geometry.y["no-direction"] == 0
    assert by_id.reported_offset_m["no-direction"] == 30.5  # how far out it may really be
    assert audit.recovery_status.str.endswith("direction_missing").sum() == 1


def test_a_reused_report_number_is_resolved_within_each_run_of_dates():
    # Two versions of a January 2023 crash, and a later crash under the same number.
    raw = pd.DataFrame(
        [
            _raw_crash(1, "CR-5", 1, when="2023-01-10T08:00:00"),
            _raw_crash(2, "CR-5", 2, when="2023-01-10T08:30:00"),
            _raw_crash(3, "CR-5", 3, when="2024-01-10T08:00:00"),
        ]
    )
    kept, superseded, _ = ccrs.clean_crashes(raw)
    assert sorted(kept.ccrs_collision_id) == [2, 3]
    assert superseded.set_index("ccrs_collision_id").superseded_by.to_dict() == {1: 2}
    assert kept.report_number_conflict.all()
    # Dates 50 days apart in a row do not chain into one run of 100 days.
    spread = pd.DataFrame(
        [
            _raw_crash(1, "CR-6", 1, when="2023-01-01T08:00:00"),
            _raw_crash(2, "CR-6", 2, when="2023-02-20T08:00:00"),
            _raw_crash(3, "CR-6", 3, when="2023-04-10T08:00:00"),
        ]
    )
    kept, superseded, _ = ccrs.clean_crashes(spread)
    assert sorted(kept.ccrs_collision_id) == [2, 3]
    assert superseded.ccrs_collision_id.tolist() == [1]


def test_police_street_abbreviations_match_the_mapped_name():
    assert ccrs._road_key("DE ANZA BL") == ccrs._road_key("De Anza Boulevard")
    assert ccrs._road_key("FOOTHILL EXPR") == ccrs._road_key("Foothill Expressway")


def test_of_two_equal_candidates_the_nearer_report_is_linked():
    tims = _tims([("8100061", "4316", "2019-06-03", "09:00", "MAIN ST", "OAK AV")])
    tims["POINT_X"], tims["POINT_Y"] = -122.05, 37.35
    rows = _ccrs(
        [
            (3000071, "4316", "2019-06-03", "09:00", "MAIN ST", "OAK AV"),  # 5.5 km away
            (3000072, "4316", "2019-06-03", "09:00", "MAIN ST", "OAK AV"),  # at the same place
        ]
    )
    rows["LATITUDE"], rows["LONGITUDE"] = [37.40, 37.35], [-122.05, -122.05]
    links = ccrs.link_tims(
        tims, rows, pd.DataFrame(columns=["ccrs_collision_id", "superseded_by"]), CRS
    )
    assert links.ccrs_collision_id.tolist() == [3000072]
    assert links.metres_apart.iloc[0] < 1


def test_a_corrected_party_row_replaces_the_earlier_one():
    parties = pd.DataFrame(
        {
            "PartyId": ["1", "2", "3", "4"],
            "CollisionId": ["10", "10", "10", "11"],
            "PartyNumber": ["1", "2", "1", "1"],  # party 1 of crash 10 filed again
            "StatedAge": ["17", "40", "19", "30"],
        }
    )
    kept = ccrs.latest_rows(parties, [["PartyId"], ["CollisionId", "PartyNumber"]])
    assert kept.PartyId.tolist() == ["2", "3", "4"] and "17" not in set(kept.StatedAge)
    assert len(ccrs.latest_rows(parties, [["NoSuchColumn"]])) == 4


def test_two_agencies_reports_with_different_road_users_are_not_one_crash():
    points = gpd.points_from_xy([-122.05] * 3, [37.35] * 3)
    crashes = gpd.GeoDataFrame(
        {
            "merged_id": ["CCRS-1", "CCRS-2", "CCRS-3"],
            "reporting_agency": ["4316", "9340", "9340"],
            "collision_date": pd.to_datetime(["2018-10-01"] * 3),
            "collision_time": ["10:00", "10:05", "10:05"],
            "PRIMARY_RD": ["MAIN ST"] * 3,
            "SECONDARY_RD": ["SECOND AV"] * 3,
            "_priority": [4, 5, 5],
            # Two drivers; a driver and a cyclist; an unknown party list.
            "_party_signature": ["1:F:40,1:M:50", "1:F:40,4:M:15", ""],
        },
        geometry=points,
        crs="EPSG:4326",
    )
    pairs = ccrs.duplicate_reports(crashes, CRS)
    assert pairs[["keep", "duplicate"]].values.tolist() == [["CCRS-1", "CCRS-3"]]
    assert ccrs.same_kinds("1:F:40,4:M:15", "4:-:998,1:-:998,3:-:998")
    assert not ccrs.same_kinds("1:F:40,2:M:15", "1:F:40,4:M:15")


def test_cause_categories_are_learned_from_rows_that_have_both_codes():
    crashes = pd.DataFrame(
        {
            "PCF_VIOLATION": ["21453"] * 6 + ["22350"] * 3 + ["21650"] * 6 + ["VC 21453(A)"],
            "PCF_VIOL_CATEGORY": ["12"] * 6 + ["03"] * 3 + ["05"] * 3 + ["08"] * 3 + [None],
        }
    )
    # 22350 has too few rows, 21650 no clear category.
    assert ccrs.cause_categories(crashes) == {"21453": "12"}


NO_SUPERSEDED = pd.DataFrame(columns=["ccrs_collision_id", "superseded_by"])


def test_a_missing_street_name_is_not_a_name_two_reports_share():
    assert ccrs._road_key(float("nan")) == ccrs._road_key(pd.NA) == ccrs._road_key(None) == ""
    tims = _tims([("8100062", "4316", "2019-06-03", "09:00", float("nan"), None)])
    rows = _ccrs([(3000081, "4316", "2019-06-03", "09:00", float("nan"), pd.NA)])
    links = ccrs.link_tims(tims, rows, NO_SUPERSEDED, CRS)
    assert links.link_method.tolist() == ["unlinked"]


def test_timestamps_of_differing_precision_are_all_read():
    raw = pd.DataFrame(
        [
            _raw_crash(1, "CR-1", 1, when="2024-05-01T08:30:00"),
            _raw_crash(1, "CR-1", 2, when="2024-05-01T08:30:00.500", IsDeleted="True"),
            _raw_crash(2, "CR-2", 1, when="2024-05-02T08:30:00.250"),
        ]
    )
    raw.loc[1, "ModifiedDate"] = "2025-01-02T00:00:00.123"
    kept, _, stats = ccrs.clean_crashes(raw)
    # The deleted second version is the latest, so collision 1 is gone.
    assert kept.ccrs_collision_id.tolist() == [2] and kept._crash_dt.notna().all()
    assert stats["crash_dates_not_understood"] == stats["modified_dates_not_understood"] == 0
    raw.loc[2, "Crash Date Time"] = "sometime in May"
    assert ccrs.clean_crashes(raw)[2]["crash_dates_not_understood"] == 1


def test_a_report_at_the_same_place_beats_one_across_town_a_minute_closer():
    tims = _tims([("8100063", "4316", "2019-06-03", "09:00", "MAIN ST", "OAK AV")])
    tims["POINT_X"], tims["POINT_Y"] = -122.05, 37.35
    rows = _ccrs(
        [
            (3000091, "4316", "2019-06-03", "09:00", "MAIN ST", "OAK AV"),  # 5.5 km away
            (3000092, "4316", "2019-06-03", "09:01", "MAIN ST", "OAK AV"),  # at the same place
        ]
    )
    rows["LATITUDE"], rows["LONGITUDE"] = [37.40, 37.35], [-122.05, -122.05]
    assert ccrs.link_tims(tims, rows, NO_SUPERSEDED, CRS).ccrs_collision_id.tolist() == [3000092]
    # With no nearer report, both street names still carry the far one.
    alone = ccrs.link_tims(tims, rows.iloc[:1], NO_SUPERSEDED, CRS)
    assert alone.ccrs_collision_id.tolist() == [3000091]


def test_two_different_tims_crashes_cannot_share_one_best_ccrs_report():
    tims = _tims(
        [
            ("8100064", "4316", "2019-06-03", "09:00", "MAIN ST", "OAK AV"),
            ("8100065", "4316", "2019-06-03", "09:10", "MAIN ST", "OAK AV"),
        ]
    )
    rows = _ccrs(
        [
            (3000101, "4316", "2019-06-03", "09:05", "MAIN ST", "OAK AV"),  # 5 minutes from each
            (3000102, "4316", "2019-06-03", "09:20", "MAIN ST", "OAK AV"),  # a worse candidate
        ]
    )
    for order in ([0, 1], [1, 0]):
        links = ccrs.link_tims(tims.iloc[order].reset_index(drop=True), rows, NO_SUPERSEDED, CRS)
        assert links.link_method.tolist() == ["attributes_ambiguous"] * 2
        assert links.ccrs_collision_id.isna().all()
    # A clearly better claim wins, and the other crash takes what is left.
    tims.loc[0, "collision_time"] = "09:05"
    links = ccrs.link_tims(tims, rows, NO_SUPERSEDED, CRS).set_index("CASE_ID")
    assert links.ccrs_collision_id.to_dict() == {"8100064": 3000101, "8100065": 3000102}


def test_a_person_taken_out_of_a_corrected_report_does_not_survive():
    parties = pd.DataFrame(
        {
            "PartyId": ["1", "2", "3", "4"],
            "CollisionId": ["10", "10", "10", "11"],
            "PartyNumber": ["1", "2", "1", "1"],
            "PartyType": ["Driver", "Bicyclist", "Driver", "Driver"],
            "ccrs_file": ["Parties_2024", "Parties_2024", "Parties_2025", "Parties_2024"],
        }
    )
    chosen = pd.DataFrame(
        {
            "ccrs_collision_id": pd.array([10, 11, 12], dtype="Int64"),
            "ccrs_file": ["Crashes_2025", "Crashes_2024", "Crashes_2025"],
        }
    )
    keys = [["PartyId"], ["CollisionId", "PartyNumber"]]
    kept = ccrs.latest_rows(parties, keys, chosen)
    assert kept.PartyId.tolist() == ["3", "4"] and "Bicyclist" not in set(kept.PartyType)
    # Everyone taken out: the corrected 2025 report of collision 12 lists nobody.
    injured = pd.DataFrame(
        {"InjuredWitPassId": ["7"], "CollisionId": ["12"], "ccrs_file": ["Injured_2024"]}
    )
    assert ccrs.latest_rows(injured, [["InjuredWitPassId"]], chosen).empty


def test_two_agencies_reports_of_different_cyclists_are_not_one_crash():
    assert not ccrs.same_kinds("1:M:40,4:F:16", "1:F:60,4:M:45")  # sex and age both differ
    assert not ccrs.same_kinds("1:M:40,4:-:16", "1:F:60,4:M:45")  # ages 29 years apart
    assert ccrs.same_kinds("1:M:40,4:F:16", "1:F:60,4:-:998")  # nothing recorded to compare
    assert ccrs.same_kinds("1:M:40,4:F:16", "1:M:41,4:F:17")
    # Sex and age are compared person by person, not as two separate lists.
    assert not ccrs.same_kinds("4:F:16,4:M:45", "4:M:16,4:F:45")
    assert ccrs.same_kinds("4:F:16,4:M:45", "4:M:44")


def test_a_report_number_reused_weeks_later_elsewhere_is_another_crash():
    raw = pd.DataFrame(
        [
            _raw_crash(
                1, "1", 1, when="2024-12-20T08:00:00", PrimaryRoad="OAK ST", SecondaryRoad="ELM ST"
            ),
            _raw_crash(
                2,
                "1",
                1,
                when="2025-01-10T17:00:00",
                PrimaryRoad="PINE ST",
                SecondaryRoad="BIRCH ST",
            ),
            # The same report sent again with its date corrected: one street in common.
            _raw_crash(3, "2", 1, when="2024-12-20T08:00:00"),
            _raw_crash(4, "2", 2, when="2024-12-28T08:00:00"),
        ]
    )
    kept, superseded, _ = ccrs.clean_crashes(raw)
    assert sorted(kept.ccrs_collision_id) == [1, 2, 4]
    assert superseded.ccrs_collision_id.tolist() == [3]
    assert kept.set_index("ccrs_collision_id").report_number_conflict.to_dict() == {
        1: True,
        2: True,
        4: False,
    }
    # 47 hours apart is not within a day, whichever version is the later crash.
    apart = pd.DataFrame(
        [
            _raw_crash(
                1, "3", 1, when="2024-05-03T00:00:00", PrimaryRoad="OAK ST", SecondaryRoad="ELM ST"
            ),
            _raw_crash(
                2,
                "3",
                2,
                when="2024-05-01T01:00:00",
                PrimaryRoad="PINE ST",
                SecondaryRoad="BIRCH ST",
            ),
        ]
    )
    assert sorted(ccrs.clean_crashes(apart)[0].ccrs_collision_id) == [1, 2]
    # Two versions each of two crashes under one number: one of each is kept.
    twice = pd.DataFrame(
        [
            _raw_crash(
                1, "4", 1, when="2024-05-01T08:00:00", PrimaryRoad="OAK ST", SecondaryRoad="ELM ST"
            ),
            _raw_crash(
                2, "4", 2, when="2024-05-01T08:00:00", PrimaryRoad="OAK ST", SecondaryRoad="ELM ST"
            ),
            _raw_crash(
                3,
                "4",
                3,
                when="2024-05-20T08:00:00",
                PrimaryRoad="PINE ST",
                SecondaryRoad="BIRCH ST",
            ),
            _raw_crash(
                4,
                "4",
                4,
                when="2024-05-20T08:00:00",
                PrimaryRoad="PINE ST",
                SecondaryRoad="BIRCH ST",
            ),
        ]
    )
    assert sorted(ccrs.clean_crashes(twice)[0].ccrs_collision_id) == [2, 4]
    # A day apart each time and no street in common: the first and third are 48 hours apart.
    chain = pd.DataFrame(
        [
            _raw_crash(n, "5", n, when=f"2024-05-0{n}T08:00:00", PrimaryRoad=a, SecondaryRoad=b)
            for n, (a, b) in enumerate(
                [("OAK ST", "ELM ST"), ("PINE ST", "BIRCH ST"), ("ASH ST", "CEDAR ST")], start=1
            )
        ]
    )
    assert sorted(ccrs.clean_crashes(chain)[0].ccrs_collision_id) == [2, 3]


def test_only_files_in_the_downloads_list_are_read_and_empty_tables_have_columns(tmp_path):
    import json

    from bike_safety_ca import config as settings

    config = settings.load("config/los_altos.yaml")
    (tmp_path / "Crashes_2024.csv").write_text("Collision Id\n1\n")
    (tmp_path / "Crashes_2019.csv").write_text("Collision Id\n2\n")  # left by another download
    (tmp_path / "Parties_2024.csv").write_text("")
    wanted = {"County Code": config.ccrs_county_code, "City Name": list(config.ccrs_cities)}
    manifest = {"filter": wanted, "files": {"Crashes_2024.csv": {}, "Parties_2024.csv": {}}}
    (tmp_path / "ccrs_manifest.json").write_text(json.dumps(manifest))
    listed = ccrs.manifest_files(tmp_path, config)
    assert ccrs._read("Crashes", tmp_path, listed)["Collision Id"].tolist() == ["1"]
    parties = ccrs._read("Parties", tmp_path, listed, ccrs.PARTY_COLUMNS)
    injured = ccrs._read("InjuredWitnessPassengers", tmp_path, listed, ccrs.INJURED_COLUMNS)
    assert parties.empty and injured.empty
    # The steps that read them run on the empty tables.
    assert ccrs.ccrs_party_columns(ccrs.latest_rows(parties, [["PartyId"]]), {}).empty
    assert ccrs.ccrs_victim_columns(injured).empty
    manifest["filter"] = wanted | {"City Name": ["Elsewhere"]}
    (tmp_path / "ccrs_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="not for this config"):
        ccrs.manifest_files(tmp_path, config)


def test_a_ccrs_point_far_from_the_streets_its_report_names_is_replaced():
    from shapely.geometry import Point

    merged = gpd.GeoDataFrame(
        {
            "merged_id": ["far-ccrs", "near-ccrs", "far-tims", "far-unnamed"],
            "source": ["ccrs", "ccrs", "tims", "ccrs"],
            "injury_crash": True,
            "CITY": "LOS ALTOS",
            "PRIMARY_RD": "ALMOND AV",
            "SECONDARY_RD": ["GORDON WY", "GORDON WY", "GORDON WY", "NOWHERE ST"],
            "DISTANCE": 0,
            "DIRECTION": float("nan"),
            "geometry_source": ["ccrs", "ccrs", "tims", "ccrs"],
        },
        # The corner is at (200, 0).
        geometry=[Point(30_000, 0), Point(900, 0), Point(30_000, 0), Point(30_000, 0)],
        crs=CRS,
    )
    placed, audit = ccrs.place_unlocated(merged, _centerlines(), CRS)
    by_id = placed.set_index("merged_id")
    assert by_id.reported_point_replaced.to_dict() == {
        "far-ccrs": True,
        "near-ccrs": False,  # within a kilometre: the reported point stands
        "far-tims": False,  # TIMS points are kept
        "far-unnamed": False,  # no corner to compare with
    }
    assert (by_id.geometry.x["far-ccrs"], by_id.geometry.y["far-ccrs"]) == (200, 0)
    assert by_id.geometry_source["far-ccrs"] == "intersection_centerline"
    assert by_id.geometry.x["near-ccrs"] == 900 and by_id.geometry.x["far-unnamed"] == 30_000
    assert audit.reported_point_doubted.sum() == 2  # one of them could not be placed


def test_a_street_table_and_city_outlines_make_a_centerline_layer():
    from shapely.geometry import LineString, box

    from bike_safety_ca.crashes.locate import streets_as_centerlines

    streets = gpd.GeoDataFrame(
        {"name": ["Oak Street", "Elm Avenue", None, "Far Road"]},
        geometry=[
            LineString([(0, 50), (300, 50)]),  # crosses from Alder into Birch
            LineString([(50, 0), (50, 100)]),
            LineString([(10, 0), (10, 100)]),  # unnamed: left out
            LineString([(900, 0), (900, 100)]),  # in no city
        ],
        crs=CRS,
    )
    places = gpd.GeoDataFrame(
        {"NAME": ["Alder", "Birch"]}, geometry=[box(0, 0, 100, 100), box(200, 0, 400, 100)], crs=CRS
    )
    lines = streets_as_centerlines(streets, places)
    assert sorted(zip(lines.STNAME, lines.MUNICIPALI)) == [
        ("Elm Avenue", "ALDER"),
        ("Far Road", "UNINCORPORATED"),
        ("Oak Street", "ALDER"),
        ("Oak Street", "BIRCH"),
        ("Oak Street", "UNINCORPORATED"),
    ]
    # Each part is cut at the city limit, so a city's streets stay inside it.
    oak = lines[lines.STNAME.eq("Oak Street")].set_index("MUNICIPALI").geometry
    assert oak["ALDER"].bounds == (0, 50, 100, 50) and oak["UNINCORPORATED"].length == 100
    crash = pd.DataFrame(
        {
            "PRIMARY_RD": ["OAK ST"],
            "SECONDARY_RD": ["ELM AV"],
            "CITY": ["ALDER"],
            "DISTANCE": [0],
            "DIRECTION": [float("nan")],
        }
    )
    found = locate_reported_intersections(crash, lines)
    assert (found.geometry.x[0], found.geometry.y[0]) == (50, 50)


def _long_streets():
    from shapely.geometry import LineString

    lines = [
        ("OAK AVE", LineString([(0, 0), (5000, 0)])),
        ("ELM ST", LineString([(0, -50), (0, 5000)])),
    ]
    return gpd.GeoDataFrame(
        {
            "STNAME": [name for name, _ in lines],
            "FULLNAME": [name for name, _ in lines],
            "MUNICIPALI": "UNINCORPORATED",
        },
        geometry=[line for _, line in lines],
        crs=CRS,
    )


def test_a_ccrs_point_on_a_named_street_stands_however_far_from_the_corner_found():
    from shapely.geometry import Point

    # "Oak Street" is matched to Oak Avenue, whose corner with Elm is 2 km from
    # the point; but the point is on Elm, so there is no reason to doubt it.
    merged = gpd.GeoDataFrame(
        {
            "merged_id": ["on-elm", "far-offset"],
            "source": "ccrs",
            "injury_crash": True,
            "CITY": "UNINCORPORATED",
            "PRIMARY_RD": ["OAK ST", "OAK AV"],
            "SECONDARY_RD": "ELM ST",
            "DISTANCE": [0, 600],  # 600 ft is past the first pass's limit
            "DIRECTION": [float("nan"), "E"],
            "geometry_source": "ccrs",
        },
        geometry=[Point(0, 2000), Point(30_000, 30_000)],
        crs=CRS,
    )
    # The report's city is looked up under its alias and, failing that, its own name.
    placed, _ = ccrs.place_unlocated(
        merged, _long_streets(), CRS, {"UNINCORPORATED": "SOME COUNTY"}
    )
    by_id = placed.set_index("merged_id")
    assert by_id.reported_point_replaced.to_dict() == {"on-elm": False, "far-offset": True}
    assert by_id.geometry.y["on-elm"] == 2000
    assert round(by_id.geometry.x["far-offset"], 1) == 182.9 and by_id.geometry.y["far-offset"] == 0


def test_placement_keeps_its_flags_straight_whatever_the_table_index_and_missing_names():
    from shapely.geometry import Point

    merged = gpd.GeoDataFrame(
        {
            "merged_id": ["far", "one-name", "no-name"],
            "source": "ccrs",
            "injury_crash": True,
            "CITY": "LOS ALTOS",
            "PRIMARY_RD": pd.array(["ALMOND AV", "ALMOND AV", pd.NA], dtype="string"),
            "SECONDARY_RD": pd.array(["GORDON WY", pd.NA, pd.NA], dtype="string"),
            "DISTANCE": 0,
            "DIRECTION": float("nan"),
            "geometry_source": "ccrs",
        },
        geometry=[Point(30_000, 0), Point(100, 0), Point(30_000, 0)],
        crs=CRS,
        index=[11, 10, 4],
    )
    placed, audit = ccrs.place_unlocated(merged, _centerlines(), CRS)
    assert placed.set_index("merged_id").reported_point_replaced.to_dict() == {
        "far": True,
        "one-name": False,
        "no-name": False,
    }
    assert audit.set_index("merged_id").reported_point_doubted.to_dict() == {"far": True}


COMPASS_AND_TYPE_NAMES = {
    "South Street": "SOUTH",
    "SOUTH ST": "SOUTH",
    "N Street": "N",
    "E ST": "E",
    "North Avenue": "NORTH",
    "West Lane": "WEST",
    "WEST LN": "WEST",
    "SOUTH BL": "SOUTH",
    "Court Street": "COURT",
    "N Court St": "COURT",
    "West B Street": "B",
    "N Main St": "MAIN",
    "Main Street": "MAIN",
    "St Francis Drive": "SAINT FRANCIS",
    "N ST. FRANCIS DR": "SAINT FRANCIS",
    "Saint Francis Drive": "SAINT FRANCIS",
    "Francis Drive": "FRANCIS",
    # A direction or a type alone, and a direction of travel, are still no name.
    "NORTH": "",
    "ST": "",
    "N/B": "",
    "S B": "",
    "SOUTHBOUND": "",
}


def test_a_street_named_by_a_direction_or_a_type_word_has_one_key_everywhere():
    from bike_safety_ca.crashes import locate
    from bike_safety_ca.network import junctions

    for text, key in COMPASS_AND_TYPE_NAMES.items():
        assert ccrs._road_key(text) == key, text
        assert locate._report_road_name(text) == key, text
        assert junctions.road_key(text) == key, text
    assert locate._report_road_name("ST RT 82") == locate._report_road_name("RT 82")
    assert ccrs._road_key("ST RT 82") == ccrs._road_key("RT 82")


def test_reports_on_a_street_named_by_a_direction_are_linked_and_placed_by_its_name():
    # No time on either report: only both street names can link them.
    tims = _tims([("8100071", "4316", "2019-05-03", None, "SOUTH ST", "OAK AV")])
    rows = _ccrs([(3000071, "4316", "2019-05-03", None, "South Street", "OAK AVE")])
    links = ccrs.link_tims(tims, rows, NO_SUPERSEDED, CRS)
    assert links.link_method.tolist() == ["attributes"]

    from shapely.geometry import LineString

    lines = gpd.GeoDataFrame(
        {"STNAME": ["SOUTH ST", "OAK AVE"], "FULLNAME": ["SOUTH ST", "OAK AVE"]},
        geometry=[LineString([(0, 0), (400, 0)]), LineString([(200, -300), (200, 300)])],
        crs=CRS,
    ).assign(MUNICIPALI="LOS ALTOS")
    crashes = pd.DataFrame(
        [("SOUTH STREET", "OAK AV", 0, None)],
        columns=["PRIMARY_RD", "SECONDARY_RD", "DISTANCE", "DIRECTION"],
    ).assign(CITY="LOS ALTOS")
    found = locate_reported_intersections(crashes, lines)
    assert found.recovery_status.tolist() == ["recovered_unique_centerline_intersection"]
    assert (round(found.geometry[0].x), round(found.geometry[0].y)) == (200, 0)


@pytest.mark.parametrize(("x", "y"), [(0.0, 0.0), (0.0, 37.39), (-122.03, 0.0)])
def test_a_tims_point_of_zero_is_no_point_when_linking(x, y):
    # TIMS writes 0 for a crash SafeTREC could not geocode: one shared street must still link.
    tims = _tims([("7100001", "4316", "2019-03-04", "18:30", "FIG ST", "PLUM ST")])
    tims["POINT_X"], tims["POINT_Y"] = x, y
    reports = _ccrs([(3000016, "4316", "2019-03-04", "18:40", "FIG ST", "")])
    reports["LATITUDE"], reports["LONGITUDE"] = 37.39, -122.03
    links = ccrs.link_tims(
        tims, reports, pd.DataFrame(columns=["ccrs_collision_id", "superseded_by"]), CRS
    )
    assert links.link_method.tolist() == ["attributes"]
    assert links.ccrs_collision_id.tolist() == [3000016]
    assert links.metres_apart.isna().all()


def test_a_report_refused_for_its_date_is_named_in_the_links():
    tims = _tims(
        [
            ("81000011", "4316", "2024-01-08", "15:40", "FIRST AV", "OAK AV"),
            ("81000099", "4316", "2024-02-01", "10:00", "MARY AV", "EVELYN AV"),
            ("81000077", "4316", "2024-02-01", "11:00", "FIG ST", "PLUM ST"),
            # An id used again for another crash: other streets, kilometres away.
            ("81000055", "4316", "2024-02-01", "12:00", "QUINCE ST", "DATE ST"),
            ("81000056", "4316", "2024-02-01", "12:00", "QUINCE ST", "DATE ST"),  # one shared name
            ("81000057", "4316", "2024-02-01", "12:00", "QUINCE ST", "DATE ST"),  # near, no names
            ("81000058", "4316", "2024-02-01", "12:00", "QUINCE ST", "DATE ST"),  # nothing known
            # One shared name counts only with points that put the two within the limit.
            ("81000059", "4316", "2024-02-01", "12:00", "QUINCE ST", "DATE ST"),  # no TIMS point
            ("81000060", "4316", "2024-02-01", "12:00", "QUINCE ST", "DATE ST"),  # 500 m apart
        ]
    )
    tims.loc[3:5, "POINT_X"], tims.loc[3:5, "POINT_Y"] = -122.03, 37.39
    tims.loc[8, "POINT_X"], tims.loc[8, "POINT_Y"] = -122.03, 37.39
    reports = _ccrs(
        [
            (1000011, "4316", "2024-01-08", "15:40", "FIRST AV", "OAK AV"),
            (1000099, "4316", "2024-03-15", "10:00", "MARY AV", "EVELYN AV"),
            (1000078, "4316", "2024-04-20", "11:00", "FIG ST", "PLUM ST"),
            (1000055, "4316", "2024-03-15", "12:00", "GUAVA ST", "LIME ST"),
            (1000056, "4316", "2024-03-15", "12:00", "QUINCE ST", "LIME ST"),
            (1000057, "4316", "2024-03-15", "12:00", "", ""),
            (1000058, "4316", "2024-03-15", "12:00", "", ""),
            (1000059, "4316", "2024-03-15", "12:00", "QUINCE ST", "LIME ST"),
            (1000060, "4316", "2024-03-15", "12:00", "QUINCE ST", "LIME ST"),
        ]
    )
    reports["LATITUDE"] = [None, None, None, 37.45, 37.45, 37.3901, None, 37.39, 37.3945]
    reports["LONGITUDE"] = [None, None, None, *[-122.03] * 3, None, -122.03, -122.03]
    # Report 1000077 was filed again as 1000078.
    superseded = pd.DataFrame({"ccrs_collision_id": [1000077], "superseded_by": [1000078]})
    links = ccrs.link_tims(tims, reports, superseded, CRS).set_index("CASE_ID")
    assert links.link_method.tolist() == ["case_id"] + ["case_id_date_mismatch"] * 8
    assert links.ccrs_collision_id.fillna(0).tolist() == [1000011, *[0] * 8]
    assert links.date_mismatch_ccrs_id.fillna(0).tolist()[:3] == [0, 1000099, 1000078]
    # The id alone does not make the report the same crash: a street name or the points must agree.
    assert links.date_mismatch_corroborated.to_dict() == {
        "81000011": False,
        "81000099": True,
        "81000077": True,
        "81000055": False,
        "81000056": False,
        "81000057": True,
        "81000058": False,
        "81000059": False,
        "81000060": True,
    }


def _severities(rows, injured):
    raw = pd.DataFrame(rows)
    for column in [*ccrs_required_columns(), "SecondaryDistance", "SecondaryUnitOfMeasure"]:
        raw[column] = raw.get(column, pd.Series(pd.NA, index=raw.index))
    kept, _, _ = ccrs.clean_crashes(raw)
    people = pd.DataFrame(
        injured, columns=["CollisionId", "IsWitnessOnly", "ExtentOfInjuryCode"]
    ).assign(PartyType=None)
    return ccrs.ccrs_crash_columns(kept, people, people).set_index("ccrs_collision_id")


def test_an_injury_crash_with_no_usable_injured_row_has_no_severity_rather_than_none():
    out = _severities(
        [
            _raw_crash(1, "A", 1, NumberInjured="1"),  # no injured row at all
            _raw_crash(2, "B", 1, NumberInjured="1"),  # an injury label not in the table
            _raw_crash(3, "C", 1, NumberInjured="1"),  # only a witness
            _raw_crash(4, "D", 1, NumberInjured="1"),
            _raw_crash(5, "E", 1, NumberInjured="0"),
            _raw_crash(6, "F", 1, NumberKilled="1"),
        ],
        [
            ("2", "False", "SomeNewLabel"),
            ("3", "True", "SuspectMinor"),
            ("4", "False", "PossibleInjury"),
        ],
    )
    assert out.injury_crash.to_dict() == {1: True, 2: True, 3: True, 4: True, 5: False, 6: True}
    assert out.COLLISION_SEVERITY.isna().to_dict() == {
        1: True,
        2: True,
        3: True,
        4: False,
        5: False,
        6: False,
    }
    assert out.COLLISION_SEVERITY.dropna().to_dict() == {4: "4", 5: "0", 6: "1"}


def test_a_ccrs_folder_with_no_list_of_files_or_an_unfinished_one_is_warned_about(tmp_path, caplog):
    import json

    with caplog.at_level("WARNING"):
        assert ccrs.manifest_files(tmp_path) is None
    assert "no ccrs_manifest.json" in caplog.text and "not checked" in caplog.text
    caplog.clear()
    manifest = {"filter": {}, "files": {"Crashes_2024.csv": {}}, "complete": False}
    (tmp_path / "ccrs_manifest.json").write_text(json.dumps(manifest))
    with caplog.at_level("WARNING"):
        assert ccrs.manifest_files(tmp_path) == {"Crashes_2024.csv"}
    assert "did not finish" in caplog.text
    caplog.clear()
    # A list written before downloads recorded this is taken as finished.
    del manifest["complete"]
    (tmp_path / "ccrs_manifest.json").write_text(json.dumps(manifest))
    with caplog.at_level("WARNING"):
        assert ccrs.manifest_files(tmp_path) == {"Crashes_2024.csv"}
    assert not caplog.text


def test_a_centerline_file_that_does_not_exist_is_an_error(tmp_path):
    from bike_safety_ca import config as settings

    config = settings.load("config/los_altos.yaml")
    with pytest.raises(FileNotFoundError, match="nowhere.parquet"):
        ccrs.build(tmp_path, tmp_path, config, centerlines=tmp_path / "nowhere.parquet")
