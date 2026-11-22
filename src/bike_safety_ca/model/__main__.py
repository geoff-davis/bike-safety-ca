"""Rank a built city's intersections: ``python -m bike_safety_ca.model --config ...``.

Reads the street table and outlines (``python -m bike_safety_ca.network``) and
the crash tables (``python -m bike_safety_ca.crashes``), ranks every
intersection from all years of crashes, and writes
``intersection_ranking.csv`` and ``intersection_ranking.geojson``.  The files
give crash counts for single corners, so they go to ``output/``, which is
git-ignored.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bike_safety_ca import config as settings
from bike_safety_ca.model import crash_history, ranking


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="city settings (YAML)")
    parser.add_argument("--crashes", type=Path, default=Path("data/processed/crashes"))
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    parser.add_argument("--area", type=Path, help="your own outline of the area")
    parser.add_argument("--out", type=Path, default=Path("output/ranking"))
    parser.add_argument(
        "--children",
        action="store_true",
        help=f"rank from child cyclist crashes only; refused under {crash_history.MIN_CRASHES} of them",
    )
    parser.add_argument(
        "--force", action="store_true", help="with --children: rank even with too few crashes"
    )
    parser.add_argument("--top", type=int, metavar="N", help="write only the N highest-ranked")
    args = parser.parse_args()
    if args.top is not None and args.top < 1:
        parser.error("--top must be 1 or more")
    config = settings.load(args.config)
    try:
        found = ranking.inputs(config, args.crashes, args.processed, args.area)
        assert found["ways"] is not None and found["area"] is not None
        table, summary = ranking.rank(
            config,
            args.crashes,
            found["ways"],
            found["area"],
            found["city_limit"],
            args.children,
            args.force,
        )
    except ranking.RankingError as error:
        raise SystemExit(f"error: {error}") from None
    print(f"Intersection ranking ({config.city}, {summary['outcome']})")
    print(ranking.describe(summary))
    for path in ranking.write(table, args.out, args.children, args.top).values():
        print(f"wrote {path}")
    print("These files give crash counts for single corners: read them before passing them on.")


if __name__ == "__main__":
    main()
