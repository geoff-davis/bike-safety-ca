"""The crash pipeline must ingest TIMS exports dropped into data/raw/crashes/tims/<batch>/ unchanged."""

import geopandas as gpd
import pandas as pd
import pytest

from bike_safety_ca.config import Reassignment
from bike_safety_ca.crashes import tims as crashes

RULES = (Reassignment(filed_as="4312", agency="4305", beat_prefix="LA", city="Los Altos"),)


def test_crash_pipeline_on_synthetic_export(tmp_path):
    batch = tmp_path / "tims" / "2014-2023_final"
    batch.mkdir(parents=True)
    pd.DataFrame(
        {
            "CASE_ID": ["1", "2", "3"],
            "COLLISION_DATE": ["2019-05-01", "2020-06-02", "2021-07-03"],
            "COLLISION_SEVERITY": ["4", "2", "1"],
            "PEDESTRIAN_ACCIDENT": ["Y", "", ""],
            "BICYCLE_ACCIDENT": ["", "Y", "Y"],
            "COLLISION_TIME": ["849 ", "1535", "2500"],
            "POINT_X": [-122.1, -122.11, ""],
            "POINT_Y": [37.38, 37.37, ""],
            "PRIMARY_COLL_FACTOR": ["A", "B", "C"],
        }
    ).to_csv(batch / "Crashes.csv", index=False)
    pd.DataFrame(
        {
            "CASE_ID": ["1", "1", "2"],
            "PARTY_NUMBER": [1, 2, 1],
            "PARTY_TYPE": ["1", "2", "4"],
            "STWD_VEHICLE_TYPE": ["A", "N", "L"],
            "CHP_VEH_TYPE_TOWING": ["01", "", "04"],
            "VEHICLE_MAKE": ["TOYT", "", "SUPER 73"],
        }
    ).to_csv(batch / "Parties.csv", index=False)
    pd.DataFrame({"CASE_ID": ["1", "2"], "VICTIM_DEGREE_OF_INJURY": ["2", "3"]}).to_csv(
        batch / "Victims.csv", index=False
    )
    prov = tmp_path / "tims" / "2024-2025_provisional"
    prov.mkdir()
    pd.DataFrame(
        {
            "CASE_ID": ["3", "4"],
            "COLLISION_DATE": ["2021-07-03", "2024-01-09"],
            "COLLISION_SEVERITY": ["1", "3"],
            "PEDESTRIAN_ACCIDENT": ["", "Y"],
            "BICYCLE_ACCIDENT": ["Y", ""],
            "POINT_X": [-122.1, -122.09],
            "POINT_Y": [37.38, 37.39],
        }
    ).to_csv(prov / "Crashes.csv", index=False)
    out = tmp_path / "processed" / "crashes"
    assert crashes.build(tmp_path / "tims", out, "EPSG:26910", RULES)
    g = gpd.read_parquet(out / "crashes_4326.parquet")
    assert len(g) == 4  # case 3 deduplicated (later batch wins)
    assert g[g.CASE_ID == "3"].provisional_batch.iloc[0]
    assert g.geocoded_by_safetrec.sum() == 4
    assert g.ped_involved.sum() == 2 and g.bike_involved.sum() == 2
    assert "PRIMARY_COLL_FACTOR" in g.columns
    assert (out / "parties.parquet").exists() and (out / "victims.parquet").exists()
    by_case = g.set_index("CASE_ID")
    assert by_case.loc["1", "collision_time"] == "08:49"
    assert by_case.loc["2", "collision_hour"] == 15
    assert by_case.ebike_involved.to_dict() == {"1": False, "2": True, "3": False, "4": False}
    assert not g.agency_reporting_gap.any() and not g.agency_has_reporting_gap.any()
    assert (out / "crashes_agency_reporting.csv").exists()
    bikes = pd.read_parquet(out / "bicycle_parties.parquet")
    assert bikes.CASE_ID.tolist() == ["2"] and bikes.ebike_tier.tolist() == ["ebike"]


