from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from bike_safety_ca.checks import reporting

YEARS = range(2014, 2024)


def _crashes() -> pd.DataFrame:
    """Made-up reports: agency A is steady, B stops reporting in 2022, every agency dips in 2020."""
    rows = []
    for year in YEARS:
        dip = 0.5 if year == 2020 else 1.0
        counts = {"A": int(60 * dip), "B": int(40 * dip) if year < 2022 else 3, "C": 2}
        for agency, count in counts.items():
            for i in range(count):
                rows.append(
                    {
                        "merged_id": f"{agency}{year}{i}",
                        # Made-up case numbers: agency A files in the new format from 2022.
                        "CASE_ID": f"8{i:07d}" if (agency == "A" and year >= 2022) else f"9{i:06d}",
                        "COLLISION_SEVERITY": "4" if (i % 2 and year < 2021) else "3",
                        "year": year,
                        "collision_date": f"{year}-{'06' if year < 2023 else '09'}-15",
                        "reporting_agency": agency,
                        "CITY": {"A": "ALDER", "B": "BIRCH", "C": "CEDAR"}[agency],
                        "source": "ccrs" if (year == 2023 and i % 2) else "tims",
                        "injury_crash": True,
                        "bike_involved": i % 4 == 0,
                        "possible_duplicate_of": None,
                    }
                )
    return pd.DataFrame(rows)


def test_a_department_that_stops_reporting_is_flagged_and_a_shared_dip_is_not() -> None:
    found = reporting.diagnose(_crashes())
    flagged = found["injury_crashes_flags"]
    assert set(zip(flagged.reporting_agency, flagged.year, strict=True)) == {
        ("B", 2022),
        ("B", 2023),
    }
    assert found["injury_crashes"].loc["A", 2020] == 30
    bikes = found["cyclist_injury_crashes_flags"]
    assert set(bikes.reporting_agency) == {"B"} and 2020 not in set(bikes.year)


def test_ccrs_only_share_and_labels() -> None:
    crashes = _crashes()
    share = reporting.ccrs_only_share(crashes)
    assert share.loc["A", 2023] == 0.5 and share.loc["A", 2019] == 0
    assert share.loc["C"].isna().all()  # too few crashes for a share
    assert reporting.agency_names(crashes)["B"] == "B · mostly Birch"
    assert reporting.last_year_ends(crashes) == "2023 runs to 15 Sep"
    assert list(reporting.busiest(reporting.yearly(crashes))) == ["A", "B"]
    assert reporting._spans(pd.Series([2022, 2023, 2024, 2026])) == "2022–2024, 2026"


def test_tables_and_pictures_are_written(tmp_path: Path) -> None:
    written = reporting.write(_crashes(), tmp_path)
    assert {p.name for p in written} >= {
        "injury_crashes.csv",
        "injury_crashes_flags.csv",
        "injury_crashes.png",
        "cyclist_injury_crashes.png",
        "ccrs_only_share.png",
        "reports_by_format.png",
        "injury_crashes_by_severity.png",
    }
    assert all(p.stat().st_size > 0 for p in written)


def test_format_and_severity_tables() -> None:
    crashes = _crashes()
    kinds = reporting.report_format(crashes).value_counts()
    assert kinds[reporting.CCRS_ALONE] == int(crashes.source.eq("ccrs").sum())
    formats = reporting.by_format(crashes)
    a: dict[str, dict[str, int]] = {}
    for key, row in formats.to_dict("index").items():
        if isinstance(key, tuple) and key[0] == "A":
            a[str(key[1])] = {str(k): int(v) for k, v in row.items()}
    assert next(iter(a)) == "2020Q2"  # two years before the first new-format report
    none = {reporting.UNRECOGNISED: 0}
    assert a["2021Q2"] == {
        reporting.EARLIER: 60,
        reporting.CCRS_FORMAT: 0,
        reporting.CCRS_ALONE: 0,
        **none,
    }
    assert a["2022Q2"] == {
        reporting.EARLIER: 0,
        reporting.CCRS_FORMAT: 60,
        reporting.CCRS_ALONE: 0,
        **none,
    }
    assert a["2023Q3"] == {
        reporting.EARLIER: 0,
        reporting.CCRS_FORMAT: 30,
        reporting.CCRS_ALONE: 30,
        **none,
    }
    severity = reporting.by_severity(crashes).to_dict("index")
    assert severity[("A", 2019)] == {
        "Complaint of pain": 30, "Visible injury": 30, "Serious injury": 0, "Fatal": 0,
    }  # fmt: skip
    assert severity[("A", 2022)]["Visible injury"] == 60  # regraded, same total
    assert reporting.by_format(crashes.assign(source="ccrs")).empty


