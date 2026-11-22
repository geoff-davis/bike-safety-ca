"""Reading the EpiCenter tables saved by ``bike_safety_ca.hospital.epicenter``.

Source: California Department of Public Health, EpiCenter – California Injury
Data Online.  The tables are published county-level totals; counts under 11
are suppressed and appear here as missing values.  Nothing here works out a
suppressed count from other figures.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from bike_safety_ca.hospital import epicenter

MANIFEST = "epicenter_manifest.json"
KIND = {
    "Transportation: MVT-Pedal Cyclist": "Traffic",
    "Transportation: Pedal Cyclist, Other": "Other",
}


def _ages() -> dict[str, tuple[int, int]]:
    """The age range each saved table was pulled for, by file name."""
    found = {}
    for outcome in epicenter.OUTCOMES:
        for name, ages, _groups, outcomes in epicenter.QUERIES + epicenter.STATEWIDE_QUERIES:
            if outcome in (outcomes or ("ed", "hosp")):
                found[f"{outcome}_{name}.csv"] = ages
    return found


def _manifest(folder: Path) -> dict:
    return json.loads((Path(folder) / MANIFEST).read_text())


def table(folder: Path, name: str) -> pd.DataFrame:
    """One saved table, refused unless the manifest says what it holds."""
    if f"{name}.csv" not in _manifest(folder)["files"]:
        raise ValueError(f"{name} has no manifest entry: what it holds is not on record")
    d = pd.read_csv(Path(folder) / f"{name}.csv")
    if "Injury Mechanism" in d:
        d["kind"] = d["Injury Mechanism"].map(KIND)
    return d


def check_source(
    folder: Path,
    county: str | None,
    years: tuple[int, int],
    state_years: tuple[int, int] = epicenter.STATEWIDE_YEARS,
    required: tuple[str, ...] = (),
) -> None:
    """Stop unless every saved table is the county and years a report assumes.

    Tables pulled for another county or period would otherwise be divided by
    the wrong residents without a word.  The filters the site recorded must be
    exactly bicycle injuries, unintentional, for the table's own ages and (for
    a county table) the county, with nothing else.  ``required`` names tables
    (without ".csv") that must have a manifest entry.  A table without a
    checksum, or changed since its manifest entry was written, is refused too.  With ``county`` None only the
    statewide tables are checked, for a statewide report.
    """
    folder = Path(folder)
    manifest = _manifest(folder)
    absent = [name for name in required if f"{name}.csv" not in manifest["files"]]
    if absent:
        raise ValueError(f"no manifest entry for {absent}")
    for name, entry in manifest["files"].items():
        state = "_state_" in name
        if county is None and not state:
            continue
        text = entry["site_filter_text"]
        definition = "surveillance" if name.startswith("hosp_surveillance") else "comprehensive"
        if name.startswith("hosp") and f"{definition} case definition" not in text:
            raise ValueError(f"{name} does not use the {definition} case definition")
        found = epicenter.filters(text)
        first, last = state_years if state else years
        if found.get("County of Residence") != (None if state else county) or (
            f"from {first} to {last} " not in text
        ):
            where = "all of California" if state else f"{county} County"
            raise ValueError(f"{name} is not {where} {first}–{last}: {text[:120]}")
        wanted = {"Injury Intent": "Unintentional", "Injury Mechanism": ", ".join(epicenter.BIKE)}
        if not state:
            wanted["County of Residence"] = str(county)
        ages = _ages().get(name)
        if found != wanted or ages is None or f"aged {ages[0]} to {ages[1]} " not in text:
            raise ValueError(f"{name} is not the table of that name: {text[:200]}")
        if "sha256" not in entry:
            raise ValueError(f"{name} has no checksum in the manifest: pull it again")
        if entry["sha256"] != hashlib.sha256((folder / name).read_bytes()).hexdigest():
            raise ValueError(f"{name} has changed since its manifest entry was written")


def whole[Counts: (pd.Series, pd.DataFrame)](counts: Counts, what: str) -> Counts:
    """The counts, once it is certain none is suppressed.

    A sum skips a blank cell as if it were zero, so every total stated as
    exact goes through here first.
    """
    hidden = int(counts.isna().to_numpy().sum())
    if hidden:
        raise ValueError(f"{what}: {hidden} suppressed cells in an exact total")
    return counts
