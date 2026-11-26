"""Crash summaries and the movement map: ``python -m bike_safety_ca.report --config ...``.

Steps: ``summary`` (tables of totals, printed and written as CSV) and ``map``
(the crash movement map).  With no step named, both run.  Everything goes to
``output/``, which is git-ignored.  The map shows individual crash records,
with the TIMS and CCRS credits.
"""

from __future__ import annotations

import argparse
import json
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


def framing_url(framing: settings.Print, page: Path) -> str:
    """The map page's address that opens on ``framing``.

    An ``at`` is looked up among the intersections the page draws, and must name exactly one.
    """
    url = page.resolve().as_uri() + ("?view=risk" if framing.view == "risk" else "")
    centre = framing.centre
    if framing.at is not None:
        text = page.read_text()
        drawn, _ = json.JSONDecoder().raw_decode(text, text.index("const SITES=") + 12)
        found = [(s["lat"], s["lon"]) for s in drawn if s.get("n") == framing.at]
        if len(found) != 1:
            raise ValueError(
                f"prints: {framing.name}: {len(found) or 'no'} intersections on the map are "
                f"named {framing.at!r}; use the name exactly as the map shows it, or a centre"
            )
        centre = found[0]
    if centre is None:
        return url  # the map's opening view
    return f"{url}#{centre[0]:.5f},{centre[1]:.5f},{framing.zoom:g}"


def print_framings(
    framings: tuple[settings.Print, ...], page: Path, out: Path, ranked: bool
) -> list[Path]:
    """Print each framing of the map page to ``<name>.pdf`` in ``out``.

    ``ranked`` says whether the page has ranked corners, which a risk framing needs: without
    them the page has no risk view.  Every framing is checked before anything is printed.
    """
    from bike_safety_ca.hospital import pdf as printer

    for framing in framings:
        if framing.view == "risk" and not ranked:
            raise ValueError(
                f"prints: {framing.name}: a risk framing needs ranked corners (--ranking with"
                " corners in the city), and this map has no ranked corners"
            )
    urls = [(framing.name, framing_url(framing, page)) for framing in framings]
    return [printer.print_url(url, out / f"{name}.pdf", wait_ms=15000) for name, url in urls]


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
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="print the config's map framings (prints:) when the map is made; with --ranking,"
        " also top_corners.pdf, and predicted_risk.pdf (the map's risk view with its list of"
        " corners)",
    )
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
    # None with no crashes to date them: the map is then the streets alone.
    years = (int(crashes.year.min()), int(crashes.year.max())) if len(crashes) else None
    # The ranking's own years, where it records them: its counts and estimates are for those.
    ranked_years = ranking.period(args.ranking, years) if args.ranking else years
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
            ranked=ranking.markers(top, ranked_years) if top is not None else None,
            circles=ranking.circles(args.ranking, ranked_years) if args.ranking else None,
        )
        logging.info("wrote %s", written)
        if top is not None and args.pdf:
            if top.empty:  # the page has no risk view to print
                logging.warning("no ranked corner in the city: predicted_risk.pdf not printed")
            else:
                from bike_safety_ca.hospital import pdf as printer

                risk = written.parent / "predicted_risk.pdf"
                printer.print_url(written.resolve().as_uri() + "?view=risk", risk, wait_ms=15000)
                logging.info("wrote %s", risk)
        if args.pdf and config.prints:
            ranked = top is not None and not top.empty
            for target in print_framings(config.prints, written, args.out, ranked):
                logging.info("wrote %s", target)
    if top is not None:
        for written in ranking.write(top, config.city, ranked_years, args.out, args.pdf):
            logging.info("wrote %s", written)


if __name__ == "__main__":
    main()
