"""Get the area and its streets: ``python -m bike_safety_ca.network --config config/<city>.yaml``.

Steps, in order: ``area`` (outline of the config's cities, from Census
boundary files), ``download`` (OpenStreetMap streets inside the outline's
bounding box, through the Overpass API) and ``build`` (the street table the
hold-out check reads).  With no step named, all three run; downloads already
on disk are not fetched again.  ``--area`` uses your own outline, in any
format GeoPandas reads, instead of the one built from the city list.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import httpx

from bike_safety_ca import config as settings
from bike_safety_ca.cli import chosen_steps
from bike_safety_ca.download import arcgis, census, osm, schools
from bike_safety_ca.network import area, streets

STEPS = ["area", "download", "build"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("steps", nargs="*", help=f"any of: {' '.join(STEPS)} (default: all)")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--area", type=Path, help="your own outline of the area")
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--out", type=Path, default=Path("data/processed"))
    parser.add_argument("--overwrite", action="store_true", help="download again")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = settings.load(args.config)
    steps = chosen_steps(parser, args.steps, STEPS)
    if "area" in steps:
        sources = census.download(args.raw / "boundaries", overwrite=args.overwrite)
        own_limit = None
        if config.city_limit_url:
            # A saved layer from another address is refused (ValueError) and stops
            # the command; only a failed fetch falls back to the Census outline.
            try:
                own_limit = arcgis.download(
                    config.city_limit_url,
                    args.raw / "boundaries" / "city_limit.geojson",
                    overwrite=args.overwrite,
                )
            except (httpx.HTTPError, arcgis.FetchError) as error:
                logging.warning(
                    "could not fetch the city's own limit (%s); using the Census outline", error
                )
        directory = None
        if config.area_schools:
            directory = schools.download(
                args.raw / "schools" / schools.NAME, overwrite=args.overwrite
            )
        built = area.build(sources, args.out / "boundaries", config, own_limit, directory)
        for written in built.values():
            logging.info("wrote %s", written)
    if "download" in steps and config.streets_file is None:
        outline = area.chosen(config, args.out / "boundaries", args.area)["area"]
        assert outline is not None
        osm.download(
            streets.area_bounds(outline),
            args.raw / "osm",
            overwrite=args.overwrite,
            date=config.osm_date,
        )
    if "build" in steps:
        raw_streets = config.streets_file or args.raw / "osm" / "overpass_streets.json"
        written = streets.build(raw_streets, args.out / "network", config.crs)
        logging.info("wrote %s", written)


if __name__ == "__main__":
    main()
