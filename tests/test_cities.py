"""The cross-city summaries, on made-up tables."""

from __future__ import annotations

from typing import Any

import pandas as pd

from bike_safety_ca.checks import cities, reporting
from bike_safety_ca.checks.sensitivity import EVERY, VISIBLE


def _step(city: str, agency: str, measure: str, before: float, after: float, kind: str) -> dict:
    return {
        "city": city,
        "reporting_agency": agency,
        "measure": measure,
        "from_year": 2019,
        "before": before,
        "after": after,
        "kind": kind,
    }


def test_step_counts_tally_measures_and_kinds_and_say_how_many_cities_have_one() -> None:
    found = pd.DataFrame(
        [
            _step("a", "1", cities.PAIN, 100, 30, reporting.FEWER),
            _step("a", "1", reporting.ALL_INJURY, 200, 100, reporting.FEWER),
            _step("a", "2", cities.PAIN, 100, 30, reporting.REGRADED),
            _step("b", "1", cities.PAIN, 10, 40, reporting.MORE),  # a rise: not a fall
            _step("b", "1", "Serious injury", 20, 40, reporting.MORE),
        ]
    )
    table, line = cities.step_counts(found, cities=5)
    assert table.index.tolist() == [reporting.ALL_INJURY, *reporting.SEVERITIES.values()]
    assert table.columns.tolist() == [reporting.FEWER, reporting.REGRADED, reporting.MORE]
    rows = {str(name): list(values.values()) for name, values in table.to_dict("index").items()}
    assert rows[cities.PAIN] == [1, 1, 1]
    assert rows[reporting.ALL_INJURY] == [1, 0, 0]
    assert rows["Serious injury"] == [0, 0, 1]
    assert int(table.to_numpy().sum()) == len(found)
    assert line == (
        "2 of 5 cities have at least one agency with a step, 3 agencies in all; "
        "2 agencies have a fall in complaint-of-pain reports, "
        "1 of them with a step in their total as well"
    )
    empty, line = cities.step_counts(found.iloc[0:0], cities=5)
    assert int(empty.to_numpy().sum()) == 0 and line.startswith("0 of 5 cities")


def _window(city: str, window: int, fitted: tuple[bool, bool], scores: tuple[float, ...]) -> list:
    """Four rows of ``severity``'s table: scores are (all|all, all|visible, visible|all, v|v)."""
    rows = []
    order = [(EVERY, EVERY), (EVERY, VISIBLE), (VISIBLE, EVERY), (VISIBLE, VISIBLE)]
    for (target, trained), score in zip(order, scores, strict=True):
        rows.append(
            {
                "city": city,
                "trained": trained,
                "target": target,
                "window": window,
                "fitted": fitted[0] if trained == EVERY else fitted[1],
                "training": 100,
                "later": 40,
                "score": score,
            }
        )
    return rows


