"""Two checks run over many cities: ``python -m bike_safety_ca.checks.cities --configs config``.

For every config in a folder whose city has been built under
``<processed>/<config name>/`` (its ``crashes``, ``network`` and ``boundaries``
folders, as the other commands write them), it runs

- the hold-out check (``checks.holdout.holdout``),
- the lasting changes of level in police reporting (``checks.reporting.level_steps``), and
- the ranking with and without "complaint of pain" crashes
  (``checks.sensitivity.severity_windows``),

and prints the cross-city summaries given in ``docs/where_the_ranking_helps.md``.
With ``--out`` it also writes the per-city rows behind them.

Cities are compared as separate samples, so a config that overlaps others is
either left out (``--skip``) or named as a pooled area (``--pool``); both take
shell-style patterns on the config name, such as ``pool_*``.  A pooled area
is fitted as a whole and scored inside the limit of each city that lies in
it, beside that city's score when fitted alone.  All figures are totals or scores per agency, city and window, not
individual records.
"""

from __future__ import annotations

import argparse
import fnmatch
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from bike_safety_ca.checks import reporting
from bike_safety_ca.checks.holdout import ALL_CYCLISTS, MODEL, OUTCOMES, holdout, placed
from bike_safety_ca.checks.sensitivity import EVERY, VISIBLE, severity_windows
from bike_safety_ca.config import Config
from bike_safety_ca.config import load as load_config
from bike_safety_ca.io import crs_tag, read_shapes
from bike_safety_ca.model.crash_history import MIN_CRASHES
from bike_safety_ca.network import area as outlines
from bike_safety_ca.network.streets import path as street_path

if TYPE_CHECKING:
    import geopandas as gpd
    from shapely.geometry.base import BaseGeometry

log = logging.getLogger(__name__)

PAIN = "Complaint of pain"
# Rows of the severity summary.
ALL_WINDOWS = "All windows scored"
BOTH_FITTED = "Both rankings from a fitted model"
ONE_FELL_BACK = "Only the ranking without minor crashes fell back to the blend"
BOTH_FELL_BACK = "Both rankings fell back to the blend"
WITH_FALL = "Cities with a lasting fall in complaint-of-pain reports"
WITHOUT_FALL = "Cities without one"
# Names the hold-out gives its rows.
EVERYONE, CHILDREN = list(OUTCOMES)
HISTORY = "Past bike crashes"
WHOLE = "All intersections"
LIMIT = "City limit"
FITTED, BLEND = "street-length model", "hand-built blend"
# A city belongs to a pooled area that holds this share of its limit.
INSIDE = 0.95

Cities = dict[str, tuple[Config, Path]]
Placed = tuple["gpd.GeoDataFrame", pd.Series, pd.DataFrame]


def built(
    configs: Path, processed: Path, skip: Sequence[str] = ()
) -> tuple[dict[str, tuple[Config, Path]], dict[str, str]]:
    """The cities to run, and why each of the others is left out.

    A city is run when its config's name matches no ``skip`` pattern, the
    config loads, and ``<processed>/<name>/crashes`` holds its merged crash
    table.
    """
    found: dict[str, tuple[Config, Path]] = {}
    left: dict[str, str] = {}
    for path in sorted(configs.glob("*.yaml")):
        name = path.stem
        if any(fnmatch.fnmatch(name, pattern) for pattern in skip):
            left[name] = "skipped by name"
            continue
        try:
            config = load_config(path)
        except ValueError as error:  # a file the config names is no longer there, say
            left[name] = f"config not usable: {error}"
            continue
        folder = processed / name
        table = folder / "crashes" / f"crashes_merged_{crs_tag(config.crs)}.parquet"
        if not table.exists():
            left[name] = f"no crash table at {table}"
        else:
            found[name] = (config, folder)
    return found, left


def steps(cities: Cities) -> pd.DataFrame:
    """``reporting.level_steps`` for each city, with a ``city`` column in front."""
    tables = []
    for name, (config, folder) in cities.items():
        crashes = reporting.load(folder / "crashes", config.crs, config.first_year)
        found = reporting.level_steps(crashes)
        found.insert(0, "city", name)
        tables.append(found)
    columns = ["city", *reporting.level_steps(_no_crashes()).columns]
    return pd.concat(tables, ignore_index=True) if tables else pd.DataFrame(columns=columns)


