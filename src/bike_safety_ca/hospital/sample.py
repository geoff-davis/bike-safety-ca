"""A county report on made-up counts, to show what one looks like: ``python -m bike_safety_ca.hospital.sample``.

Every count here is invented, for an invented "Sample County" in an invented
two-county state, and laid out the way EpiCenter's tables are.  Nothing is
taken from, fitted to or checked against CDPH data or a real county.  The
report itself is the real code (``report.markdown`` and ``pdf.write``), so
hidden cells, held-back groups and ranges come out as they would for a real
county.  The CDPH credit, which would be false here, is replaced with a
made-up-data notice on every page.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from bike_safety_ca.hospital import epicenter, pdf, population, report, tables

COUNTY = "Sample"
NOTICE = (
    "Made-up counts for an invented county, laid out as the report lays out CDPH EpiCenter "
    "tables, to show what a county report looks like. None of these figures is real."
)
GROUPS = ["<1", "1-4", "5-9", "10-14", "15-19", "20-24", "25-44", "45-64", "65-84", "85+"]
# Visits and admissions over 2016–2024, by age; None is a hidden cell.
VISITS: list[int | None] = [None, 200, 1100, 2100, 1300, 600, 2600, 2900, 900, 40]
ADMISSIONS: list[int | None] = [None, None, 30, 70, 60, 35, 160, 260, 140, 12]
# Visits by year: under 18, then 18 and over.  They add up to the age table
# above with 5 in its hidden cell.
UNDER_18: list[int | None] = [520, 500, 480, 450, 470, 430, 410, 400, 390]
ADULT: list[int | None] = [760, 780, 810, 840, 1030, 930, 880, 850, 815]
CAUSES = [
    "Pedal cyclist injured in collision with car, pick-up truck or van in traffic accident",
    "Pedal cyclist (driver) injured in noncollision transport accident",
    "Electric (assisted) bicycle driver injured in noncollision transport accident",
    "Electric (assisted) bicycle driver injured in collision with car in traffic accident",
]
# Statewide visits and admissions over 2023–2024 per cause (as above), by age.
STATE: dict[str, list[list[int | None]]] = {
    "ed": [
        [40, 900, 2600, 4200, 3100, 1500, 6000, 6500, 2400, 150],
        [60, 1500, 4300, 6900, 4900, 2200, 8200, 8900, 3800, 300],
        [None, 20, 300, 1900, 1300, 400, 1500, 1200, 300, None],
        [None, None, 60, 500, 420, 150, 600, 450, 90, None],
    ],
    "hosp": [
        [None, 40, 150, 330, 320, 210, 900, 1300, 650, 60],
        [None, 30, 110, 240, 190, 90, 500, 900, 600, 70],
        [None, None, 15, 120, 110, 40, 200, 260, 110, None],
        [None, None, None, 40, 45, 20, 90, 110, 30, None],
    ],
}
# Residents in each Census five-year age column in 2016, growing 0.5% a year.
RESIDENTS = {COUNTY: 62_000, "Rest of the state": 2_000_000}


def grown(size: int, year: int) -> int:
    return round(size * 1.005 ** (year - epicenter.YEARS[0]))


def _save(folder: Path, name: str, frame: pd.DataFrame, county: str | None) -> None:
    """One table and its manifest entry, as the downloader would write them."""
    state = county is None
    first, last = epicenter.STATEWIDE_YEARS if state else epicenter.YEARS
    ages = tables._ages()[f"{name}.csv"]
    filters = ["Injury Intent: Unintentional", "Injury Mechanism: " + ", ".join(epicenter.BIKE)]
    if not state:
        filters.insert(0, f"County of Residence: {county}")
    summary = f"Counts from {first} to {last} for residents aged {ages[0]} to {ages[1]} "
    if name.startswith("hosp"):
        summary += "(comprehensive case definition) "
    text = frame.to_csv(index=False)
    (folder / f"{name}.csv").write_text(text)
    record = folder / tables.MANIFEST
    manifest = json.loads(record.read_text()) if record.exists() else {"files": {}}
    manifest["files"][f"{name}.csv"] = {
        "site_filter_text": summary + "filtered by:\n" + "\n".join(filters),
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
    }
    record.write_text(json.dumps(manifest))


def build_tables(folder: Path) -> None:
    """The made-up county's tables and the made-up state's, in one folder."""
    folder.mkdir(parents=True, exist_ok=True)
    years = range(epicenter.YEARS[0], epicenter.YEARS[1] + 1)
    for name, counts in (("ed_total_year_under18", UNDER_18), ("ed_total_year_adult", ADULT)):
        _save(folder, name, pd.DataFrame({"Year": years, "Count": counts}), COUNTY)
    for name, counts in (("ed_total_age_groups", VISITS), ("hosp_total_age_groups", ADMISSIONS)):
        _save(folder, name, pd.DataFrame({report.AGE: GROUPS, "Count": counts}), COUNTY)
    for outcome, by_cause in STATE.items():
        rows = [
            {report.CAUSE: cause, report.AGE: age, "Count": count}
            for cause, counts in zip(CAUSES, by_cause, strict=True)
            for age, count in zip(GROUPS, counts, strict=True)
        ]
        _save(folder, f"{outcome}_state_bike_cause_age_groups", pd.DataFrame(rows), None)


def build_residents(folder: Path) -> None:
    """Census-style resident files for the made-up state's two counties."""
    folder.mkdir(parents=True, exist_ok=True)
    columns = [c for cols in population.AGE_GROUPS.values() for c in cols]
    for name, _url, first_year, first_code, last_year in population.SOURCES:
        rows = [
            {"COUNTY": code, "CTYNAME": f"{county} County", "YEAR": first_code + offset}
            | {"POPESTIMATE": grown(size, first_year + offset) * len(columns)}
            | dict.fromkeys(columns, grown(size, first_year + offset))
            for code, (county, size) in zip((1, 3), RESIDENTS.items(), strict=True)
            for offset in range(last_year - first_year + 1)
        ]
        pd.DataFrame(rows).to_csv(folder / name, index=False)


