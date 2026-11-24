"""The textbook empirical Bayes model, alone and with street effects.  Made-up data."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bike_safety_ca.model.crash_history import rank_score
from bike_safety_ca.model.standard_eb import (
    COUNT_ONLY,
    design,
    fit_standard_eb,
    rank_standard,
)
from bike_safety_ca.model.street_effects import (
    fit_street_effects,
    membership,
    rank_street_effects,
)

YEARS = 5.0


def _city(seed: int = 11, effect_spread: float = 0.8) -> dict:
    """A made-up grid: rates depend on car crashes, road class and the two streets."""
    rng = np.random.default_rng(seed)
    side = 30
    sites = pd.RangeIndex(side * side)
    streets = {site: {f"R{site // side}", f"C{site % side}"} for site in sites}
    effect = {name: rng.normal(0, effect_spread) for names in streets.values() for name in names}
    major = pd.Series(np.where(sites % side % 5 == 0, "Arterial", "Local"), index=sites)
    minor = pd.Series("Local", index=sites)
    car = pd.Series(rng.poisson(np.where(major.eq("Arterial"), 6.0, 1.5)), index=sites)
    background = 0.05 * (1 + car / YEARS) * np.where(major.eq("Arterial"), 2.0, 1.0)
    background = background * np.exp([sum(effect[name] for name in streets[s]) for s in sites])
    rate = background * rng.gamma(2.0, 1 / 2.0, len(sites))
    return {
        "bike": pd.Series(rng.poisson(YEARS * rate), index=sites),
        "later": pd.Series(rng.poisson(YEARS * rate), index=sites),
        "car": car,
        "classes": pd.DataFrame({"major": major, "minor": minor}),
        "streets": streets,
        "effect": pd.Series(effect),
    }


@pytest.fixture(scope="module")
def city() -> dict:
    return _city()


def test_design_leaves_out_the_commonest_class_and_classes_nobody_has(city: dict) -> None:
    columns = design(city["car"], city["classes"], YEARS)
    assert list(columns.columns) == ["constant", "log(1 + car crashes per year)", "major: Arterial"]
    assert columns["log(1 + car crashes per year)"].iloc[0] == pytest.approx(
        np.log1p(city["car"].iloc[0] / YEARS)
    )


def test_estimate_is_the_gamma_update_of_the_background(city: dict) -> None:
    fit = fit_standard_eb(city["bike"], city["car"], city["classes"], YEARS)
    sites, k = fit["sites"], fit["shape"]
    by_hand = sites.predicted * (k + sites.observed) / (k + sites.predicted)
    assert sites.eb.tolist() == pytest.approx(by_hand.tolist())
    # the brief's worked example: T = 5, m = 0.2, k = 1, Y = 3 gives 0.4 a year
    assert (1 + 3) / (1 / 0.2 + 5) == pytest.approx(0.4)
    assert fit["coefficients"]["major: Arterial"] > 0


def test_years_only_move_the_constant(city: dict) -> None:
    short = fit_standard_eb(city["bike"], city["car"] * 2, city["classes"], YEARS * 2)
    base = fit_standard_eb(city["bike"], city["car"], city["classes"], YEARS)
    # car crashes per year are the same, so the counts over the period are fitted alike
    assert short["sites"].eb.tolist() == pytest.approx(base["sites"].eb.tolist(), rel=1e-3)
    assert short["coefficients"]["constant"] == pytest.approx(
        base["coefficients"]["constant"] - np.log(2), abs=1e-3
    )


def test_too_few_crashes_ranks_by_the_count_and_says_why(city: dict) -> None:
    ranked = rank_standard(city["bike"], city["car"], city["classes"], YEARS, min_crashes=10**6)
    assert ranked["method"] == COUNT_ONLY and ranked["fit"] is None
    assert "fewer than" in ranked["reason"]
    assert ranked["score"].tolist() == city["bike"].astype(float).tolist()


def test_membership_counts_each_street_once() -> None:
    matrix, names = membership(pd.Index([7, 8, 9]), {7: ["A", "A", "B"], 8: ["B"], 9: []})
    assert names == ["A", "B"]
    assert matrix.toarray().tolist() == [[1, 1], [0, 1], [0, 0]]


def test_street_effects_are_recovered_and_help(city: dict) -> None:
    plain = fit_standard_eb(city["bike"], city["car"], city["classes"], YEARS)
    joint = fit_street_effects(city["bike"], city["car"], city["classes"], city["streets"], YEARS)
    assert joint["tau"] == pytest.approx(0.8, abs=0.25)
    truth = city["effect"].reindex(joint["effects"].index)
    assert np.corrcoef(joint["effects"], truth)[0, 1] > 0.8
    assert rank_score(joint["sites"].eb, city["later"]) > rank_score(
        plain["sites"].eb, city["later"]
    )
    sites, k = joint["sites"], joint["shape"]
    by_hand = sites.predicted * (k + sites.observed) / (k + sites.predicted)
    assert sites.eb.tolist() == pytest.approx(by_hand.tolist())


def test_street_effects_fall_back_like_the_plain_model(city: dict) -> None:
    ranked = rank_street_effects(
        city["bike"], city["car"], city["classes"], city["streets"], YEARS, min_crashes=10**6
    )
    assert ranked["method"] == COUNT_ONLY and ranked["fit"] is None
    unnamed = rank_street_effects(city["bike"], city["car"], city["classes"], {}, YEARS)
    assert unnamed["fit"] is None and "no named street" in unnamed["reason"]
