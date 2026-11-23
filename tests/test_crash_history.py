from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bike_safety_ca.model.crash_history import (
    fit_history_model,
    fit_shape,
    fit_street_model,
    forecast,
    gamma_blend,
    rank_score,
    same_street_mean,
    shrink_to_street_mean,
    street_blend_score,
    street_length_average,
    top_share,
)


def test_same_street_mean_leaves_out_the_intersection_itself() -> None:
    values = pd.Series([4.0, 2.0, 0.0, 6.0], index=[1, 2, 3, 4])
    streets = {1: {"MAIN"}, 2: {"MAIN", "OAK"}, 3: {"MAIN"}, 4: {"OAK"}}
    mean = same_street_mean(values, streets)
    assert mean[1] == pytest.approx((2 + 0) / 2)
    assert mean[3] == pytest.approx((4 + 2) / 2)
    # on two streets: the mean of the others on Main plus the mean of the others on Oak
    assert mean[2] == pytest.approx((4 + 0) / 2 + 6)
    assert mean[4] == pytest.approx(2)


def test_same_street_mean_is_zero_without_neighbours() -> None:
    values = pd.Series([3.0, 5.0], index=[1, 2])
    mean = same_street_mean(values, {1: {"LONELY"}, 2: set()})
    assert mean.tolist() == [0.0, 0.0]


def _synthetic(n_streets: int = 300, per_street: int = 12) -> tuple[pd.Series, pd.Series, dict]:
    rng = np.random.default_rng(11)
    street = np.repeat(np.arange(n_streets), per_street)
    hazard = np.repeat(rng.lognormal(0, 0.8, n_streets), per_street)  # shared along a street
    car = rng.poisson(3 * hazard * rng.lognormal(0, 0.5, street.size))
    bike = rng.poisson(0.15 * hazard * (1 + car) ** 0.5)
    index = pd.RangeIndex(street.size)
    streets = {i: {f"S{s}"} for i, s in zip(index, street, strict=True)}
    return pd.Series(bike, index=index), pd.Series(car, index=index), streets


def test_fit_finds_that_car_crashes_and_the_street_both_matter() -> None:
    bike, car, streets = _synthetic()
    fit = fit_history_model(bike, car, streets)
    assert set(fit["powers"].index) == {"car", "street_bike", "street_car"}
    assert fit["powers"]["car"] > 0.2
    assert fit["powers"]["street_bike"] > 0.2
    assert fit["k"] > 0
    sites = fit["sites"]
    # the blend sits between the prediction and the intersection's own count
    low, high = (
        sites[["observed", "predicted"]].min(axis=1),
        sites[["observed", "predicted"]].max(axis=1),
    )
    assert ((sites.eb >= low - 1e-9) & (sites.eb <= high + 1e-9)).all()


def test_fit_recovers_a_street_effect_better_than_the_count_alone() -> None:
    # The later crashes are drawn from the observed street means, so this
    # checks that the fit picks up a street effect put there by hand.  The
    # made-up city in test_synthetic_holdout.py tests prediction from true rates.
    bike, car, streets = _synthetic()
    rng = np.random.default_rng(12)
    later = pd.Series(
        rng.poisson(bike.groupby(pd.Series(streets).map(min)).transform("mean")), index=bike.index
    )
    fitted = rank_score(fit_history_model(bike, car, streets)["sites"].eb, later)
    assert fitted > rank_score(bike.astype(float), later)
    assert fitted > 0.6


def test_rank_score_counts_ties_as_half() -> None:
    later = pd.Series([1, 0, 0, 1])
    assert rank_score(pd.Series([4.0, 1.0, 2.0, 3.0]), later) == pytest.approx(1.0)
    assert rank_score(pd.Series([1.0, 4.0, 3.0, 2.0]), later) == pytest.approx(0.0)
    # one of the four hit/miss pairs is in the right order
    assert rank_score(pd.Series([1.0, 4.0, 3.0, 3.5]), later) == pytest.approx(0.25)
    assert rank_score(pd.Series([1.0, 1.0, 1.0, 1.0]), later) == pytest.approx(0.5)
    assert np.isnan(rank_score(pd.Series([1.0, 2.0]), pd.Series([0, 0])))


