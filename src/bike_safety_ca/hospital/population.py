"""Residents of every California county by year and age group.

From the Census Bureau's Population Estimates Program county files by age and
sex (public domain, no key needed): the 2010–2020 intercensal estimates for
years to 2019 and the vintage 2024 estimates for 2020 on.  Each is the
resident population on 1 July.

The age groups are EpiCenter's summary groups, so a count and its population
line up.  EpiCenter splits children under five into "<1" and "1-4"; the Census
files do not, so the two are one group here, "0-4".

``python -m bike_safety_ca.hospital.population --out <folder>`` downloads the
two files into that folder.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from bike_safety_ca.download.census import _fetch  # the same Census Bureau server

BASE = "https://www2.census.gov/programs-surveys/popest/datasets"
# file, address, first July-1 year, the YEAR code of that year, last year used
SOURCES = [
    (
        "cc-est2020int-agesex-06.csv",
        f"{BASE}/2010-2020/intercensal/county/asrh/cc-est2020int-agesex-06.csv",
        2010,
        2,  # code 1 is the April 2010 estimates base, code 12 the April 2020 census
        2019,
    ),
    (
        "cc-est2024-agesex-06.csv",
        f"{BASE}/2020-2024/counties/asrh/cc-est2024-agesex-06.csv",
        2020,
        2,  # code 1 is the April 2020 base
        2024,
    ),
]
# EpiCenter summary age group -> the Census columns that make it up
AGE_GROUPS = {
    "0-4": ["AGE04_TOT"],
    "5-9": ["AGE59_TOT"],
    "10-14": ["AGE1014_TOT"],
    "15-19": ["AGE1519_TOT"],
    "20-24": ["AGE2024_TOT"],
    "25-44": ["AGE2529_TOT", "AGE3034_TOT", "AGE3539_TOT", "AGE4044_TOT"],
    "45-64": ["AGE4549_TOT", "AGE5054_TOT", "AGE5559_TOT", "AGE6064_TOT"],
    "65-84": ["AGE6569_TOT", "AGE7074_TOT", "AGE7579_TOT", "AGE8084_TOT"],
    "85+": ["AGE85PLUS_TOT"],
}
# EpiCenter's own labels for the two groups joined into "0-4"
UNDER_FIVE = ("<1", "&lt;1", "1-4")
COUNTIES = 58
CODES = range(1, 2 * COUNTIES, 2)  # California's county codes are the odd numbers 1 to 115
NAMES = (
    "Alameda",
    "Alpine",
    "Amador",
    "Butte",
    "Calaveras",
    "Colusa",
    "Contra Costa",
    "Del Norte",
    "El Dorado",
    "Fresno",
    "Glenn",
    "Humboldt",
    "Imperial",
    "Inyo",
    "Kern",
    "Kings",
    "Lake",
    "Lassen",
    "Los Angeles",
    "Madera",
    "Marin",
    "Mariposa",
    "Mendocino",
    "Merced",
    "Modoc",
    "Mono",
    "Monterey",
    "Napa",
    "Nevada",
    "Orange",
    "Placer",
    "Plumas",
    "Riverside",
    "Sacramento",
    "San Benito",
    "San Bernardino",
    "San Diego",
    "San Francisco",
    "San Joaquin",
    "San Luis Obispo",
    "San Mateo",
    "Santa Barbara",
    "Santa Clara",
    "Santa Cruz",
    "Shasta",
    "Sierra",
    "Siskiyou",
    "Solano",
    "Sonoma",
    "Stanislaus",
    "Sutter",
    "Tehama",
    "Trinity",
    "Tulare",
    "Tuolumne",
    "Ventura",
    "Yolo",
    "Yuba",
)  # in the order of the codes

log = logging.getLogger(__name__)


def download(out: Path, overwrite: bool = False) -> list[Path]:
    """Fetch the two Census files into ``out``; returns their paths."""
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, url, *_ in SOURCES:
        dest = out / name
        if overwrite or not dest.exists():
            _fetch(url, dest)
        paths.append(dest)
    return paths


def tidy(raw: pd.DataFrame, first_year: int, first_code: int, last_year: int) -> pd.DataFrame:
    """One Census file as rows of county, year, age group and residents.

    ``raw`` has the file's columns; ``first_code`` is the YEAR code of 1 July
    ``first_year``.  Codes before it (census counts and estimate bases) and
    years after ``last_year`` are left out.
    """
    named = set(zip(raw.COUNTY.astype(int), raw.CTYNAME))
    if named != {(code, f"{name} County") for code, name in zip(CODES, NAMES)}:
        raise ValueError("the file does not hold California's counties under their own codes")
    year = raw.YEAR.astype(int) - first_code + first_year
    kept = raw[(year >= first_year) & (year <= last_year)]
    year = year[kept.index]
    total = kept.POPESTIMATE.astype(int)
    parts = {group: kept[columns].astype(int).sum(axis=1) for group, columns in AGE_GROUPS.items()}
    wide = pd.DataFrame(parts)
    if not wide.sum(axis=1).eq(total).all():
        raise ValueError("the age groups do not add up to the county totals")
    wide.insert(0, "year", year)
    wide.insert(0, "county", kept.CTYNAME.str.removesuffix(" County"))
    long = wide.melt(["county", "year"], var_name="age_group", value_name="residents")
    return long.sort_values(["county", "year"]).reset_index(drop=True)


def residents(folder: Path) -> pd.DataFrame:
    """Residents by county, year (2010 on) and age group, from the saved files."""
    frames = []
    for name, _url, first_year, first_code, last_year in SOURCES:
        raw = pd.read_csv(folder / name, encoding="latin-1", dtype=str)
        frames.append(tidy(raw, first_year, first_code, last_year))
    table = pd.concat(frames, ignore_index=True)
    years = range(SOURCES[0][2], SOURCES[-1][4] + 1)
    counties = sorted(table.county.unique())
    complete = pd.MultiIndex.from_product([counties, years, AGE_GROUPS])
    found = pd.MultiIndex.from_frame(table[["county", "year", "age_group"]])
    if (
        len(counties) != COUNTIES
        or found.has_duplicates
        or not found.sort_values().equals(complete.sort_values())
    ):
        raise ValueError(
            f"expected {COUNTIES} counties, each with every age group in every year "
            f"{years[0]}–{years[-1]}, once"
        )
    if table.residents.isna().any() or (table.residents < 0).any():
        raise ValueError("a missing or negative resident count")
    return table


def age_group(label: str) -> str:
    """EpiCenter's summary age group as named here ("<1" and "1-4" are "0-4")."""
    label = str(label).strip()
    if label in UNDER_FIVE:
        return "0-4"
    if label not in AGE_GROUPS:
        raise KeyError(f"unknown age group: {label}")
    return label


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="folder for the two files")
    parser.add_argument("--overwrite", action="store_true", help="download again if present")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for path in download(args.out, args.overwrite):
        log.info("saved %s", path)
