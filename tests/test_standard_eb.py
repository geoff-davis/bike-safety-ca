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
    membership,
    rank_standard,
    street_context,
)
from bike_safety_ca.model.street_effects import fit_street_effects, rank_street_effects

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


def test_street_context_counts_each_neighbour_once_and_uses_no_bike_crash() -> None:
    # 1 and 2 share both streets; 3 is on A only; 4 is alone on C; 5 has no name
    streets = {1: ["A", "B"], 2: ["A", "B"], 3: ["A"], 4: ["C"], 5: []}
    car = pd.Series([4, 0, 2, 6, 3], index=[1, 2, 3, 4, 5])
    found = street_context(car, streets, years=2.0)
    neighbours = np.expm1(found["log(1 + intersections on the same streets)"])
    assert neighbours.round(9).tolist() == [2, 2, 2, 0, 0]
    rate = np.expm1(found["log(1 + car crashes per year at those)"])
    # site 1: neighbours 2 and 3, (0 + 2) crashes over 2 sites and 2 years
    assert rate.loc[1] == pytest.approx(0.5)
    assert rate.loc[3] == pytest.approx((4 + 0) / (2 * 2.0))
    # no neighbour: the area's car crashes per intersection per year
    assert rate.loc[4] == pytest.approx(15 / 5 / 2.0)
    assert rate.loc[5] == pytest.approx(15 / 5 / 2.0)


def test_street_context_enters_the_regression_only_when_streets_are_given(city: dict) -> None:
    # On the whole grid every site has the same number of neighbours: that column would be
    # a second constant, so it is left out and the fit is not singular.
    grid = fit_standard_eb(city["bike"], city["car"], city["classes"], YEARS, city["streets"])
    assert "log(1 + intersections on the same streets)" not in grid["coefficients"].index
    assert "log(1 + car crashes per year at those)" in grid["coefficients"].index
    # Every seventh site keeps one street, and both columns vary.
    streets = {site: names if site % 7 else {min(names)} for site, names in city["streets"].items()}
    plain = fit_standard_eb(city["bike"], city["car"], city["classes"], YEARS)
    wider = fit_standard_eb(city["bike"], city["car"], city["classes"], YEARS, streets)
    added = set(wider["coefficients"].index) - set(plain["coefficients"].index)
    assert added == {
        "log(1 + intersections on the same streets)",
        "log(1 + car crashes per year at those)",
    }
    sites, k = wider["sites"], wider["shape"]
    by_hand = sites.predicted * (k + sites.observed) / (k + sites.predicted)
    assert sites.eb.tolist() == pytest.approx(by_hand.tolist())
    ranked = rank_standard(city["bike"], city["car"], city["classes"], YEARS, streets=streets)
    assert ranked["score"].tolist() == pytest.approx(sites.eb.tolist())


def test_a_road_class_with_no_bike_crash_does_not_stop_the_fit(city: dict) -> None:
    # The Poisson fit that gives the starting values cannot converge here: the class's
    # coefficient runs off toward minus infinity.  The model's own fit does converge.
    classes, bike = city["classes"].copy(), city["bike"].copy()
    quiet = bike.index[bike.index % 23 == 0]
    classes.loc[quiet, "minor"] = "Track"
    bike.loc[quiet] = 0
    fit = fit_standard_eb(bike, city["car"], classes, YEARS)
    assert fit["coefficients"]["minor: Track"] < -10
    assert fit["sites"].eb.loc[quiet].max() < 1e-6
    assert np.isfinite(fit["sites"].eb).all() and fit["shape"] > 0
    ranked = rank_standard(bike, city["car"], classes, YEARS)
    assert ranked["reason"] is None


def test_street_effects_fit_when_every_site_has_the_same_car_count(city: dict) -> None:
    # The car column is then a second constant and is left out of both fits alike.
    car = pd.Series(3, index=city["car"].index)
    fit = fit_street_effects(city["bike"], car, city["classes"], city["streets"], YEARS)
    assert "log(1 + car crashes per year)" not in fit["coefficients"].index
    assert np.isfinite(fit["sites"].eb).all()