def test_top_share_splits_places_among_ties_at_the_cut() -> None:
    score = pd.Series([5.0, 3.0, 3.0, 1.0])
    later = pd.Series([2, 4, 0, 9])
    assert top_share(score, later, 1) == pytest.approx(2)
    # one place left for two tied sites: half of their four crashes
    assert top_share(score, later, 2) == pytest.approx(2 + 4 / 2)
    assert top_share(score, later, 3) == pytest.approx(6)


def test_shrink_to_street_mean_includes_the_intersection_and_averages_its_streets() -> None:
    values = pd.Series([4.0, 2.0, 0.0, 6.0, 5.0], index=[1, 2, 3, 4, 5])
    streets = {1: {"MAIN"}, 2: {"MAIN", "OAK"}, 3: {"MAIN"}, 4: {"OAK"}, 5: set()}
    # Main averages (4 + 2 + 0) / 3 = 2 and Oak (2 + 6) / 2 = 4
    shrunk = shrink_to_street_mean(values, streets, weight=1.0)
    assert shrunk[1] == pytest.approx((4 + 2) / 2)
    assert shrunk[2] == pytest.approx((2 + (2 + 4) / 2) / 2)
    assert shrunk[4] == pytest.approx((6 + 4) / 2)
    assert shrunk[5] == pytest.approx(5.0)  # no named street: unchanged
    assert shrink_to_street_mean(values, streets, weight=0.0).tolist() == values.tolist()
    heavy = shrink_to_street_mean(values, streets, weight=3.0)
    assert heavy[1] == pytest.approx((4 + 3 * 2) / 4)


def test_street_blend_score_multiplies_the_two_blended_counts() -> None:
    bike = pd.Series([1.0, 0.0, 0.0], index=[1, 2, 3])
    car = pd.Series([3.0, 3.0, 0.0], index=[1, 2, 3])
    streets = {1: {"MAIN"}, 2: {"MAIN"}, 3: {"ELM"}}
    score = street_blend_score(bike, car, streets, bike_weight=1.0, car_weight=0.5)
    assert score[1] == pytest.approx((1 + (1 + 0.5) / 2) * (1 + 3))
    # no bike crash of its own, but it shares a street with one
    assert score[2] == pytest.approx((1 + 0.5 / 2) * (1 + 3))
    assert score[3] == pytest.approx(1.0)
    assert score[1] > score[2] > score[3]


def test_street_length_average_pulls_toward_the_typical_street_of_that_length() -> None:
    values = pd.Series([4.0, 2.0, 0.0, 6.0, 0.0, 2.0, 9.0], index=[1, 2, 3, 4, 5, 6, 7])
    streets = {
        1: {"MAIN"},
        2: {"MAIN", "OAK"},
        3: {"MAIN"},
        4: {"OAK"},
        5: {"ELM"},
        6: {"ELM"},
        7: set(),
    }
    # two street lengths, so the fitted power law passes through both group averages:
    # three-corner streets average 2 per corner, two-corner streets (8 + 2) / 4 = 2.5
    long, short = 2.0, 2.5
    average = street_length_average(values, streets, pseudo=1.0)
    assert average[1] == pytest.approx((2 + 0 + long) / 3)
    assert average[4] == pytest.approx((2 + short) / 2)
    assert average[5] == pytest.approx((2 + short) / 2)
    # on two streets: the sum of the two averages
    assert average[2] == pytest.approx((4 + 0 + long) / 3 + (6 + short) / 2)
    # no named street: the power law carried down to a one-corner street
    power = np.log(long / short) / np.log(3 / 2)
    assert average[7] == pytest.approx(short * 2**-power)
    # a strong pull leaves only the street's length
    heavy = street_length_average(values, streets, pseudo=1e9)
    assert heavy[[1, 3]].tolist() == pytest.approx([long, long], rel=1e-6)
    assert heavy[[4, 5, 6]].tolist() == pytest.approx([short] * 3, rel=1e-6)