def _no_crashes() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["reporting_agency", "year", "COLLISION_SEVERITY", "collision_date"]
    )


def step_counts(found: pd.DataFrame, cities: int) -> tuple[pd.DataFrame, str]:
    """Steps per measure and kind, and a sentence on how many cities and agencies have one."""
    kinds = [reporting.FEWER, reporting.REGRADED, reporting.MORE]
    measures = [reporting.ALL_INJURY, *reporting.SEVERITIES.values()]
    table = pd.crosstab(found.measure, found.kind).reindex(
        index=measures, columns=kinds, fill_value=0
    )
    agencies = len(found[["city", "reporting_agency"]].drop_duplicates())
    pain = found[found.measure.eq(PAIN) & found.after.lt(found.before)]
    total = found[found.measure.eq(reporting.ALL_INJURY)]
    both = pain.merge(total, on=["city", "reporting_agency"])
    line = (
        f"{found.city.nunique()} of {cities} cities have at least one agency with a step, "
        f"{agencies} agencies in all; {len(pain)} agencies have a fall in complaint-of-pain "
        f"reports, {len(both)} of them with a step in their total as well"
    )
    return table, line


def place(cities: Cities) -> dict[str, Placed]:
    """Each city's intersections, street names and placed crashes (``holdout.placed``).

    A city whose streets or outline are missing is logged and left out.
    """
    places = {}
    for name, (config, folder) in cities.items():
        area = outlines.chosen(config, folder / "boundaries")["area"]
        ways = street_path(folder / "network", config.crs)
        if area is None or not area.exists() or not ways.exists():
            log.warning("%s: no outline or street table, left out", name)
            continue
        outline = read_shapes(area).to_crs(config.crs).union_all()
        places[name] = placed(config, folder / "crashes", ways, outline)
    return places


def severity(cities: Cities, places: dict[str, Placed]) -> pd.DataFrame:
    """``sensitivity.severity_windows`` for each placed city, with a ``city`` column in front.

    A city whose crash table has no severity is logged and left out; so is
    one with no window scored.
    """
    tables = []
    for name, (sites, streets, hits) in places.items():
        scored = severity_windows(cities[name][0].holdout_windows, sites.index, streets, hits)
        if scored is None:
            log.warning("%s: no severity in the crash table, left out", name)
            continue
        if scored.empty:
            log.warning("%s: no window with enough later crashes of both kinds", name)
        scored.insert(0, "city", name)
        tables.append(scored)
    columns = ["city", "trained", "target", "window", "fitted", "training", "later", "score"]
    return pd.concat(tables, ignore_index=True) if tables else pd.DataFrame(columns=columns)


def holdouts(cities: Cities, places: dict[str, Placed]) -> pd.DataFrame:
    """``holdout.holdout`` for each placed city, with ``city`` and ``intersections`` in front.

    Where the city has a limit of its own, the intersections inside it are
    scored as well, as the area ``LIMIT``.  A city with no windows is logged
    and left out.
    """
    tables = []
    for name, (sites, streets, hits) in places.items():
        config, folder = cities[name]
        limit = _outline(outlines.chosen(config, folder / "boundaries")["city_limit"], config.crs)
        areas = {} if limit is None else {LIMIT: sites.index[sites.geometry.within(limit)]}
        table = holdout(hits, sites.index, streets.to_dict(), config.holdout_windows, areas)
        if table.empty:
            log.warning("%s: no hold-out windows in its config, left out", name)
            continue
        table.insert(0, "city", name)
        table.insert(1, "intersections", len(sites))
        tables.append(table)
    return pd.concat(tables, ignore_index=True) if tables else _no_holdout(["intersections"])


def _no_holdout(extra: list[str]) -> pd.DataFrame:
    columns = ["trained through", "tested on", "outcome", "area", "ranking", "method"]
    columns += ["training crashes", "later crashes", "rank score", "found in top 100"]
    return pd.DataFrame(columns=["city", *extra, *columns])


def _outline(path: Path | None, crs: str) -> BaseGeometry | None:
    if path is None or not path.exists():
        return None
    return read_shapes(path).to_crs(crs).union_all()


