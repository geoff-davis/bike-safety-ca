"""Bike-route flags: does knowing where the bike lanes and routes are improve the ranking?

Each intersection is marked from the OpenStreetMap streets:

- "lane": within 20 m of a street tagged with a bike lane or track
  (``cycleway``, ``cycleway:left``, ``cycleway:right`` or ``cycleway:both``
  set to lane, track, buffered_lane, separate and the like);
- "route, no lane": not that, but within 20 m of a street on a mapped bike
  route (a way in a ``route=bicycle`` relation) or marked ``bicycle_road``,
  ``cyclestreet`` or ``bicycle=designated``;
- "neither".

For each hold-out window the street-length model is fitted with and without
the two flags as extra terms, and both are scored on later bike crashes. The
table gives the rank scores and top-100 shares, the fitted multipliers of the
flags (relative to "neither", or to the last group present when no site is
in neither), a likelihood-ratio p-value for them, and later crashes over the
model's expectation in each group. Windows where the model falls back to the
hand-built blend are not refitted.

Limits: the flags come from today's map, applied to past years; bike lanes
draw riders, so a flag mixes more exposure with any effect of the lane
itself; the windows overlap. All figures are totals, not individual records.

The bike-route relations are not in the street download: they are fetched from
Overpass once and saved beside it (``overpass_bike_routes.json``), or given
with ``--routes``.  ``--synthetic`` runs the check on the made-up city with
made-up flags and needs no data.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import chi2

from bike_safety_ca import CAR, CYCLISTS
from bike_safety_ca.checks.holdout import WINDOWS, Window, placed
from bike_safety_ca.config import load as load_config
from bike_safety_ca.download import osm
from bike_safety_ca.io import atomic_write_json, read_shapes
from bike_safety_ca.model.crash_history import (
    fit_street_model,
    rank_intersections,
    rank_score,
    top_share,
)
from bike_safety_ca.network.area import chosen as chosen_outlines
from bike_safety_ca.network.streets import path as street_path
from bike_safety_ca.network.streets import read_raw

LANE_KEYS = ("cycleway", "cycleway:left", "cycleway:right", "cycleway:both")
LANE_VALUES = {
    "lane",
    "track",
    "opposite_lane",
    "opposite_track",
    "buffered_lane",
    "separate",
}
NEAR_M = 20.0
GROUPS = ("lane", "route, no lane", "neither")
ROUTES = "overpass_bike_routes.json"


def tagged_ways(raw: dict[str, Any]) -> tuple[set[int], set[int]]:
    """Ids of the ways in an Overpass street answer with a bike lane, and of designated ones."""
    lane, designated = set(), set()
    for element in raw.get("elements", []):
        if element.get("type") != "way":
            continue
        tags = element.get("tags") or {}
        if any(tags.get(key) in LANE_VALUES for key in LANE_KEYS):
            lane.add(element["id"])
        if (
            tags.get("bicycle_road") == "yes"
            or tags.get("cyclestreet") == "yes"
            or (
                tags.get("bicycle") == "designated"
                and tags.get("highway") not in ("cycleway", "path", "footway")
            )
        ):
            designated.add(element["id"])
    return lane, designated


def route_ways(relations: dict[str, Any]) -> set[int]:
    """Ids of the ways that belong to a bike-route relation."""
    return {
        member["ref"]
        for relation in relations.get("elements", [])
        if relation.get("type") == "relation"
        for member in relation.get("members", [])
        if member.get("type") == "way"
    }


def flags(
    sites: gpd.GeoSeries, ways: gpd.GeoDataFrame, lane: set[int], route: set[int]
) -> pd.Series:
    """Each site's group: "lane", "route, no lane" or "neither" (see the module notes).

    ``sites`` and ``ways`` (with ``osm_id``) are in the same metre-based CRS.
    """

    def near(ids: set[int]) -> pd.Series:
        chosen = ways[ways.osm_id.isin(ids)]
        if chosen.empty:
            return pd.Series(False, index=sites.index)
        reach = sites.buffer(NEAR_M).intersects(chosen.geometry.union_all())
        return pd.Series(reach.to_numpy(), index=sites.index)

    by_lane, by_route = near(lane), near(route)
    group = np.select([by_lane, by_route], ["lane", "route, no lane"], "neither")
    return pd.Series(group, index=sites.index)


def compare(
    crashes: pd.DataFrame,
    sites: pd.Index,
    streets: Mapping[Any, Collection[str]],
    group: pd.Series,
    windows: Sequence[Window] = WINDOWS,
) -> pd.DataFrame:
    """One row per window: the model with and without the flags, scored on later bike crashes.

    ``crashes`` has ``site``, ``year`` and ``group`` as for ``holdout``;
    ``group`` gives each site's flag group.  All cyclists only.
    """

    def count(groups: list[str], first: int, last: int | None) -> pd.Series:
        years = crashes.year.ge(first) if last is None else crashes.year.between(first, last)
        chosen = crashes[crashes.group.isin(groups) & years]
        return chosen.groupby("site").size().reindex(sites, fill_value=0)

    group = group.reindex(sites)
    # One 0/1 column per group present, less a reference group, so the columns
    # never add up to the intercept: "neither" when any site has it, else the
    # last group present.  The multipliers are relative to the reference.
    present = [name for name in GROUPS if group.eq(name).any()]
    reference = present[-1] if present else None
    extra = pd.DataFrame(
        {name: group.eq(name) for name in present if name != reference}, index=sites
    ).astype(float)
    rows = []
    for train_to, test_from, test_to in windows:
        early, car = count(CYCLISTS, 0, train_to), count([CAR], 0, train_to)
        later = count(CYCLISTS, test_from, test_to)
        ranked = rank_intersections(early, car, streets)
        row: dict[str, Any] = {
            "trained through": train_to,
            "scored on": f"{test_from}–{test_to or 'latest'}",
            "later crashes": int(later.sum()),
            "method": ranked["method"],
            "rank score": rank_score(ranked["score"], later),
            "top 100": top_share(ranked["score"], later, 100),
            "reference group": reference,
        }
        if ranked["fit"] is not None and not extra.empty and later.sum() > 0:
            base = ranked["fit"]
            try:
                flagged = fit_street_model(early, car, streets, extra=extra)
            except (RuntimeError, ValueError, FloatingPointError) as error:
                row["note"] = f"fit with flags failed: {error}"
            else:
                row["rank score, flags"] = rank_score(flagged["sites"].eb, later)
                row["top 100, flags"] = top_share(flagged["sites"].eb, later, 100)
                for column in extra.columns:
                    row[f"multiplier, {column}"] = float(np.exp(flagged["powers"][column]))
                gain = 2 * (flagged["log_likelihood"] - base["log_likelihood"])
                row["p, flags"] = float(chi2.sf(max(gain, 0.0), len(extra.columns)))
            expected = base["sites"].eb * later.sum() / base["sites"].eb.sum()
            for name in GROUPS:
                inside = group.eq(name)
                if inside.any():
                    row[f"later / expected, {name}"] = float(
                        later[inside].sum() / expected[inside].sum()
                    )
        rows.append(row)
    return pd.DataFrame(rows)


def routes(raw: Path, out: Path, overwrite: bool = False) -> dict[str, Any]:
    """The bike-route relations in the box of the street download ``raw``, saved as ``out``.

    Fetched from Overpass once; a saved answer for another box is refused.
    """
    note = raw.with_name(raw.name.replace(".json", ".metadata.json"))
    box = json.loads(note.read_text())["bounds_west_south_east_north"]
    if out.exists() and not overwrite:
        saved: dict[str, Any] = json.loads(out.read_text())
        if saved.get("bounds_west_south_east_north") != list(box):
            raise ValueError(f"{out} was fetched for another box; pass --overwrite to replace it")
        return saved
    west, south, east, north = box
    query = f'[out:json][timeout:300];\nrelation["route"="bicycle"]({south},{west},{north},{east});\nout body;\n'
    answer = osm.run(query, require_elements=False)
    answer["bounds_west_south_east_north"] = list(box)
    answer["retrieved_at_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    answer["license"] = osm.LICENCE
    atomic_write_json(out, answer)
    return answer


def report(table: pd.DataFrame, shares: pd.Series) -> str:
    """The share of sites in each group, then the table, scores to three places."""
    lines = ["Share of intersections: " + ", ".join(f"{k} {v:.1%}" for k, v in shares.items())]
    shown = table.copy()
    for column in shown.columns:
        if shown[column].dtype.kind == "f":
            shown[column] = shown[column].round(1 if column.startswith("top 100") else 3)
    lines.append(shown.T.to_string(header=False, na_rep="–"))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--synthetic", action="store_true", help="use the made-up city")
    parser.add_argument("--config", type=Path, help="city settings (YAML)")
    parser.add_argument("--crashes", type=Path, default=Path("data/processed/crashes"))
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--area", type=Path, help="your own outline of the area")
    parser.add_argument("--routes", type=Path, help="saved Overpass answer of bike-route relations")
    parser.add_argument("--overwrite", action="store_true", help="fetch the relations again")
    parser.add_argument("--out", type=Path, help="also write the table to this CSV file")
    args = parser.parse_args()
    if args.synthetic:
        from bike_safety_ca.synthetic import make_city

        city = make_city()
        rng = np.random.default_rng(1)
        group = pd.Series(
            rng.choice(list(GROUPS), len(city.sites), p=[0.2, 0.1, 0.7]), index=city.sites.index
        )
        table = compare(city.crashes, city.sites.index, city.streets, group)
        title = "synthetic city, made-up flags"
    else:
        if not args.config:
            parser.error("give --synthetic or --config")
        config = load_config(args.config)
        outline_path = chosen_outlines(config, args.processed / "boundaries", args.area)["area"]
        assert outline_path is not None
        ways_path = street_path(args.processed / "network", config.crs)
        outline = read_shapes(outline_path).to_crs(config.crs).union_all()
        sites, streets, hits = placed(config, args.crashes, ways_path, outline)
        raw_path = config.streets_file or args.raw / "osm" / "overpass_streets.json"
        lane, designated = tagged_ways(read_raw(raw_path))
        relations = (
            json.loads(args.routes.read_text())
            if args.routes
            else routes(raw_path, raw_path.with_name(ROUTES), args.overwrite)
        )
        ways = gpd.read_parquet(ways_path, columns=["osm_id", "geometry"]).to_crs(config.crs)
        group = flags(sites.geometry, ways, lane, route_ways(relations) | designated)
        table = compare(hits, sites.index, streets.to_dict(), group, config.holdout_windows)
        title = config.city
    print(f"Bike-route flags, scored on later bike crashes ({title})")
    print(report(table, group.value_counts(normalize=True).reindex(GROUPS, fill_value=0)))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