def test_gamma_blend_is_a_weighted_average_of_count_and_mean() -> None:
    count, mean = pd.Series([0.0, 3.0, 3.0]), pd.Series([2.0, 2.0, 0.5])
    blend = gamma_blend(count, mean, shape=1.0)
    # shape 1: (1 + count) * mean / (1 + mean)
    assert blend.tolist() == pytest.approx([2 / 3, 8 / 3, 4 / 3])
    weight = 1.0 / (1.0 + mean)
    assert blend.tolist() == pytest.approx((weight * mean + (1 - weight) * count).tolist())
    # a large shape means little spread in rates, so the mean wins
    assert gamma_blend(count, mean, shape=1e6).tolist() == pytest.approx(mean.tolist(), rel=1e-4)


def test_fit_shape_recovers_the_spread_of_rates() -> None:
    rng = np.random.default_rng(5)
    mean = pd.Series(np.full(20000, 2.0))
    count = pd.Series(rng.poisson(rng.gamma(1.5, 2.0 / 1.5, mean.size)))
    assert fit_shape(count, mean) == pytest.approx(1.5, rel=0.15)


def test_street_model_finds_both_terms_and_beats_the_count_alone() -> None:
    bike, car, streets = _synthetic()
    fit = fit_street_model(bike, car, streets)
    assert set(fit["powers"].index) == {"street_bike", "car"}
    assert (fit["powers"] > 0.2).all()
    assert 0.5 <= fit["spread_power"] <= 2.5
    assert fit["alpha"] > 0 and fit["car_shape"] > 0
    sites = fit["sites"]
    low = sites[["observed", "predicted"]].min(axis=1)
    high = sites[["observed", "predicted"]].max(axis=1)
    assert ((sites.eb >= low - 1e-9) & (sites.eb <= high + 1e-9)).all()
    rng = np.random.default_rng(12)
    later = pd.Series(
        rng.poisson(bike.groupby(pd.Series(streets).map(min)).transform("mean")), index=bike.index
    )
    assert rank_score(sites.eb, later) > rank_score(bike.astype(float), later)


def test_street_model_with_a_fixed_spread_power() -> None:
    bike, car, streets = _synthetic()
    free = fit_street_model(bike, car, streets)
    fixed = fit_street_model(bike, car, streets, spread_power=1.0)
    assert fixed["spread_power"] == 1.0
    # power 1: every corner's own count gets the same weight, alpha / (1 + alpha)
    sites, weight = fixed["sites"], fixed["alpha"] / (1 + fixed["alpha"])
    blend = (1 - weight) * sites.predicted + weight * sites.observed
    assert sites.eb.tolist() == pytest.approx(blend.tolist())
    # the fitted power cannot fit worse; it costs one more parameter
    assert free["aic"] <= fixed["aic"] + 2 + 1e-6


def test_forecast_mean_scales_with_the_period_and_variance_exceeds_it() -> None:
    sites = pd.DataFrame(
        {"observed": [0.0, 2.0], "predicted": [0.5, 1.0], "prior_shape": [1.0, 1.0]}
    )
    one = forecast(sites)
    # shape 1: the mean is (1 + observed) / (1 / predicted + 1)
    assert one["mean"].tolist() == pytest.approx([1 / 3, 3 / 2])
    assert one.variance.tolist() == pytest.approx([1 / 3 + 1 / 9, 3 / 2 + 3 / 4])
    half = forecast(sites, ratio=0.5)
    assert half["mean"].tolist() == pytest.approx((one["mean"] / 2).tolist())
    assert (half.variance > half["mean"]).all()