def pooled(pools: Cities, cities: Cities) -> pd.DataFrame:
    """Each pooled area's hold-out, scored inside the limit of each city that lies in it.

    One fit per pool and window; the rows kept are those of the member
    cities, with ``pool`` and ``city`` columns in front.  A city is a member
    when at least ``INSIDE`` of its limit (the area it was fitted on, if it
    has no limit of its own) is inside the pool's area.  A city whose child
    age differs from the pool's is logged and left out.
    """
    tables = []
    for pool, (sites, streets, hits) in place(pools).items():
        config, folder = pools[pool]
        area = _outline(outlines.chosen(config, folder / "boundaries")["area"], config.crs)
        areas = {}
        for name, (own, home) in cities.items():
            chosen = outlines.chosen(own, home / "boundaries")
            limit = _outline(chosen["city_limit"], config.crs)
            if limit is None:
                limit = _outline(chosen["area"], config.crs)
            if area is None or limit is None or limit.area == 0:
                continue
            if limit.intersection(area).area < INSIDE * limit.area:
                continue
            if own.child_max_age != config.child_max_age:
                # Its child scores alone and pooled would be of different age groups.
                log.warning("%s: its child age differs from %s's, not compared", name, pool)
                continue
            areas[name] = sites.index[sites.geometry.within(limit)]
        if not areas:
            log.warning("%s: no city lies inside this pooled area", pool)
            continue
        table = holdout(hits, sites.index, streets.to_dict(), config.holdout_windows, areas)
        if table.empty:
            log.warning("%s: no hold-out windows in its config, left out", pool)
            continue
        table = table[table.area.isin(list(areas))].rename(columns={"area": "city"})
        table.insert(0, "pool", pool)
        tables.append(table)
    if not tables:
        return _no_holdout([]).drop(columns="area").assign(pool=[])
    return pd.concat(tables, ignore_index=True)


def results(table: pd.DataFrame) -> pd.DataFrame:
    """One row per city from ``holdouts``' table, best rank score first.

    Scores are means over the windows scored (those with enough later
    crashes).  ``fit`` says whether the street-length model was fitted in
    every window ("model"), in some ("mixed") or in none ("blend").  The
    top-100 figures are later bike crashes at the 100 highest-ranked
    intersections, summed over the windows scored.
    """
    rows = {}
    columns = ["intersections", "windows scored", "rank score", "history alone", "fit"]
    columns += ["top 100, model", "top 100, history", "later crashes", "child windows scored"]
    columns += ["rank score, children", "fewest later child crashes"]
    whole = table[table.area.eq(WHOLE)]
    for city, part in whole.groupby("city", sort=False):

        def pick(outcome: str, ranking: str, part: pd.DataFrame = part) -> pd.DataFrame:
            chosen = part[part.outcome.eq(outcome) & part.ranking.eq(ranking)]
            return chosen[chosen["rank score"].notna()]

        model, history, child = (
            pick(EVERYONE, MODEL),
            pick(EVERYONE, HISTORY),
            pick(CHILDREN, MODEL),
        )
        every = part[part.ranking.eq(MODEL)]
        methods = set(every.method[every.outcome.eq(EVERYONE)])
        counts = every["later crashes"][every.outcome.eq(CHILDREN)]
        rows[str(city)] = {
            "intersections": int(part.intersections.iloc[0]),
            "windows scored": len(model),
            "rank score": round(float(model["rank score"].mean()), 3),
            "history alone": round(float(history["rank score"].mean()), 3),
            "fit": "model" if methods == {FITTED} else "blend" if methods == {BLEND} else "mixed",
            "top 100, model": round(float(model["found in top 100"].sum())),
            "top 100, history": round(float(history["found in top 100"].sum())),
            "later crashes": int(model["later crashes"].sum()),
            "child windows scored": len(child),
            "rank score, children": round(float(child["rank score"].mean()), 3),
            "fewest later child crashes": int(counts.min()) if len(counts) else 0,
        }
    out = pd.DataFrame.from_dict(rows, orient="index", columns=columns)
    return out.sort_values("rank score", ascending=False)


