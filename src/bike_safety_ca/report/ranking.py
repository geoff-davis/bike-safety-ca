"""The model's top-ranked intersections: a layer for the crash map and a one-page list.

Both read the ranking the model writes (``intersection_ranking.csv``, see
``bike_safety_ca.model``) and keep its highest-ranked intersections inside
the city limit, or in the whole area when the ranking has no city limit.
Each corner's line says, in plain words, what the model saw there: the
roads that meet, the crashes recorded and the model's estimate.

The estimate is of police-recorded bike crashes over the whole period the
ranking was built from, the same years as the recorded counts beside it.  It
is not a rate per year and not a forecast of a later period.
"""

from __future__ import annotations

import html
import math
from pathlib import Path
from typing import Any

import pandas as pd

from bike_safety_ca import links

# Corners with an estimate under this many bike crashes, over the years used, get no circle:
# most of a city's intersections, and too small to see.
FLOOR = 0.5

CREDIT = (
    "*Data: crash records from the Transportation Injury Mapping System (TIMS), Safe "
    "Transportation Research and Education Center, University of California, Berkeley, and "
    "the California Crash Reporting System (CCRS), California Highway Patrol, via "
    "data.ca.gov. Streets © OpenStreetMap contributors (ODbL).*"
)


def top(path: Path, n: int = 20) -> pd.DataFrame:
    """The ``n`` highest-ranked intersections: in the city when the ranking has a city
    limit (none, if no corner lies inside it), otherwise in the whole area."""
    return _in_city(pd.read_csv(path)).head(n).reset_index(drop=True)


def _in_city(table: pd.DataFrame) -> pd.DataFrame:
    # The model writes ``in_city`` empty when there is no city limit.
    if "in_city" in table and table.in_city.notna().any():
        table = table[table.in_city.astype(str).str.lower().eq("true")]
    return table.sort_values("rank")


def period(path: Path, otherwise: tuple[int, int] | None) -> tuple[int, int] | None:
    """The years of crashes the ranking was built from, as the ranking records them.

    ``otherwise`` is used for a ranking written before it recorded its years.
    """
    table = pd.read_csv(path, nrows=1)
    if {"first_year", "last_year"} <= set(table.columns) and len(table):
        first, last = table.first_year.iloc[0], table.last_year.iloc[0]
        if pd.notna(first) and pd.notna(last):
            return int(first), int(last)
    return otherwise


def circles(path: Path, years: tuple[int, int] | None, floor: float = FLOOR) -> dict[str, Any]:
    """The city's intersections where the model's estimate is at least ``floor`` bike
    crashes over ``years``, as [lat, lon, estimate, streets] for the risk circles; none
    when the blend was used."""
    table = _in_city(pd.read_csv(path))
    expected = pd.to_numeric(table.expected_bike_crashes, errors="coerce")
    keep = expected >= floor
    rows = zip(
        table.latitude[keep].astype(float).tolist(),
        table.longitude[keep].astype(float).tolist(),
        expected[keep].astype(float).tolist(),
        table.streets[keep].astype(str).tolist(),
        strict=True,
    )
    return {
        "y": _period(years),
        "c": [[round(la, 6), round(lo, 6), round(e, 2), n] for la, lo, e, n in rows],
    }


def _period(years: tuple[int, int] | None) -> str:
    return f"{years[0]}–{years[1]}" if years else "the years used"


def _gaps(table: pd.DataFrame) -> bool:
    """Whether the area ranks skip numbers: the area reaches beyond the city."""
    ranks = table["rank"].astype(int).tolist()
    return ranks != list(range(1, len(ranks) + 1))


def _count(value: Any, one: str, many: str) -> str:
    number = int(value)
    return f"{number} {one if number == 1 else many}"


def _a(word: str) -> str:
    return f"{'an' if word[:1] in 'aeiou' else 'a'} {word}"