def test_top_share_of_more_sites_than_exist_is_every_later_crash() -> None:
    score = pd.Series([3.0, 1.0, 2.0])
    later = pd.Series([1, 0, 4])
    assert top_share(score, later, 100) == pytest.approx(5)


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
@pytest.mark.filterwarnings("ignore::statsmodels.tools.sm_exceptions.ConvergenceWarning")
@pytest.mark.filterwarnings("ignore::statsmodels.tools.sm_exceptions.HessianInversionWarning")
def test_the_scores_do_not_depend_on_the_order_street_names_are_read_in() -> None:
    """Street names are held in sets, whose order follows Python's hash seed.

    A sum of three or more street averages depends, in its last digits, on the
    order they are added in, so each intersection here is on three streets.
    """
    from bike_safety_ca.model.crash_history import (
        rank_intersections,
        same_street_mean,
        street_blend_score,
    )

    rng = np.random.default_rng(7)
    sites = pd.RangeIndex(600)
    # Made-up network: every intersection on one of 40 avenues, 35 streets and 30 lanes.
    names = {
        site: [f"Avenue {site % 40}", f"Street {site % 35}", f"Lane {site % 30}"] for site in sites
    }
    car = pd.Series(rng.poisson(3 + (sites % 40) / 4), index=sites)
    bike = pd.Series(rng.poisson(0.2 + car / 10), index=sites)

    def scores(streets: dict[int, list[str]]) -> list[bytes]:
        ranked = rank_intersections(bike, car, streets)
        assert ranked["method"] == "street-length model"  # fitted, not the fallback
        return [
            street_blend_score(bike, car, streets).to_numpy().tobytes(),
            ranked["score"].to_numpy().tobytes(),
            same_street_mean(car.astype(float), streets).to_numpy().tobytes(),
        ]

    forwards = scores(names)
    backwards = scores({site: roads[::-1] for site, roads in names.items()})
    rotated = scores({site: roads[1:] + roads[:1] for site, roads in names.items()})
    assert forwards == backwards == rotated


def _one_street() -> tuple[pd.Series, pd.Series, dict]:
    """120 corners on one street: the first optimiser start fails here, the second converges."""
    rng = np.random.default_rng(7)
    bike, car = pd.Series(rng.poisson(1, 120)), pd.Series(rng.poisson(3, 120))
    return bike, car, {site: {"S"} for site in bike.index}


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
@pytest.mark.filterwarnings("ignore::statsmodels.tools.sm_exceptions.SingularMatrixWarning")
def test_a_failed_start_does_not_discard_one_that_converged() -> None:
    bike, car, streets = _one_street()
    fit = fit_street_model(bike, car, streets, spread_power=0.5 + (3 - np.sqrt(5.0)))
    assert np.isfinite(fit["sites"].eb).all()
    assert fit["log_likelihood"] == pytest.approx(-148.877, abs=0.01)


@pytest.mark.parametrize(
    ("attempts", "kept"),
    [
        ([(False, np.nan), (True, 9.0)], 9.0),  # a failed start with no value
        ([(False, 3.0), (True, 9.0)], 9.0),  # a failed start that stopped lower
        ([(True, 9.0), (True, 4.0)], 4.0),  # both converged: the lower one
        ([(True, np.inf), (True, 9.0)], 9.0),
        ([(False, 3.0), (False, np.nan)], None),  # neither usable: the fit fails
    ],
)
def test_the_fit_is_chosen_among_the_starts_that_converged(
    monkeypatch: pytest.MonkeyPatch, attempts: list[tuple[bool, float]], kept: float | None
) -> None:
    from types import SimpleNamespace

    from bike_safety_ca.model import crash_history

    queue = iter(attempts)

    def stub(loss: object, start: np.ndarray, **_: object) -> SimpleNamespace:
        success, value = next(queue)
        return SimpleNamespace(success=success, fun=value, x=np.zeros(len(start)))

    monkeypatch.setattr(crash_history, "minimize", stub)
    count, design = np.ones(4), np.ones((4, 1))
    if kept is None:
        with pytest.raises(RuntimeError, match="did not converge"):
            crash_history._fit_spread(count, design, 1.5)
    else:
        assert crash_history._fit_spread(count, design, 1.5)[2] == -kept
