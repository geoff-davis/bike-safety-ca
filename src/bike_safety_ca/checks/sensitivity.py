"""What moves the hold-out scores: ``python -m bike_safety_ca.checks.sensitivity --config ...``.

Runs the hold-out check again with one choice changed at a time and prints
the street-length model's mean rank score for each.  The choices: the rule
that places crashes at intersections, how close corners are joined, the city
limit, and, when you supply them, streets of another date (``--other-ways``)
and a street table covering the whole area built from the config's city list
(``--wide-ways``).

With ``--wide-ways`` a second table splits the last test window by where the
intersections are, which is how a change in one police agency's reporting
shows up in the scores (see "Check for changes in police reporting first" in docs/guide.md).

A last table builds the ranking with and without "complaint of pain" crashes,
the least serious grade, which departments differ in filing (see "Lasting changes of
level" in docs/guide.md).

All figures are totals or scores over many intersections, not individual
records.  Needs the crash tables, the outlines and the street table that the
other commands write.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry.base import BaseGeometry

from bike_safety_ca import CAR, CYCLISTS, age_label
from bike_safety_ca.checks.holdout import (
    MIN_LATER,
    MODEL,
    OUTCOMES,
    Window,
    holdout,
    placed,
    rankings,
)
from bike_safety_ca.config import Config
from bike_safety_ca.config import load as load_config
from bike_safety_ca.download import census
from bike_safety_ca.io import read_shapes
from bike_safety_ca.model.crash_history import rank_score
from bike_safety_ca.network import area as outlines
from bike_safety_ca.network.streets import path as street_path

WIDE_SPAN_M = 40.0
CHAIN_LIMIT_M = 25.0
ELSEWHERE = "Unincorporated"
# TIMS severity codes for fatal, serious and visible injury: everything but "complaint of pain".
WORSE = ("1", "2", "3")
EVERY, VISIBLE = "all injury crashes", "visible injury and worse"
FITTED = "street-length model"  # ``rank_intersections``'s method when the model was fitted
WITHIN = "Each city scored on its own, averaged"


def scores(
    config: Config,
    sites: gpd.GeoDataFrame,
    streets: pd.Series,
    hits: pd.DataFrame,
    limit: BaseGeometry | None,
) -> dict[str, object]:
    """Mean rank score of the model over the config's windows, with the counts behind it.

    The mean is over the windows the hold-out scored; it is empty where no
    window had enough later crashes.
    """
    areas = {}
    if limit is not None:
        areas[config.city] = sites.index[sites.geometry.within(limit)]
    table = holdout(hits, sites.index, streets.to_dict(), config.holdout_windows, areas)
    model = table[table.ranking.eq(MODEL)]
    row: dict[str, object] = {
        "intersections": len(sites),
        "crashes placed": len(hits),
        "cyclist crashes placed": int(hits.group.ne(CAR).sum()),
    }
    for area in ["All intersections", *areas]:
        for outcome in OUTCOMES:
            chosen = model[model.area.eq(area) & model.outcome.eq(outcome)]
            name = f"{area}, {age_label(outcome, config.child_max_age)}"
            row[name] = round(float(chosen["rank score"].mean()), 3)
    return row


def variants(
    config: Config,
    crash_folder: Path,
    ways: Path,
    outline: BaseGeometry,
    limit: BaseGeometry | None,
    others: dict[str, tuple[Path, BaseGeometry, BaseGeometry | None]] | None = None,
) -> pd.DataFrame:
    """One row per variant.  ``others`` adds runs on another (streets, outline, limit)."""
    rows = {}
    sites, streets, hits = placed(config, crash_folder, ways, outline)
    rows["As configured"] = scores(config, sites, streets, hits, limit)
    narrow = sites.index[sites.span_m.le(WIDE_SPAN_M)]
    rows[f"Leaving out intersections wider than {WIDE_SPAN_M:g} m"] = scores(
        config, sites.loc[narrow], streets.loc[narrow], hits[hits.site.isin(narrow)], limit
    )
    loose = placed(config, crash_folder, ways, outline, check_names=False)
    rows["Nearness counts whatever streets the report names"] = scores(config, *loose, limit)
    split = placed(config, crash_folder, ways, outline, max_cluster_m=CHAIN_LIMIT_M)
    # Corners with the same street names within 60 m are still joined after the split.
    rows[f"Chains of close corners split at {CHAIN_LIMIT_M:g} m"] = scores(config, *split, limit)
    for label, (other_ways, other_outline, other_limit) in (others or {}).items():
        rows[label] = scores(
            config, *placed(config, crash_folder, other_ways, other_outline), other_limit
        )
    return pd.DataFrame.from_dict(rows, orient="index")


def city_of(sites: gpd.GeoDataFrame, places: gpd.GeoDataFrame) -> pd.Series:
    """The incorporated place each intersection lies in, from the Census outlines."""
    assert sites.crs is not None
    cities = outlines.incorporated(places).to_crs(sites.crs)[["NAME", "geometry"]]
    found = gpd.sjoin(sites[["geometry"]], cities, how="left", predicate="within").NAME
    return found[~found.index.duplicated()].reindex(sites.index).fillna(ELSEWHERE)


def within_cities(score: pd.Series, later: pd.Series, city: pd.Series) -> float:
    """Rank score with each intersection compared only with others in its own city.

    Each city's own rank score, averaged with the number of comparisons it
    holds as the weight (intersections with a later crash times those
    without).  A city where every intersection, or none, had a later crash
    has no comparison to make and is left out.
    """
    total = weight = 0.0
    for _, members in score.groupby(city):
        hit = later.loc[members.index] > 0
        pairs = float(hit.sum()) * float((~hit).sum())
        if pairs:
            total += pairs * rank_score(members, later.loc[members.index])
            weight += pairs
    return total / weight if weight else float("nan")


def by_place(
    config: Config,
    crash_folder: Path,
    wide_ways: Path,
    wide_outline: BaseGeometry,
    study_outline: BaseGeometry,
    places: gpd.GeoDataFrame,
    leave_out: str | None = None,
) -> pd.DataFrame:
    """The last test window on the wide area, split by where the intersections are.

    The ranking is fitted once on the whole wide area.  Each row scores it on
    a subset: inside ``study_outline``, outside it, outside without the city
    ``leave_out``, and city by city (``within_cities``), so that a city
    reporting few crashes is not compared with one reporting many.  The
    missing reports stay missing and the fit still pools the cities: this is
    a check, not a correction.
    """
    sites, streets, hits = placed(config, crash_folder, wide_ways, wide_outline)
    inside = sites.geometry.within(study_outline)
    city = city_of(sites, places)
    train_to, test_from, test_to = config.holdout_windows[-1]

    def count(groups: list[str], first: int, last: int | None) -> pd.Series:
        years = hits.year.ge(first) if last is None else hits.year.between(first, last)
        chosen = hits[hits.group.isin(groups) & years]
        return chosen.groupby("site").size().reindex(sites.index, fill_value=0)

    subsets = {
        "All intersections": pd.Series(True, index=sites.index),
        "Inside the configured area": inside,
        "Outside it": ~inside,
    }
    if leave_out:
        subsets[f"Outside it, without {leave_out}"] = ~inside & city.ne(leave_out)
    rows: dict[str, dict[str, object]] = {name: {} for name in [*subsets, WITHIN]}
    car = count([CAR], 0, train_to)
    for outcome, groups in OUTCOMES.items():
        later = count(groups, test_from, test_to)
        score = rankings(count(groups, 0, train_to), car, streets.to_dict())[0][MODEL]
        label = age_label(outcome, config.child_max_age)
        for name, mask in subsets.items():
            rows[name]["intersections"] = int(mask.sum())
            # As in the hold-out: no score on fewer than MIN_LATER later crashes.
            enough = int(later[mask].sum()) >= MIN_LATER
            rows[name][label] = (
                round(rank_score(score[mask], later[mask]), 3) if enough else float("nan")
            )
            rows[name][f"{label}: later crashes"] = int(later[mask].sum())
            rows[name][f"{label}: intersections with a later crash"] = int((later[mask] > 0).sum())
        rows[WITHIN]["intersections"] = len(sites)
        enough = int(later.sum()) >= MIN_LATER
        rows[WITHIN][label] = (
            round(within_cities(score, later, city), 3) if enough else float("nan")
        )
        rows[WITHIN][f"{label}: later crashes"] = int(later.sum())
        rows[WITHIN][f"{label}: intersections with a later crash"] = int((later > 0).sum())
    table = pd.DataFrame.from_dict(rows, orient="index")
    table.attrs["window"] = (
        f"trained through {train_to}, tested on {test_from}–{test_to or 'latest'}"
    )
    return table


def severity_windows(
    windows: Sequence[Window], sites: pd.Index, streets: pd.Series, hits: pd.DataFrame
) -> pd.DataFrame | None:
    """The scores behind ``by_severity``, one row per window, ranking and kind of later crash.

    Only the windows scored are kept (see ``by_severity``).  Columns: ``trained``
    and ``target`` (``EVERY`` or ``VISIBLE``), ``window`` (its position in
    ``windows``), ``fitted`` (the ranking came from the model, not the blend),
    ``training`` and ``later`` (cyclist crashes), ``score``.  None when the
    crash table has no severity column.
    """
    if "COLLISION_SEVERITY" not in hits:
        return None
    worse = hits.COLLISION_SEVERITY.astype("string").str.strip().isin(WORSE)
    kinds = {EVERY: hits, VISIBLE: hits[worse]}
    names = streets.to_dict()

    def count(frame: pd.DataFrame, groups: list[str], first: int, last: int | None) -> pd.Series:
        years = frame.year.ge(first) if last is None else frame.year.between(first, last)
        chosen = frame[frame.group.isin(groups) & years]
        return chosen.groupby("site").size().reindex(sites, fill_value=0)

    found = []
    for number, (train_to, test_from, test_to) in enumerate(windows):
        for trained, frame in kinds.items():
            early = count(frame, CYCLISTS, 0, train_to)
            scores, method = rankings(early, count(frame, [CAR], 0, train_to), names)
            for target, later_frame in kinds.items():
                later = count(later_frame, CYCLISTS, test_from, test_to)
                enough = int(later.sum()) >= MIN_LATER
                found.append(
                    {
                        "trained": trained,
                        "target": target,
                        "window": number,
                        "fitted": method == FITTED,
                        "training": int(early.sum()),
                        "later": int(later.sum()),
                        "score": rank_score(scores[MODEL], later) if enough else float("nan"),
                    }
                )
    scored = pd.DataFrame(
        found, columns=["trained", "target", "window", "fitted", "training", "later", "score"]
    )
    if len(scored):
        # Only windows where every ranking has a score on both kinds of later crash, so
        # that each figure in the table is a mean over the same windows.
        scored = scored[scored.groupby("window").score.transform(lambda s: s.notna().all())]
    return scored.reset_index(drop=True)


def by_severity(
    windows: Sequence[Window], sites: pd.Index, streets: pd.Series, hits: pd.DataFrame
) -> pd.DataFrame | None:
    """Does leaving out "complaint of pain" crashes change the ranking?

    The ranking is built twice per window: from all injury crashes, and from
    crashes with a visible injury or worse (bike and car crashes alike).
    Each is scored on later cyclist crashes of both kinds.  One row per
    ranking, with its mean rank score on each kind over the windows scored,
    the number of those windows, and the cyclist crashes trained on and
    scored, summed over them.  A window is scored when it has enough later
    crashes of both kinds and all four scores exist.

    ``rank_intersections`` falls back to the hand-built blend where there are
    too few crashes to fit the street-length model, which happens sooner
    without the minor crashes.  "windows with a fitted model" says in how
    many of the windows scored the ranking came from the model; where it is
    lower for one row than the other, the comparison is partly between the
    model and the blend.

    Police departments differ, and change, in how many of the least serious
    crashes they file (see ``checks.reporting.level_steps``), so this shows
    whether the ranking would be better off without them.  A crash with no
    severity recorded counts only among all injury crashes.  None when the
    crash table has no severity column.
    """
    scored = severity_windows(windows, sites, streets, hits)
    if scored is None:
        return None
    kinds = (EVERY, VISIBLE)
    rows = {}
    for trained in kinds:
        mine = scored[scored.trained.eq(trained)] if len(scored) else scored
        first = mine[mine.target.eq(EVERY)] if len(mine) else mine
        row: dict[str, object] = {
            "windows scored": len(first),
            "windows with a fitted model": int(first.fitted.sum()) if len(first) else 0,
            "cyclist crashes trained on": int(first.training.sum()) if len(first) else 0,
        }
        for target in kinds:
            chosen = mine[mine.target.eq(target)] if len(mine) else mine
            mean = float(chosen.score.mean()) if len(chosen) else float("nan")
            row[f"Later cyclist crashes, {target}"] = round(mean, 3)
            row[f"Later cyclist crashes, {target}: count"] = (
                int(chosen.later.sum()) if len(chosen) else 0
            )
        rows[f"Trained on {trained}"] = row
    return pd.DataFrame.from_dict(rows, orient="index")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--crashes", type=Path, default=Path("data/processed/crashes"))
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    parser.add_argument("--boundaries", type=Path, default=Path("data/raw/boundaries"))
    parser.add_argument("--area", type=Path, help="your own outline of the area")
    parser.add_argument("--other-ways", type=Path, help="street table of another date")
    parser.add_argument("--wide-ways", type=Path, help="street table for the city-list area")
    parser.add_argument("--leave-out", help="a city to leave out of the outside rows")
    parser.add_argument("--out", type=Path, help="folder for the tables as CSV files")
    args = parser.parse_args()
    config = load_config(args.config)
    chosen = outlines.chosen(config, args.processed / "boundaries", args.area)
    assert chosen["area"] is not None
    outline = read_shapes(chosen["area"]).to_crs(config.crs).union_all()
    limit = None
    if chosen["city_limit"] is not None:
        limit = read_shapes(chosen["city_limit"]).to_crs(config.crs).union_all()
    ways = street_path(args.processed / "network", config.crs)

    others: dict[str, tuple[Path, BaseGeometry, BaseGeometry | None]] = {}
    places = None
    stems = census.names()
    found = {kind: args.boundaries / f"{stem}.zip" for kind, stem in stems.items()}
    if all(path.exists() for path in found.values()):
        places = gpd.read_file(found["places"])
        wide, census_limit = outlines.outlines(places, gpd.read_file(found["counties"]), config)
        wide_outline, census_shape = wide.union_all(), census_limit.union_all()
        others["Census city limit"] = (ways, outline, census_shape)
        if args.wide_ways:
            others["Area built from the city list"] = (args.wide_ways, wide_outline, census_shape)
    elif args.wide_ways:
        parser.error(f"--wide-ways needs the Census outlines in {args.boundaries}")
    if args.other_ways:
        others["Streets of another date"] = (args.other_ways, outline, limit)

    pd.set_option("display.width", 250)
    table = variants(config, args.crashes, ways, outline, limit, others)
    print(f"Street-length model, mean rank score over the test windows ({config.city})")
    print(table.to_string())
    split = None
    if args.wide_ways and places is not None:
        split = by_place(
            config, args.crashes, args.wide_ways, wide_outline, outline, places, args.leave_out
        )
        print(f"\nArea built from the city list, {split.attrs['window']}")
        print(split.to_string())
    sites, streets, hits = placed(config, args.crashes, ways, outline)
    severity = by_severity(config.holdout_windows, sites.index, streets, hits)
    if severity is not None:
        print("\nWith and without complaint-of-pain crashes, mean rank score over the test windows")
        print(severity.to_string())
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        table.to_csv(args.out / "sensitivity.csv")
        if severity is not None:
            severity.to_csv(args.out / "sensitivity_by_severity.csv")
        if split is not None:
            split.to_csv(args.out / "sensitivity_by_place.csv")
        print(f"\nwrote the tables to {args.out}")


if __name__ == "__main__":
    main()