def test_the_severity_summary_splits_windows_by_how_the_rankings_were_built() -> None:
    scored = pd.DataFrame(
        _window("a", 0, (True, True), (0.80, 0.78, 0.82, 0.81))
        + _window("a", 1, (True, False), (0.90, 0.80, 0.90, 0.84))
        + _window("b", 0, (True, True), (0.70, 0.72, 0.70, 0.70))
        + _window("c", 2, (False, False), (0.60, 0.58, 0.62, 0.60))
        + _window("d", 0, (True, True), (0.80, 0.70, 0.80, 0.80))
    )
    summary = cities.severity_summary(scored, with_fall=["a", "d"])
    rows = {str(name): values for name, values in summary.to_dict("index").items()}
    every = f"later {EVERY}"
    visible = f"later {VISIBLE}"

    everything = rows[cities.ALL_WINDOWS]
    assert (everything["windows"], everything["cities"]) == (5, 4)
    assert everything[f"{every}, trained on {EVERY}"] == 0.76
    assert everything[f"{every}, trained on {VISIBLE}"] == 0.716
    assert everything[f"{every}: lost without minor crashes"] == 0.044
    assert everything[f"{every}: windows where it loses"] == 4  # not b, where it gains
    assert everything[f"{visible}: lost without minor crashes"] == 0.018
    assert everything[f"{visible}: windows where it loses"] == 3  # b and d are level: no loss

    fitted = rows[cities.BOTH_FITTED]
    assert (fitted["windows"], fitted["cities"]) == (3, 3)
    assert fitted[f"{every}: lost without minor crashes"] == 0.033  # 0.02, -0.02 and 0.10
    one = rows[cities.ONE_FELL_BACK]
    assert (one["windows"], one["cities"]) == (1, 1)
    assert one[f"{every}: lost without minor crashes"] == 0.1
    assert rows[cities.BOTH_FELL_BACK]["windows"] == 1

    # A city counts once however many windows it has.  Cities a (two windows, losing 0.02
    # and 0.10) and d (one, losing 0.10): (0.06 + 0.10) / 2, where the three windows
    # taken together would give 0.073.
    fall, none = rows[cities.WITH_FALL], rows[cities.WITHOUT_FALL]
    assert (fall["windows"], fall["cities"]) == (3, 2)
    assert fall[f"{every}: lost without minor crashes"] == 0.08
    assert fall[f"{every}, trained on {EVERY}"] == 0.825  # (0.85 + 0.80) / 2, not 0.833
    assert (none["windows"], none["cities"]) == (2, 2)
    assert none[f"{every}: lost without minor crashes"] == 0.0  # b -0.02, c 0.02


def test_the_severity_summary_of_no_windows_has_empty_rows() -> None:
    columns = ["city", "trained", "target", "window", "fitted", "training", "later", "score"]
    summary = cities.severity_summary(pd.DataFrame(columns=columns))
    assert summary.windows.tolist() == [0] * 6 and summary.cities.tolist() == [0] * 6
    assert summary[f"later {EVERY}: lost without minor crashes"].isna().all()


def _holdout_row(
    city: str,
    through: int,
    outcome: str,
    ranking: str,
    score: float | None,
    later: int,
    top: float = 0.0,
    training: int = 500,
    method: str = cities.FITTED,
    sites: int = 900,
) -> dict[str, object]:
    return {
        "city": city,
        "intersections": sites,
        "trained through": through,
        "tested on": f"{through + 1}–{through + 2}",
        "outcome": outcome,
        "area": cities.WHOLE,
        "ranking": ranking,
        "method": method,
        "training crashes": training,
        "later crashes": later,
        "rank score": score,
        "found in top 100": top if score is not None else None,
    }


