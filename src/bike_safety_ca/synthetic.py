"""A made-up city for tests and demos, so nothing here needs real crash records.

Streets form a grid.  Every sixth line is an arterial that runs the whole way
under one name; the lines between are broken into short local streets, each
with its own name.  Every intersection has a true yearly bike crash rate that
depends on the traffic of its streets, a hazard shared along each street and
its own luck, and crashes are drawn from those rates year by year.  Because
the true rates are known, a ranking can be scored against them as well as
against later crashes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from bike_safety_ca import ADULT, CAR, CHILD


@dataclass(frozen=True)
class City:
    """``sites``: one row per intersection (x, y, in_city, true yearly rates).
    ``streets``: the named streets meeting at each intersection.
    ``crashes``: one row per crash (site, year, group)."""

    sites: pd.DataFrame
    streets: dict[int, frozenset[str]]
    crashes: pd.DataFrame


def _line_names(rng: np.random.Generator, line: int, size: int, kind: str) -> list[str]:
    """Street name at each of the ``size`` intersections along one grid line."""
    if line % 6 == 0:
        return [f"{kind} {line} ARTERIAL"] * size
    names: list[str] = []
    piece = 0
    while len(names) < size:
        names += [f"{kind} {line}-{piece}"] * int(rng.integers(2, 9))
        piece += 1
    return names[:size]


def make_city(seed: int = 0, size: int = 30, first_year: int = 2014, last_year: int = 2025) -> City:
    """A ``size`` by ``size`` grid city with crashes for each year in the range."""
    rng = np.random.default_rng(seed)
    east_west = [_line_names(rng, i, size, "EW") for i in range(size)]
    north_south = [_line_names(rng, j, size, "NS") for j in range(size)]
    names = sorted({n for line in east_west + north_south for n in line})
    arterial = np.array(["ARTERIAL" in n for n in names])
    traffic = pd.Series(rng.lognormal(0, 0.5, len(names)) * np.where(arterial, 6.0, 1.0), names)
    hazard = pd.Series(rng.lognormal(0, 0.6, len(names)), names)

    rows = []
    streets: dict[int, frozenset[str]] = {}
    for i in range(size):
        for j in range(size):
            site = i * size + j
            pair = (east_west[i][j], north_south[j][i])
            streets[site] = frozenset(pair)
            flow = float(traffic[list(pair)].sum())
            rows.append(
                {
                    "site": site,
                    "x": 100.0 * j,
                    "y": 100.0 * i,
                    "in_city": j < size // 2,
                    "car_rate": 0.08 * flow * rng.lognormal(0, 0.5),
                    "bike_rate": 0.03
                    * flow**0.6
                    * float(hazard[list(pair)].mean())
                    * rng.lognormal(0, 0.5),
                }
            )
    sites = pd.DataFrame(rows).set_index("site")

    parts = []
    for year in range(first_year, last_year + 1):
        for group, rate in (
            (CAR, sites.car_rate),
            (CHILD, 0.35 * sites.bike_rate),
            (ADULT, 0.65 * sites.bike_rate),
        ):
            n = rng.poisson(rate.to_numpy())
            parts.append(
                pd.DataFrame({"site": sites.index.repeat(n), "year": year, "group": group})
            )
    return City(sites, streets, pd.concat(parts, ignore_index=True))
