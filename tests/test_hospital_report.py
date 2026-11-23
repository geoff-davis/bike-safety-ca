"""The county report and the table checks, on a made-up county and made-up counts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
from scipy import stats

from bike_safety_ca import links
from bike_safety_ca.hospital import ebike, epicenter, population, report, tables

GROUPS = ["<1", "1-4", "5-9", "10-14", "15-19", "20-24", "25-44", "45-64", "65-84", "85+"]
CAUSES = [
    "Pedal cyclist injured in collision with car, pick-up truck or van in traffic accident",
    "Pedal cyclist (driver) injured in noncollision transport accident",
    "Electric (assisted) bicycle driver injured in noncollision transport accident",
    "Electric (assisted) bicycle driver injured in collision with car in traffic accident",
]
BIKE = "Injury Mechanism: " + ", ".join(epicenter.BIKE)


def _filter(years: tuple[int, int], county: str | None, hosp: bool, ages=(0, 100)) -> str:
    summary = f"Counts from {years[0]} to {years[1]} for residents aged {ages[0]} to {ages[1]} "
    if hosp:
        summary += "(comprehensive case definition) "
    lines = ["Injury Intent: Unintentional", BIKE]
    if county:
        lines.insert(0, f"County of Residence: {county}")
    return summary + "filtered by:\n" + "\n".join(lines)


def _save(folder: Path, name: str, frame: pd.DataFrame, county: str | None, years) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    text = frame.to_csv(index=False)
    (folder / f"{name}.csv").write_text(text)
    record = folder / tables.MANIFEST
    manifest = json.loads(record.read_text()) if record.exists() else {"files": {}}
    manifest["files"][f"{name}.csv"] = {
        "site_filter_text": _filter(
            years, county, name.startswith("hosp"), tables._ages()[f"{name}.csv"]
        ),
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
    }
    record.write_text(json.dumps(manifest))


def _county_tables(folder: Path, county: str = "Alder", years=(2016, 2024)) -> None:
    span = range(years[0], years[1] + 1)
    _save(folder, "ed_total_year_under18", pd.DataFrame({"Year": span, "Count": 40}), county, years)
    adult = pd.DataFrame({"Year": span, "Count": [60 + 5 * i for i in range(len(span))]})
    _save(folder, "ed_total_year_adult", adult, county, years)
    by_age = pd.DataFrame({report.AGE: GROUPS, "Count": [None, 12, 50, 80, 70, 30, 90, 60, 20, 12]})
    _save(folder, "ed_total_age_groups", by_age, county, years)
    stays = pd.DataFrame(
        {report.AGE: GROUPS, "Count": [None, None, 12, 15, 14, 12, 30, 40, 25, 13]}
    )
    _save(folder, "hosp_total_age_groups", stays, county, years)
    for outcome in ("ed", "hosp"):
        rows = [
            {report.CAUSE: cause, report.AGE: age, "Count": 20 + 3 * i if j < 2 else None}
            for i, age in enumerate(GROUPS)
            for j, cause in enumerate(CAUSES)
        ]
        state = epicenter.STATEWIDE_YEARS
        _save(folder, f"{outcome}_state_bike_cause_age_groups", pd.DataFrame(rows), None, state)


def _residents(folder: Path, monkeypatch) -> None:
    """Census-style county files for two made-up counties, 2016 to 2024."""
    monkeypatch.setattr(population, "COUNTIES", 2)
    monkeypatch.setattr(population, "CODES", (1, 3))
    monkeypatch.setattr(population, "NAMES", ("Alder", "Birch"))
    monkeypatch.setattr(population, "SOURCES", [("pep.csv", "", 2016, 2, 2024)])
    columns = [c for cols in population.AGE_GROUPS.values() for c in cols]
    rows = []
    for code, name, size in ((1, "Alder", 3000), (3, "Birch", 9000)):
        for year in range(2, 11):
            rows.append(
                {"COUNTY": code, "CTYNAME": f"{name} County", "YEAR": year}
                | {"POPESTIMATE": size * len(columns)}
                | dict.fromkeys(columns, size)
            )
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(folder / "pep.csv", index=False)


def test_a_report_for_a_made_up_county(tmp_path, monkeypatch):
    _county_tables(tmp_path / "alder")
    _residents(tmp_path / "pep", monkeypatch)
    text, drawn = report.markdown(tmp_path / "alder", tmp_path / "pep", "Alder")
    assert text.startswith("# Bicycle injuries treated in hospital: Alder County")
    assert "EpiCenter@cdph.ca.gov" in text and "Santa Clara" not in text
    assert f"]({links.REPO})" in text and f"]({links.doc('county_rates_method.md')})" in text
    assert "| 2016 | 100 |" in text and "| 2024 | 140 |" in text
    assert "Emergency department visits by Alder County residents | **275**" in text
    assert set(drawn) == {"yearly", "ages"} and "<!-- chart: yearly -->" in text
    assert "<!-- chart: ages -->" in text


def test_the_report_refuses_another_county_or_years(tmp_path, monkeypatch):
    _residents(tmp_path / "pep", monkeypatch)
    _county_tables(tmp_path / "birch", county="Birch")
    with pytest.raises(ValueError, match="is not Alder County 2016–2024"):
        report.markdown(tmp_path / "birch", tmp_path / "pep", "Alder")
    _county_tables(tmp_path / "late", years=(2018, 2022))
    with pytest.raises(ValueError, match="is not Alder County 2016–2024"):
        report.markdown(tmp_path / "late", tmp_path / "pep", "Alder")
    # Years that miss the statewide years cannot be set against the state.
    with pytest.raises(ValueError, match="do not cover 2023–2024"):
        report.markdown(tmp_path / "late", tmp_path / "pep", "Alder", (2018, 2022))
    _county_tables(tmp_path / "oak", county="Oak")
    with pytest.raises(ValueError, match="no California county named 'Oak'"):
        report.markdown(tmp_path / "oak", tmp_path / "pep", "Oak")


def test_check_source_refuses_missing_and_changed_tables(tmp_path):
    folder = tmp_path / "alder"
    _county_tables(folder)
    tables.check_source(folder, "Alder", (2016, 2024))
    with pytest.raises(ValueError, match="no manifest entry"):
        tables.check_source(folder, "Alder", (2016, 2024), required=("ed_bike_age_groups",))
    with pytest.raises(ValueError, match="has no manifest entry"):
        tables.table(folder, "ed_bike_age_groups")
    (folder / "ed_total_year_adult.csv").write_text("Year,Count\n2016,99\n")
    with pytest.raises(ValueError, match="has changed"):
        tables.check_source(folder, "Alder", (2016, 2024))
    # A statewide check looks at the statewide tables only.
    tables.check_source(folder, None, epicenter.STATEWIDE_YEARS)


def test_check_source_refuses_the_wrong_case_definition(tmp_path):
    folder = tmp_path / "alder"
    _county_tables(folder)
    record = folder / tables.MANIFEST
    manifest = json.loads(record.read_text())
    entry = manifest["files"]["hosp_total_age_groups.csv"]
    entry["site_filter_text"] = entry["site_filter_text"].replace("comprehensive", "surveillance")
    record.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="comprehensive case definition"):
        tables.check_source(folder, "Alder", (2016, 2024))


def test_the_ebike_report_reads_only_the_statewide_tables(tmp_path, monkeypatch):
    _county_tables(tmp_path / "birch", county="Birch")
    _residents(tmp_path / "pep", monkeypatch)
    text, drawn = ebike.markdown(tmp_path / "birch", tmp_path / "pep")
    assert text.startswith("# Electric bicycle injuries treated in hospital: California")
    assert "EpiCenter@cdph.ca.gov" in text and set(drawn) == {"shares"}
    assert f"]({links.REPO})" in text
    low, high = ebike.admission_ratio(tmp_path / "birch")
    assert 0 < low <= high and f"**{low:.2f} to {high:.2f}**" in text
    # With one hidden e-bike cell in an age group, its range would give that cell away.
    for outcome in ("ed", "hosp"):
        name = f"{outcome}_state_bike_cause_age_groups"
        saved = tables.table(tmp_path / "birch", name).drop(columns="kind", errors="ignore")
        saved = saved[saved[report.CAUSE] != CAUSES[3]]
        _save(tmp_path / "birch", name, saved, None, epicenter.STATEWIDE_YEARS)
    with pytest.raises(ValueError, match="exactly one hidden cell"):
        ebike.markdown(tmp_path / "birch", tmp_path / "pep")


def test_the_downloader_refuses_an_unknown_county_or_table():
    with pytest.raises(SystemExit):
        epicenter.main(["--county", "Atlantis", "--out", "unused"])
    with pytest.raises(SystemExit):
        epicenter.main(["--county", "Santa Clara", "--out", "unused", "--only", "ed_nothing"])
    with pytest.raises(ValueError, match="ed_nothing"):
        epicenter.download("Alder", Path("unused"), names={"ed_nothing"})


def test_the_default_pull_is_exactly_the_tables_the_reports_read():
    assert set(report.TABLES) | set(ebike.STATE_TABLES) == epicenter.REPORT_TABLES
    assert epicenter.REPORT_TABLES <= set(epicenter.table_names())


def test_the_downloader_will_not_mix_two_counties_in_one_folder(tmp_path, monkeypatch):
    import sys
    import types

    (tmp_path / tables.MANIFEST).write_text(
        json.dumps({"county_of_residence": "Birch", "files": {}})
    )
    # Stands in for Playwright, which is not installed; the refusal comes before any browser.
    fake = types.ModuleType("playwright.sync_api")
    fake.sync_playwright = lambda: pytest.fail("opened a browser")  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake)
    with pytest.raises(ValueError, match="another county"):
        epicenter.download("Alder", tmp_path)


def test_the_downloader_accepts_any_county_filter():
    result = {
        "busy": False,
        "columns": ["Select", "Year", "Count"],
        "filter": _filter((2016, 2024), "Alder", False).replace("aged 0 to 100", "aged 0 to 17"),
    }
    assert epicenter.accepts(result, ["Year"], (0, 17), (2016, 2024), "Alder")
    assert not epicenter.accepts(result, ["Year"], (0, 17), (2016, 2024), "Birch")


def test_check_source_refuses_other_filters_and_a_missing_checksum(tmp_path):
    for change, message in (
        (
            lambda e: e.update(
                site_filter_text=e["site_filter_text"].replace(BIKE, "Injury Mechanism: Fall")
            ),
            "not the table",
        ),
        (
            lambda e: e.update(site_filter_text=e["site_filter_text"] + "\nSex: Male"),
            "not the table",
        ),
        (
            lambda e: e.update(
                site_filter_text=e["site_filter_text"].replace("aged 0 to 17", "aged 0 to 4")
            ),
            "not the table",
        ),
        (lambda e: e.pop("sha256"), "no checksum"),
    ):
        folder = tmp_path / message.replace(" ", "_") / str(id(change))
        _county_tables(folder)
        record = folder / tables.MANIFEST
        manifest = json.loads(record.read_text())
        change(manifest["files"]["ed_total_year_under18.csv"])
        record.write_text(json.dumps(manifest))
        with pytest.raises(ValueError, match=message):
            tables.check_source(folder, "Alder", (2016, 2024))


def test_a_mixed_group_is_not_enough_on_its_own():
    table = pd.DataFrame(
        {"low": [13, 50, 40], "high": [22, 50, 40], "hidden": [True, False, False]},
        index=["0-4", "5-9", "10-14"],
    )
    # The source gives the total, so 0-4 alone would be the total less 5-9 and 10-14.
    assert report.withheld(table).to_list() == [True, True, False]


def test_admissions_hold_back_a_second_group_too():
    table = pd.DataFrame(
        {
            "low": [12.0, 30.0, 25.0],
            "high": [21.0, 30.0, 25.0],
            "hidden": [True, False, False],
            "rate_low": 1.0,
            "rate_high": 1.0,
        },
        index=["0-4", "5-9", "10-14"],
    )
    assert report.shown(table, 1)["count"].to_list() == ["not shown", "not shown", "25"]


def test_the_under_fives_count_when_choosing_what_to_hold_back(tmp_path, monkeypatch):
    _county_tables(tmp_path / "alder")
    _residents(tmp_path / "pep", monkeypatch)
    text, _ = report.markdown(tmp_path / "alder", tmp_path / "pep", "Alder")
    # "<1" is hidden and "1-4" published: 5-9 must not be printed, nor named in the key points.
    assert "| 5–9 | not shown | not shown |" in text
    assert not [line for line in text.splitlines() if "By age" in line and "5–9" in line]


def test_absent_rows_are_zero(tmp_path, monkeypatch):
    _county_tables(tmp_path / "alder")
    _residents(tmp_path / "pep", monkeypatch)
    adult = pd.DataFrame({"Year": range(2016, 2024), "Count": 60})  # no row for 2024
    _save(tmp_path / "alder", "ed_total_year_adult", adult, "Alder", (2016, 2024))
    text, _ = report.markdown(tmp_path / "alder", tmp_path / "pep", "Alder")
    assert "| 2024 | 40 |" in text


def test_an_age_group_with_no_ebike_admissions_still_counts(tmp_path):
    """Every group: 20 ordinary-bike visits, 20 admissions, 20 e-bike visits; e-bike
    admissions of 20 in five groups and no row at all in the sixth."""
    for outcome in ("ed", "hosp"):
        rows = [
            {report.CAUSE: cause, report.AGE: age, "Count": 20}
            for age in ebike.GROUPS
            for cause in (CAUSES[0], CAUSES[2])
            if not (outcome == "hosp" and cause == CAUSES[2] and age == ebike.GROUPS[-1])
        ]
        name = f"{outcome}_state_bike_cause_age_groups"
        _save(tmp_path, name, pd.DataFrame(rows), None, epicenter.STATEWIDE_YEARS)
    # 100 admissions against (5 x 40 + 20) treated x one half admitted = 110 expected.
    assert ebike.admission_ratio(tmp_path) == (0.90, 0.91)


def test_the_report_commands_write_their_files(tmp_path, monkeypatch):
    _county_tables(tmp_path / "alder")
    _residents(tmp_path / "pep", monkeypatch)
    common = ["--tables", str(tmp_path / "alder"), "--residents", str(tmp_path / "pep")]
    report.main(["--county", "Alder", *common, "--out", str(tmp_path / "out")])
    ebike.main([*common, "--out", str(tmp_path / "out")])
    assert {p.name for p in (tmp_path / "out").iterdir()} == {
        "hospital_alder.md",
        "hospital_ebike_california.md",
    }


def test_a_hidden_yearly_cell_is_not_taken_as_zero(tmp_path, monkeypatch):
    _county_tables(tmp_path / "alder")
    _residents(tmp_path / "pep", monkeypatch)
    child = pd.DataFrame({"Year": range(2016, 2025), "Count": [40] * 8 + [None]})
    _save(tmp_path / "alder", "ed_total_year_under18", child, "Alder", (2016, 2024))
    with pytest.raises(ValueError, match="suppressed cells in an exact total"):
        report.markdown(tmp_path / "alder", tmp_path / "pep", "Alder")


def test_an_ebike_group_with_no_other_bicycles_is_refused(tmp_path):
    for outcome in ("ed", "hosp"):
        rows = [
            {report.CAUSE: cause, report.AGE: age, "Count": 20}
            for age in ebike.GROUPS
            for cause in (CAUSES[0], CAUSES[2])
            if not (cause == CAUSES[0] and age == ebike.GROUPS[-1])
        ]
        name = f"{outcome}_state_bike_cause_age_groups"
        _save(tmp_path, name, pd.DataFrame(rows), None, epicenter.STATEWIDE_YEARS)
    with pytest.raises(ValueError, match="no other bicycles to compare"):
        ebike.admission_ratio(tmp_path)


def test_the_age_key_points_say_they_cover_only_groups_shown(tmp_path, monkeypatch):
    _county_tables(tmp_path / "alder")
    _residents(tmp_path / "pep", monkeypatch)
    text, _ = report.markdown(tmp_path / "alder", tmp_path / "pep", "Alder")
    assert "Among the age groups with published counts, ages 10–14 visit most often" in text
    assert ", and hospital admissions are most frequent at ages 10–14 (55.6 per" in text
    assert "Of the age groups shown" not in text


def _state_visits(folder: Path) -> None:
    """A statewide visits table with round totals: 700 published and two hidden cells a group."""
    rows = [
        {report.CAUSE: cause, report.AGE: age, "Count": count}
        for age in GROUPS
        for cause, count in zip(CAUSES, (40, 30, None, None))
    ]
    name = "ed_state_bike_cause_age_groups"
    _save(folder, name, pd.DataFrame(rows), None, epicenter.STATEWIDE_YEARS)


def test_the_figures_match_ones_worked_out_by_hand(tmp_path, monkeypatch):
    """Alder has 3,000 residents in each of the 18 five-year age bands, Birch 9,000, every year."""
    _county_tables(tmp_path / "alder")
    _state_visits(tmp_path / "alder")
    _residents(tmp_path / "pep", monkeypatch)
    text, _ = report.markdown(tmp_path / "alder", tmp_path / "pep", "Alder")
    # By year: 100 visits among 18 x 3,000 residents is 185 per 100,000.  The 90% range is the
    # 5% and 95% points of a gamma with shape 100.5 and that year's residents as its rate.
    low, high = stats.gamma.ppf([0.05, 0.95], 100 + 0.5, scale=1 / 0.54)
    assert (round(100 / 0.54), round(low), round(high)) == (185, 157, 218)
    assert "| 2016 | 100 | 54,000 | 185 | 157 to 218 |" in text
    low, high = stats.gamma.ppf([0.05, 0.95], 140 + 0.5, scale=1 / 0.54)
    assert f"| 2024 | 140 | 54,000 | 259 | {low:.0f} to {high:.0f} |" in text
    # By age: ages 10-14 are one band, so 9 years x 3,000 = 27,000 resident-years.
    # 80 visits / 27,000 = 296 per 100,000 a year; 15 admissions / 27,000 = 55.6.
    assert "| 10–14 | 80 | 296 | 15 | 55.6 |" in text
    # 25-44 is four bands: 90 / 108,000 = 83; 30 / 108,000 = 27.8.
    assert "| 25–44 | 90 | 83 | 30 | 27.8 |" in text
    # Against the state, 2023-2024.  Each of the ten source age groups has 70 published visits
    # statewide and two hidden cells: 72 to 90, so 720 to 900 in all.  Alder holds 3,000 of
    # every 12,000 residents at every age, so a quarter is expected there: 180 to 225.
    assert "statewide rate | **180 to 225** |" in text
    # Alder's visits: 40 + 95 in 2023 and 40 + 100 in 2024.
    assert "Emergency department visits by Alder County residents | **275** |" in text
    # The ratio's range: the 5% point against the most expected, the 95% against the least.
    low = stats.gamma.ppf(0.05, 275 + 0.5, scale=1 / 225)
    high = stats.gamma.ppf(0.95, 275 + 0.5, scale=1 / 180)
    assert (round(low, 2), round(high, 2)) == (1.11, 1.69)
    assert "| 90% range for the ratio, allowing for chance | **1.11 to 1.69** |" in text
    # The ratio itself is plain division: 275 / 225 = 1.22 and 275 / 180 = 1.53.
    assert "| Ratio of the two (1.00 is the state average) | **1.22 to 1.53** |" in text
    assert (
        "statewide rates: 1.22 to 1.53 times as many (90% range allowing for chance: 1.11 to"
        in text
    )
    assert "- **Alder County has more visits than its ages predict.** In 2023–2024" in text
    assert "against 180 to 225 expected" in text


def _uncredited(text: str) -> list[str]:
    """The tables with no credit in the paragraph straight above or below them."""
    parts = text.split("\n\n")
    tables = [i for i, part in enumerate(parts) if part.startswith("|")]
    return [
        parts[i].splitlines()[0]
        for i in tables
        if report.CREDIT not in parts[i - 1] and report.CREDIT not in parts[i + 1]
    ]


def test_every_table_carries_the_credit(tmp_path, monkeypatch):
    _county_tables(tmp_path / "alder")
    _residents(tmp_path / "pep", monkeypatch)
    county, _ = report.markdown(tmp_path / "alder", tmp_path / "pep", "Alder")
    statewide, _ = ebike.markdown(tmp_path / "alder", tmp_path / "pep")
    # The age chart and the e-bike chart each carry one of their own.
    for text, tables_printed, credits in ((county, 3, 4), (statewide, 2, 3)):
        assert sum(part.startswith("|") for part in text.split("\n\n")) == tables_printed
        assert _uncredited(text) == []
        assert text.count(report.CREDIT) == credits
    # The check itself: a table that loses its credit is reported.
    lost = county.replace(f"it is a range. {report.CREDIT}", "it is a range.")
    assert _uncredited(lost) == ["| | |"]


def test_the_suppressed_note_prints_only_beside_a_suppressed_cell(tmp_path, monkeypatch):
    _county_tables(tmp_path / "alder")
    _residents(tmp_path / "pep", monkeypatch)
    text, _ = report.markdown(tmp_path / "alder", tmp_path / "pep", "Alder")
    # Only under-fives are hidden, and their row is not printed.
    assert "suppressed |" not in text and 'A "suppressed" count' not in text
    assert "| 5–9 | not shown |" in text and '"Not shown" marks' in text
    by_age = pd.DataFrame(
        {report.AGE: GROUPS, "Count": [None, 12, 50, 80, 70, 30, 90, 60, 20, None]}
    )
    _save(tmp_path / "alder", "ed_total_age_groups", by_age, "Alder", (2016, 2024))
    text, _ = report.markdown(tmp_path / "alder", tmp_path / "pep", "Alder")
    # One hidden cell among 27,000 resident-years: 1 to 10 cases is 4 to 37 per 100,000.
    assert "| 85+ | suppressed | 4 to 37 |" in text and 'A "suppressed" count' in text


def test_a_hidden_count_is_said_to_stop_an_exact_total(tmp_path, monkeypatch):
    _county_tables(tmp_path / "alder")
    _residents(tmp_path / "pep", monkeypatch)
    county, _ = report.markdown(tmp_path / "alder", tmp_path / "pep", "Alder")
    statewide, _ = ebike.markdown(tmp_path / "alder", tmp_path / "pep")
    for text in (county, statewide):
        assert "enters every calculation" not in text
        assert (
            "A total stated as exact cannot take a range, so a hidden count in one stops the "
            "report instead." in text
        )


def test_the_ebike_ranges_say_they_leave_chance_out(tmp_path, monkeypatch):
    """Nothing hidden, so every range is as narrow as it can be: it must not read as precise."""
    for outcome, bike, electric in (("ed", 400, 200), ("hosp", 100, 70)):
        rows = [
            {report.CAUSE: cause, report.AGE: age, "Count": count}
            for age in ebike.GROUPS
            for cause, count in ((CAUSES[0], bike), (CAUSES[2], electric))
        ]
        name = f"{outcome}_state_bike_cause_age_groups"
        _save(tmp_path / "state", name, pd.DataFrame(rows), None, epicenter.STATEWIDE_YEARS)
    _residents(tmp_path / "pep", monkeypatch)
    text, _ = ebike.markdown(tmp_path / "state", tmp_path / "pep")
    # 70 of 270 admitted against 100 of 500: 420 admissions against 6 x 270 x 0.2 = 324 expected.
    assert ebike.admission_ratio(tmp_path / "state") == (1.29, 1.30)
    assert "hidden counts only, not chance" in ebike.NOT_CHANCE
    box, rest = text.split("<!-- /box -->")
    assert "1.29 to 1.30 times as many, before any allowance for chance." in box
    assert f"*{ebike.NOT_CHANCE}*" in box  # under the key points
    assert f"**1.29 to 1.30**. {ebike.NOT_CHANCE}" in rest  # where the ratio is printed
    assert f"hidden (under 11). {ebike.NOT_CHANCE}" in rest  # under the table by age group
    assert "It covers hidden counts only, not chance.*" in rest  # under the chart
    assert "- **Ranges are not margins of error.**" in rest


def test_the_highest_ebike_rate_is_scoped_to_the_ages_shown(tmp_path, monkeypatch):
    _county_tables(tmp_path / "alder")
    _residents(tmp_path / "pep", monkeypatch)
    text, _ = ebike.markdown(tmp_path / "alder", tmp_path / "pep")
    # Ages under 10 and over 84 are left out because they are hidden, not because they are lower.
    point = next(line for line in text.splitlines() if "e-bike injury rates" in line)
    assert point.startswith("- **Among the age groups shown (ages 10 to 84), ages ")


def test_the_age_chart_draws_what_the_table_prints_and_no_more(tmp_path, monkeypatch):
    _county_tables(tmp_path / "alder")
    _residents(tmp_path / "pep", monkeypatch)
    text, drawn = report.markdown(tmp_path / "alder", tmp_path / "pep", "Alder")
    chart = drawn["ages"]
    # 5-9 is held back in the table, so the chart names it without a rate.
    assert "| 5–9 | not shown | not shown |" in text
    assert chart.count("5 to 9 not shown") == 2
    # Every rate the table prints is the rate the chart draws, to the same places.
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        is_age = "–" in cells[0] or cells[0].endswith("+")
        if len(cells) == 5 and is_age and cells[2] != "not shown":
            age = cells[0].replace("–", " to ")
            assert f"{age} {cells[2]}" in chart and f"{age} {cells[4]}" in chart


def test_a_held_back_rate_never_reaches_the_chart():
    table = pd.DataFrame(
        {
            "low": [12.0, 30.0, 25.0] + [40.0] * 6,
            "high": [21.0, 30.0, 25.0] + [40.0] * 6,
            "hidden": [True] + [False] * 8,
            "rate_low": [3.0, 7.123, 6.0] + [9.0] * 6,
            "rate_high": [5.0, 7.123, 6.0] + [9.0] * 6,
        },
        index=report.ORDER,
    )
    rows = report.plotted(table)
    assert rows.loc["5-9"].status == "not shown" and rows.loc["5-9"].isna().sum() == 2
    from bike_safety_ca.hospital import charts

    svg = charts.by_age([("Visits", rows, 1)])
    assert "7.1" not in svg and "5 to 9 not shown" in svg


def test_a_panel_of_zero_rates_still_draws():
    from bike_safety_ca.hospital import charts

    ages = ["10-14", "15-19", "20-24"]
    zero = pd.DataFrame(
        {"status": "published", "rate_low": 0.0, "rate_high": 0.0}, index=pd.Index(ages)
    )
    held = zero.copy()
    held.loc["10-14", "status"] = "not shown"
    held.loc["10-14", ["rate_low", "rate_high"]] = float("nan")
    svg = charts.by_age([("Visits", zero, 0), ("Admissions", held, 1)])
    assert "nan" not in svg.lower() and "inf" not in svg.lower()
    assert "10 to 14 not shown" in svg and "15 to 19 0.0" in svg and "10 to 14 0" in svg
    assert svg.count(">1.0<") == 2  # each panel's scale runs from 0 to 1
