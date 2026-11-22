"""Build the crash tables: ``python -m bike_safety_ca.crashes --config config/<city>.yaml``.

Steps, in order: ``download`` (CCRS from data.ca.gov), ``tims`` (read the
hand-made TIMS exports), ``merge`` (combine the two and place crashes that
have no coordinates).  With no step named, ``tims`` and ``merge`` run.

Placing crashes from their street names uses ``--centerlines`` when given.
Otherwise it uses the street table and Census city outlines that
``python -m bike_safety_ca.network`` writes, when they are where that command
puts them (``--streets`` and ``--boundaries`` say where else), so run the
network command first.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import geopandas as gpd

from bike_safety_ca import config as settings
from bike_safety_ca.cli import chosen_steps
from bike_safety_ca.config import Config
from bike_safety_ca.crashes import merge, tims
from bike_safety_ca.crashes.locate import streets_as_centerlines
from bike_safety_ca.download import ccrs, census
from bike_safety_ca.network import area
from bike_safety_ca.network.streets import path as street_path


def street_lines(config: Config, streets: Path, boundaries: Path) -> gpd.GeoDataFrame | None:
    """The street table as a centerline layer, or None when a file is missing."""
    places = boundaries / f"{census.names()['places']}.zip"
    if not streets.exists() or not places.exists():
        logging.warning("no street table (%s) or city outlines (%s)", streets, places)
        return None
    cities = area.incorporated(gpd.read_file(places))
    return streets_as_centerlines(gpd.read_parquet(streets).to_crs(config.crs), cities)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("steps", nargs="*", help="download, tims, merge (default: tims merge)")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/crashes"))
    parser.add_argument("--out", type=Path, default=Path("data/processed/crashes"))
    parser.add_argument("--centerlines", type=Path, help="road centerlines (GeoParquet)")
    parser.add_argument("--streets", type=Path, help="street table (default: beside --out)")
    parser.add_argument("--boundaries", type=Path, help="Census outlines (default: beside --raw)")
    parser.add_argument("--overwrite", action="store_true", help="download every year again")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = settings.load(args.config)
    steps = chosen_steps(parser, args.steps, ["download", "tims", "merge"], ["tims", "merge"])
    if "merge" in steps and args.centerlines is not None and not args.centerlines.exists():
        parser.error(f"--centerlines {args.centerlines} does not exist")
    if "download" in steps:
        ccrs.download(config, args.raw / "ccrs", overwrite=args.overwrite)
    if "tims" in steps and not tims.build(
        args.raw / "tims", args.out, config.crs, config.agency_reassignments
    ):
        raise SystemExit(1)
    if "merge" in steps:
        lines = None
        if args.centerlines is None:
            lines = street_lines(
                config,
                args.streets or street_path(args.out.parent / "network", config.crs),
                args.boundaries or args.raw.parent / "boundaries",
            )
        if not merge.build(args.raw / "ccrs", args.out, config, args.centerlines, lines):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
