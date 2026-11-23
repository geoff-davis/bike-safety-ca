"""Crash summaries and the movement map: ``python -m bike_safety_ca.report --config ...``.

Steps: ``summary`` (tables of totals, printed and written as CSV) and ``map``
(the crash movement map).  With no step named, both run.  Everything goes to
``output/``, which is git-ignored.  The map shows individual crash records,
with the TIMS and CCRS credits.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from bike_safety_ca import age_label
from bike_safety_ca import config as settings
from bike_safety_ca.cli import chosen_steps
from bike_safety_ca.io import read_shapes
from bike_safety_ca.network import area as outlines
from bike_safety_ca.network import streets as street_table
from bike_safety_ca.report import crashes as crash_table
from bike_safety_ca.report import movement, ranking, summary

STEPS = ["summary", "map"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("steps", nargs="*", help=f"any of: {' '.join(STEPS)} (default: all)")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--crashes", type=Path, default=Path("data/processed/crashes"))
    parser.add_argument("--area", type=Path, help="your own outline of the area")
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    parser.add_argument("--out", type=Path, default=Path("output"))
    parser.add_argument(
        "--ranking",
        type=Path,
        help="the model's intersection_ranking.csv: adds a switch to its top corners on the"
        " map and writes top_corners.md beside it",
    )
    parser.add_argument("--top", type=int, default=20, help="how many top corners (default 20)")
    parser.add_argument("--pdf", action="store_true", help="also print top_corners.pdf")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="build the map library into the page, so it opens with no internet connection",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = settings.load(args.config)
    steps = chosen_steps(parser, args.steps, STEPS)
    chosen = outlines.chosen(config, args.processed / "boundaries", args.area)
    assert chosen["area"] is not None
    outline = read_shapes(chosen["area"]).to_crs(config.crs).union_all()
    crashes = crash_table.load(args.crashes, config, outline)
    parties = pd.read_parquet(args.crashes / "parties_merged.parquet")
    if "summary" in steps:
        scopes = {"area": crashes, config.city.lower().replace(" ", "_"): crashes[crashes.in_city]}
        for scope, rows in scopes.items():
            found = summary.tables(rows, parties, config.child_max_age)
            found = {  # headings follow the config's child age
                name: table.rename(
                    index=lambda v: age_label(v, config.child_max_age) if isinstance(v, str) else v,
                    columns=lambda v: (
                        age_label(v, config.child_max_age) if isinstance(v, str) else v
                    ),
                )
                for name, table in found.items()
            }
            for name, table in found.items():
                print(f"\n{scope}: {name.replace('_', ' ')}\n{table.to_string()}")
            for written in summary.write(found, args.out / "summary", scope):
                logging.info("wrote %s", written)
    top = ranking.top(args.ranking, args.top) if args.ranking else None
    if "map" in steps:
        ways = gpd.read_parquet(street_table.path(args.processed / "network", config.crs))
        limit = chosen["city_limit"]
        centre = read_shapes(limit).geometry if limit is not None else None
        written = movement.build(
            crashes,
            parties[movement.PARTY_COLUMNS],
            ways,
            config,
            args.out / "crash_movement_map.html",
            centre,
            area=outline,
            offline=args.offline,
            ranked=ranking.markers(top) if top is not None else None,
        )
        logging.info("wrote %s", written)
    if top is not None:
        years = (int(crashes.year.min()), int(crashes.year.max()))
        for written in ranking.write(top, config.city, years, args.out, args.pdf):
            logging.info("wrote %s", written)


if __name__ == "__main__":
    main()
