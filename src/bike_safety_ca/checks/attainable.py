"""Attainable rank score: what the model's own rates say its rank score should be.

A city's rank score depends on how evenly its risk is spread, so a low score
need not mean a poor ranking.  For each hold-out window this fits the
street-length model on the training years, draws later crashes from the
model's own posterior rates many times, and scores the model's ranking on
each draw.  The mean is the score the ranking would expect if the model were
exactly right about the city; a real score far below the simulated range
points to differences the model misses.

Also given: an "oracle" score (ranking by the drawn true rates, the best any
ranking could do on the draws), a "no spread" score (later crashes drawn
around the model's estimates with no corner-to-corner variation beyond
them), and the car-crashes-only rank score.  Windows where the model falls
back to the hand-built blend have no rates to draw from and are left empty.

Limits: the fitted parameters are taken as known; the simulation cannot tell
evenly spread risk from a model that misses differences; windows overlap.
All figures are totals or scores, not individual records.

``python -m bike_safety_ca.checks.attainable --synthetic`` runs it on the
made-up city and needs no data.
"""

from __future__ import annotations

import argparse
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from bike_safety_ca import CAR, CYCLISTS
from bike_safety_ca.checks.holdout import WINDOWS, Window, placed
from bike_safety_ca.config import load as load_config
from bike_safety_ca.io import read_shapes
from bike_safety_ca.model.crash_history import rank_intersections, rank_score
from bike_safety_ca.network.area import chosen as chosen_outlines
from bike_safety_ca.network.streets import path as street_path

DRAWS = 2000
SEED = 20261117
# Draws are made this many at a time, so a city of many intersections does not
# hold every draw in memory at once.  The draws depend on it as well as on the
# seed, so changing it changes the figures slightly: keep it fixed.
CHUNK = 100
# The oracle ranks each draw by its own rates, one draw at a time: every
# ORACLE_STEP-th draw is enough for its mean.
ORACLE_STEP = 10


def rank_scores(score: np.ndarray, hits: np.ndarray) -> np.ndarray:
    """Rank score of one ``score`` against each row of ``hits`` (draws x sites, boolean).

    The same figure as ``rank_score``, ties counted as half, for many draws at
    once.  A draw with no hits, or nothing but hits, scores NaN.
    """
    ranks = rankdata(score)
    n1 = hits.sum(axis=1).astype(float)
    n0 = hits.shape[1] - n1
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (hits @ ranks - n1 * (n1 + 1) / 2) / (n1 * n0)
    return np.where((n1 > 0) & (n0 > 0), out, np.nan)


def simulate(
    sites: pd.DataFrame,
    later_total: float,
    draws: int = DRAWS,
    seed: int = SEED,
) -> tuple[dict[str, float], np.ndarray]:
    """Simulated rank scores of the model's ranking, from its own posterior rates.

    ``sites`` is the table from ``fit_street_model`` (``observed``,
    ``predicted``, ``prior_shape`` and ``eb``).  Each intersection's rate is
    drawn from its gamma posterior, scaled so the expected later total is
    ``later_total``, and a Poisson count drawn from it.  Returns the figures
    (mean, 5th and 95th percentiles of the simulated scores, the oracle and
    no-spread means, the share of intersections with a simulated later
    crash) and the simulated scores themselves.
    """
    rng = np.random.default_rng(seed)
    score = sites.eb.to_numpy(float)
    shape = (sites.prior_shape + sites.observed).to_numpy(float)
    rate = (sites.prior_shape / sites.predicted + 1).to_numpy(float)
    ratio = later_total / float((shape / rate).sum())
    flat = score * later_total / score.sum()
    simulated, oracle, no_spread, hit_share = [], [], [], []
    for start in range(0, draws, CHUNK):
        size = min(CHUNK, draws - start)
        rates = rng.gamma(shape, 1 / rate, size=(size, len(score))) * ratio
        hits = rng.poisson(rates) > 0
        simulated.append(rank_scores(score, hits))
        hit_share.append(hits.mean(axis=1))
        for row in range(-start % ORACLE_STEP, size, ORACLE_STEP):
            oracle.append(rank_scores(rates[row], hits[row : row + 1])[0])
        flat_hits = rng.poisson(np.broadcast_to(flat, (size, len(score)))) > 0
        no_spread.append(rank_scores(score, flat_hits))
    sims = np.concatenate(simulated)
    figures = {
        "simulated mean": float(np.nanmean(sims)),
        "simulated 5%": float(np.nanquantile(sims, 0.05)),
        "simulated 95%": float(np.nanquantile(sims, 0.95)),
        "oracle mean": float(np.nanmean(oracle)),
        "no-spread mean": float(np.nanmean(np.concatenate(no_spread))),
        "simulated share hit": float(np.concatenate(hit_share).mean()),
    }
    return figures, sims