def test_empty_kinds_of_crash_and_small_agencies_do_not_stop_the_check(tmp_path: Path) -> None:
    crashes = _crashes()
    none_on_bikes = crashes.assign(bike_involved=False)
    found = reporting.diagnose(none_on_bikes)
    assert (found["cyclist_injury_crashes"] == 0).all().all()
    assert found["cyclist_injury_crashes"].shape == found["injury_crashes"].shape
    assert len(found["cyclist_injury_crashes_flags"]) == 0
    reporting.diagnose(crashes.assign(source="tims"))  # nothing found only in CCRS
    small = crashes[crashes.reporting_agency.eq("C")]  # two crashes a year: below the chart rule
    written = reporting.write(small, tmp_path)
    assert all(path.stat().st_size > 0 for path in written)
    assert {p.name for p in written} >= {"injury_crashes.png", "cyclist_injury_crashes.png"}


def test_certain_changes_get_a_solid_ring_and_possible_ones_a_dotted_one() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    marked = pd.DataFrame(
        {
            "year": [2019, 2021, 2022, 2023],
            "crashes": [30, 5, 200, 150],
            "change": ["possible fall", "fall", "rise", "possible rise"],
        }
    )
    figure, axis = plt.subplots()
    reporting.ring(axis, marked)
    solid, dotted = axis.collections
    assert np.asarray(solid.get_offsets()).tolist() == [[2021, 5], [2022, 200]]
    assert np.asarray(dotted.get_offsets()).tolist() == [[2019, 30], [2023, 150]]
    assert list(solid.get_linestyle()) == [(0.0, None)]  # an unbroken line
    assert list(dotted.get_linestyle()) != list(solid.get_linestyle())
    reporting.ring(axis, marked.iloc[0:0])  # nothing flagged: nothing drawn
    assert len(axis.collections) == 2
    plt.close(figure)


def test_cyclist_years_are_judged_over_the_whole_records_span_and_to_their_last_date() -> None:
    crashes = _crashes()
    last = crashes.year.eq(YEARS[-1])
    # No cyclist crash at all in the last year, for any agency: the year is still judged.
    none = reporting.diagnose(crashes[~(crashes.bike_involved & last)])[
        "cyclist_injury_crashes_flags"
    ]
    assert ("A", YEARS[-1], "fall") in set(zip(none.reporting_agency, none.year, none.change))
    # One cyclist crash for A, in January, in records that run to September:
    # judged against the months the records cover, not against the first weeks of January.
    early = crashes[~(crashes.bike_involved & last)]
    one = crashes[crashes.bike_involved & last & crashes.reporting_agency.eq("A")].head(1)
    some = pd.concat([early, one.assign(collision_date=f"{YEARS[-1]}-01-10")], ignore_index=True)
    found = reporting.diagnose(some)["cyclist_injury_crashes_flags"]
    row = found[found.reporting_agency.eq("A") & found.year.eq(YEARS[-1])].iloc[0]
    assert row.change == "fall" and row.expected == pytest.approx(15 * 258 / 365, abs=0.1)


def test_the_chart_note_calls_a_year_unfinished_as_the_rule_does() -> None:
    crashes = _crashes()
    assert reporting.last_year_ends(crashes) == "2023 runs to 15 Sep"
    assert (
        reporting.last_year_ends(crashes.assign(collision_date="2023-12-01"))
        == "2023 runs to 1 Dec"
    )
    assert reporting.last_year_ends(crashes.assign(collision_date="2023-12-20")) is None


