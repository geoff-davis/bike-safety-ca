"""Hold-out check: how well do rankings built on early crashes find later ones?

Each ranking uses only crashes up to a cut-off year and is scored on the bike
crashes after it.  All figures are counts per ranking, not individual records.

``python -m bike_safety_ca.checks.holdout --synthetic`` runs the check on the
made-up city and needs no data.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Collection, Mapping, Sequence
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry.base import BaseGeometry

from bike_safety_ca import CAR, CHILD, CYCLISTS, age_label
from bike_safety_ca.config import Config
from bike_safety_ca.config import load as load_config
from bike_safety_ca.io import read_shapes
from bike_safety_ca.model.crash_history import (
    MIN_CRASHES,
    fit_history_model,
    rank_intersections,
    rank_score,
    street_blend_score,
    top_share,
)
from bike_safety_ca.network.area import chosen as chosen_outlines
from bike_safety_ca.network.streets import path as street_path

Window = tuple[int, int, int | None]
Streets = Mapping[Any, Collection[str]]
Rankings = Callable[[pd.Series, pd.Series], Mapping[str, pd.Series]]

WINDOWS: tuple[Window, ...] = ((2018, 2019, 2022), (2020, 2021, 2022), (2022, 2023, None))
OUTCOMES = {"All cyclists": CYCLISTS, "Cyclists 18 or under": [CHILD]}
TOPS = (25, 50, 100)
# Fewer later crashes than this and a rank score says little: its uncertainty is
# roughly 0.09 either way at 10 crashes and 0.05 at 30.
MIN_LATER = 30


MODEL = "Street-length model"
EARLIER_MODEL = "Crash history with same-street averages"
# For an outcome that is part of all cyclists (children): the all-cyclist model's
# ranking, scored on that outcome's later crashes.
ALL_CYCLISTS = "All-cyclist ranking"
log = logging.getLogger(__name__)


def rankings(
    early: pd.Series, car: pd.Series, streets: Streets
) -> tuple[dict[str, pd.Series], str]:
    """Score per intersection for each ranking, from crashes in the training years.

    Also says which method ``rank_intersections`` used for the model's row.
    """
    ranked = rank_intersections(early, car, streets)
    scores = {
        "Past bike crashes": early.astype(float),
        "Bike + car crashes, added": (early + car).astype(float),
        "Bike x car crashes, blended with street averages": street_blend_score(early, car, streets),
    }
    try:
        scores[EARLIER_MODEL] = fit_history_model(early, car, streets)["sites"].eb
    except Exception as error:  # noqa: BLE001 - too few crashes to fit; the row is left out
        log.warning("%s not fitted, row left out: %s", EARLIER_MODEL, error)
    scores[MODEL] = ranked["score"]
    return scores, ranked["method"]


def holdout(
    crashes: pd.DataFrame,
    sites: pd.Index,
    streets: Streets,
    windows: Sequence[Window] = WINDOWS,
    areas: Mapping[str, pd.Index] | None = None,
    extra: Rankings | None = None,
    min_later: int = MIN_LATER,
) -> pd.DataFrame:
    """One row per window, outcome, area and ranking.

    ``crashes`` has one row per crash already placed at an intersection, with
    columns ``site``, ``year`` and ``group``.  ``areas`` names subsets of
    ``sites`` to score separately.  The ``method`` column shows where the
    street-length model's row fell back to the hand-built blend for want of
    crashes, and ``training crashes`` is the number of the outcome's crashes
    the rankings were built from.  ``extra`` may add rankings from another
    model: it is given the early bike and car counts per intersection.

    An outcome that is only some cyclists also gets an "All-cyclist ranking"
    row: the model fitted to every cyclist crash, scored on that outcome's
    later crashes.  Where the outcome has few crashes of its own this is the
    ranking to use, and the row shows what is given up or gained by it.

    Where an area has fewer than ``min_later`` later crashes of an outcome, the
    row keeps the count and its rank score and found-in-top figures are left
    empty: a score on a handful of crashes is close to those crashes' own ranks.
    """
    areas = {"All intersections": sites, **(areas or {})}

    def count(groups: list[str], first: int, last: int | None) -> pd.Series:
        years = crashes.year.ge(first) if last is None else crashes.year.between(first, last)
        chosen = crashes[crashes.group.isin(groups) & years]
        return chosen.groupby("site").size().reindex(sites, fill_value=0)

    rows = []
    for train_to, test_from, test_to in windows:
        car = count([CAR], 0, train_to)
        everyone = rankings(count(CYCLISTS, 0, train_to), car, streets)
        for outcome, groups in OUTCOMES.items():
            early, later = count(groups, 0, train_to), count(groups, test_from, test_to)
            whole = set(groups) == set(CYCLISTS)
            scores, method = everyone if whole else rankings(early, car, streets)
            scores = dict(scores)
            if extra is not None:
                scores.update(extra(early, car))
            methods = {MODEL: method}
            if not whole:
                scores[ALL_CYCLISTS], methods[ALL_CYCLISTS] = everyone[0][MODEL], everyone[1]
            for area, index in areas.items():
                target = later.reindex(index)
                enough = int(target.sum()) >= min_later
                for name, score in scores.items():
                    score = score.reindex(index)
                    rows.append(
                        {
                            "trained through": train_to,
                            "tested on": f"{test_from}–{test_to or 'latest'}",
                            "outcome": outcome,
                            "area": area,
                            "ranking": name,
                            "method": methods.get(name, name),
                            "training crashes": int(early.sum()),
                            "later crashes": int(target.sum()),
                            "rank score": round(rank_score(score, target), 3)
                            if enough
                            else float("nan"),
                            **{
                                f"found in top {k}": round(top_share(score, target, k), 1)
                                if enough
                                else float("nan")
                                for k in TOPS
                            },
                        }
                    )
    return pd.DataFrame(rows)


def _cell(score: float, count: int, min_later: int) -> str:
    if pd.notna(score):
        return f"{score:.3f}"
    # Enough crashes and still no score: every intersection had one, so nothing to compare.
    return f"too few ({count})" if count < min_later else "no score"


def wide(table: pd.DataFrame, min_later: int = MIN_LATER) -> pd.DataFrame:
    """Rank scores as text, one row per ranking and one column per test period.

    A period with too few later crashes to score shows the count instead, and
    the mean is over the scored periods only.  ``min_later`` is the floor the
    table was made with.
    """
    keys = ["area", "outcome", "ranking"]
    cells = [
        _cell(score, count, min_later)
        for score, count in zip(table["rank score"], table["later crashes"])
    ]
    out = table.assign(cell=cells).pivot_table(
        index=keys, columns="tested on", values="cell", aggfunc="first", sort=False
    )
    mean = table.groupby(keys, sort=False)["rank score"].mean()
    out["mean"] = [f"{m:.3f}" if pd.notna(m) else "none scored" for m in mean.reindex(out.index)]
    return out


def report(table: pd.DataFrame, min_later: int = MIN_LATER) -> str:
    """``wide`` as printed text."""
    return str(wide(table, min_later).to_string())


def notes(table: pd.DataFrame) -> list[str]:
    """What to say under the report where a ranking had too few crashes to be fitted."""
    blend = table[(table.ranking == MODEL) & (table.method != "street-length model")]
    partial = set(table.outcome[table.ranking == ALL_CYCLISTS])
    lines = []
    for _, row in blend.drop_duplicates(["trained through", "outcome"]).iterrows():
        where = f"{row.outcome}, trained through {row['trained through']}"
        if row["training crashes"] >= MIN_CRASHES:
            # Enough crashes, but the fit failed: the blend stands in, with no other advice.
            lines.append(f"the model could not be fitted, so the blend was used: {where}")
            continue
        line = f"too few crashes to fit: {where} ({row['training crashes']} crashes)"
        if row.outcome in partial:
            line += f"; rank this group by the {ALL_CYCLISTS.lower()} instead"
        lines.append(line)
    return lines


def placed(
    config: Config,
    crash_folder: Path,
    ways: Path,
    outline: BaseGeometry,
    check_names: bool = True,
    max_cluster_m: float | None = None,
) -> tuple[gpd.GeoDataFrame, pd.Series, pd.DataFrame]:
    """Intersections inside ``outline``, their street names, and the crashes placed at them.

    The two options are passed to ``assign_in_area`` and ``build_junctions``.
    A crash recorded just outside the outline counts at an intersection
    inside it.
    """
    from bike_safety_ca.crashes import groups
    from bike_safety_ca.network import junctions
    from bike_safety_ca.network import streets as street_table

    lines = gpd.read_parquet(ways, columns=street_table.COLUMNS)
    sites, streets = junctions.build_junctions(lines, outline, max_cluster_m)
    # Out to the edge reach: a crash at a corner on the outline can be
    # recorded a few metres outside it (see ``assign_in_area``).
    reach = outline.buffer(junctions.EDGE_REACH_M)
    crashes = groups.load(crash_folder, config.crs, config.child_max_age, reach)
    crashes = crashes[crashes.group.isin([*CYCLISTS, CAR]) & crashes.year.ge(config.first_year)]
    hits = junctions.assign_in_area(
        crashes, sites.geometry, streets, lines, outline, check_names, max_cluster_m
    )
    return sites, streets, hits


def city_holdout(
    config: Config, crash_folder: Path, ways: Path, area: Path, city_limit: Path | None = None
) -> pd.DataFrame:
    """Run the check on real crash tables.

    ``ways`` is a GeoParquet of OpenStreetMap streets in the config's
    coordinate system, as written by
    ``python -m bike_safety_ca.network``, ``area`` a polygon file of the
    area the crash tables cover, and ``city_limit`` an optional polygon whose
    intersections are also scored on their own, under the city's name.
    """
    outline = read_shapes(area).to_crs(config.crs).union_all()
    sites, streets, hits = placed(config, crash_folder, ways, outline)
    areas = {}
    if city_limit is not None:
        limit = read_shapes(city_limit).to_crs(config.crs).union_all()
        areas[config.city] = sites.index[sites.geometry.within(limit)]
    return holdout(hits, sites.index, streets.to_dict(), config.holdout_windows, areas)


KEYS = ["trained through", "outcome", "area", "ranking"]


def compare(table: pd.DataFrame, expected: pd.DataFrame) -> str:
    """Empty if ``table`` has the same rows and figures as ``expected``, else what differs."""
    for name, frame in (("the new table", table), ("the saved table", expected)):
        repeats = int(frame.duplicated(KEYS).sum())
        if repeats:
            return f"{name} has {repeats} repeated rows"
    both = table.merge(expected, on=KEYS, how="outer", suffixes=("", " expected"), indicator=True)
    unmatched = int(both["_merge"].ne("both").sum())
    if unmatched:
        return f"{unmatched} rows are in only one of the two tables"
    figures = [
        c
        for c in expected.columns
        if c not in KEYS and c in table and expected[c].dtype.kind in "if"
    ]
    problems = [f"{c} is missing" for c in expected.columns if c not in table]
    for column in expected.columns:
        if column in KEYS or column in figures or column not in table:
            continue
        differs = int((both[column].astype(str) != both[f"{column} expected"].astype(str)).sum())
        if differs:
            problems.append(f"{column} differs in {differs} rows")
    for column in figures:
        got, want = both[column], both[f"{column} expected"]
        missing = int((got.isna() != want.isna()).sum())
        if missing:
            problems.append(f"{column} is missing in one table for {missing} rows")
        gap = (got - want).abs().max()
        if pd.notna(gap) and gap > 1e-9:
            problems.append(f"{column} differs by up to {float(gap):g}")
    return ", ".join(problems)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic", action="store_true", help="use the made-up city")
    parser.add_argument("--config", type=Path, help="city settings (YAML)")
    parser.add_argument("--crashes", type=Path, default=Path("data/processed/crashes"))
    parser.add_argument(
        "--processed",
        type=Path,
        default=Path("data/processed"),
        help="folder holding the built boundaries and network folders",
    )
    parser.add_argument("--ways", type=Path, help="street table (default: the one in --processed)")
    parser.add_argument("--area", type=Path, help="your own outline of the area")
    parser.add_argument("--city-limit", type=Path, help="your own outline scored on its own")
    parser.add_argument("--expect", type=Path, help="a saved table the result must match")
    parser.add_argument("--out", type=Path, help="also write the full table to this CSV file")
    args = parser.parse_args()
    if args.synthetic:
        from bike_safety_ca.synthetic import make_city

        city = make_city()
        table = holdout(
            city.crashes,
            city.sites.index,
            city.streets,
            areas={"City": city.sites.index[city.sites.in_city]},
        )
        print("Rank score on later bike crashes (synthetic city)")
    else:
        if not args.config:
            parser.error("give --synthetic or --config")
        config = load_config(args.config)
        outlines = chosen_outlines(config, args.processed / "boundaries", args.area)
        ways = args.ways or street_path(args.processed / "network", config.crs)
        outline, limit = outlines["area"], args.city_limit or outlines["city_limit"]
        assert outline is not None
        table = city_holdout(config, args.crashes, ways, outline, limit)
        table["outcome"] = [age_label(name, config.child_max_age) for name in table.outcome]
        print(f"Rank score on later bike crashes ({config.city})")
    print(report(table))
    for line in notes(table):
        print(line)
    if args.expect:
        differences = compare(table, pd.read_csv(args.expect))
        print(f"\ncompared with {args.expect}: " + (differences or "every figure matches"))
        if differences:
            raise SystemExit(1)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(args.out, index=False)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
