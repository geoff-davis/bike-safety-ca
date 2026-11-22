"""Bicycle injury counts for one California county from CDPH EpiCenter
(California Injury Data Online, https://skylab4.cdph.ca.gov/epicenter/).

**You accept the EpiCenter user agreement yourself.**  The site opens with a
user agreement.  This module opens it in a browser window you can see and
waits for you to read it and click "I Agree"; it never clicks the agreement
for you, and it stops if the agreement closes any other way.  Among other
things the agreement asks that you cite CDPH/EpiCenter in any product, tell
EpiCenter@cdph.ca.gov of publications, and never try to identify individuals.
After you agree, leave the window alone while the tables are pulled.

EpiCenter tabulates non-fatal emergency department (ED) visits and
hospitalizations from HCAI discharge data. The finest geography is the county,
here county of residence; there is no city, ZIP or crash location. Counts under
11 are suppressed and saved as blanks. Bicycle injuries fall under two
mechanisms: "MVT-Pedal Cyclist" (a motor-vehicle traffic crash) and "Pedal
Cyclist, Other" (falls, paths, collisions with bikes or pedestrians). ICD-10-CM
electric (assisted) bicycle codes, in use from October 2022, are counted under
those same mechanisms and are separated here by injury cause description.
A visit can carry codes in both mechanisms, so mechanism rows can sum to more
than the unique visits; the ``total_*`` queries group without mechanism and give
unique counts. Hospitalizations are pulled with EpiCenter's comprehensive case
definition (an injury code anywhere on the record) and, as
``hosp_surveillance``, its surveillance definition (injury is the principal
diagnosis, the main reason for admission).

The site is a Shiny app with no API, so this module drives it with a
browser, one table at a time with pauses between settings.  By default it
pulls only the six tables the county and e-bike reports read
(``REPORT_TABLES``); ``--all`` pulls every table below, which takes much
longer, and ``--only`` names tables to pull again.  Playwright is not a
dependency; run with

    uv run --with playwright python -m bike_safety_ca.hospital.epicenter \
        --county "Santa Clara" --out data/raw/epicenter/santa_clara

Set EPICENTER_CHROMIUM to a Chromium executable if Playwright's own browser is
not installed.

One statewide table (no county filter, ``ed_state_*`` and ``hosp_state_*``)
compares electric and ordinary bicycles by age group for 2023–2024, the first
full years of the e-bike codes: county counts of e-bike admissions are mostly
suppressed.  It is saved with each county's tables.

Saved to the ``--out`` folder: <outcome>_<query>.csv (one row per table cell,
Count blank when suppressed) and epicenter_manifest.json (filters as the site
describes them, row counts, retrieval time, checksum and the source citation).
Use one folder per county: the file names do not name the county."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import os
from collections.abc import Collection
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bike_safety_ca.io import atomic_write_json, atomic_write_text

URL = "https://skylab4.cdph.ca.gov/epicenter/"
YEARS = (2016, 2024)
CITATION = "California Department of Public Health, EpiCenter – California Injury Data Online"
BIKE = ["Transportation: MVT-Pedal Cyclist", "Transportation: Pedal Cyclist, Other"]
# Element ids differ between the ED and hospitalization tabs.
OUTCOMES = {
    "ed": {
        "tab": "ED-Visits",
        "prefix": "ed_",
        "group": "ed_g",
        "year": "ed_year",
        "year_submit": "submitYearE",
        "age": "ed_age",
        "age_submit": "submitAgeE",
        "table": "edTable",
        "filter": "ed_filter_text",
    },
    "hosp": {
        "tab": "Hospitalizations",
        "prefix": "",
        "group": "g",
        "year": "year",
        "year_submit": "submitYearH",
        "age": "age",
        "age_submit": "submitAgeH",
        "table": "myTable",
        "filter": "pdd_filter_text",
        "case_definition": "No",
    },
    "hosp_surveillance": {
        "tab": "Hospitalizations",
        "prefix": "",
        "group": "g",
        "year": "year",
        "year_submit": "submitYearH",
        "age": "age",
        "age_submit": "submitAgeH",
        "table": "myTable",
        "filter": "pdd_filter_text",
        "case_definition": "Yes",
    },
}
# Filter-text wording of each hospitalization case definition (princ_dx radio).
CASE_DEFINITION_TEXT = {
    "No": "comprehensive case definition",
    "Yes": "surveillance case definition",
}
# Grouping labels that differ between the ED and hospitalization tabs.
GROUP_LABELS = {
    "Month": {"ed": "Service Month", "hosp": "Admission Month"},
    "Day of Week": {"ed": "Service Day of Week", "hosp": "Admission Day of Week"},
}
CAUSE_BY_AGE_GROUP = ["Injury Cause Description", "Age, Summary Groups"]
SCHOOL_AGE = (5, 17)
ED = ("ed",)
HOSP = ("hosp",)
SURVEILLANCE = ("hosp_surveillance",)
# name, age range, groupings, outcomes (None = ed and hosp, comprehensive definition)
QUERIES: list[tuple[str, tuple[int, int], list[str], tuple[str, ...] | None]] = [
    ("bike_year_under18", (0, 17), ["Year", "Injury Mechanism"], None),
    ("bike_year_adult", (18, 100), ["Year", "Injury Mechanism"], None),
    ("bike_age_groups", (0, 100), ["Injury Mechanism", "Age, Summary Groups"], None),
    ("bike_age_single", (0, 100), ["Age", "Injury Mechanism"], None),
    ("bike_year_age5_10", (5, 10), ["Year", "Injury Mechanism"], None),
    ("bike_year_age11_13", (11, 13), ["Year", "Injury Mechanism"], None),
    ("bike_year_age14_17", (14, 17), ["Year", "Injury Mechanism"], None),
    ("bike_cause_year", (0, 100), ["Injury Cause Description", "Injury Mechanism", "Year"], None),
    ("bike_cause_under18", (0, 17), ["Injury Cause Description", "Injury Mechanism"], None),
    ("bike_cause_school_age", SCHOOL_AGE, ["Injury Cause Description"], None),
    ("bike_cause_age5_10", (5, 10), ["Injury Cause Description", "Injury Mechanism"], None),
    ("bike_cause_age11_13", (11, 13), ["Injury Cause Description", "Injury Mechanism"], None),
    ("bike_cause_age14_17", (14, 17), ["Injury Cause Description", "Injury Mechanism"], None),
    ("bike_cause_year_under18", (0, 17), ["Injury Cause Description", "Year"], ED),
    ("bike_sex_school_age", SCHOOL_AGE, ["Sex", "Injury Mechanism"], None),
    ("bike_age_sex", (5, 18), ["Age", "Sex"], None),
    ("bike_month_school_age", SCHOOL_AGE, ["Month", "Injury Mechanism"], None),
    ("bike_weekday_school_age", SCHOOL_AGE, ["Day of Week", "Injury Mechanism"], None),
    ("bike_disposition_school_age", SCHOOL_AGE, ["Disposition", "Injury Mechanism"], None),
    ("bike_payer_school_age", SCHOOL_AGE, ["Expected Payer"], None),
    ("bike_stay_school_age", SCHOOL_AGE, ["Hospital Length of Stay"], HOSP),
    ("bike_stay_adult", (18, 100), ["Hospital Length of Stay", "Injury Mechanism"], HOSP),
    # Unique visits, without the (overlapping) mechanism split.
    ("total_year_under18", (0, 17), ["Year"], None),
    ("total_year_adult", (18, 100), ["Year"], None),
    ("total_age_groups", (0, 100), ["Age, Summary Groups"], None),
    ("total_year_age5_10", (5, 10), ["Year"], None),
    ("total_year_age11_13", (11, 13), ["Year"], None),
    ("total_year_age14_17", (14, 17), ["Year"], None),
    ("total_sex_school_age", SCHOOL_AGE, ["Sex"], None),
    ("total_month_school_age", SCHOOL_AGE, ["Month"], None),
    ("total_weekday_school_age", SCHOOL_AGE, ["Day of Week"], None),
    ("total_year_month_under18", (0, 17), ["Year", "Month"], ED),
    # Surveillance-definition hospitalizations, for admission-share sensitivity.
    ("bike_age_groups", (0, 100), ["Injury Mechanism", "Age, Summary Groups"], SURVEILLANCE),
    ("total_age_groups", (0, 100), ["Age, Summary Groups"], SURVEILLANCE),
    ("bike_sex_school_age", SCHOOL_AGE, ["Sex", "Injury Mechanism"], SURVEILLANCE),
    ("total_sex_school_age", SCHOOL_AGE, ["Sex"], SURVEILLANCE),
    ("bike_cause_school_age", SCHOOL_AGE, ["Injury Cause Description"], SURVEILLANCE),
]
# Statewide (no county filter), for the years with e-bike codes throughout.
STATEWIDE_YEARS = (2023, 2024)
STATEWIDE_QUERIES: list[tuple[str, tuple[int, int], list[str], tuple[str, ...] | None]] = [
    ("state_bike_cause_age_groups", (0, 100), CAUSE_BY_AGE_GROUP, None),
]
Scope = tuple[str | None, tuple[int, int], list[tuple[str, tuple[int, int], list[str], Any]]]
# The tables the county report and the e-bike report read (file names without
# ".csv"); the default pull.  A test keeps this in step with the two reports.
REPORT_TABLES = frozenset(
    {
        "ed_total_year_under18",
        "ed_total_year_adult",
        "ed_total_age_groups",
        "hosp_total_age_groups",
        "ed_state_bike_cause_age_groups",
        "hosp_state_bike_cause_age_groups",
    }
)
# How long to wait for the person to read the agreement and click "I Agree".
AGREEMENT_MS = 15 * 60_000


def scopes(county: str, years: tuple[int, int] = YEARS) -> list[Scope]:
    """County of residence (None = all of California), years and queries, in pull order."""
    return [(county, years, QUERIES), (None, STATEWIDE_YEARS, STATEWIDE_QUERIES)]


def plan(
    county: str, years: tuple[int, int] = YEARS, names: Collection[str] | None = None
) -> list[tuple[str, list[Scope]]]:
    """Each outcome tab with the scopes and queries to pull there, in pull order.

    ``names`` are table names (file names without ".csv"); None means every
    table.  Tabs and scopes with nothing to pull are left out.
    """
    steps = []
    for outcome in OUTCOMES:
        scoped: list[Scope] = []
        for where, span, queries in scopes(county, years):
            chosen = [
                q
                for q in queries
                if outcome in (q[3] or ("ed", "hosp"))
                and (names is None or f"{outcome}_{q[0]}" in names)
            ]
            if chosen:
                scoped.append((where, span, chosen))
        if scoped:
            steps.append((outcome, scoped))
    return steps


def table_names() -> list[str]:
    """Every table this module can pull, in pull order."""
    return [
        f"{outcome}_{q[0]}"
        for outcome, scoped in plan("any")
        for _where, _span, queries in scoped
        for q in queries
    ]


SETTLE_MS = 4000
POLLS = 40

log = logging.getLogger(__name__)

_SET_FILTERS = """([ids, county, mech]) => {
  const set = (id, v) => document.getElementById(id).selectize.setValue(v);
  set(ids.prefix + 'res_cnty', county ? [county] : []);
  set(ids.prefix + 'int', ['Unintentional']);
  set(ids.prefix + 'mech', mech);
}"""
_SET_RANGE = """([id, submit, lo, hi]) => {
  const inputs = document.querySelectorAll('#' + id + ' input');
  inputs[0].value = lo; inputs[1].value = hi;
  $(inputs).trigger('change'); $('#' + submit).click();
}"""
# The case-definition radio sits in a collapsed panel, so set it through jQuery.
_SET_CASE_DEFINITION = """(v) => $('input[name=princ_dx][value=' + v + ']')
  .prop('checked', true).trigger('change')"""
_SET_GROUP = """([id, value]) => $('#' + id).val(value).trigger('change')"""
# Notes a click on the agreement's "I Agree" button made by the person: a trusted
# event (a real mouse or keyboard action, not a script's .click()) on a button in
# the agreement dialog labelled exactly "I Agree".  Installed before the site's
# own scripts run, so an early click is not missed.  Nothing here clicks it.
_WATCH_AGREEMENT = """document.addEventListener('click', (e) => {
  const b = e.target instanceof Element ? e.target.closest('#shiny-modal button') : null;
  if (b && e.isTrusted && b.innerText.trim() === 'I Agree') window.__bscAgreed = true;
}, true);"""
_AGREED = "() => window.__bscAgreed === true"
_SHOWN_OR_AGREED = (
    "() => window.__bscAgreed === true || document.querySelector('#shiny-modal button') !== null"
)
_READ = """(ids) => {
  const t = $('#' + ids.table + ' table.dataTable').DataTable();
  return {columns: t.columns().header().toArray().map(h => h.innerText),
          rows: t.rows().data().toArray(),
          filter: document.getElementById(ids.filter).innerText,
          busy: document.documentElement.classList.contains('shiny-busy')};
}"""


def filters(text: str) -> dict[str, str]:
    """The filters the site says a table has, from its "filtered by:" lines."""
    lines = _filter_lines(text)
    if lines is None or len(dict(lines)) != len(lines):
        raise ValueError(f"filters named twice or unreadable: {text[:200]}")
    return dict(lines)


def _filter_lines(text: str) -> list[tuple[str, str]] | None:
    """Each filter line as (name, value); None if a line cannot be read as one."""
    if "filtered by:" not in text:
        return []
    found = []
    for line in text.split("filtered by:", 1)[1].splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            return None
        name, value = line.split(":", 1)
        found.append((name.strip(), value.strip()))
    return found


def accepts(
    result: dict,
    groups: list[str],
    ages: tuple[int, int],
    years: tuple[int, int],
    county: str | None,
    case_definition: str | None = None,
) -> bool:
    """Whether a table read from the page is the one asked for, and nothing else.

    The filters must be exactly the expected ones: an extra county, intent,
    mechanism or any other filter is refused, as is a missing one.
    """
    wanted = {"Injury Intent": "Unintentional", "Injury Mechanism": ", ".join(BIKE)}
    if county:
        wanted["County of Residence"] = county
    summary = result["filter"].split("filtered by:", 1)[0]
    lines = _filter_lines(result["filter"])
    return (
        not result["busy"]
        and result["columns"][1:-1] == groups
        and lines is not None
        and len(lines) == len(wanted)  # a filter named twice is refused
        and dict(lines) == wanted
        and f"from {years[0]} to {years[1]} " in summary
        and f"aged {ages[0]} to {ages[1]} " in summary
        and (case_definition is None or case_definition in summary)
    )


def _query(
    page: Any,
    outcome: str,
    ids: dict[str, str],
    ages: tuple[int, int],
    groups: list[str],
    county: str | None,
    years: tuple[int, int],
) -> dict:
    tab = outcome.split("_")[0]
    groups = [GROUP_LABELS.get(g, {}).get(tab, g) for g in groups]
    page.evaluate(_SET_FILTERS, [ids, county, BIKE])
    page.wait_for_timeout(SETTLE_MS)
    page.evaluate(_SET_RANGE, [ids["age"], ids["age_submit"], *ages])
    page.wait_for_timeout(SETTLE_MS)
    for i in range(1, 5):
        page.evaluate(_SET_GROUP, [f"{ids['group']}{i}", groups[i - 1] if i <= len(groups) else ""])
        page.wait_for_timeout(SETTLE_MS)
    # The table refreshes asynchronously; wait until it reflects every setting.
    definition = None
    if "case_definition" in ids:
        definition = CASE_DEFINITION_TEXT[ids["case_definition"]]
    previous = None
    for _ in range(POLLS):
        result = page.evaluate(_READ, ids)
        matches = accepts(result, groups, ages, years, county, definition)
        # Accept only a table that matches and is unchanged on a second read, so a
        # redraw still in progress (same headers, old rows) is not saved.  This
        # shows the table is steady, not that its rows belong to the summary
        # above it: check a new pull against the totals tables before using it.
        if matches and previous == result:
            return result
        previous = result if matches else None
        page.wait_for_timeout(3000)
    raise RuntimeError(f"EpiCenter table never matched {groups} {ages}: {result['filter'][:300]}")


def await_agreement(page: Any, timeout_ms: int = AGREEMENT_MS) -> None:
    """Wait for the person to click "I Agree" on the agreement; never click it.

    The page must have been opened with ``_WATCH_AGREEMENT`` as an init script.
    Stops unless the agreement closed after the person clicked "I Agree".
    """
    page.wait_for_function(_SHOWN_OR_AGREED, timeout=90_000)
    log.info('Read the EpiCenter user agreement in the browser window and click "I Agree".')
    page.wait_for_selector("#shiny-modal", state="hidden", timeout=timeout_ms)
    if page.evaluate(_AGREED) is not True:
        raise RuntimeError('The EpiCenter agreement closed without "I Agree"; nothing was pulled.')
    log.info("Agreed. Leave the window alone while the tables are pulled.")


def _csv(result: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    columns = result["columns"][1:]  # first column is the constant "Select"
    writer.writerow(columns)
    for row in result["rows"]:
        writer.writerow(["" if v is None else v for v in row[1:]])
    return buffer.getvalue()


def download(
    county: str,
    out: Path,
    years: tuple[int, int] = YEARS,
    names: Collection[str] | None = REPORT_TABLES,
) -> dict:
    """Pull the named tables (None = every table) for ``county`` into ``out``.

    Opens a visible browser and waits for the person to accept the EpiCenter
    user agreement themselves.
    """
    unknown = sorted(set(names or ()) - set(table_names()))
    if unknown:
        raise ValueError(f"no such EpiCenter tables: {', '.join(unknown)}")
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "source": URL,
        "citation": CITATION,
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "county_of_residence": county,
        "intent": "Unintentional",
        "mechanisms": BIKE,
        "years": list(years),
        "suppression": "counts under 11 are blank",
        "hospitalization_case_definitions": {
            "hosp": "comprehensive (injury code anywhere on the record)",
            "hosp_surveillance": "surveillance (injury is the principal diagnosis)",
        },
        "files": {},
    }
    # Files this run does not replace keep their entries; each has its own retrieved_at.
    record = out / "epicenter_manifest.json"
    if record.exists():
        earlier = json.loads(record.read_text())
        if earlier.get("county_of_residence") != county:
            raise ValueError(f"{out} holds another county's tables; use one folder per county")
        manifest["files"] = earlier["files"]
    with sync_playwright() as p:
        # Visible, so the person can read the agreement and click "I Agree" themselves.
        browser = p.chromium.launch(
            headless=False, executable_path=os.environ.get("EPICENTER_CHROMIUM")
        )
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.add_init_script(_WATCH_AGREEMENT)  # before the site's scripts: no click missed
        # The page's "load" event can hang on a slow asset; the modal wait below is the real test.
        page.goto(URL, wait_until="domcontentloaded", timeout=120_000)
        await_agreement(page)
        page.wait_for_timeout(1500)
        for outcome, scoped in plan(county, years, names):
            ids = OUTCOMES[outcome]
            page.click(f'a[data-value="{ids["tab"]}"]')
            page.wait_for_timeout(3000)
            if "case_definition" in ids:
                page.evaluate(_SET_CASE_DEFINITION, ids["case_definition"])
                page.wait_for_timeout(SETTLE_MS)
            for where, span, wanted in scoped:
                page.evaluate(_SET_RANGE, [ids["year"], ids["year_submit"], *span])
                page.wait_for_timeout(SETTLE_MS)
                for name, ages, groups, _outcomes in wanted:
                    result = _query(page, outcome, ids, ages, groups, where, span)
                    path = out / f"{outcome}_{name}.csv"
                    text = _csv(result)
                    atomic_write_text(path, text)
                    manifest["files"][path.name] = {
                        "ages": list(ages),
                        "groups": groups,
                        "county_of_residence": where or "all of California",
                        "years": list(span),
                        "rows": len(result["rows"]),
                        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
                        "site_filter_text": result["filter"],
                        "sha256": hashlib.sha256(text.encode()).hexdigest(),
                    }
                    # Saved with every file, so a run that stops later keeps this
                    # table's description.  A stop between the two writes can still
                    # leave them out of step; the checksum lets a reader detect it.
                    atomic_write_json(record, manifest)
                    log.info("%s: %d rows", path.name, len(result["rows"]))
        browser.close()
    return manifest


NOTICE = (
    "A browser window opens on EpiCenter's user agreement. Read it and click "
    '"I Agree" yourself; nothing is pulled until you do. It asks, among other things, '
    "that you cite CDPH/EpiCenter in any product, tell EpiCenter@cdph.ca.gov of "
    "publications, and never try to identify individuals."
)


def main(argv: list[str] | None = None) -> None:
    from bike_safety_ca.hospital.population import NAMES

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=NOTICE)
    parser.add_argument("--county", required=True, choices=NAMES, metavar="COUNTY")
    parser.add_argument("--out", type=Path, required=True, help="this county's folder")
    which = parser.add_mutually_exclusive_group()
    which.add_argument(
        "--all", action="store_true", help="every table, not just the six the reports read"
    )
    which.add_argument(
        "--only", nargs="+", metavar="TABLE", help="tables to pull, e.g. ed_total_age_groups"
    )
    args = parser.parse_args(argv)
    names = None if args.all else set(args.only) if args.only else REPORT_TABLES
    unknown = sorted(set(names or ()) - set(table_names()))
    if unknown:
        parser.error(f"no such tables: {', '.join(unknown)}")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log.info("%s", NOTICE)
    download(args.county, args.out, names=names)


if __name__ == "__main__":
    main()
