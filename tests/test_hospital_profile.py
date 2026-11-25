"""The statewide profile, on a made-up state of two counties and made-up counts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from bike_safety_ca.hospital import epicenter, population, profile, tables

GROUPS = ["<1", "1-4", "5-9", "10-14", "15-19", "20-24", "25-44", "45-64", "65-84", "85+"]
MVT, OTHER = epicenter.BIKE
# cause, mechanism, e-bike
CAUSES = [
    ("Pedal cyclist injured in collision with car, pick-up truck or van in traffic accident", MVT),
    ("Pedal cyclist (driver) injured in noncollision transport accident", OTHER),
    ("Electric (assisted) bicycle driver injured in noncollision transport accident", OTHER),
    ("Electric (assisted) bicycle driver injured in collision with car in traffic accident", MVT),
]
STATE = epicenter.STATEWIDE_YEARS


def _save(folder: Path, name: str, rows: list[dict]) -> None:
    """A statewide table and its manifest entry, as the downloader writes them."""
    folder.mkdir(parents=True, exist_ok=True)
    text = pd.DataFrame(rows).to_csv(index=False)
    (folder / f"{name}.csv").write_text(text)
    ages = tables._ages()[f"{name}.csv"]
    first, last = epicenter.YEARS if "_trend_" in name else STATE
    summary = f"Counts from {first} to {last} for residents aged {ages[0]} to {ages[1]} "
    if name.startswith("hosp"):
        summary += "(comprehensive case definition) "
    filters = ["Injury Intent: Unintentional", "Injury Mechanism: " + ", ".join(epicenter.BIKE)]
    record = folder / tables.MANIFEST
    manifest = json.loads(record.read_text()) if record.exists() else {"files": {}}
    manifest["files"][f"{name}.csv"] = {
        "site_filter_text": summary + "filtered by:\n" + "\n".join(filters),
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
    }
    record.write_text(json.dumps(manifest))


def _tables(folder: Path) -> None:
    age, sex, mech, cause = "Age, Summary Groups", "Sex", "Injury Mechanism", profile.CAUSE
    # Unique visits: under-1s hidden; one ED visit of unknown sex group.
    for outcome, men, women in (("ed", 48, 16), ("hosp", 12, 12)):
        rows = [
            {age: g, sex: s, "Count": None if g == "<1" and outcome == "ed" else count}
            for g in GROUPS
            for s, count in (("Male", men), ("Female", women))
        ]
        if outcome == "ed":
            rows.append({age: "25-44", sex: "Other/Unknown", "Count": 15})
        _save(folder, f"{outcome}_state_total_age_sex", rows)
        # The same visits by age alone: men, women and the one of unknown sex.
        total = [
            {
                age: g,
                "Count": None
                if g == "<1" and outcome == "ed"
                else men + women + (15 if (g, outcome) == ("25-44", "ed") else 0),
            }
            for g in GROUPS
        ]
        _save(folder, f"{outcome}_state_total_age_groups", total)
    # Mechanism by age and sex.  Female ages 10-14: motor-vehicle cells hidden in both
    # tables; female ages 15-19: hidden in the ED table only.
    counts = {"ed": {MVT: 30, OTHER: 70}, "hosp": {MVT: 20, OTHER: 30}}
    female_counts = {"ed": {MVT: 30, OTHER: 50}, "hosp": {MVT: 20, OTHER: 20}}
    for outcome in ("ed", "hosp"):
        rows = []
        for g in GROUPS:
            for s in ("Male", "Female"):
                for m in (MVT, OTHER):
                    count: int | None = (female_counts if s == "Female" else counts)[outcome][m]
                    if (
                        s == "Female"
                        and m == MVT
                        and (g == "10-14" or (g, outcome) == ("15-19", "ed"))
                    ):
                        count = None
                    rows.append({mech: m, age: g, sex: s, "Count": count})
        _save(folder, f"{outcome}_state_bike_mech_age_sex", rows)
    # Cause and mechanism: the same in every age group and for each sex.
    per = {"ed": (40, 60, 20, 20), "hosp": (20, 20, 20, 20)}
    for outcome, values in per.items():
        for by, labels in ((age, GROUPS), (sex, ["Male", "Female"])):
            rows = [
                {cause: c, mech: m, by: label, "Count": n}
                for label in labels
                for (c, m), n in zip(CAUSES, values, strict=True)
            ]
            suffix = "age" if by == age else "sex"
            _save(folder, f"{outcome}_state_bike_cause_mech_{suffix}", rows)
    # Trends: 30 in every age group and year, but under-1s hidden in 2016's ED table;
    # causes as above in every year.
    years = range(epicenter.YEARS[0], epicenter.YEARS[1] + 1)
    for outcome, values in per.items():
        rows = [
            {"Year": y, age: g, "Count": None if (y, g, outcome) == (2016, "<1", "ed") else 30}
            for y in years
            for g in GROUPS
        ]
        _save(folder, f"{outcome}_state_trend_total_year_age", rows)
        rows = [
            {cause: c, mech: m, "Year": y, "Count": n}
            for y in years
            for (c, m), n in zip(CAUSES, values, strict=True)
        ]
        _save(folder, f"{outcome}_state_trend_bike_cause_mech_year", rows)


def _residents(folder: Path, monkeypatch) -> None:
    """Two counties, each with 600 men and 400 women in every Census age column, every year."""
    monkeypatch.setattr(population, "COUNTIES", 2)
    monkeypatch.setattr(population, "CODES", (1, 3))
    monkeypatch.setattr(population, "NAMES", ("Alder", "Birch"))
    monkeypatch.setattr(population, "SOURCES", [("pep.csv", "", 2016, 2, 2024)])
    columns = [c.removesuffix("_TOT") for cols in population.AGE_GROUPS.values() for c in cols]
    rows = []
    for code, name in ((1, "Alder"), (3, "Birch")):
        for year in range(2, 11):
            row = {"COUNTY": code, "CTYNAME": f"{name} County", "YEAR": year}
            row |= {"POPESTIMATE": 1000 * len(columns), "POPEST_MALE": 600 * len(columns)}
            row |= {"POPEST_FEM": 400 * len(columns)}
            for c in columns:
                row |= {f"{c}_TOT": 1000, f"{c}_MALE": 600, f"{c}_FEM": 400}
            rows.append(row)
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(folder / "pep.csv", index=False)


def test_residents_by_sex_add_up(tmp_path, monkeypatch):
    _residents(tmp_path, monkeypatch)
    by_sex = population.residents(tmp_path, by_sex=True)
    assert set(by_sex.sex) == {"Male", "Female"}
    one = by_sex[(by_sex.year == 2023) & (by_sex.age_group == "10-14")]
    assert one.groupby("sex").residents.sum().to_dict() == {"Female": 800, "Male": 1200}


def test_the_profile_figures_match_ones_worked_out_by_hand(tmp_path, monkeypatch):
    _tables(tmp_path / "state")
    _residents(tmp_path / "pep", monkeypatch)
    text, drawn = profile.markdown(tmp_path / "state", tmp_path / "pep")
    assert "EpiCenter@cdph.ca.gov" in text
    assert set(drawn) == {
        "totals",
        "sexes",
        "vehicle",
        "ebike",
        "admitted",
        "trend_rates",
        "trend_vehicle",
    }
    assert all(
        svg.startswith("<svg") and f"<!-- chart: {n} -->" in text for n, svg in drawn.items()
    )
    # All riders, ages 10-14 over 2023-2024: 2 x 2,000 residents.  64 ED visits and 24
    # admissions: 1,600, 600 and 2,200 per 100,000; 24 of 88 admitted.
    assert "| 10–14 | 1,600.0 | 600.0 | 2,200.0 | 27% |" in text
    # Under-fives join a hidden "<1" ED cell to a published "1-4" one: a range.  ED 65
    # to 74, admissions 48; admitted 48 / (48 + 74) to 48 / (48 + 65).
    assert "| 0–4 | 1,625.0 to 1,850.0 | 1,200.0 | 2,825.0 to 3,050.0 | 39 to 43% |" in text
    # By sex, ages 10-14: women 28 of 2 x 800 (12 of 28 admitted), men 60 of 2 x 1,200
    # (12 of 60).  Under-fives: women 41 to 50, men 73 to 82, 24 admissions each.
    assert "| 10–14 | 1,750.0 | 2,500.0 | 43% | 20% |" in text
    assert "| 0–4 | 2,562.5 to 3,125.0 | 3,041.6 to 3,416.7 | 48 to 59% | 29 to 33% |" in text
    assert "left out: 15 emergency department visits and 0 admissions" in text
    # Motor vehicle by age, both sexes.  Ages 10-14: men 50, women two hidden cells (2
    # to 20), against 170 others.  Ages 15-19: women one hidden beside a published 20.
    assert "| 10–14 | 23 to 30% |" in text
    assert "| 15–19 | 29 to 32% |" in text
    # E-bikes: 80 of 220 treated; motor vehicle in 40 of 80, against 60 of 140.
    assert "| 10–14 | 36% | 50% | 43% |" in text
    assert "| Female | 36% | 50% | 43% |" in text and "| Male | 36% | 50% | 43% |" in text
    # Admitted, all ages: e-bikes 200 of 400 either way; others 200 of 600 and 200 of 800.
    assert "| Electric bicycle | 50% | 50% |" in text
    assert "| Other bicycle | 33% | 25% |" in text
    # Within each age, e-bikes 40 of 80 admitted, others 40 of 140: 40 / (80 x 2/7) = 1.75.
    assert profile.admission_ratio(tmp_path / "state") == (1.75, 1.75)
    assert "**E-bike injuries were admitted more often: about 1.8 times as often**" in text
    # Key points.  Men 553 to 562 treated over 600 a Census column, women 265 to 274 over
    # 400: 1.35 to 1.41, rounded outwards.  E-bikes, 80 in each of the ten EpiCenter age
    # groups: two of them in each of 10-19 and 25-64, so 2/10 each.
    assert "**Males were treated at 1.3 to 1.5 times the rate of females**" in text
    assert (
        "**By count, ages 10–19 and 25–64 cannot be told apart:** ages 25–64 had 20% of all "
        "e-bike injuries treated and ages 10–19 20%."
    ) in text
    assert "Caveat: an admitted patient's record is fuller" in text
    # Trends, under 15: four groups of 30 over 3 columns x 1,000 x 2 counties a year;
    # in 2016 one ED cell is hidden, so 91 to 100.
    assert "| 2016 | 1,516.6 to 1,666.7 |" in text and "| 2024 | 2,000.0 |" in text
    # Motor vehicle in (40 + 20) + (20 + 20) of 220; e-bikes 80 of 220, from 2023 only.
    assert "| 2016 | 45% | — |" in text and "| 2024 | 45% | 36% |" in text


def test_the_chance_intervals_match_standard_ones():
    from statsmodels.stats.proportion import proportion_confint

    part = pd.Series({"low": 40, "high": 40, "hidden": 0, "cells": 1})
    rest = pd.Series({"low": 60, "high": 60, "hidden": 0, "cells": 1})
    figure = profile.share_of(part, rest)
    wilson = proportion_confint(40, 100, method="wilson")
    assert figure["ci_low"] == pytest.approx(wilson[0]) and figure["ci_high"] == pytest.approx(
        wilson[1]
    )
    # A range: the lower limit at the lowest share (31 of 100), the upper at the highest (40 of 100).
    hidden = pd.Series({"low": 31, "high": 40, "hidden": 1, "cells": 2})
    ranged = profile.share_of(hidden, pd.Series({"low": 60, "high": 60}))
    assert ranged["ci_low"] == pytest.approx(proportion_confint(31, 91, method="wilson")[0])
    assert ranged["ci_high"] == pytest.approx(proportion_confint(40, 100, method="wilson")[1])
    # No cases among 100,000 resident-years: up to 3.69 a year by chance (exact Poisson).
    none = profile.rate_of(pd.Series({"low": 0, "high": 0, "hidden": 0, "cells": 1}), 1e5)
    assert none["ci_low"] == 0 and none["ci_high"] == pytest.approx(3.689, abs=1e-3)


def test_the_profile_needs_its_tables(tmp_path, monkeypatch):
    _tables(tmp_path / "state")
    _residents(tmp_path / "pep", monkeypatch)
    (tmp_path / "state" / "hosp_state_bike_cause_mech_sex.csv").unlink()
    record = tmp_path / "state" / tables.MANIFEST
    manifest = json.loads(record.read_text())
    del manifest["files"]["hosp_state_bike_cause_mech_sex.csv"]
    record.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="no manifest entry"):
        profile.markdown(tmp_path / "state", tmp_path / "pep")


def test_the_profile_leaves_out_trends_not_yet_pulled(tmp_path, monkeypatch):
    _tables(tmp_path / "state")
    _residents(tmp_path / "pep", monkeypatch)
    record = tmp_path / "state" / tables.MANIFEST
    manifest = json.loads(record.read_text())
    del manifest["files"]["ed_state_trend_total_year_age.csv"]
    record.write_text(json.dumps(manifest))
    text, drawn = profile.markdown(tmp_path / "state", tmp_path / "pep")
    assert "## Trends" not in text and "trend_rates" not in drawn and "totals" in drawn


def test_the_profile_command_writes_its_file(tmp_path, monkeypatch):
    _tables(tmp_path / "state")
    _residents(tmp_path / "pep", monkeypatch)
    common = ["--tables", str(tmp_path / "state"), "--residents", str(tmp_path / "pep")]
    profile.main([*common, "--out", str(tmp_path / "out")])
    assert [p.name for p in (tmp_path / "out").iterdir()] == ["hospital_profile_california.md"]


def test_the_census_download_keeps_only_a_county_table(tmp_path):
    good, bad = tmp_path / "good.csv", tmp_path / "bad.csv"
    good.write_text("SUMLEV,STATE,COUNTY,STNAME,CTYNAME,YEAR,POPESTIMATE\n")
    bad.write_text("<html>not found</html>\n")
    assert population._holds_county_table(good) and not population._holds_county_table(bad)
