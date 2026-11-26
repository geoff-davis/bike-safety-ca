"""The textbook crash model with a shared effect for each street, fitted in one step.

``standard_eb`` with one addition: every named street has an effect ``u`` on
the log of the background rate, shared by the intersections on it, and the
effects are normal with mean 0 and standard deviation ``tau``:

    log(background rate) = regression + sum of u over the intersection's streets

An intersection counts once for each of its streets (a multiple-membership
random intercept).  The regression, the street effects, ``tau`` and the shape
``k`` of the intersections' own multipliers are fitted together to the bike
counts, each count entering once; no street average is worked out first.

Fitting is approximate.  For a given ``k`` and ``tau`` the regression and the
effects together maximise the penalised likelihood (Newton's method).  ``k``
and ``tau`` then maximise that penalised likelihood with a Laplace correction
for the street effects: ``- S log(tau) - 0.5 log det(Z' W Z + I / tau ** 2)``,
the curvature in the effects alone with the regression held where it is.  So
the regression maximises the penalised likelihood, not the corrected one.
The usual Laplace fit of mixed-model software (``lme4`` with ``nAGQ = 1``)
optimises the regression against the corrected likelihood too; this is the
faster and less exact scheme ``lme4`` calls ``nAGQ = 0``, and it has not been
checked against that or any other package.  The normal distribution of the
effects is an assumption that pulls them toward 0; ``k`` and ``tau`` are
fitted with no further prior.

The estimate for an intersection takes the fitted effects as known and
updates its own multiplier with its own count, as in ``standard_eb``.  The
uncertainty of the effects is not averaged over, which can move the
estimates themselves and not only their spread.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import minimize
from scipy.sparse.linalg import splu
from scipy.special import gammaln

from bike_safety_ca.model.crash_history import MIN_CRASHES, gamma_blend
from bike_safety_ca.model.standard_eb import COUNT_ONLY, design, fit_standard_eb, membership

FITTED = "street-effects model"
# Limits on the search for log(k) and log(tau).
LOG_SHAPE, LOG_TAU = (-6.0, 8.0), (-6.0, 3.0)


def _log_likelihood(count: np.ndarray, mean: np.ndarray, shape: float) -> float:
    return float(
        np.sum(
            gammaln(count + shape)
            - gammaln(shape)
            - gammaln(count + 1)
            + shape * np.log(shape / (shape + mean))
            + count * np.log(mean / (shape + mean))
        )
    )


def _modes(
    count: np.ndarray,
    both: sparse.csc_matrix,
    offset: np.ndarray,
    fixed: int,
    shape: float,
    tau: float,
    start: np.ndarray,
) -> tuple[np.ndarray, float, np.ndarray]:
    """The regression and street effects that maximise the penalised likelihood.

    Returns them, the penalised log likelihood there and the weights of the
    last Newton step.  Raises ``RuntimeError`` if Newton's method stalls.
    """
    penalty = np.r_[np.zeros(fixed), np.full(both.shape[1] - fixed, 1 / tau**2)]

    def value(at: np.ndarray) -> float:
        mean = np.exp(np.clip(both @ at + offset, -50, 50))
        return _log_likelihood(count, mean, shape) - 0.5 * float(penalty @ at**2)

    at, now = start.copy(), value(start)
    for _ in range(100):
        mean = np.exp(np.clip(both @ at + offset, -50, 50))
        gradient = both.T @ ((count - mean) * shape / (shape + mean)) - penalty * at
        weight = mean * shape * (shape + count) / (shape + mean) ** 2
        hessian = (both.T @ sparse.diags(weight) @ both + sparse.diags(penalty + 1e-9)).tocsc()
        step = splu(hessian).solve(gradient)
        size = 1.0
        while size > 1e-6:
            tried = value(at + size * step)
            if np.isfinite(tried) and tried >= now:
                break
            size /= 2
        else:
            raise RuntimeError("street-effects model: Newton's method stalled")
        gain, at, now = tried - now, at + size * step, tried
        if gain < 1e-9 and float(np.max(np.abs(size * step))) < 1e-6:
            return at, now, weight
    raise RuntimeError("street-effects model did not converge")


def fit_street_effects(
    bike: pd.Series,
    car: pd.Series,
    classes: pd.DataFrame,
    streets: Mapping[Any, Collection[str]],
    years: float,
) -> dict[str, Any]:
    """Fit the model to counts over ``years`` years; return the per-site estimates.

    ``sites`` is as in ``standard_eb.fit_standard_eb``; ``predicted`` includes
    the street effects.  Also returned: ``coefficients``, ``effects`` (by
    street name), ``tau``, ``shape`` and ``alpha`` (``1 / shape``).  Raises
    ``RuntimeError`` if a fit does not converge.
    """
    car = car.reindex(bike.index)
    columns = design(car, classes, years)
    member, names = membership(bike.index, streets)
    if not names:
        raise RuntimeError("street-effects model: no named street")
    both = sparse.hstack([sparse.csr_matrix(columns.to_numpy()), member]).tocsc()
    fixed, count = columns.shape[1], bike.to_numpy(float)
    offset = np.full(len(count), np.log(years))
    plain = fit_standard_eb(bike, car, classes, years)
    state = {"at": np.r_[plain["coefficients"].to_numpy(), np.zeros(len(names))]}
    street_part = member.tocsc()

    def negative(parameters: np.ndarray) -> float:
        shape, tau = float(np.exp(parameters[0])), float(np.exp(parameters[1]))
        try:
            at, penalised, weight = _modes(count, both, offset, fixed, shape, tau, state["at"])
        except RuntimeError:
            return float("inf")
        state["at"] = at
        curvature = street_part.T @ sparse.diags(weight) @ street_part
        curvature = (curvature + sparse.diags(np.full(len(names), 1 / tau**2))).tocsc()
        log_det = float(np.sum(np.log(np.abs(splu(curvature).U.diagonal()))))
        return -(penalised - len(names) * np.log(tau) - 0.5 * log_det)

    found = minimize(
        negative,
        np.array([np.clip(np.log(plain["shape"]), *LOG_SHAPE), np.log(0.5)]),
        method="Nelder-Mead",
        bounds=[LOG_SHAPE, LOG_TAU],
        options={"xatol": 1e-3, "fatol": 1e-4, "maxiter": 400},
    )
    if not (found.success and np.isfinite(found.fun)):
        raise RuntimeError("street-effects model did not converge")
    shape, tau = float(np.exp(found.x[0])), float(np.exp(found.x[1]))
    at, _, _ = _modes(count, both, offset, fixed, shape, tau, state["at"])
    predicted = pd.Series(np.exp(both @ at + offset), index=bike.index)
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
        "coefficients": pd.Series(at[:fixed], index=columns.columns),
        "effects": pd.Series(at[fixed:], index=names),
        "tau": tau,
        "shape": shape,
        "alpha": 1 / shape,
        "log likelihood": -float(found.fun),
    }


def rank_street_effects(
    bike: pd.Series,
    car: pd.Series,
    classes: pd.DataFrame,
    streets: Mapping[Any, Collection[str]],
    years: float,
    min_crashes: int = MIN_CRASHES,
) -> dict[str, Any]:
    """Score every intersection by the model; by its own count where it cannot be fitted.

    The threshold and the result are as in ``standard_eb.rank_standard``.
    """
    total = int(bike.sum())
    fit, reason = None, None
    if total < min_crashes:
        reason = f"{total} bike crashes, fewer than {min_crashes}"
    else:
        try:
            fit = fit_street_effects(bike, car, classes, streets, years)
        except (RuntimeError, ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
            reason = f"fit failed: {error}"
    if fit is not None and not bool(np.isfinite(fit["sites"].eb).all()):
        fit, reason = None, "fit gave values that are not finite"
    if fit is None:
        return {"score": bike.astype(float), "method": COUNT_ONLY, "reason": reason, "fit": None}
    return {"score": fit["sites"].eb, "method": FITTED, "reason": None, "fit": fit}