def test_a_rise_is_flagged_and_drawn(tmp_path: Path) -> None:
    crashes = _crashes()
    # Agency A files three times its usual number in 2021.
    extra = crashes[crashes.reporting_agency.eq("A") & crashes.year.eq(2021)]
    copies = [extra.assign(merged_id=extra.merged_id + mark) for mark in "xy"]
    more = pd.concat([crashes, *copies], ignore_index=True)
    flagged = reporting.diagnose(more)["injury_crashes_flags"]
    rise = flagged[flagged.reporting_agency.eq("A")]
    assert rise.year.tolist() == [2021] and rise.change.tolist() == ["rise"]
    assert set(flagged.change[flagged.reporting_agency.eq("B")]) == {
        "fall"
    }  # B is not excused by it
    written = reporting.write(more, tmp_path)
    assert (tmp_path / "injury_crashes.png").stat().st_size > 0 and len(written) > 3
    saved = pd.read_csv(tmp_path / "injury_crashes_flags.csv")
    assert set(saved.change) == {"rise", "fall"}


def _series(counts: list[int], start: int = 2015) -> pd.Series:
    return pd.Series(counts, index=range(start, start + len(counts)))


def test_a_lasting_step_is_found_with_its_year_and_levels() -> None:
    assert reporting.level_step(_series([110, 120, 100, 30, 25, 20, 22, 24])) == (2018, 110, 24)
    assert reporting.level_step(_series([20, 22, 18, 25, 70, 80, 85, 90])) == (2019, 21, 82.5)
    # One odd year is allowed on either side; two are not.
    assert reporting.level_step(_series([110, 30, 100, 105, 25, 20, 22, 24])) == (2019, 102.5, 23)
    assert reporting.level_step(_series([110, 30, 100, 105, 25, 20, 90, 24])) is None
    # Not a step: a steady series, a single low year, a change smaller than the line.
    assert reporting.level_step(_series([100, 105, 95, 100, 98, 102, 100])) is None
    assert reporting.level_step(_series([100, 105, 95, 30, 98, 102, 100])) is None
    assert reporting.level_step(_series([100, 105, 95, 65, 62, 66, 64])) is None
    assert reporting.level_step(_series([100, 105, 95, 55, 52, 56, 54])) == (2018, 100, 54.5)
    # Too small to judge, and too short on one side.
    assert reporting.level_step(_series([19, 18, 19, 2, 1, 2, 1])) is None
    assert reporting.level_step(_series([100, 100, 100, 100, 100, 20, 20])) is None
    assert reporting.level_step(_series([100, 100, 100, 100, 100, 20, 20]), min_years=2) == (
        2020,
        100,
        20,
    )
    # A year exactly at the midpoint is not out of place, in a rise or a fall.
    assert reporting.level_step(_series([10, 10, 20, 40, 40, 40]), min_level=1) == (2018, 10, 40)
    assert reporting.level_step(_series([40, 40, 40, 20, 10, 10]), min_level=1) == (2018, 40, 10)
    # A gap that closes again has no single split, so nothing is reported.
    assert reporting.level_step(_series([120, 120, 120, 20, 20, 20, 100, 100, 100])) is None
    # A fall to nothing.
    assert reporting.level_step(_series([40, 38, 42, 0, 0, 0])) == (2018, 40, 0)
    assert reporting.level_step(_series([])) is None


def _graded(agency: str, per_year: dict[int, dict[str, int]]) -> pd.DataFrame:
    """Made-up injury crashes of one agency: a count per year and severity code."""
    rows = [
        {"reporting_agency": agency, "year": year, "COLLISION_SEVERITY": code,
         "collision_date": f"{year}-12-28"}
        for year, codes in per_year.items()
        for code, count in codes.items()
        for _ in range(count)
    ]  # fmt: skip
    return pd.DataFrame(rows)


def test_a_step_at_one_severity_is_called_regrading_or_fewer_reports() -> None:
    years = range(2015, 2023)
    # A: from 2019 most "complaint of pain" (4) crashes are graded "visible injury" (3).
    regraded = _graded(
        "A", {y: {"4": 60, "3": 30} if y < 2019 else {"4": 10, "3": 80} for y in years}
    )
    # B: from 2019 most complaint-of-pain crashes are no longer filed at all.
    dropped = _graded(
        "B", {y: {"4": 60, "3": 30} if y < 2019 else {"4": 10, "3": 30} for y in years}
    )
    # C: steady.
    steady = _graded("C", {y: {"4": 60, "3": 30} for y in years})
    steps = reporting.level_steps(pd.concat([regraded, dropped, steady], ignore_index=True))

    def row(agency: str, measure: str) -> dict[str, Any]:
        match = steps[steps.reporting_agency.eq(agency) & steps.measure.eq(measure)]
        return {str(key): value for key, value in match.iloc[0].to_dict().items()}

    assert set(zip(steps.reporting_agency, steps.measure)) == {
        ("A", "Complaint of pain"),
        ("A", "Visible injury"),
        ("B", "Complaint of pain"),
        ("B", "All injury crashes"),
    }
    pain = row("A", "Complaint of pain")
    assert (pain["from_year"], pain["before"], pain["after"]) == (2019, 60, 10)
    assert (pain["other_before"], pain["other_after"], pain["moved"]) == (30, 80, 1.0)
    assert pain["kind"] == "regraded" and row("A", "Visible injury")["kind"] == "regraded"
    lost = row("B", "Complaint of pain")
    assert lost["moved"] == 0 and lost["kind"] == "fewer reports"
    total = row("B", "All injury crashes")
    assert (total["before"], total["after"], total["kind"]) == (90, 40, "fewer reports")
    assert pd.isna(total["moved"])


