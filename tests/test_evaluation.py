from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from bike_safety_ca import ADULT, CAR, CHILD
from bike_safety_ca.checks import evaluation
from bike_safety_ca.checks.evaluation import (
    BIKE,
    BLEND,
    CARS,
    CONTEXT,
    EVERY,
    POOLED,
    WORST,
    B,
    H,
    compare,
    score_city,
    verdict,
)  # fmt: skip
from bike_safety_ca.model.crash_history import top_capture


def _city(
    seed: int, rate: float = 0.05, side: int = 24
) -> tuple[pd.DataFrame, pd.Index, dict, pd.DataFrame]:
    """A made-up grid city: crashes by site, year, group and severity, 2015 to 2024."""
    rng = np.random.default_rng(seed)
    sites = pd.RangeIndex(side * side)
    streets = {site: {f"R{site // side}", f"C{site % side}"} for site in sites}
    busy = rng.lognormal(0, 0.7, side)[sites // side] * rng.lognormal(0, 0.7, side)[sites % side]
    parts = []
    for group, each in ((ADULT, rate), (CHILD, rate * 0.8), (CAR, 0.6)):
        for year in range(2015, 2025):
            hit = np.repeat(sites.to_numpy(), rng.poisson(each * busy))
            parts.append(pd.DataFrame({"site": hit, "year": year, "group": group}))
    hits = pd.concat(parts, ignore_index=True)
    hits["COLLISION_SEVERITY"] = rng.choice(
        ["1", "2", "3", "4"], len(hits), p=[0.02, 0.1, 0.4, 0.48]
    )
    classes = pd.DataFrame(
        {"major": np.where(sites % side < 4, "primary", "residential"), "minor": "residential"},
        index=sites,
    )
    return hits, sites, streets, classes


@pytest.fixture(scope="module")
def scored() -> pd.DataFrame:
    return score_city(*_city(3), first_year=2015)


def test_every_model_is_scored_on_both_outcomes_from_the_fitting_years_only(
    scored: pd.DataFrame,
) -> None:
    assert set(scored.model) == set(evaluation.MODELS)
    assert set(scored.outcome) == {EVERY, WORST}
    hits, sites, _, _ = _city(3)
    bike = hits[hits.group.isin([ADULT, CHILD])]
    early = bike[bike.year.le(2020)].groupby("site").size().reindex(sites, fill_value=0)
    later = bike[bike.year.between(2021, 2024)].groupby("site").size().reindex(sites, fill_value=0)
    row = scored[scored.model.eq(BIKE) & scored.outcome.eq(EVERY)].iloc[0]
    assert row["training crashes"] == early.sum() and row["later crashes"] == later.sum()
    assert row.places == 29 and row.intersections == 576  # 5% of 576, rounded up
    assert row.capture == pytest.approx(100 * top_capture(early.astype(float), later, 29))
    # the best possible list is in order of the later crashes; nothing captures more
    assert row["best capture"] == pytest.approx(100 * top_capture(later.astype(float), later, 29))
    assert row["share of best"] == pytest.approx(100 * row.capture / row["best capture"])
    every = scored[scored.outcome.eq(EVERY)]
    assert every.capture.le(every["best capture"]).all() and every["share of best"].le(100).all()
    worst = scored[scored.outcome.eq(WORST)]
    assert 0 < worst["later crashes"].iloc[0] < row["later crashes"]
    assert bool(row.larger) and scored[scored.model.eq(B)].fitted.all()
    # every list does better than one in random order (in this made-up city car and
    # bike crashes follow the same pattern, so no order among the lists is expected)
    by_model = scored[scored.outcome.eq(EVERY)].set_index("model").capture
    assert by_model.gt(100 * (29 + 1) / (2 * 576)).all()


def test_a_city_too_small_to_fit_is_scored_by_the_blend_for_every_fitted_model() -> None:
    small = score_city(*_city(5, rate=0.004), first_year=2015)
    rows = small[small.outcome.eq(EVERY)].set_index("model")
    assert not rows.larger.any()
    assert not rows.fitted[[B, H, CONTEXT, evaluation.PLAIN]].any()
    assert rows.capture[[B, H, CONTEXT, evaluation.PLAIN]].eq(rows.capture[BLEND]).all()


def test_a_crash_table_without_severity_is_scored_on_all_crashes_only() -> None:
    hits, sites, streets, classes = _city(3)
    scored = score_city(hits.drop(columns="COLLISION_SEVERITY"), sites, streets, classes, 2015)
    assert set(scored.outcome) == {EVERY}


def _table(captures: dict[str, tuple[float, float, int]]) -> pd.DataFrame:
    """Made-up scores: for each city, model a's and model b's capture and its later crashes."""
    rows = []
    for city, (mine, theirs, later) in captures.items():
        for model, capture in (("a", mine), ("b", theirs)):
            rows.append({"city": city, "model": model, "outcome": EVERY,
                         "later crashes": later, "capture": capture})  # fmt: skip
    return pd.DataFrame(rows)


def test_the_city_mean_weighs_cities_equally_and_the_pooled_figure_by_later_crashes() -> None:
    table = _table({"p": (30.0, 20.0, 10), "q": (10.0, 20.0, 90), "r": (np.nan, np.nan, 0)})
    mean = compare(table, "a", "b", draws=200)
    assert mean["model value"] == pytest.approx(20) and mean["difference"] == pytest.approx(0)
    assert (mean["cities"], mean["without"], mean["units"]) == (2, 1, 3)
    pooled = compare(table, "a", "b", how=POOLED, draws=200)
    assert pooled["model value"] == pytest.approx((30 * 10 + 10 * 90) / 100)
    assert pooled["difference"] == pytest.approx(12 - 20)
    assert pooled["lower"] <= pooled["difference"] <= pooled["upper"]


def test_cities_of_one_unit_are_drawn_together() -> None:
    table = _table({"p": (30.0, 20.0, 10), "q": (10.0, 20.0, 10)})
    apart = compare(table, "a", "b", draws=400, seed=1)
    assert apart["lower"] == pytest.approx(-10) and apart["upper"] == pytest.approx(10)
    together = compare(table, "a", "b", units={"p": "u", "q": "u"}, draws=400, seed=1)
    assert together["units"] == 1
    assert together["lower"] == together["upper"] == pytest.approx(0)


def test_a_comparison_with_no_later_crash_anywhere_is_not_a_number() -> None:
    empty = compare(_table({"p": (np.nan, np.nan, 0)}), "a", "b", how=POOLED, draws=20)
    assert np.isnan(empty["difference"]) and np.isnan(empty["lower"])
    assert verdict(empty["lower"], empty["upper"]) == evaluation.INCONCLUSIVE


def test_no_worse_needs_the_lower_bound_inside_the_margin() -> None:
    assert verdict(-0.9, 0.5) == evaluation.NO_WORSE
    assert verdict(-3.0, -1.2) == evaluation.WORSE
    assert verdict(-3.0, 1.4) == evaluation.INCONCLUSIVE  # the mean could pass; the bound does not
    assert verdict(-1.0, 0.0) == evaluation.INCONCLUSIVE  # on the line is not inside it


def _selection(context: float, h: float) -> pd.DataFrame:
    rows = []
    for number in range(8):
        for model, capture in ((B, 25.0), (H, 25.0 + h), (CONTEXT, 25.0 + context)):
            rows.append({"city": f"c{number}", "model": model, "outcome": EVERY, "larger": True,
                         "later crashes": 50, "capture": capture + 0.1 * (number % 3)})  # fmt: skip
    return pd.DataFrame(rows)


def test_selection_keeps_b_unless_it_is_shown_worse_and_takes_a_simpler_model_that_is_no_worse() -> (
    None
):
    kept = evaluation.select(_selection(context=-2.0, h=0.2), draws=200)
    # B's comparator is H, the model it was kept over, not the street context it turned down
    assert (kept["chosen"], kept["comparator"]) == (B, H)
    assert [c["verdict"] for c in kept["comparisons"]] == [evaluation.NO_WORSE, evaluation.WORSE]
    simpler = evaluation.select(_selection(context=-0.3, h=0.2), draws=200)
    assert (simpler["chosen"], simpler["comparator"]) == (CONTEXT, B)
    flexible = evaluation.select(_selection(context=-2.0, h=1.5), draws=200)
    assert (flexible["chosen"], flexible["comparator"]) == (H, B)
    # a city under the fitting threshold is not in the rule
    mixed = _selection(context=-2.0, h=0.2)
    mixed.loc[mixed.city.eq("c0"), "larger"] = False
    assert evaluation.select(mixed, draws=50)["comparisons"][0]["cities"] == 7


def test_the_final_test_folder_is_refused_without_a_written_down_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    final = tmp_path / "final_test"
    final.mkdir()
    bad = {
        "empty.json": "{}",
        "list.json": "[]",
        "broken.json": "{",
        "same.json": json.dumps({"chosen": evaluation.B, "comparator": evaluation.B}),
        "unknown.json": json.dumps({"chosen": evaluation.B, "comparator": "something else"}),
    }
    for name, text in bad.items():
        (tmp_path / name).write_text(text)
        with pytest.raises(ValueError, match=name):
            evaluation.read_frozen(tmp_path / name)
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"chosen": evaluation.B, "comparator": evaluation.H, "note": "x"}))
    assert evaluation.read_frozen(good)["comparator"] == evaluation.H
    refused = [[], ["--frozen", str(tmp_path / "missing.json")]]
    refused += [["--frozen", str(tmp_path / name)] for name in bad]
    for extra in refused:
        argv = ["evaluation", "--configs", str(final), "--out", str(tmp_path / "out"), *extra]
        monkeypatch.setattr("sys.argv", argv)
        with pytest.raises(SystemExit):
            evaluation.main()
        assert "written-down choice" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_a_folder_with_no_built_city_stops_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "selection").mkdir()
    argv = ["evaluation", "--configs", str(tmp_path / "selection"), "--out", str(tmp_path / "out")]
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit):
        evaluation.main()
    assert "no built city" in capsys.readouterr().err