def _agency_years(counts: dict[str, list[int]], start: int = 2016) -> pd.DataFrame:
    rows = [
        {"CASE_ID": f"{agency}-{start + i}-{n}", "JURIS": agency, "year": start + i}
        for agency, per_year in counts.items()
        for i, total in enumerate(per_year)
        for n in range(total)
    ]
    return pd.DataFrame(rows)


def test_agency_reporting_gap_flags_a_collapse_but_not_a_regional_dip():
    c = _agency_years(
        {
            "A": [100, 100, 100, 50, 100, 5, 0],  # region-wide dip in 2019, then stops reporting
            "B": [200, 200, 200, 100, 200, 200, 200],
            "C": [10, 10, 10, 10, 10, 0, 10],  # too small to judge
        }
    )
    gaps = crashes.agency_reporting_gaps(c).set_index(["reporting_agency", "year"])
    flagged = set(gaps.index[gaps.reporting_gap])
    assert flagged == {("A", 2021), ("A", 2022)}
    # The region-wide dip of 2019: A's own ratio is 0.5, excused by B's 0.5 as far as 0.6.
    assert gaps.loc[("A", 2019), "agency_ratio"] == 0.5
    assert gaps.loc[("A", 2019), "relative_ratio"] == pytest.approx(0.833)
    assert gaps.loc[("A", 2019), "change"] == ""
    # Every year is judged, the first ones too, each against the agency's typical year.
    assert set(gaps.loc["A"].index) == set(range(2016, 2023))
    assert gaps.loc[("A", 2021), "change"] == "fall" and gaps.change.isin(["", "fall"]).all()
    assert gaps.loc["C"].change.eq("").all()


def _changes(counts: dict[str, list[int]], **options: object) -> dict[tuple[str, int], str]:
    """The marked agency-years of made-up yearly counts starting in 2016."""
    gaps = crashes.agency_reporting_gaps(_agency_years(counts), **options)  # type: ignore[arg-type]
    marked = gaps[gaps.change.ne("")]
    return dict(zip(zip(marked.reporting_agency, marked.year), marked.change))


def test_one_agencys_gap_and_recovery_is_never_marked_against_a_steady_neighbour():
    # A stops for four years and comes back; B is steady throughout.
    found = _changes(
        {
            "A": [800, 150, 50, 20, 200, 850, 1000, 1200, 1100],
            "B": [470, 550, 590, 570, 570, 390, 470, 450, 430],
        }
    )
    # The whole gap is marked, its first years too, and the baseline is not dragged down by it.
    assert found == {("A", year): "fall" for year in (2017, 2018, 2019, 2020)}


def test_a_gap_in_the_first_years_is_seen():
    found = _changes(
        {"A": [5, 12, 250, 280, 240, 230, 250], "B": [170, 160, 180, 175, 200, 170, 180]}
    )
    assert found == {("A", 2016): "fall", ("A", 2017): "fall"}


def test_a_rise_is_marked_as_well_as_a_fall():
    found = _changes({"A": [15, 20, 10, 25, 30, 22, 45, 70, 80, 85], "B": [60] * 10})
    assert found == {
        ("A", 2022): "possible rise",
        ("A", 2023): "rise",
        ("A", 2024): "rise",
        ("A", 2025): "rise",
    }


def test_a_halving_is_worth_a_look_and_a_smaller_move_is_not():
    steady = [50] * 8
    # 130 against a typical 245 is 0.53: under the 0.6 line, over the 0.4 one.
    assert _changes({"A": [260, 290, 250, 240, 240, 240, 245, 130], "B": steady}) == {
        ("A", 2023): "possible fall"
    }
    # Reports that seem to move from one agency's code to the other's: 0.67 and 1.5, neither marked.
    assert (
        _changes(
            {
                "A": [210, 215, 250, 235, 230, 210, 155, 142],
                "B": [150, 155, 160, 150, 155, 150, 155, 233],
            }
        )
        == {}
    )
    # The lines can be moved.
    looser = {"A": [260, 290, 250, 240, 240, 240, 245, 130], "B": steady}
    assert _changes(looser, look_ratio=0.5) == {}
    assert _changes(looser, min_relative_ratio=0.55) == {("A", 2023): "fall"}