def share_below(sims: np.ndarray, real: float) -> float:
    """Share of the simulated scores below ``real``, over the draws that have a score.

    NaN when ``real`` has no score or no draw does.
    """
    valid = sims[np.isfinite(sims)]
    if not np.isfinite(real) or len(valid) == 0:
        return float("nan")
    return float(np.mean(valid < real))


def attainable(
    crashes: pd.DataFrame,
    sites: pd.Index,
    streets: Mapping[Any, Collection[str]],
    windows: Sequence[Window] = WINDOWS,
    draws: int = DRAWS,
    seed: int = SEED,
) -> pd.DataFrame:
    """One row per window: the real rank score of the model beside the simulated ones.

    ``crashes`` has one row per crash placed at an intersection, with columns
    ``site``, ``year`` and ``group``, as for ``holdout``.  All cyclists only.
    """

    def count(groups: list[str], first: int, last: int | None) -> pd.Series:
        years = crashes.year.ge(first) if last is None else crashes.year.between(first, last)
        chosen = crashes[crashes.group.isin(groups) & years]
        return chosen.groupby("site").size().reindex(sites, fill_value=0)

    rows = []
    for train_to, test_from, test_to in windows:
        early, car = count(CYCLISTS, 0, train_to), count([CAR], 0, train_to)
        later = count(CYCLISTS, test_from, test_to)
        ranked = rank_intersections(early, car, streets)
        row: dict[str, Any] = {
            "trained through": train_to,
            "scored on": f"{test_from}–{test_to or 'latest'}",
            "intersections": len(sites),
            "later crashes": int(later.sum()),
            "share hit": float((later > 0).mean()),
            "method": ranked["method"],
            "rank score": rank_score(ranked["score"], later),
            "car crashes alone": rank_score(car.astype(float), later),
        }
        if ranked["fit"] is not None and later.sum() > 0:
            found, sims = simulate(ranked["fit"]["sites"], float(later.sum()), draws, seed)
            row |= found
            row["share of draws below the real score"] = share_below(sims, row["rank score"])
        rows.append(row)
    return pd.DataFrame(rows)


def report(table: pd.DataFrame) -> str:
    """The table as text, scores to three places and shares as percentages."""
    shown = table.copy()
    for column in shown.columns:
        if "share" in column:
            shown[column] = (100 * shown[column]).round(1)
        elif shown[column].dtype.kind == "f":
            shown[column] = shown[column].round(3)
    shown.columns = [c.replace("share ", "% ") for c in shown.columns]
    return shown.to_string(index=False, na_rep="–")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
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
    parser.add_argument(
        "--draws", type=int, default=DRAWS, help=f"simulated draws (default {DRAWS})"
    )
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--out", type=Path, help="also write the table to this CSV file")
    args = parser.parse_args()
    if args.synthetic:
        from bike_safety_ca.synthetic import make_city

        city = make_city()
        table = attainable(
            city.crashes, city.sites.index, city.streets, draws=args.draws, seed=args.seed
        )
        title = "synthetic city"
    else:
        if not args.config:
            parser.error("give --synthetic or --config")
        config = load_config(args.config)
        outline_path = chosen_outlines(config, args.processed / "boundaries", args.area)["area"]
        assert outline_path is not None
        ways = args.ways or street_path(args.processed / "network", config.crs)
        outline = read_shapes(outline_path).to_crs(config.crs).union_all()
        sites, streets, hits = placed(config, args.crashes, ways, outline)
        table = attainable(
            hits, sites.index, streets.to_dict(), config.holdout_windows, args.draws, args.seed
        )
        title = config.city
    print(f"Attainable rank score on later bike crashes ({title})")
    print(report(table))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