def _records(per_year: dict[int, int]) -> pd.DataFrame:
    """Made-up injury crashes of one agency: how many in each year, a tenth of them serious."""
    rows = [
        {
            "year": year,
            "COLLISION_SEVERITY": "2" if number % 10 == 0 else "4",
            "reporting_agency": "4301",
            "bike_involved": number % 7 == 0,
            "collision_date": f"{year}-{1 + number % 12:02d}-15",
        }
        for year, count in per_year.items()
        for number in range(count)
    ]
    return pd.DataFrame(rows)


@pytest.mark.parametrize(
    ("changed", "clear", "minor", "agency"),
    [
        ({}, True, "not flagged", ""),
        ({2022: 8}, False, "not flagged", "4301 2022 fall"),
        ({2021: 40, 2022: 40, 2023: 40, 2024: 40}, False, "flagged", None),
    ],
)
def test_a_city_is_clear_only_when_neither_count_check_flags_it(
    changed: dict[int, int], clear: bool, minor: str, agency: str | None,
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:  # fmt: skip
    records = _records(dict.fromkeys(range(2015, 2025), 100) | changed)
    monkeypatch.setattr(evaluation.reporting, "load", lambda *_: records)
    config = SimpleNamespace(crs="EPSG:26910", first_year=2015)
    found = evaluation.reporting_checks(config, tmp_path)  # type: ignore[arg-type]
    assert found["clear"] is clear and found["minor check"] == minor
    if agency is not None:
        assert found["agency years"] == agency


def _set_of_cities() -> pd.DataFrame:
    """Made-up scores: six larger cities and two smaller, every model, both outcomes."""
    rows = []
    for number in range(8):
        for outcome, later in ((EVERY, 40 + number), (WORST, 4)):
            for shift, model in enumerate(evaluation.MODELS):
                rows.append({"city": f"c{number}", "model": model, "outcome": outcome,
                             "larger": number < 6, "later crashes": later,
                             "capture": 30.0 - 2 * shift + 0.1 * number,
                             "share of best": 2 * (30.0 - 2 * shift + 0.1 * number)})  # fmt: skip
    return pd.DataFrame(rows)


def test_the_report_gives_each_result_its_cities_and_pairs() -> None:
    table = _set_of_cities()
    clear = {f"c{number}": number != 0 for number in range(8)}
    found = evaluation.report(table, None, clear, draws=50)
    assert (found["chosen"], found["comparator"]) == (B, H)
    pairs = lambda rows: [(row["model"], row["other"]) for row in rows]  # noqa: E731
    assert pairs(found["primary"]) == [(B, BIKE), (B, H)]
    assert pairs(found["companion"]) == [(B, BIKE), (B, H), (B, CARS)]
    assert {row["aggregate"] for row in found["companion"]} == {POOLED}
    assert {row["outcome"] for row in found["companion"]} == {WORST}
    assert [row["cities"] for row in found["primary"]] == [6, 6]
    assert [row["cities"] for row in found["without flagged cities"]] == [5, 5]
    # the same pairs as a share of the best possible list (twice the capture, as made up here)
    of_best = found["share of best possible"]
    assert pairs(of_best) == pairs(found["primary"])
    assert {row["value"] for row in of_best} == {evaluation.OF_BEST}
    assert of_best[0]["difference"] == pytest.approx(2 * found["primary"][0]["difference"])
    assert {row["value"] for row in found["primary"]} == {evaluation.CAPTURE}
    # every list that is in neither primary pair is described against the chosen model
    assert pairs(found["other lists"]) == [
        (B, evaluation.CONTEXT), (B, evaluation.PLAIN), (B, evaluation.BLEND), (B, CARS)
    ]  # fmt: skip
    assert {row["cities"] for row in found["other lists"]} == {6}
    # the smaller cities are compared with both floors, not with the comparator
    assert pairs(found["smaller cities"]) == [(B, BIKE), (B, CARS)]
    assert [row["cities"] for row in found["smaller cities"]] == [2, 2]
    # the made-up capture falls by 2 for each place down MODELS, and past bike
    # crashes are five places below B (four before the textbook regression was listed)
    steps = evaluation.MODELS.index(BIKE) - evaluation.MODELS.index(B)
    assert found["smaller cities"][0]["difference"] == pytest.approx(2.0 * steps)
    frozen = evaluation.report(table, None, clear, {"chosen": H, "comparator": B}, draws=50)
    assert "chosen" not in frozen and pairs(frozen["primary"]) == [(H, BIKE), (H, B)]


def test_a_set_with_no_clear_city_or_no_smaller_city_still_reports_the_rest() -> None:
    table = _set_of_cities()
    none_clear = evaluation.report(table, None, {}, draws=50)
    assert [row["cities"] for row in none_clear["without flagged cities"]] == [0, 0]
    assert all(np.isnan(row["difference"]) for row in none_clear["without flagged cities"])
    assert [row["cities"] for row in none_clear["primary"]] == [6, 6]
    all_larger = evaluation.report(table[table.larger], None, {}, draws=50)
    assert [row["cities"] for row in all_larger["smaller cities"]] == [0, 0]
    json.dumps(none_clear)  # what the command writes