@contextlib.contextmanager
def made_up_state() -> Iterator[None]:
    """Let ``population`` read a state of two counties, and keep the CDPH credit off.

    The report checks a county against California's 58; here there are two.
    """
    changes = [
        (population, "COUNTIES", 2),
        (population, "CODES", range(1, 4, 2)),
        (population, "NAMES", tuple(RESIDENTS)),
        (pdf, "STYLE", pdf.STYLE.replace(pdf.CREDIT, "Made-up counts: not CDPH data")),
    ]
    saved = [(module, name, getattr(module, name)) for module, name, _ in changes]
    try:
        for module, name, value in changes:
            setattr(module, name, value)
        yield
    finally:
        for module, name, value in saved:
            setattr(module, name, value)


def markdown(folder: Path) -> tuple[str, dict[str, str]]:
    """The made-up county's report, with the notice in place of the CDPH credit and sharing note."""
    build_tables(folder / "tables")
    build_residents(folder / "residents")
    with made_up_state():
        text, charts = report.markdown(folder / "tables", folder / "residents", COUNTY)
    for real in (report.CREDIT, f"**{report.SHARING}**"):
        if real not in text:
            raise ValueError("the report's credit or sharing note has changed: update the sample")
        text = text.replace(real, "")
    # The source paragraph would say these counts came from CDPH.
    paragraphs = text.split("\n\n")
    sources = [i for i, p in enumerate(paragraphs) if p.startswith("**Source.**")]
    if len(sources) != 1:
        raise ValueError("the report's source paragraph has changed: update the sample")
    paragraphs[sources[0]] = f"**Source.** {NOTICE}"
    text = "\n\n".join(paragraphs)
    # The appendix says where a real report's counts and residents come from.
    for real, here in (
        ("as published by EpiCenter.", "made up here (a real report uses EpiCenter's)."),
        (
            "Residents are the Census Bureau's yearly county estimates,",
            "Residents are made up here"
            " (a real report uses the Census Bureau's yearly county estimates),",
        ),
    ):
        if text.count(real) != 1:
            raise ValueError("the report's appendix has changed: update the sample")
        text = text.replace(real, here)
    paragraphs = text.split("\n\n")
    title, rest = "\n\n".join(paragraphs).split("\n", 1)
    return f"{title}\n\n**{NOTICE}**\n{rest}", charts


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=Path("output/hospital_sample"))
    parser.add_argument("--pdf", action="store_true", help="print a PDF too (needs Chrome)")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as folder:
        text, charts = markdown(Path(folder))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "hospital_sample.md").write_text(text)
    if args.pdf:
        with made_up_state():
            pdf.write("hospital_sample", text, charts, args.out)


if __name__ == "__main__":
    main()
