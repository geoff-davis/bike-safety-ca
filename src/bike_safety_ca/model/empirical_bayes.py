"""Empirical Bayes blend of a model's prediction with a site's own count."""

from __future__ import annotations

import pandas as pd
from scipy.stats import gamma


def empirical_bayes(observed: pd.Series, predicted: pd.Series, k: float) -> pd.DataFrame:
    """Empirical Bayes estimate per site (Hauer) from a negative binomial fit.

    With overdispersion ``k`` the site's true mean has a gamma posterior with
    shape ``1/k + observed`` and rate ``1/(k * predicted) + 1``.  ``eb`` is its
    mean, a weighted average of the prediction and the observed count, and
    ``p_over_2x`` is the probability that the true mean is at least twice the
    prediction.
    """
    if not k > 0:
        raise ValueError(
            "empirical_bayes needs overdispersion k > 0; with k = 0 (Poisson) the "
            "estimate is the prediction itself"
        )
    weight = 1 / (1 + k * predicted)
    shape, rate = 1 / k + observed, 1 / (k * predicted) + 1
    sites = pd.DataFrame(
        {
            "observed": observed,
            "predicted": predicted,
            "weight": weight,
            "eb": weight * predicted + (1 - weight) * observed,
            "p_over_2x": gamma.sf(2 * predicted, shape, scale=1 / rate),
        }
    )
    sites["excess"] = sites.eb - sites.predicted
    sites["ratio"] = sites.eb / sites.predicted
    return sites
