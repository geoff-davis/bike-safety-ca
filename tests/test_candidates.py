from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bike_safety_ca import ADULT, CAR, CHILD
from bike_safety_ca.checks import candidates
from bike_safety_ca.checks.candidates import (
    BLEND,
    CHILDREN,
    EVERYONE,
    FITTED_POWER,
    HISTORY,
    POWER_ONE,
    paired,
    score_windows,
    summarise,
)
from bike_safety_ca.model.crash_history import SPREAD_POWER, rank_intersections

WINDOWS = [(2019, 2020, 2022), (2021, 2022, None)]


def _city(seed: int = 3) -> tuple[pd.DataFrame, pd.Index, dict]:
    """A made-up grid city: crashes by site, year and group, 2015 to 2024."""
    rng = np.random.default_rng(seed)
    side = 24
    sites = pd.RangeIndex(side * side)
    streets = {site: {f"R{site // side}", f"C{site % side}"} for site in sites}
    busy = rng.lognormal(0, 0.7, side)[sites // side] * rng.lognormal(0, 0.7, side)[sites % side]
    parts = []
    for group, rate in ((ADULT, 0.05), (CHILD, 0.04), (CAR, 0.6)):
        for year in range(2015, 2025):
            hit = np.repeat(sites.to_numpy(), rng.poisson(rate * busy))
            parts.append(pd.DataFrame({"site": hit, "year": year, "group": group}))
    return pd.concat(parts, ignore_index=True), sites, streets


@pytest.fixture(scope="module")
def city() -> tuple[pd.DataFrame, pd.Index, dict]:
    return _city()


@pytest.fixture(scope="module")
def scored(city: tuple[pd.DataFrame, pd.Index, dict]) -> pd.DataFrame:
    return score_windows(*city, WINDOWS)


def test_every_version_is_scored_for_each_fitted_and_scored_group(scored: pd.DataFrame) -> None:
    groups = scored.groupby(["fitted on", "scored on"]).size()
    assert set(groups.index) == {(EVERYONE, EVERYONE), (EVERYONE, CHILDREN), (CHILDREN, CHILDREN)}
    assert set(scored.version) == {HISTORY, BLEND, *candidates.VERSIONS}
    assert groups.eq(len(WINDOWS) * (2 + len(candidates.VERSIONS))).all()
    # An open-ended window names the last year with a crash.
    assert set(scored["tested to"]) == {2022, 2024}


def test_each_version_is_fitted_with_its_own_spread_power(scored: pd.DataFrame) -> None:
    fitted = scored[scored.method.eq("street-length model")]
    assert len(fitted) > 0
    assert fitted[fitted.version.eq(POWER_ONE)]["spread power"].eq(1.0).all()
    assert not fitted[fitted.version.eq(FITTED_POWER)]["spread power"].eq(1.0).any()
    held = fitted[fitted.version.eq(candidates.POWER_HELD)]["spread power"]
    assert len(held) > 0
    assert held.between(1.0, 2.0).all()


def test_a_ranking_scored_on_children_is_the_one_fitted_to_everyone(
    city: tuple[pd.DataFrame, pd.Index, dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def stub(early: pd.Series, car: pd.Series, streets: object, **options: object) -> dict:
        calls.append((int(early.sum()), options["spread_power"]))
        # Rank by the fitting crashes alone, so the two fits give different scores.
        return {"score": early.astype(float), "method": "stub", "reason": None, "fit": None}

    monkeypatch.setattr(candidates, "rank_intersections", stub)
    hits, sites, streets = city
    table = score_windows(hits, sites, streets, WINDOWS[:1], {POWER_ONE: 1.0})
    early = hits[hits.year.le(2019)]
    everyone, children = int(early.group.ne(CAR).sum()), int(early.group.eq(CHILD).sum())
    # One fit per group fitted to, none of them for the extra child scoring.
    assert calls == [(everyone, 1.0), (children, 1.0)]
    rows = table[table.version.eq(POWER_ONE) & table["scored on"].eq(CHILDREN)].set_index(
        "fitted on"
    )
    assert rows.loc[EVERYONE, "training crashes"] == everyone
    assert rows.loc[CHILDREN, "training crashes"] == children
    score = rows["rank score"].astype(float)
    assert score[EVERYONE] != score[CHILDREN]
    # The all-cyclist ranking scored on children is the past-crash count of everyone.
    same = table[table.version.eq(HISTORY) & table["fitted on"].eq(EVERYONE)]
    assert score[EVERYONE] == float(
        same.set_index("scored on")["rank score"].astype(float)[CHILDREN]
    )


def test_later_crashes_do_not_reach_the_fit(city: tuple[pd.DataFrame, pd.Index, dict]) -> None:
    hits, sites, streets = city
    moved = hits.copy()
    late = moved.year.gt(2019)
    moved.loc[late, "site"] = np.random.default_rng(1).permutation(moved.loc[late, "site"])
    versions = {FITTED_POWER: None, POWER_ONE: 1.0}
    before = score_windows(hits, sites, streets, WINDOWS[:1], versions)
    after = score_windows(moved, sites, streets, WINDOWS[:1], versions)
    assert before.alpha.equals(after.alpha) and before["spread power"].equals(after["spread power"])
    assert before["top 50 shared with reference"].equals(after["top 50 shared with reference"])
    assert not before["rank score"].equals(after["rank score"])


def test_each_top_list_has_its_share_of_the_later_crashes(scored: pd.DataFrame) -> None:
    rows = scored[scored["later crashes"].gt(0)]
    assert len(rows) > 0
    for size in ("25", "50", "100", "5%"):
        share = 100 * rows[f"found in top {size}"] / rows["later crashes"]
        assert np.allclose(rows[f"top {size} share"].astype(float), share.astype(float))
    assert {f"top {size} share" for size in ("25", "50", "100", "5%")} <= set(candidates.MEASURES)


def test_scores_are_not_rounded(scored: pd.DataFrame) -> None:
    score = scored["rank score"].dropna()
    assert (score.round(3) != score).mean() > 0.9


def test_rank_intersections_passes_the_spread_power_on(
    city: tuple[pd.DataFrame, pd.Index, dict],
) -> None:
    hits, sites, streets = city
    bike = hits[hits.group.ne(CAR)].groupby("site").size().reindex(sites, fill_value=0)
    car = hits[hits.group.eq(CAR)].groupby("site").size().reindex(sites, fill_value=0)
    fit = rank_intersections(bike, car, streets)["fit"]  # the rankings' own setting
    assert fit["spread_power"] == SPREAD_POWER == 1.0
    # With power 1 every corner's own count has the same weight, alpha / (1 + alpha).
    table, alpha = fit["sites"], fit["alpha"]
    expected = (table.predicted + alpha * table.observed) / (1 + alpha)
    assert np.allclose(table.eb, expected)
    # ``None`` still fits the power, for comparisons with the earlier model.
    assert rank_intersections(bike, car, streets, spread_power=None)["fit"]["spread_power"] != 1.0


def _table() -> pd.DataFrame:
    """Three cities; the version beats the reference by a known amount in each window."""
    rows = []
    gains = {"a": [0.01, 0.03], "b": [-0.02], "c": [0.04, 0.04, 0.01]}
    for name, values in gains.items():
        for year, gain in enumerate(values, start=2018):
            for version, score in ((FITTED_POWER, 0.8), (POWER_ONE, 0.8 + gain)):
                rows.append(
                    {
                        "city": name, "trained through": year, "fitted on": EVERYONE,
                        "scored on": EVERYONE, "version": version, "enough later": True,
                        "method": "street-length model", "rank score": score,
                        "rank score, no past bike crash": score, "top 25 share": 50 * score,
                        "top 50 share": 100 * score, "top 100 share": 100 * score,
                        "top 5% share": float("nan"),
                    }
                )  # fmt: skip
    return pd.DataFrame(rows)


def test_summary_pairs_windows_and_weighs_cities_both_ways() -> None:
    row = summarise(_table(), draws=2000).set_index("measure").loc["rank score"]
    assert (row.windows, row.cities, row["cities lower"]) == (6, 3, 1)
    assert row["mean over windows"] == pytest.approx(0.11 / 6)
    assert row["mean over cities"] == pytest.approx((0.02 - 0.02 + 0.03) / 3)
    # Leaving out b (the only loss) gives the highest mean; leaving out c the lowest.
    assert row["highest leaving one city out"] == pytest.approx(0.13 / 5)
    assert row["lowest leaving one city out"] == pytest.approx(0.02 / 3)
    assert (
        -0.02 <= row["5th percentile"] < row["mean over windows"] < row["95th percentile"] <= 0.03
    )
    again = summarise(_table(), draws=2000).set_index("measure").loc["rank score"]
    assert again["5th percentile"] == row["5th percentile"]
    # A measure with no value in any window is counted as none, not as zero.
    assert summarise(_table(), draws=10).set_index("measure").loc["top 5% share", "windows"] == 0


def test_only_windows_with_a_fitted_reference_and_enough_later_crashes_are_paired() -> None:
    table = _table()
    table.loc[table.city.eq("a") & table["trained through"].eq(2018), "enough later"] = False
    fell_back = table.city.eq("c") & table["trained through"].eq(2019)
    table.loc[fell_back & table.version.eq(FITTED_POWER), "method"] = "hand-built blend"
    kept = paired(table, POWER_ONE)
    assert sorted(zip(kept.city, kept["trained through"], strict=True)) == [
        ("a", 2019), ("b", 2018), ("c", 2018), ("c", 2020),
    ]  # fmt: skip


def test_a_city_without_a_measure_is_missing_from_it_not_zero() -> None:
    table = _table()
    table = table[table.city.isin(["a", "b"])].copy()
    table.loc[table.city.eq("b"), "rank score, no past bike crash"] = float("nan")
    row = summarise(table, draws=500).set_index("measure").loc["rank score, no past bike crash"]
    # Only a has the measure (+0.01 and +0.03): a draw of b alone has no value, and so
    # has leaving a out.  Neither may count as a difference of zero.
    assert (row.windows, row.cities) == (2, 1)
    assert row["5th percentile"] == pytest.approx(0.02) == row["95th percentile"]
    assert np.isnan(row["lowest leaving one city out"])
    assert np.isnan(row["highest leaving one city out"])
    empty = summarise(table, draws=50).set_index("measure").loc["top 5% share"]
    assert empty.windows == 0 and empty[["5th percentile", "95th percentile"]].isna().all()
    assert np.isnan(empty["lowest leaving one city out"])


def test_nothing_to_compare_gives_an_empty_summary_with_its_columns() -> None:
    table = _table()
    table["method"] = "hand-built blend"  # no window has a fitted reference
    summary = summarise(table, draws=10)
    assert summary.empty and list(summary.columns) == candidates.SUMMARY
    assert candidates.shown(summary) == "no window has a fitted reference and enough later crashes"
