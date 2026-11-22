"""Expected bike crashes per intersection from crash history and street names alone.

It uses no modelled traffic and no road
features beyond the number of intersections on each named street.  Everything
else is how many bike and car crashes each intersection has had and how many
the other intersections on the same named streets have had.

``rank_intersections`` is the entry point: it uses ``fit_street_model`` and
falls back to ``street_blend_score`` when there are too few crashes to fit.
``fit_street_model`` is the main method; ``docs/forecasting_model.md`` gives
the argument for its form.  ``street_blend_score`` is a score that needs no
fitting, and ``fit_history_model`` an earlier fitted formula kept for
comparison.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy.optimize import minimize, minimize_scalar
from scipy.special import gammaln
from scipy.stats import nbinom, rankdata

from bike_safety_ca.model.empirical_bayes import empirical_bayes

FORMULA = "bike ~ log_car + log_street_bike + log_street_car"


def _named(streets: Mapping[Any, Collection[str]], site: Any) -> list[str]:
    """The named streets at ``site``, in name order.

    They are usually held in a set, whose order follows Python's hash seed.
    Read in that order, the sums and the fit differed from run to run in the
    last digits, enough to tip a fit that only just converges.
    """
    return sorted((road for road in streets.get(site, ()) if road), key=str)


def street_length_average(
    values: pd.Series, streets: Mapping[Any, Collection[str]], pseudo: float
) -> pd.Series:
    """Average of ``values`` along each intersection's streets, itself left out.

    Each named road's average is taken over its other intersections plus
    ``pseudo`` imaginary intersections at the average expected for a road with
    that many intersections.  That expectation is a power law in the number of
    intersections, fitted to the road totals by Poisson regression: short
    streets are quieter per corner than long ones, so a short street with no
    record is pulled toward a low figure, not the overall mean.  An
    intersection on several roads gets the sum of their averages; one with no
    named road gets the expectation for a one-intersection road.
    """
    pairs = pd.DataFrame(
        [(site, road) for site in values.index for road in _named(streets, site)],
        columns=["site", "road"],
    )
    pairs["value"] = values.reindex(pairs.site).to_numpy(float)
    by_road = pairs.groupby("road").value
    roads = pd.DataFrame({"total": by_road.sum(), "size": by_road.size()})
    log_size = np.log(roads["size"].to_numpy(float))
    fit = sm.GLM(
        roads.total.to_numpy(),
        sm.add_constant(log_size, has_constant="add"),
        family=sm.families.Poisson(),
        offset=log_size,
    ).fit()
    intercept, power = (float(p) for p in fit.params)
    size = by_road.transform("size")
    typical = np.exp(intercept + power * np.log(size))
    average = (by_road.transform("sum") - pairs.value + pseudo * typical) / (size - 1 + pseudo)
    summed: pd.Series = average.groupby(pairs.site).sum().reindex(values.index)
    return summed.fillna(np.exp(intercept))


def gamma_blend(count: pd.Series, mean: pd.Series, shape: float | pd.Series) -> pd.Series:
    """Expected rate given a count, when rates are gamma-distributed around ``mean``.

    With Poisson counts and gamma rates of the given ``shape`` this is the
    posterior mean ``(shape + count) / (shape / mean + 1)``: a weighted average
    of the count and the mean, with weight ``shape / (shape + mean)`` on the mean.
    """
    return (shape + count) / (shape / mean + 1)


def fit_shape(count: pd.Series, mean: pd.Series) -> float:
    """Maximum-likelihood gamma shape for counts that are negative binomial around ``mean``."""

    def loss(log_shape: float) -> float:
        shape = np.exp(log_shape)
        return -float(nbinom.logpmf(count, shape, shape / (shape + mean)).sum())

    return float(np.exp(minimize_scalar(loss, bounds=(-4, 6), method="bounded").x))


def _fit_spread(
    count: np.ndarray, design: np.ndarray, spread_power: float
) -> tuple[np.ndarray, float, float]:
    """Negative binomial fit with variance ``mean + alpha * mean ** spread_power``.

    Returns the coefficients, ``alpha`` and the log-likelihood.
    """

    def loss(theta: np.ndarray) -> float:
        mean = np.exp(np.clip(design @ theta[:-1], -30, 30))
        size = mean ** (2 - spread_power) / np.exp(theta[-1])
        return -float(
            (
                gammaln(count + size)
                - gammaln(size)
                - gammaln(count + 1)
                + size * np.log(size / (size + mean))
                + count * np.log(mean / (size + mean))
            ).sum()
        )

    start = np.zeros(design.shape[1])
    start[0] = np.log(max(float(count.mean()), 1e-9))
    fits = [
        minimize(loss, np.r_[start, np.log(alpha)], method="L-BFGS-B", options={"maxiter": 2000})
        for alpha in (0.5, 2.0)
    ]
    best = min(fits, key=lambda fit: fit.fun)
    if not best.success:
        raise RuntimeError("street crash model did not converge")
    return best.x[:-1], float(np.exp(best.x[-1])), -float(best.fun)


def fit_street_model(
    bike: pd.Series,
    car: pd.Series,
    streets: Mapping[Any, Collection[str]],
    pull: float = 20.0,
    car_pull: float = 1.0,
    spread_power: float | None = None,
) -> dict[str, Any]:
    """Fit expected bike crashes to the street's bike record and the corner's car record.

    ``bike`` and ``car`` are crash counts per intersection over the same period.
    The fit is

        expected = c * (street bike average)^b * (blended car crashes)^a

    where the street average comes from ``street_length_average`` with ``pull``
    imaginary intersections, and the car term is the corner's car count blended
    with its street's car average (``car_pull`` imaginary intersections) by
    ``gamma_blend``.  Counts are negative binomial with variance
    ``expected + alpha * expected ** spread_power``; the power is fitted when
    not given (2 is the textbook case; a smaller power lets a corner's own
    record count for more where little is expected).  Each intersection's own
    bike count is then blended in with ``gamma_blend``.

    Returns the per-site table (``observed``, ``predicted``, ``prior_shape``
    and the blend ``eb`` to rank by), the fitted ``powers``, ``spread_power``,
    ``alpha``, ``car_shape`` and the AIC.  Raises if the fit does not converge.
    """
    bike = bike.astype(float)
    car = car.reindex(bike.index).astype(float)
    car_street = street_length_average(car, streets, car_pull)
    car_shape = fit_shape(car, car_street)
    terms = pd.DataFrame(
        {
            "street_bike": np.log(street_length_average(bike, streets, pull)),
            "car": np.log(gamma_blend(car, car_street, car_shape)),
        }
    )
    count = bike.to_numpy()
    design = np.column_stack([np.ones(len(terms)), terms.to_numpy()])
    fitted_power = spread_power is None
    if spread_power is None:
        spread_power = float(
            minimize_scalar(
                lambda power: -_fit_spread(count, design, power)[2],
                bounds=(0.5, 2.5),
                method="bounded",
                options={"xatol": 0.02},
            ).x
        )
    coefficients, alpha, log_likelihood = _fit_spread(count, design, spread_power)
    predicted = pd.Series(np.exp(design @ coefficients), index=bike.index)
    prior_shape = predicted ** (2 - spread_power) / alpha
    sites = pd.DataFrame(
        {
            "observed": bike,
            "predicted": predicted,
            "prior_shape": prior_shape,
            "eb": gamma_blend(bike, predicted, prior_shape),
        }
    )
    return {
        "sites": sites,
        "powers": pd.Series(coefficients[1:], index=terms.columns),
        "spread_power": spread_power,
        "alpha": alpha,
        "car_shape": car_shape,
        "aic": 2 * (len(coefficients) + 1 + fitted_power) - 2 * log_likelihood,
    }


def forecast(sites: pd.DataFrame, ratio: float = 1.0) -> pd.DataFrame:
    """Mean and variance of each intersection's crash count in a later period.

    ``sites`` is the table from ``fit_street_model`` (columns ``observed``,
    ``predicted`` and ``prior_shape``) and ``ratio`` the length of the later
    period relative to the fitting period.  The count is negative binomial.
    Summing ``variance`` over a group of intersections gives the variance of
    their total only as an approximation: it takes the fitted street averages
    and parameters as known and the intersections as independent, and
    intersections on one street share an estimated average, so the true
    spread of a total is somewhat wider.
    """
    posterior_shape = sites.prior_shape + sites.observed
    posterior_rate = sites.prior_shape / sites.predicted + 1
    mean = ratio * posterior_shape / posterior_rate
    return pd.DataFrame(
        {"mean": mean, "variance": mean + ratio**2 * posterior_shape / posterior_rate**2}
    )


def same_street_mean(values: pd.Series, streets: Mapping[Any, Collection[str]]) -> pd.Series:
    """Mean of ``values`` at the other intersections on each intersection's streets.

    ``streets`` gives the named roads meeting at each intersection.  For every
    road the intersection lies on, the mean is taken over the road's other
    intersections; an intersection on several roads gets the sum of those means,
    so a corner of two busy streets borrows from both.  A road with no other
    intersection contributes nothing.
    """
    pairs = pd.DataFrame(
        [(site, road) for site in values.index for road in _named(streets, site)],
        columns=["site", "road"],
    )
    pairs["value"] = values.reindex(pairs.site).to_numpy(float)
    by_road = pairs.groupby("road").value
    others = (by_road.transform("size") - 1).clip(lower=1)
    mean = (by_road.transform("sum") - pairs.value) / others
    return mean.groupby(pairs.site).sum().reindex(values.index, fill_value=0.0)


def fit_history_model(
    bike: pd.Series, car: pd.Series, streets: Mapping[Any, Collection[str]]
) -> dict[str, Any]:
    """Fit expected bike crashes to car crashes and same-street crash averages.

    ``bike`` and ``car`` are crash counts per intersection over the same period.
    The negative binomial fit is

        expected = c * (1 + car)^a * (1 + street bike mean)^b * (1 + street car mean)^d

    and each intersection's own bike count is then blended in by empirical
    Bayes.  Returns the per-site table from ``empirical_bayes`` (rank by
    ``eb``), the fitted ``powers``, the overdispersion ``k`` and the AIC.
    Raises if the fit does not converge.
    """
    car = car.reindex(bike.index).astype(float)
    data = pd.DataFrame(
        {
            "bike": bike,
            "log_car": np.log1p(car),
            "log_street_bike": np.log1p(same_street_mean(bike.astype(float), streets)),
            "log_street_car": np.log1p(same_street_mean(car, streets)),
        }
    )
    poisson = smf.poisson(FORMULA, data=data).fit(disp=0, maxiter=300)
    fit = smf.negativebinomial(FORMULA, data=data).fit(
        start_params=np.r_[poisson.params.to_numpy(), 0.5], method="bfgs", maxiter=2000, disp=0
    )
    if not (poisson.mle_retvals["converged"] and fit.mle_retvals["converged"]):
        raise RuntimeError("crash history model did not converge")
    k = float(fit.params["alpha"])
    return {
        "sites": empirical_bayes(bike.astype(float), fit.predict(data), k),
        "powers": fit.params.drop(["Intercept", "alpha"]).rename(lambda t: t[4:]),
        "k": k,
        "aic": float(fit.aic),
    }


def shrink_to_street_mean(
    values: pd.Series, streets: Mapping[Any, Collection[str]], weight: float
) -> pd.Series:
    """Blend each intersection's value with the average along its streets.

    Each named road's average is taken over all its intersections, this one
    included; an intersection on several roads uses the mean of those averages.
    The result is ``(own + weight * street average) / (1 + weight)``, so a
    weight of 1 gives the two equal say.  An intersection with no named road
    keeps its own value.
    """
    pairs = pd.DataFrame(
        [(site, road) for site in values.index for road in _named(streets, site)],
        columns=["site", "road"],
    )
    pairs["value"] = values.reindex(pairs.site).to_numpy(float)
    road_mean = pairs.groupby("road").value.transform("mean")
    target = road_mean.groupby(pairs.site).mean().reindex(values.index).fillna(values)
    return (values + weight * target) / (1 + weight)


def street_blend_score(
    bike: pd.Series,
    car: pd.Series,
    streets: Mapping[Any, Collection[str]],
    bike_weight: float = 1.0,
    car_weight: float = 0.5,
) -> pd.Series:
    """A ranking score that needs no fitting: (1 + bike crashes) * (1 + car crashes).

    Both counts are first blended with their street averages by
    ``shrink_to_street_mean``.  The score orders intersections; it is not an
    expected number of crashes.  Car crashes are more numerous, so they lean
    less on the street by default.
    """
    car = car.reindex(bike.index).astype(float)
    return (1 + shrink_to_street_mean(bike.astype(float), streets, bike_weight)) * (
        1 + shrink_to_street_mean(car, streets, car_weight)
    )


MIN_CRASHES = 100


def rank_intersections(
    bike: pd.Series,
    car: pd.Series,
    streets: Mapping[Any, Collection[str]],
    min_crashes: int = MIN_CRASHES,
) -> dict[str, Any]:
    """Score every intersection, by the fitted model where there is enough to fit it.

    With fewer than ``min_crashes`` bike crashes in all, or when the fit fails,
    the score is ``street_blend_score``, which needs no fitting.  On made-up
    cities the fitted model ranks the true rates better above roughly 100 bike
    crashes and the blend does as well or better below about 50; the default
    sits between.

    Returns ``score`` (rank by this), ``method`` ("street-length model" or
    "hand-built blend"), ``reason`` (why the blend was used, else ``None``)
    and ``fit`` (the ``fit_street_model`` result, else ``None``).  The model's
    score is an expected number of crashes; the blend's only orders
    intersections, so ``forecast`` needs ``fit``.
    """
    total = int(bike.sum())
    fit, reason = None, None
    if total < min_crashes:
        reason = f"{total} bike crashes, fewer than {min_crashes}"
    else:
        try:
            fit = fit_street_model(bike, car, streets)
        except (RuntimeError, ValueError, FloatingPointError) as error:
            reason = f"fit failed: {error}"
    if fit is not None and not bool(np.isfinite(fit["sites"].eb).all()):
        fit, reason = None, "fit gave values that are not finite"
    if fit is None:
        return {
            "score": street_blend_score(bike, car, streets),
            "method": "hand-built blend",
            "reason": reason,
            "fit": None,
        }
    return {"score": fit["sites"].eb, "method": "street-length model", "reason": None, "fit": fit}


def rank_score(score: pd.Series, later: pd.Series) -> float:
    """Chance that a site with a later crash outranks one without (0.5 = random).

    This is the area under the ROC curve of ``score`` against ``later > 0``,
    with tied scores counted as half.
    """
    hit = later.reindex(score.index).to_numpy() > 0
    if hit.all() or not hit.any():
        return float("nan")
    ranks = rankdata(score.to_numpy())
    n_hit = int(hit.sum())
    return float((ranks[hit].sum() - n_hit * (n_hit + 1) / 2) / (n_hit * int((~hit).sum())))


def top_share(score: pd.Series, later: pd.Series, k: int) -> float:
    """Later crashes at the ``k`` highest-scoring sites; ties at the cut share the places."""
    ordered = score.sort_values(ascending=False)
    k = min(k, len(ordered))  # an area with fewer than k sites: all of them
    if k < 1:
        return 0.0
    cut = ordered.iloc[k - 1]
    above, tied = ordered[ordered > cut].index, ordered[ordered == cut].index
    later = later.reindex(score.index)
    return float(later[above].sum() + later[tied].sum() * (k - len(above)) / len(tied))