def test_a_small_rise_beside_a_larger_fall_elsewhere_is_not_called_regrading() -> None:
    years = range(2015, 2023)
    # Serious injuries (2) double while complaint of pain falls by ten times as much.
    crashes = _graded(
        "A", {y: {"4": 300, "2": 20} if y < 2019 else {"4": 100, "2": 40} for y in years}
    )
    found = reporting.level_steps(crashes).set_index("measure")
    assert found.moved["Serious injury"] == 10 and found.kind["Serious injury"] == "more reports"
    assert found.kind["Complaint of pain"] == "fewer reports"  # 20 of the 200 turned up elsewhere
    # The fifth is judged within the years of the higher level: 100 of 450 before, though
    # the other severities reach 470 after.
    big = _graded(
        "A", {y: {"4": 100, "3": 350} if y < 2019 else {"4": 20, "3": 470} for y in years}
    )
    found = reporting.level_steps(big).set_index("measure")
    assert found.moved["Complaint of pain"] == 1.5 and found.kind["Complaint of pain"] == "regraded"
    # A small severity beside a large one is not called regrading even at a matching share:
    # serious injuries rise by 20 while the 300 others fall by 25, which could be their drift.
    small = _graded(
        "A", {y: {"4": 300, "2": 20} if y < 2019 else {"4": 275, "2": 40} for y in years}
    )
    found = reporting.level_steps(small).set_index("measure")
    assert found.moved["Serious injury"] == 1.25 and found.kind["Serious injury"] == "more reports"


def test_steps_leave_out_an_unfinished_last_year_and_are_written_out(tmp_path: Path) -> None:
    years = range(2015, 2023)
    # Two finished years at the new level are too few; the part-year must not make a third.
    crashes = _graded("A", {y: {"4": 60 if y < 2021 else 10} for y in years})
    part = _graded("A", {2023: {"4": 10}}).assign(collision_date="2023-03-01")
    assert reporting.level_steps(pd.concat([crashes, part], ignore_index=True)).empty
    whole = part.assign(collision_date="2023-12-28")
    counted = reporting.level_steps(pd.concat([crashes, whole], ignore_index=True))
    assert counted.from_year.tolist() == [2021, 2021]  # the total, and complaint of pain
    assert reporting.level_steps(crashes.iloc[0:0]).empty
    found = reporting.diagnose(_crashes())
    assert list(found[reporting.STEPS].columns)[:3] == ["reporting_agency", "measure", "from_year"]
    reporting.write(_crashes(), tmp_path)
    saved = pd.read_csv(tmp_path / "level_steps.csv")
    assert list(saved.columns) == list(found[reporting.STEPS].columns)


def test_one_agency_alone_is_still_flagged_and_says_on_what_basis() -> None:
    crashes = _crashes()
    alone = crashes[crashes.reporting_agency.eq("B")]
    flagged = reporting.diagnose(alone)["injury_crashes_flags"]
    # With no other agency the 2020 halving cannot be told from a shared dip: worth a look.
    assert dict(zip(flagged.year, flagged.change, strict=True)) == {
        2020: "possible fall",
        2022: "fall",
        2023: "fall",
    }
    assert all(basis.startswith("own history only") for basis in flagged.basis)


