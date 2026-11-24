"""Compare versions of the street crash model on every built city's hold-out windows.

Each version is refitted on each window's fitting years and scored on the
later years, with the same intersections, placed crashes and fallback rule
(``rank_intersections``).  A version is fitted to all cyclists and scored on
later crashes of all cyclists and of children, and fitted to children and
scored on later child crashes; the two child rows are different rankings, so
the table names both the crashes fitted to and the crashes scored on.

    python -m bike_safety_ca.checks.candidates --configs config \\
        --processed data/processed --out output/model_candidates

writes ``windows.csv`` (one row per city, window, version, crashes fitted to
and crashes scored on, at full precision), ``summary.csv`` (each version
against the reference, paired by city and window) and ``run.json`` (the code
revision and a hash of each city's crash table).  ``--also name=folder`` adds
an area whose tables are not under ``<processed>/<name>``, such as a study
area that overlaps cities; it is summarised on its own, not with the cities.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from bike_safety_ca.checks import cities as cross
from bike_safety_ca.checks.holdout import CAR, CHILD, CYCLISTS, MIN_LATER, Window
from bike_safety_ca.config import load as load_config
from bike_safety_ca.io import crs_tag
from bike_safety_ca.model.crash_history import (
    rank_intersections,
    rank_score,
    street_blend_score,
    top_share,
)

log = logging.getLogger(__name__)

EVERYONE, CHILDREN = "All cyclists", "Cyclists 18 or under"
GROUPS = {EVERYONE: CYCLISTS, CHILDREN: [CHILD]}
# Crashes fitted to, and the later crashes each such ranking is scored on.
SCORED_ON = {EVERYONE: (EVERYONE, CHILDREN), CHILDREN: (CHILDREN,)}

FITTED_POWER, POWER_ONE, POWER_TWO = "Spread power fitted", "Spread power 1", "Spread power 2"
# The model with each spread power; ``None`` fits it.
VERSIONS: dict[str, float | None] = {FITTED_POWER: None, POWER_ONE: 1.0, POWER_TWO: 2.0}
HISTORY, BLEND = "Past bike crashes", "Hand-built blend"
REFERENCE = FITTED_POWER

TOPS = (25, 50, 100)
TOP_SHARE = 0.05  # of the area's intersections, rounded up
MEASURES = (
    "rank score",
    "rank score, no past bike crash",
    *(f"top {k} share" for k in TOPS),
    "top 5% share",
)
DRAWS, SEED = 10_000, 20261123


def score_windows(
    hits: pd.DataFrame,
    sites: pd.Index,
    streets: Mapping[Any, Any],
    windows: Sequence[Window],
    versions: Mapping[str, float | None] = VERSIONS,
) -> pd.DataFrame:
    """One row per window, version, crashes fitted to and crashes scored on.

    ``hits`` has one row per placed crash (``site``, ``year``, ``group``).
    Scores are built from crashes up to the window's last fitting year only.
    Nothing is rounded.  ``enough later`` marks rows with at least
    ``MIN_LATER`` later crashes; the others keep their figures but a score on
    a handful of crashes says little.
    """
    last_year = int(hits.year.max()) if len(hits) else None

    def count(groups: list[str], first: int, last: int | None) -> pd.Series:
        years = hits.year.ge(first) if last is None else hits.year.between(first, last)
        chosen = hits[hits.group.isin(groups) & years]
        return chosen.groupby("site").size().reindex(sites, fill_value=0)

    cut = math.ceil(TOP_SHARE * len(sites))
    rows = []
    for train_to, test_from, test_to in windows:
        car = count([CAR], 0, train_to)
        no_past = count(CYCLISTS, 0, train_to).eq(0)
        for fitted_on, scored in SCORED_ON.items():
            early = count(GROUPS[fitted_on], 0, train_to)
            scores: dict[str, pd.Series] = {
                HISTORY: early.astype(float),
                BLEND: street_blend_score(early, car, streets),
            }
            facts: dict[str, dict[str, Any]] = {}
            for name, power in versions.items():
                began = time.perf_counter()
                ranked = rank_intersections(early, car, streets, spread_power=power)
                fit = ranked["fit"]
                scores[name] = ranked["score"]
                facts[name] = {
                    "method": ranked["method"],
                    "fallback reason": ranked["reason"] or "",
                    "spread power": float(fit["spread_power"]) if fit else float("nan"),
                    "alpha": float(fit["alpha"]) if fit else float("nan"),
                    "seconds": time.perf_counter() - began,
                }
            reference = (
                scores[REFERENCE].rank(ascending=False, method="first").le(50)
                if REFERENCE in scores
                else None
            )
            for scored_on in scored:
                later = count(GROUPS[scored_on], test_from, test_to)
                total = int(later.sum())
                for name, score in scores.items():
                    top = score.rank(ascending=False, method="first").le(50)
                    found = {k: top_share(score, later, k) for k in TOPS}
                    in_cut = top_share(score, later, cut)
                    rows.append(
                        {
                            "trained through": train_to,
                            "tested from": test_from,
                            "tested to": test_to if test_to is not None else last_year,
                            "version": name,
                            "fitted on": fitted_on,
                            "scored on": scored_on,
                            "area": cross.WHOLE,
                            "intersections": len(sites),
                            "training crashes": int(early.sum()),
                            "later crashes": total,
                            "later intersections": int(later.gt(0).sum()),
                            "enough later": total >= MIN_LATER,
                            **facts.get(name, {"method": name}),
                            "rank score": rank_score(score, later),
                            "rank score, no past bike crash": rank_score(
                                score[no_past], later[no_past]
                            ),
                            **{f"found in top {k}": found[k] for k in TOPS},
                            "found in top 5%": in_cut,
                            **{
                                f"top {k} share": 100 * found[k] / total if total else float("nan")
                                for k in TOPS
                            },
                            "top 5% share": 100 * in_cut / total if total else float("nan"),
                            "top 50 shared with reference": float("nan")
                            if reference is None
                            else int((top & reference).sum()),
                        }
                    )
    return pd.DataFrame(rows)


KEYS = ["city", "trained through", "fitted on", "scored on"]


def paired(table: pd.DataFrame, version: str, reference: str = REFERENCE) -> pd.DataFrame:
    """``version`` minus ``reference`` per city and window, where they can be compared.

    Kept are the windows with enough later crashes where the reference came
    from a fitted model, so every version there was offered the same crashes.
    """
    indexed = table[table["enough later"]].set_index([*KEYS, "version"])
    if indexed.empty or reference not in indexed.index.get_level_values("version"):
        return pd.DataFrame(columns=[*KEYS, *MEASURES])
    base = indexed.xs(reference, level="version")
    base = base[base.method.eq(cross.FITTED)]
    other = indexed.xs(version, level="version").reindex(base.index)
    return (other[list(MEASURES)] - base[list(MEASURES)]).reset_index()


SUMMARY = [
    "version",
    "fitted on",
    "scored on",
    "measure",
    "windows",
    "cities",
    "mean over windows",
    "mean over cities",
    "5th percentile",
    "95th percentile",
    "lowest leaving one city out",
    "highest leaving one city out",
    "cities lower",
]


def summarise(
    table: pd.DataFrame, reference: str = REFERENCE, draws: int = DRAWS, seed: int = SEED
) -> pd.DataFrame:
    """Each version against the reference: mean difference and how far it depends on the cities.

    For each measure: the mean over windows, the mean over cities (each
    city's windows averaged first), the 5th and 95th percentiles of the window
    mean when whole cities are drawn again with replacement (``draws`` times),
    the lowest and highest window mean with one city left out, and the number
    of cities whose own mean is lower.  The interval describes sensitivity to
    which cities are in the set; it is not a forecast interval.
    """
    rows = []
    rng = np.random.default_rng(seed)
    versions = [v for v in table.version.unique() if v != reference]
    for version in versions:
        differences = paired(table, version, reference)
        for (fitted_on, scored_on), part in differences.groupby(["fitted on", "scored on"]):
            names = part.city.unique()
            picks = rng.integers(0, len(names), size=(draws, len(names)))
            for measure in MEASURES:
                kept = part.dropna(subset=[measure])
                by_city = kept.groupby("city")[measure]
                total = by_city.sum().reindex(names, fill_value=0.0).to_numpy()
                size = by_city.size().reindex(names, fill_value=0).to_numpy()
                # A draw, or a set with one city left out, that holds no window with the
                # measure has no mean: it is left out, not counted as a difference of zero.
                drawn = _mean(total[picks].sum(axis=1), size[picks].sum(axis=1))
                left = _mean(total.sum() - total, size.sum() - size)[size > 0]
                city_mean = by_city.mean()
                rows.append(
                    {
                        "version": version,
                        "fitted on": fitted_on,
                        "scored on": scored_on,
                        "measure": measure,
                        "windows": len(kept),
                        "cities": int((size > 0).sum()),
                        "mean over windows": kept[measure].mean(),
                        "mean over cities": city_mean.mean(),
                        "5th percentile": _edge(drawn, lambda v: np.quantile(v, 0.05)),
                        "95th percentile": _edge(drawn, lambda v: np.quantile(v, 0.95)),
                        "lowest leaving one city out": _edge(left, np.min),
                        "highest leaving one city out": _edge(left, np.max),
                        "cities lower": int(city_mean.lt(0).sum()),
                    }
                )
    return pd.DataFrame(rows, columns=SUMMARY)


def _mean(total: np.ndarray, size: np.ndarray) -> np.ndarray:
    """``total / size``, missing where there is nothing to average."""
    return np.where(size > 0, total / np.maximum(size, 1), np.nan)


def _edge(values: np.ndarray, pick: Callable[[np.ndarray], Any]) -> float:
    """``pick`` of the values that exist; missing when none does."""
    found = values[~np.isnan(values)]
    return float(pick(found)) if len(found) else float("nan")


def shown(summary: pd.DataFrame) -> str:
    """The summary as printed, or a line saying there was nothing to compare."""
    if summary.empty:
        return "no window has a fitted reference and enough later crashes"
    return str(summary.round(4).to_string(index=False))


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _revision() -> str:
    try:
        found = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return found.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--configs", type=Path, default=Path("config"), help="folder of configs")
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    parser.add_argument("--skip", nargs="*", default=["pool_*"], help="config names to leave out")
    parser.add_argument(
        "--also", nargs="*", default=[], metavar="NAME=FOLDER",
        help="areas built elsewhere, summarised apart from the cities",
    )  # fmt: skip
    parser.add_argument("--out", type=Path, required=True, help="folder for the tables")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cities, left = cross.built(args.configs, args.processed, args.skip)
    for name, why in left.items():
        log.info("left out %s: %s", name, why)
    apart = []
    for entry in args.also:
        name, _, folder = entry.partition("=")
        cities[name] = (load_config(args.configs / f"{name}.yaml"), Path(folder))
        apart.append(name)
    tables = []
    hashes = {}
    for name, (sites, streets, hits) in cross.place(cities).items():
        config, folder = cities[name]
        table = score_windows(hits, sites.index, streets.to_dict(), config.holdout_windows)
        if table.empty:
            log.info("%s: no hold-out windows, left out", name)
            continue
        table.insert(0, "city", name)
        tables.append(table)
        crashes = folder / "crashes" / f"crashes_merged_{crs_tag(config.crs)}.parquet"
        hashes[name] = _hash(crashes)
        log.info("scored %s", name)
    if not tables:
        parser.error("no city with hold-out windows was found")
    windows = pd.concat(tables, ignore_index=True)
    windows.insert(1, "summarised apart", windows.city.isin(apart))
    summary = summarise(windows[~windows["summarised apart"]])
    args.out.mkdir(parents=True, exist_ok=True)
    windows.to_csv(args.out / "windows.csv", index=False)
    summary.to_csv(args.out / "summary.csv", index=False)
    record = {"revision": _revision(), "reference": REFERENCE, "crash tables": hashes}
    (args.out / "run.json").write_text(json.dumps(record, indent=2) + "\n")
    pd.set_option("display.width", 250)
    print(shown(summary))
    for name in apart:
        own = summarise(windows[windows.city.eq(name)], draws=1)
        print(f"\n{name}, on its own")
        print(shown(own[[*SUMMARY[:5], "mean over windows"]]))


if __name__ == "__main__":
    main()
