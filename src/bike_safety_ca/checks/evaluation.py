"""Score held-back cities by the evaluation's rules.  ``python -m bike_safety_ca.checks.evaluation``.

Each city is fitted on crashes through one year and scored on the bike
crashes of the years after, at its own intersections.  The score is
``crash_history.top_capture``: the share of later crashes at the top of the
list, averaged over budgets up to 5% of the intersections.

Two outcomes are scored: every later bike injury crash, and those recorded
as fatal or severe (the crash's worst injury, whoever's it was).  Two
aggregates are given: the equal-weight mean over the larger cities with at
least one later crash (the primary result, on all crashes), and the pooled
figure, each city's score weighted by its later crashes.  A larger city is
one with ``MIN_CRASHES`` bike crashes or more in the fitting years.

Models are compared in pairs on the same cities.  The interval comes from
drawing whole units again with replacement, a unit being the cities that
share a police agency.  ``verdict`` applies the rule for "no worse": the
5th percentile of the difference must be above minus the margin.

Every model is scored in every city.  Where a model cannot be fitted its
fallback is scored: the hand-built blend, for the pipeline's models and for
the street-context model alike.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from bike_safety_ca.checks import cities as cross
from bike_safety_ca.checks.candidates import top_places
from bike_safety_ca.checks.holdout import CAR, CYCLISTS
from bike_safety_ca.model.crash_history import (
    MIN_CRASHES,
    rank_intersections,
    street_blend_score,
    top_capture,
)
from bike_safety_ca.model.standard_eb import rank_standard

log = logging.getLogger(__name__)

B, H, CONTEXT = "B: spread power 1", "H: spread power fitted, 1 to 2", "Street context"
BIKE, CARS, BLEND = "Past bike crashes", "Past car crashes", "Hand-built blend"
MODELS = (B, H, CONTEXT, BLEND, BIKE, CARS)
EVERY, WORST = "all injury", "fatal or severe"
WORST_CODES = ("1", "2")
TRAIN_TO, TEST_FROM, TEST_TO = 2020, 2021, 2024
MARGIN = 1.0  # percentage points of capture
NO_WORSE, WORSE, INCONCLUSIVE = "no worse", "worse", "inconclusive"
CITY_MEAN, POOLED = "city mean", "pooled"
DRAWS, SEED = 10_000, 20261124


def score_city(
    hits: pd.DataFrame,
    sites: pd.Index,
    streets: Mapping[Any, Any],
    classes: pd.DataFrame,
    first_year: int,
    window: tuple[int, int, int] = (TRAIN_TO, TEST_FROM, TEST_TO),
) -> pd.DataFrame:
    """One row per model and outcome: the later crashes and the capture, in percent.

    ``hits`` has one row per placed crash (``site``, ``year``, ``group`` and,
    for the fatal-or-severe outcome, ``COLLISION_SEVERITY``).  ``capture`` is
    not a number when the city has no later crash of that kind.  ``larger``
    says the fitting years hold ``MIN_CRASHES`` bike crashes or more;
    ``fitted`` that the model itself was scored and not its fallback.
    """
    train_to, test_from, test_to = window

    def count(frame: pd.DataFrame, groups: list[str], first: int, last: int) -> pd.Series:
        chosen = frame[frame.group.isin(groups) & frame.year.between(first, last)]
        return chosen.groupby("site").size().reindex(sites, fill_value=0)

    early, car = count(hits, CYCLISTS, 0, train_to), count(hits, [CAR], 0, train_to)
    blend = street_blend_score(early, car, streets)
    scores: dict[str, pd.Series] = {
        BLEND: blend,
        BIKE: early.astype(float),
        CARS: car.astype(float),
    }
    fitted = dict.fromkeys(scores, True)
    for name, power in ((B, 1.0), (H, (1.0, 2.0))):
        ranked = rank_intersections(early, car, streets, spread_power=power)
        scores[name], fitted[name] = ranked["score"], ranked["fit"] is not None
    years = train_to - first_year + 1
    context = rank_standard(early, car, classes, years, streets=streets) if years > 0 else None
    fitted[CONTEXT] = context is not None and context["fit"] is not None
    scores[CONTEXT] = context["score"] if context is not None and fitted[CONTEXT] else blend
    outcomes = {EVERY: hits}
    if "COLLISION_SEVERITY" in hits:
        severity = hits.COLLISION_SEVERITY.astype("string").str.strip()
        outcomes[WORST] = hits[severity.isin(list(WORST_CODES))]
    places = top_places(len(sites))
    rows = []
    for outcome, frame in outcomes.items():
        later = count(frame, CYCLISTS, test_from, test_to)
        for model in MODELS:
            rows.append(
                {
                    "model": model,
                    "outcome": outcome,
                    "intersections": len(sites),
                    "places": places,
                    "training crashes": int(early.sum()),
                    "larger": int(early.sum()) >= MIN_CRASHES,
                    "fitted": fitted[model],
                    "later crashes": int(later.sum()),
                    "capture": 100 * top_capture(scores[model], later, places),
                }
            )
    return pd.DataFrame(rows)


def _aggregate(capture: np.ndarray, later: np.ndarray, how: str) -> float:
    """The mean of ``capture`` over cities with a later crash, or weighted by ``later``."""
    has = later > 0
    if not has.any():
        return float("nan")
    if how == CITY_MEAN:
        return float(capture[has].mean())
    return float((capture[has] * later[has]).sum() / later[has].sum())


def compare(
    table: pd.DataFrame,
    model: str,
    other: str,
    units: Mapping[str, str] | None = None,
    outcome: str = EVERY,
    how: str = CITY_MEAN,
    draws: int = DRAWS,
    seed: int = SEED,
) -> dict[str, Any]:
    """``model`` minus ``other`` over the cities of ``table``, with a resampled range.

    ``table`` is ``score_city`` for several cities with a ``city`` column.
    ``units`` maps a city to its unit (itself when not given or not named);
    whole units are drawn with replacement, ``draws`` times, and the
    aggregate of each model recomputed.  ``lower`` and ``upper`` are the 5th
    and 95th percentiles of the difference; a draw with no later crash at all
    is left out of them.  ``cities`` counts those with a later crash, and
    ``without`` those with none, which are in neither aggregate.
    """
    rows = table[table.outcome.eq(outcome)]
    wide = rows.pivot(index="city", columns="model", values="capture")
    later = rows.groupby("city")["later crashes"].first().reindex(wide.index).to_numpy(float)
    mine, theirs = wide[model].to_numpy(float), wide[other].to_numpy(float)
    found: dict[str, Any] = {
        "model": model, "other": other, "outcome": outcome, "aggregate": how,
        "cities": int((later > 0).sum()), "without": int((later == 0).sum()),
        "model value": _aggregate(mine, later, how), "other value": _aggregate(theirs, later, how),
    }  # fmt: skip
    found["difference"] = found["model value"] - found["other value"]
    unit = pd.Series(wide.index, index=wide.index).map(lambda city: (units or {}).get(city, city))
    members = [np.flatnonzero(unit.to_numpy() == name) for name in sorted(set(unit))]
    found["units"] = len(members)
    rng = np.random.default_rng(seed)
    drawn = []
    for _ in range(draws):
        picked = np.concatenate([members[i] for i in rng.integers(0, len(members), len(members))])
        drawn.append(
            _aggregate(mine[picked], later[picked], how)
            - _aggregate(theirs[picked], later[picked], how)
        )
    kept = np.array(drawn)[np.isfinite(drawn)] if drawn else np.array([])
    found["lower"] = float(np.quantile(kept, 0.05)) if len(kept) else float("nan")
    found["upper"] = float(np.quantile(kept, 0.95)) if len(kept) else float("nan")
    return found


def verdict(lower: float, upper: float, margin: float = MARGIN) -> str:
    """Is the simpler model no worse than the other, by ``margin``?

    ``lower`` and ``upper`` are the 5th and 95th percentiles of simpler
    minus other.  No worse when ``lower`` is above minus the margin, worse
    when ``upper`` is below it, and inconclusive otherwise or when either
    is not a number.
    """
    if lower > -margin:
        return NO_WORSE
    return WORSE if upper < -margin else INCONCLUSIVE


def select(table: pd.DataFrame, units: Mapping[str, str] | None = None, **options: Any) -> dict:
    """The selection rule on the larger cities: B against H, then street context.

    B is carried forward unless it is shown worse than H.  Street context
    replaces the model carried forward only if it is no worse than it.
    Returns the model ``chosen``, its ``comparator`` and the two comparisons.
    The comparator is the model the chosen one must be no worse than at the
    final test: for street context the model it replaced, and for B or H the
    other of the two, never a model that was itself turned down.
    """
    larger = table[table.larger]
    first = compare(larger, B, H, units, **options)
    first["verdict"] = verdict(first["lower"], first["upper"])
    carried = H if first["verdict"] == WORSE else B
    second = compare(larger, CONTEXT, carried, units, **options)
    second["verdict"] = verdict(second["lower"], second["upper"])
    simpler = second["verdict"] == NO_WORSE
    return {
        "chosen": CONTEXT if simpler else carried,
        "comparator": carried if simpler else (H if carried == B else B),
        "comparisons": [first, second],
    }


def read_frozen(path: Path) -> dict[str, str]:
    """The written-down choice: a JSON object naming the ``chosen`` model and its ``comparator``.

    Raises ``ValueError`` unless both are models scored here and differ.
    """
    try:
        frozen = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: not readable as JSON: {error}") from error
    if not isinstance(frozen, dict):
        raise ValueError(f"{path}: must be a JSON object")
    for key in ("chosen", "comparator"):
        if frozen.get(key) not in (B, H, CONTEXT):
            raise ValueError(f"{path}: {key} must be one of {B!r}, {H!r}, {CONTEXT!r}")
    if frozen["chosen"] == frozen["comparator"]:
        raise ValueError(f"{path}: chosen and comparator are the same model")
    return frozen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--configs", type=Path, required=True, help="folder of one set's configs")
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    parser.add_argument("--units", type=Path, help="CSV of city (config name) and unit")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--frozen", type=Path,
        help="the written-down choice (JSON); needed to score a folder named final_test",
    )  # fmt: skip
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    final = args.configs.resolve().name == "final_test"
    frozen: dict[str, str] | None = None
    if final:
        if args.frozen is None or not args.frozen.exists():
            parser.error(
                "the final test is scored only against a written-down choice: give --frozen"
            )
        try:
            frozen = read_frozen(args.frozen)
        except ValueError as error:
            parser.error(f"the final test is scored only against a written-down choice: {error}")
    cities, left = cross.built(args.configs, args.processed)
    for name, why in left.items():
        log.info("not built, so not scored: %s (%s)", name, why)
    tables = []
    for name, (sites, streets, hits) in cross.place(cities).items():
        scored = score_city(
            hits,
            sites.index,
            streets.to_dict(),
            sites[["major", "minor"]],
            cities[name][0].first_year,
        )
        scored.insert(0, "city", name)
        tables.append(scored)
    if not tables:
        parser.error("no built city was found")
    table = pd.concat(tables, ignore_index=True)
    units: dict[str, str] | None = None
    if args.units is not None:
        named = pd.read_csv(args.units, dtype=str)
        units = dict(zip(named.city, named.unit, strict=True))
    args.out.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out / "cities.csv", index=False)
    larger = table[table.larger]
    result: dict[str, Any] = {"frozen": frozen} if frozen is not None else select(table, units)
    chosen, comparator = (frozen or result)["chosen"], (frozen or result)["comparator"]
    pairs = [(chosen, BIKE), (chosen, comparator)]
    result["primary"] = [compare(larger, a, b, units) for a, b in pairs]
    result["companion"] = [
        compare(larger, a, b, units, outcome=WORST, how=POOLED)
        for a, b in [*pairs, (pairs[0][0], CARS)]
        if WORST in set(table.outcome)
    ]
    result["left out"] = left
    (args.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