def test_the_other_agencies_excuse_a_shared_dip_but_not_a_shared_collapse():
    dip = _changes({"A": [100, 100, 100, 55, 100, 100], "B": [200, 200, 200, 110, 200, 200]})
    assert dip == {}
    # One agency dipping alone has no excuse.
    assert _changes({"A": [100, 100, 100, 55, 100, 100], "B": [200] * 6}) == {
        ("A", 2019): "possible fall"
    }
    # Both stop together, as when two departments change records system at once.
    both = _changes({"A": [100, 100, 100, 100, 10, 5], "B": [200, 200, 200, 200, 30, 20]})
    assert both == {(agency, year): "fall" for agency in "AB" for year in (2020, 2021)}
    # A third agency that collapses does not excuse the others' dip or mark them.
    three = _changes(
        {
            "A": [100, 100, 100, 100, 100, 100],
            "B": [200, 200, 200, 200, 200, 200],
            "C": [300, 300, 300, 300, 20, 10],
        }
    )
    assert three == {("C", 2020): "fall", ("C", 2021): "fall"}


def test_a_small_count_that_chance_could_give_is_not_marked():
    # 11 against a typical 20 is 0.55, but a Poisson count of 20 falls that low one time in 50.
    assert _changes({"A": [20, 21, 19, 20, 22, 11, 20]}) == {}
    assert _changes({"A": [200, 210, 190, 200, 220, 110, 200]}) == {("A", 2021): "possible fall"}
    assert _changes({"A": [20, 21, 19, 20, 22, 11, 20]}, chance=0.05) == {
        ("A", 2021): "possible fall"
    }
    # And an agency below the baseline floor is not judged at all.
    assert _changes({"A": [10, 10, 10, 10, 0, 10]}) == {}
    assert _changes({"A": [10, 10, 10, 10, 0, 10]}, min_baseline=8) == {("A", 2020): "fall"}


def test_a_rise_is_not_marked_in_an_unfinished_last_year():
    c = _agency_years({"A": [50, 50, 50, 50, 50, 40]})
    c["collision_date"] = pd.to_datetime(c.year.astype(str) + "-02-01")  # 2021 runs to 1 February
    gaps = crashes.agency_reporting_gaps(c).set_index("year")
    # 40 by 1 February against 50 a year: nine times the expected 4.4, and still not marked.
    assert gaps.agency_ratio[2021] > 9 and gaps.change[2021] == ""
    assert (
        crashes.agency_reporting_gaps(c, records_to=pd.Timestamp("2021-12-31")).change.eq("").all()
    )  # a whole year of 40 is in line
    c.loc[c.year.eq(2021), "collision_date"] = pd.Timestamp("2021-12-20")
    more = pd.concat([c, c[c.year.eq(2021)], c[c.year.eq(2021)], c[c.year.eq(2021)]])
    assert crashes.agency_reporting_gaps(more).set_index("year").change[2021] == "rise"


def test_records_ending_early_in_december_are_an_unfinished_year():
    c = _agency_years({"A": [100, 100, 100, 100, 100, 300]})
    c["collision_date"] = pd.to_datetime(c.year.astype(str) + "-12-01")
    gaps = crashes.agency_reporting_gaps(c).set_index("year")
    # To 1 December: scaled, left out of the typical year, and a rise is not marked.
    assert gaps.expected[2021] == pytest.approx(100 * 335 / 365, abs=0.1)
    assert gaps.baseline[2021] == 100 and gaps.change[2021] == ""
    assert "year judged to 1 Dec 2021" in gaps.basis[2021]
    # To 20 December the year is taken as whole.
    whole = crashes.agency_reporting_gaps(c, records_to=pd.Timestamp("2021-12-20")).set_index(
        "year"
    )
    assert whole.expected[2021] == 100 and whole.change[2021] == "rise"


