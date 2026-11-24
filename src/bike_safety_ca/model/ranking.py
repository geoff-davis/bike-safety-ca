"""The intersection ranking for a built city, written as a CSV and a GeoJSON file.

``rank`` reads the crash and street tables the other commands build, places
each crash at an intersection as the hold-out check does, and ranks every
intersection from all years of crashes with ``rank_intersections``.  The files
give crash counts for single corners: read "Crash records" in ``docs/guide.md``
before passing them on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from bike_safety_ca import CAR, CHILD, CYCLISTS, age_label
from bike_safety_ca.checks.holdout import placed
from bike_safety_ca.config import Config
from bike_safety_ca.io import CRS_WGS84, crs_tag, read_shapes
from bike_safety_ca.model import crash_history
from bike_safety_ca.network import junctions
from bike_safety_ca.network.area import chosen as chosen_outlines
from bike_safety_ca.network.streets import path as street_path

STEM = "intersection_ranking"
COLUMNS = [
    "rank",
    "intersection",
    "streets",
    "street_keys",
    "major",
    "minor",
    "in_city",
    "score",
    "expected_bike_crashes",
    "observed_bike_crashes",
    "car_crashes",
    "method",
    "spread_power",
    "fallback_reason",
    "longitude",
    "latitude",
]


class RankingError(ValueError):
    """A ranking that cannot be made as asked; the message says what to do."""


def inputs(
    config: Config, crash_folder: Path, processed: Path, area: Path | None = None
) -> dict[str, Path | None]:
    """The files the ranking reads, checked to be there.

    ``processed`` holds the ``boundaries`` and ``network`` folders written by
    ``python -m bike_safety_ca.network``.  The outlines are chosen as the other
    commands choose them: ``area`` if given, else the config's, else the built
    ones.
    """
    outlines = chosen_outlines(config, processed / "boundaries", area)
    network = "python -m bike_safety_ca.network --config <file>"
    crashes = "python -m bike_safety_ca.crashes --config <file>"
    needed = {
        "area outline": (outlines["area"], network),
        "street table": (street_path(processed / "network", config.crs), network),
        "crash table": (crash_folder / f"crashes_merged_{crs_tag(config.crs)}.parquet", crashes),
        "party table": (crash_folder / "parties_merged.parquet", crashes),
    }
    missing = [
        f"{name} not found: {path} (made by `{command}`)"
        for name, (path, command) in needed.items()
        if path is None or not path.exists()
    ]
    limit = outlines["city_limit"]
    if limit is not None and not limit.exists():
        missing.append(f"city limit not found: {limit} (made by `{network}`)")
    if missing:
        raise RankingError("; ".join(missing))
    return {
        "area": outlines["area"],
        "city_limit": limit,
        "ways": needed["street table"][0],
        "crashes": crash_folder,
    }


def rank(
    config: Config,
    crash_folder: Path,
    ways: Path,
    area: Path,
    city_limit: Path | None = None,
    children: bool = False,
    force: bool = False,
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Every intersection in ``area``, best rank first, and how the ranking was made.

    The table has ``COLUMNS`` and point geometry in longitude and latitude.
    ``streets`` is the intersection's mapped street names (the first three) and
    ``street_keys`` every street that meets there, as ``junctions.road_key``
    names it.
    ``score`` is what the rank follows.  ``expected_bike_crashes`` is the
    model's estimate over the years of crashes used, and is empty when the
    hand-built blend was used, whose score only orders intersections.
    ``in_city`` is empty without a city limit.

    With ``children`` the ranking is built from child cyclist crashes only.
    Under ``crash_history.MIN_CRASHES`` of them (the number below which
    ``rank_intersections`` does not fit the model) that is refused, since the all-cyclist
    ranking finds later child crashes better there; ``force`` builds it anyway.

    The second value holds ``method``, ``reason`` (why the blend was used, else
    ``None``), ``outcome`` and the ``bike_crashes`` and ``car_crashes`` counted
    at the ``intersections``.
    """
    outline = read_shapes(area).to_crs(config.crs).union_all()
    sites, streets, hits = placed(config, crash_folder, ways, outline)
    groups = [CHILD] if children else CYCLISTS
    outcome = age_label(
        "cyclists 18 or under" if children else "all cyclists", config.child_max_age
    )
    bike = junctions.count_at(hits[hits.group.isin(groups)], sites.index)
    car = junctions.count_at(hits[hits.group.eq(CAR)], sites.index)
    total = int(bike.sum())
    floor = crash_history.MIN_CRASHES  # the model's own floor, not a second number
    if children and total < floor and not force:
        raise RankingError(
            f"{total} crashes of {outcome} at intersections, fewer than {floor}: too few "
            "for a ranking of their own. Use the all-cyclist ranking (leave out --children), "
            "fit on a wider area, or pass --force to build it anyway."
        )
    ranked = crash_history.rank_intersections(bike, car, streets.to_dict())
    fit = ranked["fit"]
    points = sites.geometry.to_crs(CRS_WGS84)
    inside: pd.Series = pd.Series(pd.NA, index=sites.index, dtype="boolean")
    if city_limit is not None:
        limit = read_shapes(city_limit).to_crs(config.crs).union_all()
        inside = sites.geometry.within(limit).astype("boolean")
    table = pd.DataFrame(
        {
            "intersection": sites.index,
            "streets": sites.name,
            "street_keys": streets.map(lambda keys: "; ".join(sorted(keys))),
            "major": sites.major,
            "minor": sites.minor,
            "in_city": inside,
            "score": ranked["score"],
            "expected_bike_crashes": fit["sites"].eb if fit is not None else float("nan"),
            "observed_bike_crashes": bike,
            "car_crashes": car,
            "method": ranked["method"],
            "spread_power": fit["spread_power"] if fit is not None else float("nan"),
            "fallback_reason": ranked["reason"] or "",
            "longitude": points.x.round(6),
            "latitude": points.y.round(6),
        },
        index=sites.index,
    )
    # Sort first, round after: rounding must not reorder close scores.
    table = table.sort_values("score", ascending=False, kind="stable")
    table = table.round({"score": 4, "expected_bike_crashes": 4})
    table.insert(0, "rank", range(1, len(table) + 1))
    summary = {
        "method": ranked["method"],
        "reason": ranked["reason"],
        "outcome": outcome,
        "bike_crashes": total,
        "car_crashes": int(car.sum()),
        "intersections": len(table),
    }
    ranking = gpd.GeoDataFrame(
        table[COLUMNS].reset_index(drop=True),
        geometry=list(points.reindex(table.index)),
        crs=CRS_WGS84,
    )
    return ranking, summary


def describe(summary: dict[str, Any]) -> str:
    """One line for the terminal: the method used and the crashes it was built from."""
    built_from = (
        f"{summary['bike_crashes']:,} bike crashes ({summary['outcome']}) and "
        f"{summary['car_crashes']:,} motor-vehicle-only crashes at "
        f"{summary['intersections']:,} intersections"
    )
    if summary["reason"] is None:
        return f"Method: {summary['method']}, fitted on {built_from}."
    return (
        f"Method: {summary['method']} ({summary['reason']}), nothing fitted; ranked from "
        f"{built_from}. The score only puts the intersections in order."
    )


def write(
    ranking: gpd.GeoDataFrame, out: Path, children: bool = False, top: int | None = None
) -> dict[str, Path]:
    """Write the ranking, or its ``top`` highest-ranked rows, as a CSV and a GeoJSON file."""
    if top is not None:
        ranking = ranking.head(top)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{STEM}_children" if children else STEM
    written = {"csv": out / f"{stem}.csv", "geojson": out / f"{stem}.geojson"}
    pd.DataFrame(ranking.drop(columns="geometry")).to_csv(written["csv"], index=False)
    ranking.to_file(written["geojson"], driver="GeoJSON")
    return written
