"""Expected cyclist crashes per corridor: a named street, its corners and the stretches between.

A corridor is one named street.  The forecast (``checks.corridors``) groups
mapped streets by ``junctions.street_key``, so "FOOTHILL EXPY" and "Foothill
Expressway" are one corridor and Park Avenue and Park Place are two, and
labels each with ``network.names.corridor``.  ``corridor_lengths`` and
``corridor_corners`` below are simpler: they group by that tidied name alone,
which drops generic street types, so they put Park Avenue with Park Road.
Each crash is counted in one place only: at a corner, where ``assign_crashes``
put it, or between corners, on the corridor of its reported primary road (the
longest street of that name, where the report's street type does not settle
which).

A corner counts fully for every street through it, in the past counts, the
forecast and the later crashes alike, so corridor totals add up to more than
the area's total.  That is right for ranking corridors and for asking how many
crashes one street had; it is wrong for adding corridors together.

``score_corridors`` is the entry point.  At corners it sums the intersection
model's expected counts (``rank_intersections``); between corners it fits a
negative binomial model to street length and car crashes and blends in each
corridor's own count, as the intersection model does.  Where either part has
too few crashes to fit it falls back to past crashes, and says so.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry.base import BaseGeometry

from bike_safety_ca.model.crash_history import (
    MIN_CRASHES,
    _fit_spread,
    gamma_blend,
    rank_intersections,
)
from bike_safety_ca.network.names import corridor

MODEL = "street-length model"
BETWEEN_MODEL = "length and car crash model"
PAST = "past crashes"


def corridor_lengths(ways: gpd.GeoDataFrame, outline: BaseGeometry | None = None) -> pd.Series:
    """Length in km of each named corridor, inside ``outline`` when given, by tidied name.

    ``ways`` needs ``name`` and a projected ``geometry`` in metres.  Unnamed
    streets belong to no corridor.
    """
    named = ways[ways["name"].notna()]
    geometry = named.geometry if outline is None else named.geometry.intersection(outline)
    km = pd.Series(geometry.length.to_numpy() / 1000, index=named["name"].map(corridor).to_numpy())
    km = km[(km.index != "") & (km > 0)]
    return km.groupby(level=0).sum().sort_index()


def corridor_corners(streets: Mapping[Any, Collection[str]]) -> dict[Any, list[Any]]:
    """The corners on each corridor, from the street names at each intersection.

    A corner on two corridors appears under both.  Corridors and their corners
    are sorted so that runs agree.
    """
    corners: dict[Any, list[Any]] = {}
    for site in sorted(streets, key=str):
        for name in sorted({corridor(n) for n in streets[site]} - {""}):
            corners.setdefault(name, []).append(site)
    return dict(sorted(corners.items()))


def on_corridors(per_site: pd.Series, corners: Mapping[Any, list[Any]]) -> pd.Series:
    """Sum of a per-intersection value over each corridor's corners."""
    keys = list(corners)
    return pd.Series(
        [float(per_site.reindex(corners[k], fill_value=0).sum()) for k in keys],
        index=pd.Index(keys, tupleize_cols=False),
        dtype=float,
    )


def fit_between(bike: pd.Series, car: pd.Series, km: pd.Series) -> pd.DataFrame:
    """Expected crashes between corners from street length and car crashes there.

    The fit is ``expected = c * km^a * (car + 1)^b`` with negative binomial
    counts (variance ``expected + alpha * expected^2``), and each corridor's own
    count is blended in with ``gamma_blend``.  All three series share the
    corridor index.  Returns ``observed``, ``predicted``, ``prior_shape`` and the
    blend ``eb``.  Raises if the fit does not converge.
    """
    count = bike.to_numpy(dtype=float)
    design = np.column_stack(
        [np.ones(len(km)), np.log(km.to_numpy()), np.log(car.to_numpy(dtype=float) + 1)]
    )
    coefficients, alpha, _ = _fit_spread(count, design, 2.0)
    predicted = pd.Series(np.exp(design @ coefficients), index=km.index)
    prior_shape = pd.Series(1 / alpha, index=km.index)
    return pd.DataFrame(
        {
            "observed": bike,
            "predicted": predicted,
            "prior_shape": prior_shape,
            "eb": gamma_blend(bike, predicted, prior_shape),
        }
    )


def score_corridors(
    bike_site: pd.Series,
    car_site: pd.Series,
    streets: Mapping[Any, Collection[str]],
    corners: Mapping[Any, list[Any]],
    bike_between: pd.Series,
    car_between: pd.Series,
    km: pd.Series,
    min_crashes: int = MIN_CRASHES,
) -> dict[str, Any]:
    """Expected cyclist crashes per corridor over the fitting period.

    ``bike_site`` and ``car_site`` are crash counts per intersection,
    ``streets`` the names at each intersection (for the intersection model),
    ``corners`` the intersections on each corridor (``corridor_corners``, or
    pieces of corridors), ``bike_between`` and ``car_between`` counts per
    corridor of crashes at no intersection, and ``km`` each corridor's length;
    corridors are the index of ``km``.  Returns ``table`` (per corridor: ``km``, ``past`` crashes,
    ``corners`` and ``between`` expected, their sum ``expected`` and
    ``per_km``) and the method used for each part, ``corner_method`` and
    ``between_method``, with ``reasons`` for any fallback.
    """
    index = km.index
    corners = {name: sites for name, sites in corners.items() if name in index}
    reasons = []
    # The corner part keeps the fitted spread power: the corridor table sums expected
    # counts, and only the intersection ranking has been compared at power 1.
    ranked = rank_intersections(bike_site, car_site, streets, min_crashes, spread_power=None)
    if ranked["fit"] is not None:
        corner_score, corner_method = ranked["score"], MODEL
    else:  # the blend only orders corners; past crashes keep the sum a count
        corner_score, corner_method = bike_site.astype(float), PAST
        reasons.append(f"corners: {ranked['reason']}")
    past_corners = on_corridors(bike_site.astype(float), corners).reindex(index, fill_value=0)
    bike_between = bike_between.reindex(index, fill_value=0).astype(float)
    car_between = car_between.reindex(index, fill_value=0).astype(float)
    between, between_method = bike_between, PAST
    if bike_between.sum() < min_crashes:
        reasons.append(
            f"between corners: {int(bike_between.sum())} bike crashes, fewer than {min_crashes}"
        )
    else:
        try:
            fit = fit_between(bike_between, car_between, km)
            if bool(np.isfinite(fit.eb).all()):
                between, between_method = fit.eb, BETWEEN_MODEL
            else:
                reasons.append("between corners: fit gave values that are not finite")
        except (RuntimeError, ValueError, FloatingPointError) as error:
            reasons.append(f"between corners: fit failed: {error}")
    table = pd.DataFrame(
        {
            "km": km,
            "past": past_corners + bike_between,
            "corners": on_corridors(corner_score, corners).reindex(index, fill_value=0),
            "between": between,
        }
    )
    table["expected"] = table.corners + table.between
    table["per_km"] = table.expected / table.km
    return {
        "table": table,
        "corner_method": corner_method,
        "between_method": between_method,
        "reasons": reasons,
    }