def test_the_city_results_average_the_scored_windows_and_say_how_the_model_was_fitted() -> None:
    every, child = cities.EVERYONE, cities.CHILDREN
    model, history = cities.MODEL, cities.HISTORY
    table = pd.DataFrame(
        [
            # City a: two windows scored and one with too few later crashes, fitted in all.
            _holdout_row("a", 2018, every, model, 0.80, 100, top=40),
            _holdout_row("a", 2018, every, history, 0.60, 100, top=30),
            _holdout_row("a", 2020, every, model, 0.90, 50, top=25),
            _holdout_row("a", 2020, every, history, 0.70, 50, top=10),
            _holdout_row("a", 2022, every, model, None, 12),
            _holdout_row("a", 2022, every, history, None, 12),
            _holdout_row("a", 2018, child, model, 0.70, 40),
            _holdout_row("a", 2020, child, model, None, 7),
            _holdout_row("a", 2022, child, model, None, 3),
            # City b: one window, the blend in it, and a better score than a.
            _holdout_row("b", 2018, every, model, 0.95, 60, top=20, method=cities.BLEND, sites=300),
            _holdout_row("b", 2018, every, history, 0.65, 60, top=15, sites=300),
            _holdout_row("b", 2018, child, model, None, 5, method=cities.BLEND, sites=300),
            # City c: the model in one window and the blend in the other.
            _holdout_row("c", 2018, every, model, 0.75, 60, top=20),
            _holdout_row("c", 2020, every, model, 0.75, 60, top=20, method=cities.BLEND),
            _holdout_row("c", 2018, every, history, 0.5, 60, top=5),
            _holdout_row("c", 2020, every, history, 0.5, 60, top=5),
            _holdout_row("c", 2018, child, model, 0.6, 30),
            _holdout_row("c", 2020, child, model, 0.8, 30),
        ]
    )
    found = cities.results(table)
    assert found.index.tolist() == ["b", "a", "c"]  # best all-cyclist score first
    rows: dict[Any, dict[Any, Any]] = found.to_dict("index")
    a = rows["a"]
    assert (a["intersections"], a["windows scored"], a["fit"]) == (900, 2, "model")
    assert (a["rank score"], a["history alone"]) == (0.85, 0.65)
    # Top-100 counts and later crashes are summed over the two windows scored, not the third.
    assert (a["top 100, model"], a["top 100, history"], a["later crashes"]) == (65, 40, 150)
    assert (a["child windows scored"], a["rank score, children"]) == (1, 0.7)
    assert a["fewest later child crashes"] == 3  # over every window, scored or not
    b, c = rows["b"], rows["c"]
    assert (b["fit"], b["intersections"], b["child windows scored"]) == ("blend", 300, 0)
    assert pd.isna(b["rank score, children"])
    assert (c["fit"], c["rank score, children"]) == ("mixed", 0.7)


def test_the_child_ranking_table_splits_windows_by_child_crashes_in_the_training_years() -> None:
    child, model, everyone = cities.CHILDREN, cities.MODEL, cities.ALL_CYCLISTS
    few, enough = cities.MIN_CRASHES - 1, cities.MIN_CRASHES
    later_test: dict[str, object] = {"tested on": "2021–2022"}
    table = pd.DataFrame(
        [
            _holdout_row("a", 2018, child, model, 0.70, 40, training=few),
            _holdout_row("a", 2018, child, everyone, 0.80, 40, training=few),
            _holdout_row("a", 2020, child, model, 0.90, 40, training=enough),
            _holdout_row("a", 2020, child, everyone, 0.85, 40, training=enough),
            _holdout_row("b", 2018, child, model, 0.60, 40, training=few),
            _holdout_row("b", 2018, child, everyone, 0.50, 40, training=few),
            # A second window of city a in the same group: two windows, still one city.
            _holdout_row("a", 2016, child, model, 0.50, 40, training=few),
            _holdout_row("a", 2016, child, everyone, 0.60, 40, training=few),
            # Two windows trained through the same year are told apart by their test years.
            _holdout_row("b", 2018, child, model, 0.90, 40, training=few) | later_test,
            _holdout_row("b", 2018, child, everyone, 0.95, 40, training=few) | later_test,
            # No child score in this window, so it is not counted.
            _holdout_row("b", 2020, child, model, None, 9, training=few),
            _holdout_row("b", 2020, child, everyone, None, 9, training=few),
            # Other outcomes are not counted either.
            _holdout_row("b", 2018, cities.EVERYONE, model, 0.99, 400, training=few),
        ]
    )
    found = cities.child_ranking(table)
    assert found.index.tolist() == [f"Under {enough}", f"{enough} or more"]
    under, over = found.iloc[0].to_dict(), found.iloc[1].to_dict()
    assert (under["windows"], under["cities"]) == (4, 2)
    assert under["ranking fitted to child crashes"] == 0.675  # 0.7, 0.5, 0.6 and 0.9
    assert under["all-cyclist ranking"] == 0.712  # 0.8, 0.6, 0.5 and 0.95
    assert under["child ranking better in"] == 1  # city b's first window
    assert (over["windows"], over["cities"], over["child ranking better in"]) == (1, 1, 1)
    assert (over["ranking fitted to child crashes"], over["all-cyclist ranking"]) == (0.9, 0.85)