def test_an_unfamiliar_case_number_is_not_called_the_earlier_format() -> None:
    rows = pd.DataFrame(
        {"CASE_ID": ["1234567", "91234567", "81234567", "AB-12", None, "5"], "source": "tims"}
    )
    assert reporting.report_format(rows).tolist() == [
        reporting.EARLIER,
        reporting.EARLIER,
        reporting.CCRS_FORMAT,
        reporting.UNRECOGNISED,
        reporting.UNRECOGNISED,
        reporting.UNRECOGNISED,
    ]


def test_cyclist_reports_falling_to_none_in_the_last_years_are_flagged() -> None:
    crashes = _crashes()
    last_two = crashes.year.ge(YEARS[-2])
    # Agency A goes on reporting, but no cyclist crash after the last two years begin.
    crashes = crashes[~(crashes.reporting_agency.eq("A") & crashes.bike_involved & last_two)]
    bikes = reporting.diagnose(crashes)["cyclist_injury_crashes_flags"]
    flagged = set(zip(bikes.reporting_agency, bikes.year, strict=True))
    assert {("A", YEARS[-2]), ("A", YEARS[-1])} <= flagged


def test_a_crash_with_no_severity_is_counted_as_not_recorded() -> None:
    crashes = _crashes()
    crashes.loc[crashes.index[:3], "COLLISION_SEVERITY"] = "0"
    table = reporting.by_severity(crashes)
    assert table[reporting.NO_SEVERITY].sum() == 3
    assert table.sum().sum() == len(crashes)


def _by_grade(counts: dict[int, dict[str, int]]) -> pd.DataFrame:
    """Made-up injury crashes: for each year, how many at each severity code."""
    rows = [
        {"year": year, "COLLISION_SEVERITY": code}
        for year, by_code in counts.items()
        for code, number in by_code.items()
        for _ in range(number)
    ]
    return pd.DataFrame(rows)


def test_a_fall_or_rise_in_minor_injury_crashes_is_flagged_and_a_steady_count_is_not() -> None:
    early = {year: {"4": 60, "3": 40, "2": 8, "1": 2} for year in range(2016, 2020)}
    busy_2020 = {2020: {"4": 500}}  # in neither period

    def later(pain: int, visible: int) -> pd.DataFrame:
        late = {year: {"4": pain, "3": visible, "2": 8, "1": 2} for year in range(2021, 2025)}
        return _by_grade(early | busy_2020 | late)

    fall = reporting.minor_injury_change(later(9, 30))
    assert fall["minor per year before"] == 100 and fall["minor per year after"] == 39
    assert fall["ratio"] == pytest.approx(0.39) and fall["verdict"] == reporting.CHANGED
    assert reporting.minor_injury_change(later(100, 60))["verdict"] == reporting.CHANGED
    for pain, ratio in ((10, 0.5), (110, 1.5), (45, 0.85)):  # the lines themselves are steady
        steady = reporting.minor_injury_change(later(pain, 40))
        assert steady["ratio"] == pytest.approx(ratio) and steady["verdict"] == reporting.STEADY
        assert steady["reason"] == ""
    # the serious grades do not enter: ten times as many change nothing
    late = {year: {"4": 45, "3": 40, "2": 80, "1": 20} for year in range(2021, 2025)}
    assert reporting.minor_injury_change(_by_grade(early | late))["ratio"] == pytest.approx(0.85)


def test_a_minor_injury_ratio_that_cannot_be_measured_is_not_assessable() -> None:
    year = {"4": 6, "3": 4, "2": 1}
    whole = dict.fromkeys([*range(2016, 2020), *range(2021, 2025)], year)
    assert reporting.minor_injury_change(_by_grade(whole))["verdict"] == reporting.STEADY
    gap = reporting.minor_injury_change(_by_grade({y: c for y, c in whole.items() if y != 2023}))
    assert gap["verdict"] == reporting.NOT_ASSESSABLE and "2023" in gap["reason"]
    assert np.isnan(gap["ratio"])
    ungraded = reporting.minor_injury_change(
        _by_grade(whole | {y: {"4": 6, "3": 4, "": 5} for y in range(2021, 2025)})
    )
    assert ungraded["verdict"] == reporting.NOT_ASSESSABLE
    assert ungraded["ungraded share after"] == pytest.approx(1 / 3)
    serious_only = whole | {y: {"2": 3} for y in range(2016, 2020)}
    none = reporting.minor_injury_change(_by_grade(serious_only))
    assert none["verdict"] == reporting.NOT_ASSESSABLE and "no minor-injury" in none["reason"]
