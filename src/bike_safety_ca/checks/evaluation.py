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

from bike_safety_ca.checks import assignment, reporting
from bike_safety_ca.checks import cities as cross
from bike_safety_ca.checks.candidates import _hash, _revision, top_places
from bike_safety_ca.checks.holdout import CAR, CYCLISTS
from bike_safety_ca.config import Config
from bike_safety_ca.crashes.tims import FALL, RISE
from bike_safety_ca.io import crs_tag
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
# The textbook regression without the street columns: scored for description
# only, never a candidate of the selection rule.
PLAIN = "Textbook regression"
MODELS = (B, H, CONTEXT, PLAIN, BLEND, BIKE, CARS)
EVERY, WORST = "all injury", "fatal or severe"
WORST_CODES = ("1", "2")
TRAIN_TO, TEST_FROM, TEST_TO = 2020, 2021, 2024
MARGIN = 1.0  # percentage points of capture
NO_WORSE, WORSE, INCONCLUSIVE = "no worse", "worse", "inconclusive"
CITY_MEAN, POOLED = "city mean", "pooled"
# The columns a comparison can be made on: the capture, or the capture as a
# percentage of what the best possible list would have captured.
CAPTURE, OF_BEST = "capture", "share of best"
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
    ``best capture`` is what a list in order of the later crashes themselves
    would have captured, and ``share of best`` the capture as a percentage
    of it.  That list is made with hindsight: it is not a benchmark a forecast is expected to reach.
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
    for name, with_streets in ((CONTEXT, streets), (PLAIN, None)):
        standard = (
            rank_standard(early, car, classes, years, streets=with_streets) if years > 0 else None
        )
        fitted[name] = standard is not None and standard["fit"] is not None
        scores[name] = standard["score"] if standard is not None and fitted[name] else blend
    outcomes = {EVERY: hits}
    if "COLLISION_SEVERITY" in hits:
        severity = hits.COLLISION_SEVERITY.astype("string").str.strip()
        outcomes[WORST] = hits[severity.isin(list(WORST_CODES))]
    places = top_places(len(sites))
    rows = []
    for outcome, frame in outcomes.items():
        later = count(frame, CYCLISTS, test_from, test_to)
        # the list in order of the later crashes themselves: no list can capture more
        best = 100 * top_capture(later.astype(float), later, places)
        for model in MODELS:
            capture = 100 * top_capture(scores[model], later, places)
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
                    CAPTURE: capture,
                    "best capture": best,
                    OF_BEST: 100 * capture / best,
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
    value: str = CAPTURE,
) -> dict[str, Any]:
    """``model`` minus ``other`` over the cities of ``table``, with a resampled range.

    ``value`` is the column compared: ``CAPTURE`` or ``OF_BEST``.

    ``table`` is ``score_city`` for several cities with a ``city`` column.
    ``units`` maps a city to its unit (itself when not given or not named);
    whole units are drawn with replacement, ``draws`` times, and the
    aggregate of each model recomputed.  ``lower`` and ``upper`` are the 5th
    and 95th percentiles of the difference; a draw with no later crash at all
    is left out of them.  ``cities`` counts those with a later crash, and
    ``without`` those with none, which are in neither aggregate.  With no
    city at all the comparison is returned with no values, not refused.
    """
    rows = table[table.outcome.eq(outcome)]
    if rows.empty:
        return {
            "model": model, "other": other, "outcome": outcome, "aggregate": how,
            "value": value, "cities": 0, "without": 0, "units": 0,
            **dict.fromkeys(("model value", "other value", "difference", "lower", "upper"), float("nan")),
        }  # fmt: skip
    wide = rows.pivot(index="city", columns="model", values=value)
    later = rows.groupby("city")["later crashes"].first().reindex(wide.index).to_numpy(float)
    mine, theirs = wide[model].to_numpy(float), wide[other].to_numpy(float)
    found: dict[str, Any] = {
        "model": model, "other": other, "outcome": outcome, "aggregate": how, "value": value,
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


def reporting_checks(config: Config, folder: Path) -> dict[str, Any]:
    """The two count checks of a city's records; neither reads a ranking or a score.

    ``minor ratio`` and ``minor check`` are ``reporting.minor_injury_change``
    on the merged table.  ``agency years`` lists the agency-years from the
    first fitting year to the last scored year whose injury crashes the
    agency check calls a fall or a rise (not a "possible" one).  ``clear``
    is true when the first is not flagged, is assessable, and the second
    lists nothing.
    """
    crashes = reporting.load(folder / "crashes", config.crs, config.first_year)
    minor = reporting.minor_injury_change(crashes)
    years_on_record = reporting.all_years(crashes)
    span = (years_on_record[0], years_on_record[-1]) if years_on_record else None
    ends = pd.to_datetime(crashes.collision_date, errors="coerce").max() if len(crashes) else None
    # as ``reporting.diagnose`` flags injury crashes
    found = reporting.flags(crashes, reporting.MEASURES["injury_crashes"][1], span, ends)
    certain = found[
        found.change.isin([FALL, RISE]) & found.year.between(config.first_year, TEST_TO)
    ]
    years = [f"{row.reporting_agency} {row.year} {row.change}" for row in certain.itertuples()]
    return {
        "minor ratio": minor["ratio"],
        "minor check": minor["verdict"],
        "minor reason": minor["reason"],
        "agency years": "; ".join(years),
        "clear": minor["verdict"] == reporting.STEADY and not years,
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


def report(
    table: pd.DataFrame,
    units: Mapping[str, str] | None,
    clear: Mapping[str, bool],
    frozen: Mapping[str, str] | None = None,
    **options: Any,
) -> dict[str, Any]:
    """Every result of one set of cities, from ``score_city``'s rows with a ``city`` column.

    Without ``frozen`` the selection rule chooses the model; with it the
    written-down choice is used.  ``primary`` is the chosen model against
    past bike crashes alone and against its comparator: the city mean on
    all injury crashes over the larger cities.  ``companion`` is those two
    and the chosen model against past car crashes, pooled on fatal or
    severe crashes.  ``without flagged cities`` repeats ``primary`` over the
    larger cities that are ``clear`` (a sensitivity result, which has no
    values when none is).  ``share of best possible`` repeats ``primary``
    on ``OF_BEST``, a secondary result with no rule.  ``other lists`` is the
    chosen model against each remaining list, as ``primary`` is computed: a
    description, declared in no claim.  ``smaller cities`` is the chosen model against
    the two floors, pooled over the cities under the fitting threshold.
    """
    result: dict[str, Any] = {"frozen": dict(frozen)} if frozen else select(table, units, **options)
    chosen, comparator = (frozen or result)["chosen"], (frozen or result)["comparator"]
    pairs = [(chosen, BIKE), (chosen, comparator)]
    larger = table[table.larger]
    result["primary"] = [compare(larger, a, b, units, **options) for a, b in pairs]
    result["companion"] = [
        compare(larger, a, b, units, outcome=WORST, how=POOLED, **options)
        for a, b in [*pairs, (chosen, CARS)]
        if WORST in set(table.outcome)
    ]
    unflagged = larger[larger.city.map(lambda city: bool(clear.get(city, False)))]
    result["without flagged cities"] = [
        compare(unflagged, a, b, units, **options) for a, b in pairs
    ]
    # A secondary result: the primary pairs as a share of the best possible list.
    result["share of best possible"] = [
        compare(larger, a, b, units, value=OF_BEST, **options) for a, b in pairs
    ]
    # Descriptions, under no rule: the chosen model against every other list scored.
    result["other lists"] = [
        compare(larger, chosen, other, units, **options)
        for other in MODELS
        if other not in (chosen, comparator, BIKE) and other in set(table.model)
    ]
    smaller = table[~table.larger]
    result["smaller cities"] = [
        compare(smaller, chosen, floor, units, how=POOLED, **options) for floor in (BIKE, CARS)
    ]
    return result


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
    checks: dict[str, dict[str, Any]] = {}
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
        config, folder = cities[name]
        table_path = folder / "crashes" / f"crashes_merged_{crs_tag(config.crs)}.parquet"
        checks[name] = reporting_checks(config, folder) | {"crash table": _hash(table_path)}
    if not tables:
        parser.error("no built city was found")
    table = pd.concat(tables, ignore_index=True)
    units: dict[str, str] | None = None
    if args.units is not None:
        named = pd.read_csv(args.units, dtype=str)
        units = dict(zip(named.city, named.unit, strict=True))
    args.out.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out / "cities.csv", index=False)
    result = report(table, units, {city: found["clear"] for city, found in checks.items()}, frozen)
    result["left out"] = left
    by_city = table[table.model.eq(B)].pivot(
        index="city", columns="outcome", values="later crashes"
    )
    facts = table.groupby("city")[["intersections", "places", "training crashes", "larger"]].first()
    manifest = facts.join(by_city.add_prefix("later crashes, ")).join(pd.DataFrame(checks).T)
    manifest.insert(0, "unit", [(units or {}).get(city, city) for city in manifest.index])
    manifest.to_csv(args.out / "manifest.csv")
    record = {
        "revision": _revision(),
        "configs": str(args.configs),
        "window": [TRAIN_TO, TEST_FROM, TEST_TO],
        "margin": MARGIN,
        "draws": DRAWS,
        "seed": SEED,
        "assignment salt": assignment.SALT,
        "not built": left,
    }
    (args.out / "run.json").write_text(json.dumps(record, indent=2) + "\n")
    (args.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
