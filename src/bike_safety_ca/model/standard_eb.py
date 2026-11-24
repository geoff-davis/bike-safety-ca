"""The textbook empirical Bayes crash model, with ordinary predictors only.

An intersection's bike crashes over ``years`` years are Poisson with mean
``years * m * theta``.  The background rate per year ``m`` comes from a
regression on the intersection's car crashes and the classes of its two main
roads; ``theta`` is the intersection's own lasting multiplier, gamma
distributed with mean 1 and shape ``k``.  Summing over ``theta`` gives the
usual negative binomial (NB2), variance ``mean + mean ** 2 / k``, which is
fitted with statsmodels.  The intersection's own count then updates its
multiplier (Hauer and others 2002):

    expected later count = later years * m * (k + count) / (k + years * m)

No predictor is built from the bike crashes, nothing is smoothed along
streets beforehand and the variance has no fitted power.  It is a plug-in
estimate: the regression and ``k`` are taken as known once fitted.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import sparse

from bike_safety_ca.model.crash_history import MIN_CRASHES, gamma_blend

FITTED, COUNT_ONLY = "standard empirical Bayes", "past bike crashes"


def design(car: pd.Series, classes: pd.DataFrame, years: float) -> pd.DataFrame:
    """The regression's columns: a constant, car crashes per year, and road classes.

    ``classes`` has one column per road position (the main road, the second
    road), each a label.  Every label but the commonest in its column gets an
    indicator, so the constant stands for the commonest kind of intersection.
    A label no intersection has gets no column.
    """
    columns: dict[str, pd.Series] = {
        "constant": pd.Series(1.0, index=car.index),
        "log(1 + car crashes per year)": pd.Series(
            np.log1p(car.to_numpy(float) / years), index=car.index
        ),
    }
    for position in classes.columns:
        labels = classes[position].reindex(car.index).astype(str)
        counts = labels.value_counts()
        ordered = sorted(counts.index, key=lambda label: (-counts[label], label))
        for label in ordered[1:]:
            columns[f"{position}: {label}"] = labels.eq(label).astype(float)
    return pd.DataFrame(columns)


def membership(
    index: pd.Index, streets: Mapping[Any, Collection[str]]
) -> tuple[sparse.csr_matrix, list[str]]:
    """Intersections by streets: 1 where the street is one of the intersection's.

    Streets are told apart by name, so two streets with one name in the area
    are one street here.  A name is counted once per intersection.
    """
    names = sorted({name for site in index for name in streets.get(site, ()) if name})
    column = {name: j for j, name in enumerate(names)}
    rows, columns = [], []
    for i, site in enumerate(index):
        for name in {name for name in streets.get(site, ()) if name}:
            rows.append(i)
            columns.append(column[name])
    matrix = sparse.csr_matrix(
        (np.ones(len(rows)), (rows, columns)), shape=(len(index), len(names))
    )
    return matrix, names


def street_context(
    car: pd.Series, streets: Mapping[Any, Collection[str]], years: float
) -> pd.DataFrame:
    """Two more columns for the regression, from the other intersections on a site's streets.

    A site's neighbours are the other intersections that share a named street
    with it, each counted once however many streets are shared.  The columns
    are ``log(1 + number of neighbours)`` and ``log(1 + car crashes per year
    at a neighbour)``, the second from the neighbours' total over the fitting
    years.  A site with no neighbour gets the area's car crashes per
    intersection per year.  No bike crash enters either column.
    """
    member, _ = membership(car.index, streets)
    shared = (member @ member.T).tocsr()
    shared.data[:] = 1.0
    shared.setdiag(0.0)
    shared.eliminate_zeros()
    count = car.to_numpy(float)
    neighbours = np.asarray(shared.sum(axis=1)).ravel()
    total = shared @ count
    typical = count.mean() / years if len(count) else 0.0
    rate = np.where(neighbours > 0, total / (np.maximum(neighbours, 1) * years), typical)
    return pd.DataFrame(
        {
            "log(1 + intersections on the same streets)": np.log1p(neighbours),
            "log(1 + car crashes per year at those)": np.log1p(rate),
        },
        index=car.index,
    )


def fit_standard_eb(
    bike: pd.Series,
    car: pd.Series,
    classes: pd.DataFrame,
    years: float,
    streets: Mapping[Any, Collection[str]] | None = None,
) -> dict[str, Any]:
    """Fit the model to counts over ``years`` years; return the per-site estimates.

    With ``streets`` the regression also has the two ``street_context`` columns.

    ``sites`` has ``observed``, ``predicted`` (the background count over the
    fitting years), ``prior_shape`` (``k``, the same at every site) and ``eb``
    (the expected count over the fitting years given the site's own count;
    rank by this, and scale by later years over ``years`` for a later period).
    The columns are those ``crash_history.forecast`` takes.  Raises
    ``RuntimeError`` if either fit does not converge.
    """
    car = car.reindex(bike.index)
    columns = design(car, classes, years)
    if streets is not None:
        columns = pd.concat([columns, street_context(car, streets, years)], axis=1)
    count = bike.to_numpy(float)
    offset = np.full(len(count), np.log(years))
    poisson = sm.Poisson(count, columns, offset=offset).fit(disp=0, maxiter=300)
    fit = sm.NegativeBinomial(count, columns, offset=offset, loglike_method="nb2").fit(
        start_params=np.r_[poisson.params.to_numpy(), 0.5], method="bfgs", maxiter=2000, disp=0
    )
    if not (poisson.mle_retvals["converged"] and fit.mle_retvals["converged"]):
        raise RuntimeError("standard empirical Bayes model did not converge")
    alpha = float(fit.params["alpha"])
    if not alpha > 0:
        raise RuntimeError("standard empirical Bayes model found no spread of rates")
    shape = 1 / alpha
    predicted = pd.Series(
        np.exp(columns.to_numpy() @ fit.params.drop("alpha").to_numpy() + offset),
        index=bike.index,
    )
    observed = bike.astype(float)
    sites = pd.DataFrame(
        {
            "observed": observed,
            "predicted": predicted,
            "prior_shape": shape,
            "eb": gamma_blend(observed, predicted, shape),
        }
    )
    return {
        "sites": sites,
        "coefficients": fit.params.drop("alpha"),
        "shape": shape,
        "alpha": alpha,
        "aic": float(fit.aic),
    }


def rank_standard(
    bike: pd.Series,
    car: pd.Series,
    classes: pd.DataFrame,
    years: float,
    min_crashes: int = MIN_CRASHES,
    streets: Mapping[Any, Collection[str]] | None = None,
) -> dict[str, Any]:
    """Score every intersection by the model; by its own count where it cannot be fitted.

    The same threshold as ``crash_history.rank_intersections``: with fewer
    than ``min_crashes`` bike crashes, or when the fit fails, the score is the
    intersection's own count.  That is a rule, not the model: with no
    predictors the model would pull every count toward the area's mean, which
    leaves the order of the counts as it is but not their values.  ``streets``
    is passed to ``fit_standard_eb``.  Returns ``score``, ``method``,
    ``reason`` and ``fit``.
    """
    total = int(bike.sum())
    fit, reason = None, None
    if total < min_crashes:
        reason = f"{total} bike crashes, fewer than {min_crashes}"
    else:
        try:
            fit = fit_standard_eb(bike, car, classes, years, streets)
        except (RuntimeError, ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
            reason = f"fit failed: {error}"
    if fit is not None and not bool(np.isfinite(fit["sites"].eb).all()):
        fit, reason = None, "fit gave values that are not finite"
    if fit is None:
        return {"score": bike.astype(float), "method": COUNT_ONLY, "reason": reason, "fit": None}
    return {"score": fit["sites"].eb, "method": FITTED, "reason": None, "fit": fit}