def child_ranking(table: pd.DataFrame) -> pd.DataFrame:
    """Is a ranking fitted to child crashes better for children than the all-cyclist one?

    Over the city-windows of ``holdouts``' table with a child score, split by
    whether the training years held ``MIN_CRASHES`` child crashes (enough to
    fit the model): the number of windows and cities, the mean rank score of
    each ranking on later child crashes, and in how many windows the child
    ranking is the better.
    """
    part = table[table.area.eq(WHOLE) & table.outcome.eq(CHILDREN) & table["rank score"].notna()]
    keys = ["city", "trained through", "tested on"]
    wide = part.pivot_table(index=keys, columns="ranking", values="rank score")
    wide = wide.reindex(columns=[MODEL, ALL_CYCLISTS])
    training = part[part.ranking.eq(MODEL)].set_index(keys)["training crashes"].reindex(wide.index)
    rows = {}
    groups = {f"Under {MIN_CRASHES}": training < MIN_CRASHES}
    groups[f"{MIN_CRASHES} or more"] = training >= MIN_CRASHES
    for label, chosen in groups.items():
        some = wide[chosen.to_numpy(bool)]
        rows[label] = {
            "windows": len(some),
            "cities": some.index.get_level_values("city").nunique(),
            "ranking fitted to child crashes": round(float(some[MODEL].mean()), 3),
            "all-cyclist ranking": round(float(some[ALL_CYCLISTS].mean()), 3),
            "child ranking better in": int((some[MODEL] > some[ALL_CYCLISTS]).sum()),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def pooled_summary(alone: pd.DataFrame, together: pd.DataFrame) -> pd.DataFrame:
    """Each member city's mean rank score fitted alone and inside its pool, per outcome.

    ``alone`` is ``holdouts``' table and ``together`` is ``pooled``'s.  Each
    mean is over the windows scored that way, whose number is given beside it.
    Both are scored inside the city's limit: fitted alone, a city with no
    limit of its own is scored over the whole area it was fitted on, which is
    then also what ``pooled`` took for its limit.
    """

    def means(table: pd.DataFrame, by: list[str], label: str) -> pd.DataFrame:
        model = table[table.ranking.eq(MODEL)]
        parts = []
        for outcome in OUTCOMES:
            scores = model[model.outcome.eq(outcome)].groupby(by, sort=False)["rank score"]
            parts.append(scores.mean().round(3).rename(f"{outcome}, {label}"))
            parts.append(scores.count().rename(f"{outcome}, {label}, windows"))
        return pd.concat(parts, axis=1)

    has_limit = set(alone.city[alone.area.eq(LIMIT)])
    inside = alone.area.eq(LIMIT) | (alone.area.eq(WHOLE) & ~alone.city.isin(has_limit))
    apart = means(alone[inside], ["city"], "alone")
    both = means(together, ["pool", "city"], "pooled").join(apart, on="city")
    counts = [column for column in both.columns if column.endswith(", windows")]
    both[counts] = both[counts].fillna(0).astype(int)  # an outcome with no rows: none scored
    return both.reindex(columns=sorted(both.columns)).reset_index()


def severity_summary(scored: pd.DataFrame, with_fall: Sequence[str] = ()) -> pd.DataFrame:
    """Mean scores of the two rankings over city-windows, in all and by how they were built.

    ``scored`` is ``severity``'s table.  Each row covers a set of city-windows:
    its number, the cities they come from, the mean rank score of each
    ranking on each kind of later crash, what leaving the minor crashes out
    loses on each, and in how many of the windows it loses.  The last two
    rows split the cities by ``with_fall`` (those with a lasting fall in
    complaint-of-pain reports); their figures are means of city means, so
    that a city with three windows counts no more than one with two.
    """
    keys = ["city", "window"]
    kinds = [EVERY, VISIBLE]
    pairs = pd.MultiIndex.from_product([kinds, kinds], names=["target", "trained"])
    # Reindexed so that a table with no windows still has every column.
    wide = scored.pivot_table(index=keys, columns=["target", "trained"], values="score")
    wide = wide.reindex(columns=pairs)
    fitted = scored.pivot_table(index=keys, columns="trained", values="fitted", aggfunc="first")
    fitted = fitted.reindex(columns=kinds).astype(bool)
    loss = {target: wide[(target, EVERY)] - wide[(target, VISIBLE)] for target in (EVERY, VISIBLE)}
    cities = wide.index.get_level_values("city")

    def row(chosen: pd.Series, by_city: bool = False) -> dict[str, object]:
        part = wide[chosen.to_numpy()]
        out: dict[str, object] = {"windows": len(part), "cities": cities[chosen].nunique()}
        for target in (EVERY, VISIBLE):
            lost = loss[target][chosen.to_numpy()]
            for trained in (EVERY, VISIBLE):
                scores = part[(target, trained)]
                if by_city:
                    scores = scores.groupby(level="city").mean()
                out[f"later {target}, trained on {trained}"] = round(float(scores.mean()), 3)
            mean = lost.groupby(level="city").mean().mean() if by_city else lost.mean()
            out[f"later {target}: lost without minor crashes"] = round(float(mean), 3)
            out[f"later {target}: windows where it loses"] = int(lost.gt(0).sum())
        return out

    everything = pd.Series(True, index=wide.index)
    fell = pd.Series(cities.isin(list(with_fall)), index=wide.index)
    rows = {
        ALL_WINDOWS: row(everything),
        BOTH_FITTED: row(fitted[EVERY] & fitted[VISIBLE]),
        ONE_FELL_BACK: row(fitted[EVERY] & ~fitted[VISIBLE]),
        BOTH_FELL_BACK: row(~fitted[EVERY] & ~fitted[VISIBLE]),
        WITH_FALL: row(fell, by_city=True),
        WITHOUT_FALL: row(~fell, by_city=True),
    }
    return pd.DataFrame.from_dict(rows, orient="index")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configs", type=Path, default=Path("config"), help="folder of configs")
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    parser.add_argument("--skip", nargs="*", default=[], help="config names to leave out")
    parser.add_argument("--pool", nargs="*", default=[], help="config names of pooled areas")
    parser.add_argument("--out", type=Path, help="folder for the tables as CSV files")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    found_configs, left = built(args.configs, args.processed, args.skip)
    for name, why in left.items():
        print(f"left out {name}: {why}")

    def is_pool(name: str) -> bool:
        return any(fnmatch.fnmatch(name, pattern) for pattern in args.pool)

    cities = {name: city for name, city in found_configs.items() if not is_pool(name)}
    pools = {name: city for name, city in found_configs.items() if is_pool(name)}
    if not cities:
        parser.error(
            f"no built city found under {args.processed} for the configs in {args.configs}"
        )
    print(f"\n{len(cities)} cities: {', '.join(cities)}")
    if pools:
        print(f"{len(pools)} pooled areas: {', '.join(pools)}")

    pd.set_option("display.width", 250)
    places = place(cities)
    tested = holdouts(cities, places)
    by_city = results(tested)
    print("\nThe hold-out check, one row per city")
    print(by_city.to_string())
    children = child_ranking(tested)
    print("\nRanking children: a ranking fitted to child crashes against the all-cyclist one")
    print(children.to_string())
    together = pooled(pools, cities)
    pools_table = pooled_summary(tested, together)
    if pools:
        print("\nFitted alone and inside a pooled area, mean rank score inside the city")
        print(pools_table.to_string(index=False))

    found = steps(cities)
    counts, line = step_counts(found, len(cities))
    print("\nLasting changes of level in police reporting, steps per measure and kind")
    print(counts.to_string())
    print(line)

    scored = severity(cities, places)
    pain = found[found.measure.eq(PAIN) & found.after.lt(found.before)]
    summary = severity_summary(scored, sorted(set(pain.city)))
    print("\nThe ranking with and without complaint-of-pain crashes, over city-windows")
    print(summary.T.to_string())
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        tested.to_csv(args.out / "holdout_windows.csv", index=False)
        by_city.to_csv(args.out / "holdout_by_city.csv")
        children.to_csv(args.out / "child_ranking.csv")
        together.to_csv(args.out / "pooled_windows.csv", index=False)
        pools_table.to_csv(args.out / "pooled_by_city.csv", index=False)
        found.to_csv(args.out / "level_steps.csv", index=False)
        counts.to_csv(args.out / "level_step_counts.csv")
        scored.to_csv(args.out / "severity_windows.csv", index=False)
        summary.to_csv(args.out / "severity_summary.csv")
        print(f"\nwrote the tables to {args.out}")


if __name__ == "__main__":
    main()