def test_the_pooled_summary_sets_each_city_alone_beside_each_pool_it_is_in() -> None:
    every, child, model = cities.EVERYONE, cities.CHILDREN, cities.MODEL
    alone = pd.DataFrame(
        [
            _holdout_row("a", 2018, every, model, 0.70, 60),
            _holdout_row("a", 2020, every, model, 0.80, 60),
            _holdout_row("a", 2018, child, model, None, 9),
            _holdout_row("a", 2020, child, model, None, 9),
            _holdout_row("b", 2018, every, model, 0.60, 60),
            _holdout_row("b", 2018, child, model, 0.50, 31),
            _holdout_row("a", 2018, every, cities.HISTORY, 0.10, 60),  # not the model: ignored
            # City b was fitted on a wider area: it is its limit that is compared.
            _holdout_row("b", 2018, every, model, 0.66, 50) | {"area": cities.LIMIT},
            _holdout_row("b", 2018, child, model, None, 20) | {"area": cities.LIMIT},
        ]
    )

    def inside(pool: str, city: str, through: int, outcome: str, score: float | None) -> dict:
        row = _holdout_row(city, through, outcome, model, score, 60)
        del row["area"], row["intersections"]
        return {"pool": pool, **row}

    together = pd.DataFrame(
        [
            inside("p", "a", 2018, every, 0.90),
            inside("p", "a", 2020, every, 0.80),
            inside("p", "a", 2018, child, 0.75),
            inside("p", "a", 2020, child, None),
            inside("p", "b", 2018, every, 0.65),
            inside("p", "b", 2018, child, 0.55),
            inside("q", "a", 2018, every, 0.72),
            inside("q", "a", 2018, child, None),
        ]
    )
    found = cities.pooled_summary(alone, together).set_index(["pool", "city"])
    assert found.index.tolist() == [("p", "a"), ("p", "b"), ("q", "a")]
    rows: dict[Any, dict[Any, Any]] = found.to_dict("index")
    first = rows[("p", "a")]
    assert (first[f"{every}, alone"], first[f"{every}, pooled"]) == (0.75, 0.85)
    assert (first[f"{every}, alone, windows"], first[f"{every}, pooled, windows"]) == (2, 2)
    assert pd.isna(first[f"{child}, alone"]) and first[f"{child}, alone, windows"] == 0
    assert (first[f"{child}, pooled"], first[f"{child}, pooled, windows"]) == (0.75, 1)
    second = rows[("q", "a")]
    assert (second[f"{every}, alone"], second[f"{every}, pooled"]) == (0.75, 0.72)
    third = rows[("p", "b")]
    assert (third[f"{every}, alone"], third[f"{child}, alone, windows"]) == (0.66, 0)
    assert pd.isna(third[f"{child}, alone"])

    # A pool with rows for one outcome only: the other has no windows, not a missing count.
    one = cities.pooled_summary(alone, together[together.outcome.eq(every)])
    assert one[f"{child}, pooled, windows"].tolist() == [0, 0, 0]


def test_the_summaries_of_no_cities_keep_their_columns() -> None:
    nothing = pd.DataFrame(
        columns=list(_holdout_row("a", 2018, cities.EVERYONE, cities.MODEL, 1, 1))
    )
    found = cities.results(nothing)
    assert found.empty and "rank score" in found.columns and "fit" in found.columns
    assert cities.child_ranking(nothing).windows.tolist() == [0, 0]
    # A city with all-cyclist rows only has no child windows and no child count.
    only = pd.DataFrame([_holdout_row("a", 2018, cities.EVERYONE, cities.MODEL, 0.8, 50)])
    row: dict[Any, Any] = cities.results(only).iloc[0].to_dict()
    assert (row["child windows scored"], row["fewest later child crashes"]) == (0, 0)