def test_a_single_unfinished_year_has_no_baseline_and_no_mark():
    c = _agency_years({"A": [100]}, start=2021)
    c["collision_date"] = pd.Timestamp("2021-06-30")
    gaps = crashes.agency_reporting_gaps(c)
    assert (
        gaps.baseline.isna().all() and gaps.agency_ratio.isna().all() and gaps.change.eq("").all()
    )
    # A single whole year is its own typical year: in line by construction.
    whole = crashes.agency_reporting_gaps(c, records_to=pd.Timestamp("2021-12-31"))
    assert whole.agency_ratio.tolist() == [1.0] and whole.change.eq("").all()


def test_the_region_ratio_is_reported_as_measured_and_applied_within_limits():
    c = _agency_years({"A": [100, 100, 100, 100, 10], "B": [200, 200, 200, 200, 20]})
    gaps = crashes.agency_reporting_gaps(c)
    row = gaps[gaps.reporting_agency.eq("A") & gaps.year.eq(2020)].iloc[0].to_dict()
    assert (row["agency_ratio"], row["region_ratio"]) == (0.1, 0.1)
    assert row["relative_ratio"] == pytest.approx(0.1 / 0.6, abs=0.001) and row["change"] == "fall"
    # A shared fall to 0.39 is excused as far as 0.6: 0.39 / 0.6 is in line.
    shared = _changes({"A": [1000, 1000, 1000, 1000, 390], "B": [1000, 1000, 1000, 1000, 390]})
    assert shared == {}
    assert _changes({"A": [1000, 1000, 1000, 1000, 350], "B": [1000, 1000, 1000, 1000, 350]}) == {
        ("A", 2020): "possible fall",
        ("B", 2020): "possible fall",
    }


def test_the_typical_year_leaves_out_years_far_from_it():
    assert crashes.typical_year(pd.Series([100, 100, 100, 100]), 0.6) == 100
    # A plain median of these is 150; without the four gap years it is 1000.
    assert (
        crashes.typical_year(pd.Series([800, 150, 50, 20, 200, 850, 1000, 1200, 1100]), 0.6) == 1000
    )
    assert crashes.typical_year(pd.Series([0, 0, 0]), 0.6) == 0
    # Two levels and no middle: with under three years left in, every year counts.
    assert crashes.typical_year(pd.Series([10, 10, 100, 100]), 0.6) == 55


def test_los_altos_reports_under_palo_alto_code_are_reassigned():
    c = pd.DataFrame(
        {
            "JURIS": ["4312", "4312", "4305", "4311"],
            "BEAT_NUMBER": ["LA1", "PA2", "LA2", "LA1"],
        }
    )
    assert crashes.reporting_agency(c, RULES).tolist() == ["4305", "4312", "4305", "4311"]
    assert crashes.reporting_agency(c).tolist() == ["4312", "4312", "4305", "4311"]


def test_an_agency_with_no_neighbour_is_judged_on_its_own_history():
    c = _agency_years({"A": [100, 100, 100, 100, 30, 100, 20]})
    c["collision_date"] = pd.to_datetime(c.year.astype(str) + "-03-01")
    c.loc[c.year == 2022, "collision_date"] = pd.Timestamp("2022-03-14")  # 2022 runs to mid-March
    gaps = crashes.agency_reporting_gaps(c).set_index("year")
    # 2022 is judged against the part of the year up to the last crash: 20 by
    # 14 March is what 100 a year gives.  The basis says which date was used.
    assert gaps.index[gaps.reporting_gap].tolist() == [2020]
    assert gaps.expected[2022] == pytest.approx(20.0) and gaps.agency_ratio[2022] == 1.0
    assert gaps.basis[2022] == "own history only; year judged to 14 Mar 2022, the last crash date"
    assert gaps.basis[2021] == "own history only"
    # Told that the records run to the end of November, the same 20 is a fall.
    later = crashes.agency_reporting_gaps(c, records_to=pd.Timestamp("2022-11-30"))
    assert later.set_index("year").change[2022] == "fall"
    # And with the year finished it is judged whole.
    whole = crashes.agency_reporting_gaps(c, records_to=pd.Timestamp("2022-12-31"))
    assert whole.set_index("year").relative_ratio[2022] == pytest.approx(0.2)