def why(row: pd.Series, years: tuple[int, int] | None = None) -> str:
    """What the model saw at a corner, in plain words.

    The recorded counts and the model's estimate are both for ``years``.  A
    corner ranked by the blend has no estimate, and none is given.
    """
    major, minor = str(row.major).lower(), str(row.minor).lower()
    if isinstance(row.minor, str) and minor != major:
        roads = f"{_a(major)} meets {_a(minor)}"
    else:
        roads = f"{major}s meet"
    seen = (
        f"Recorded in {_period(years)}: "
        f"{_count(row.observed_bike_crashes, 'bike crash', 'bike crashes')} and "
        f"{_count(row.car_crashes, 'car-only crash', 'car-only crashes')}."
    )
    expected = row.expected_bike_crashes
    if isinstance(expected, int | float) and not math.isnan(expected):
        seen += f" Model estimate for the same years: about {expected:.1f} bike crashes."
    return f"{roads[0].upper()}{roads[1:]}. {seen}"


def markers(table: pd.DataFrame, years: tuple[int, int] | None = None) -> list[dict[str, Any]]:
    """The corners as the crash map draws them: rank, name, place and why."""
    return [
        {
            "r": int(row["rank"]),
            "c": place + 1,
            "n": str(row.streets),
            "lat": round(float(row.latitude), 6),
            "lon": round(float(row.longitude), 6),
            "w": why(row, years),
        }
        for place, (_, row) in enumerate(table.iterrows())
    ]


def markdown(table: pd.DataFrame, city: str, years: tuple[int, int] | None) -> str:
    """The one-page list of the top corners."""
    method = str(table.method.iloc[0]) if len(table) else "street-length model"
    lines = [
        f"# Where the crash model ranks highest: {city}",
        "",
        f"The {len(table)} intersections in {city} that the crash model ranks highest, from "
        f"police-recorded injury crashes in {_period(years)} ({method}). A model estimate is "
        "of the bike crashes recorded at the corner over those same years; it is not a count "
        "per year or a forecast. A rank "
        "is a place worth a closer look, not a finding: deciding what is wrong at a corner, "
        "and what to change, is for an engineer who has looked at it.",
        "",
    ]
    # Ranks are the city's own, 1 to n; the area's rank is shown too when it differs.
    gaps = _gaps(table)
    lines += (
        ["| Rank | Rank in area | Intersection | What the model saw |", "|---:|---:|---|---|"]
        if gaps
        else ["| Rank | Intersection | What the model saw |", "|---:|---|---|"]
    )
    for place, (_, row) in enumerate(table.iterrows(), start=1):
        area = f" {int(row['rank'])} |" if gaps else ""
        lines.append(f"| {place} |{area} {html.escape(str(row.streets))} | {why(row, years)} |")
    note = (
        "*The rank in area is among all intersections in the area the model was fitted on, "
        "which reaches beyond the city. "
        if gaps
        else "*"
    )
    lines += [
        "",
        f"{note}A small crash count can reflect chance as well as the road. The model "
        "weighs each corner's bike crashes against "
        "its car crashes and the roads that meet, so a corner with few bike crashes can "
        "rank high when its streets are busy. Its estimate is a number of recorded crashes "
        f"at the corner, not one cyclist's risk on a trip through it.* {CREDIT}",
        "",
        "*How the model works, and how well it ranked corners in 28 California cities: "
        f"[{links.MODEL_DOC.removeprefix('https://')}]({links.MODEL_DOC}).*",
        "",
        links.MADE_WITH,
    ]
    return "\n".join(lines)


def write(
    table: pd.DataFrame, city: str, years: tuple[int, int] | None, out: Path, pdf: bool
) -> list[Path]:
    """Write ``top_corners.md``, and ``top_corners.pdf`` when ``pdf`` is set."""
    text = markdown(table, city, years)
    out.mkdir(parents=True, exist_ok=True)
    written = [out / "top_corners.md"]
    written[0].write_text(text + "\n")
    if pdf:
        from bike_safety_ca.hospital import pdf as printer

        written.append(printer.write("top_corners", text, {}, out))
    return written