def test_parties_come_from_the_crash_rows_own_export_when_it_supplies_a_party_table():
    older = pd.DataFrame({"CASE_ID": ["1", "1", "2"], "PARTY_NUMBER": ["1", "2", "1"]})
    newer = pd.DataFrame({"CASE_ID": ["1"], "PARTY_NUMBER": ["1"]})  # party 2 was removed
    frames = [older.assign(tims_batch="a"), newer.assign(tims_batch="b")]
    winning = pd.Series({"1": "b", "2": "a", "3": "c"})
    kept = crashes._latest_batch(frames, ["CASE_ID", "PARTY_NUMBER"], winning)
    assert sorted(zip(kept.CASE_ID, kept.PARTY_NUMBER, kept.tims_batch)) == [
        ("1", "1", "b"),
        ("2", "1", "a"),
    ]
    assert len(crashes._latest_batch(frames, ["CASE_ID", "PARTY_NUMBER"])) == 3  # the old rule
    # A winning batch that came without a party file leaves the older parties in place.
    lone = crashes._latest_batch(frames[:1], ["CASE_ID", "PARTY_NUMBER"], winning)
    assert len(lone) == 3
    # A winning batch whose party file has a header and no rows does remove them.
    empty = newer.iloc[:0].assign(tims_batch="b")
    empty.attrs["tims_batch"] = "b"
    cleared = crashes._latest_batch([frames[0], empty], ["CASE_ID", "PARTY_NUMBER"], winning)
    assert sorted(cleared.CASE_ID) == ["2"]


def test_a_reassignment_can_start_in_a_given_year():
    rows = pd.DataFrame(
        {"JURIS": ["4312"] * 3, "BEAT_NUMBER": ["LA1"] * 3, "year": [2022, 2023, None]}
    )
    rule = Reassignment(filed_as="4312", agency="4305", beat_prefix="LA", from_year=2023)
    assert crashes.reporting_agency(rows, [rule]).tolist() == ["4312", "4305", "4312"]
    every_year = Reassignment(filed_as="4312", agency="4305", beat_prefix="LA")
    assert crashes.reporting_agency(rows, [every_year]).tolist() == ["4305"] * 3


def test_a_batch_whose_dates_are_not_understood_stops_the_build(tmp_path):
    columns = {"COLLISION_SEVERITY": "4", "PEDESTRIAN_ACCIDENT": "", "BICYCLE_ACCIDENT": ""}
    first = tmp_path / "tims" / "2020-2023_final"
    first.mkdir(parents=True)
    pd.DataFrame(
        {"CASE_ID": ["1", "2"], "COLLISION_DATE": ["2021-05-01", "2022-06-02"]} | columns
    ).to_csv(first / "Crashes.csv", index=False)
    saved_again = tmp_path / "tims" / "2024_resaved"
    saved_again.mkdir()
    pd.DataFrame(
        # As a spreadsheet writes dates when the export is opened and saved; one left blank.
        {"CASE_ID": ["3", "4", "5"], "COLLISION_DATE": ["3/8/2024", "10/5/2024", ""]} | columns
    ).to_csv(saved_again / "Crashes.csv", index=False)
    out = tmp_path / "processed"
    with pytest.raises(ValueError, match=r"2024_resaved.Crashes\.csv: 2 of 3 .*3/8/2024"):
        crashes.build(tmp_path / "tims", out, "EPSG:26910")
    assert not list(out.glob("crashes*"))
