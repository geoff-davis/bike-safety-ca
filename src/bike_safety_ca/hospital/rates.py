"""County injury rates compared with the state, with honest ranges.

The question is which counties have more, or fewer, bicycle injuries treated
in hospital than their residents' ages would lead you to expect.  Three things
make the raw answer misleading, and this module deals with each:

1. Counties differ in age.  Each county's count is compared with the count
   expected if every age group there had the statewide rate (``expected``).
   The comparison is a ratio: 1.3 means 30% more than expected.
2. Small counties have noisy rates.  A county's ratio is estimated together
   with all the others (``fit_prior`` then ``posterior``): the counties' true
   ratios are taken to be spread around a common mean, the spread is learned
   from the data, and each county is pulled toward the mean by an amount that
   depends on how much its own data can say.  This is the gamma-Poisson
   model, the same blend the crash-history ranking uses.
3. The source hides counts from 1 to 10.  A hidden cell is not dropped,
   filled in or worked out from totals.  It enters the calculation as what is
   known about it, "some whole number from 1 to 10" (``cells``), and the
   model weighs each of those ten values by how likely it is.

docs/county_rates_method.md gives the reasoning and the formulas.

Source of the counts: California Department of Public Health, EpiCenter –
California Injury Data Online.  Nothing here identifies or tries to identify
any person, and no hidden count is ever recovered.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import optimize, special, stats

HIDDEN = (1, 10)  # what a suppressed cell is known to hold
POINTS = 2001  # values of log ratio at which a county with hidden cells is evaluated
STEP = 0.02  # and the widest spacing of those values
TAIL = 1e-10
WIDEST = 64  # the widest range of counts a single cell may have
CERTAIN = 0.95  # how sure to be before calling a county higher or lower
SHAPES = (0.02, 5000.0)  # the spread is fitted within these; the top is "all alike"
HIGHER, LOWER, UNCLEAR = "higher", "lower", ""


@dataclass(frozen=True)
class Prior:
    """How the counties' true ratios are spread: a gamma with this mean and shape.

    A large shape means the counties are much alike, so a county's own figure
    is pulled strongly toward the mean; a small one means they differ a lot.
    An infinite mean is the prior for one area on its own (see ``ALONE``).
    """

    mean: float
    shape: float

    def __post_init__(self) -> None:
        if not (self.mean > 0 and self.shape > 0 and math.isfinite(self.shape)):
            raise ValueError("a prior needs a mean and a shape above zero")

    @property
    def rate(self) -> float:
        return 0.0 if math.isinf(self.mean) else self.shape / self.mean

    @property
    def proper(self) -> bool:
        return self.rate > 0


# For one area on its own, with nothing to borrow from: the Jeffreys prior for
# a Poisson rate.  The area's own cells decide, and there is no mean to compare with.
ALONE = Prior(mean=math.inf, shape=0.5)


def cells(table: pd.DataFrame, keys: list[str], every: pd.MultiIndex | pd.Index) -> pd.DataFrame:
    """What is known about each cell's count, as a lowest and highest value.

    ``table`` is a saved EpiCenter table: one row per cell that holds at least
    one record, ``Count`` blank where the source hides it.  ``every`` lists
    all the cells that could exist (say each county and year).  A published
    count gives low = high = the count; a hidden one gives 1 to 10; a cell
    with no row holds nobody, so 0 to 0.  The bounds come from the cell's own
    row alone, never from a total it is part of.
    """
    if table.duplicated(keys).any() or every.has_duplicates:
        raise ValueError("a cell appears twice")
    index = keys[0] if len(keys) == 1 else keys
    raw = table.set_index(index).Count
    count = pd.to_numeric(raw, errors="coerce")
    blank = raw.isna() | raw.astype(str).str.strip().eq("")
    if (count.isna() & ~blank).any():
        raise ValueError("a count that is neither a number nor blank")
    shown = count.dropna()
    if (shown <= HIDDEN[1]).any() or (shown % 1 != 0).any():
        raise ValueError(f"a published count of {HIDDEN[1]} or less, or not whole: check the table")
    unknown = count.index.difference(every)
    if len(unknown):
        raise KeyError(f"cells not in the list of all cells: {list(unknown)[:5]}")
    result = pd.DataFrame(index=every)
    result["low"] = count.fillna(HIDDEN[0]).reindex(every, fill_value=0).astype(int)
    result["high"] = count.fillna(HIDDEN[1]).reindex(every, fill_value=0).astype(int)
    result["hidden"] = count.isna().reindex(every, fill_value=False)
    return result


def expected(residents: pd.DataFrame, state_rate: pd.Series, by: list[str]) -> pd.Series:
    """Counts expected if each age group had the statewide rate.

    ``residents`` has ``age_group`` and ``residents`` columns plus those in
    ``by`` (say county and year); ``state_rate`` is cases per resident,
    indexed by age group.  Returns the expected count for each ``by`` group.
    """
    missing = set(residents.age_group) - set(state_rate.index)
    if missing:
        raise KeyError(f"no statewide rate for age groups {sorted(missing)}")
    if not state_rate.index.is_unique or residents[by].isna().any().any():
        raise ValueError("an age group with two statewide rates, or a missing group label")
    for values in (residents.residents, state_rate.reindex(residents.age_group.unique())):
        numbers = values.to_numpy(float)
        if not np.isfinite(numbers).all() or (numbers < 0).any():
            raise ValueError("a missing, infinite or negative resident count or statewide rate")
    each = residents.residents * residents.age_group.map(state_rate)
    return each.groupby([residents[column] for column in by]).sum().rename("expected")


def _check(table: pd.DataFrame, unit: str) -> None:
    numbers = table[["low", "high", "expected"]].to_numpy(float)
    if not np.isfinite(numbers).all() or table[unit].isna().any():
        raise ValueError("a missing or infinite bound, expected count or unit name")
    if (table.expected <= 0).any():
        raise ValueError("every cell needs an expected count above zero")
    if (table.low > table.high).any() or (table.low < 0).any():
        raise ValueError("a cell's lowest value is above its highest, or below zero")
    if (table[["low", "high"]] % 1 != 0).any().any() or (table.high - table.low >= WIDEST).any():
        raise ValueError(f"bounds must be whole numbers less than {WIDEST} apart")


def _log_evidence(low: np.ndarray, high: np.ndarray, mean: np.ndarray) -> np.ndarray:
    """Log chance of a count from low to high, for each Poisson mean.

    The chances of the possible counts are added one by one, which stays
    accurate where a difference of two cumulative chances would not.
    """
    steps = np.arange(int((high - low).max()) + 1)
    counts = low[:, None] + steps  # cell by possible count
    each = stats.poisson.logpmf(counts[:, :, None], mean[:, None, :])
    each = np.where((counts <= high[:, None])[:, :, None], each, -np.inf)
    return np.asarray(special.logsumexp(each, axis=1))


@dataclass(frozen=True)
class _Posterior:
    """A county's ratio given its cells: summary figures and the log marginal likelihood."""

    mean: float
    low: float
    high: float
    log_marginal: float
    above: object  # chance the ratio is above a given value

    def chance_above(self, value: float) -> float:
        return float(self.above(value))  # type: ignore[operator]


def _exact(low: np.ndarray, exposure: np.ndarray, prior: Prior) -> _Posterior:
    """Nothing hidden: the ratio is a gamma, by the textbook result."""
    found = stats.gamma(prior.shape + low.sum(), scale=1 / (prior.rate + exposure.sum()))
    log_marginal = math.nan
    if prior.proper:
        log_marginal = float(
            (low * np.log(exposure) - special.gammaln(low + 1)).sum()
            + prior.shape * math.log(prior.rate)
            - special.gammaln(prior.shape)
            + special.gammaln(prior.shape + low.sum())
            - (prior.shape + low.sum()) * math.log(prior.rate + exposure.sum())
        )
    return _Posterior(
        float(found.mean()), float(found.ppf(0.05)), float(found.ppf(0.95)), log_marginal, found.sf
    )


def _censored(low: np.ndarray, high: np.ndarray, exposure: np.ndarray, prior: Prior) -> _Posterior:
    """Some cells hidden: the ratio's distribution worked out on a grid.

    The grid is in the logarithm of the ratio.  There the density falls
    smoothly to zero at both ends whatever the prior's shape, which it does
    not in the ratio itself when the shape is under 1.
    """
    scale = 1 / (prior.rate + exposure.sum())
    least = prior.shape + low.sum()
    start = math.log(stats.gamma.ppf(TAIL, least, scale=scale) or math.nan)
    if not math.isfinite(start):
        # The quantile is too small to hold as a number.  That far down, the
        # chance of being below t is (t/scale)^shape / Gamma(shape + 1).
        start = (math.log(TAIL) + special.gammaln(least + 1)) / least + math.log(scale)
    last = stats.gamma.ppf(1 - TAIL, prior.shape + high.sum(), scale=scale)
    if not (math.isfinite(start) and 0 < last < math.inf and start < math.log(last)):
        raise ValueError("the ratio's range could not be bracketed: check the expected counts")
    # A very small shape spreads the density over a long stretch of log ratio.
    points = int(min(max(POINTS, (math.log(last) - start) / STEP), 30 * POINTS))
    x = np.linspace(start, math.log(last), points)
    ratio = np.exp(x)
    # Density of the log ratio: the gamma prior's density times the ratio.
    log_density = prior.shape * x - prior.rate * ratio
    if prior.proper:
        log_density += prior.shape * math.log(prior.rate) - special.gammaln(prior.shape)
    log_density = log_density + _log_evidence(low, high, exposure[:, None] * ratio).sum(axis=0)
    peak = log_density.max()
    density = np.exp(log_density - peak)
    area = np.trapezoid(density, x)
    if not (math.isfinite(peak) and area > 0):
        raise ValueError("the ratio's distribution could not be worked out")
    density = density / area
    cumulative = np.concatenate([[0.0], np.cumsum((density[1:] + density[:-1]) / 2 * np.diff(x))])
    cumulative /= cumulative[-1]

    def above(value: float) -> float:
        return 1 - float(np.interp(math.log(value), x, cumulative)) if value > 0 else 1.0

    return _Posterior(
        float(np.trapezoid(ratio * density, x)),
        float(np.exp(np.interp(0.05, cumulative, x))),
        float(np.exp(np.interp(0.95, cumulative, x))),
        float(peak + math.log(area)) if prior.proper else math.nan,
        above,
    )


def _unit(group: pd.DataFrame, prior: Prior, grid: bool = False) -> _Posterior:
    low = group.low.to_numpy(float)
    high = group.high.to_numpy(float)
    exposure = group.expected.to_numpy(float)
    if (low == high).all() and not grid:
        return _exact(low, exposure, prior)
    if prior.shape < SHAPES[0]:
        raise ValueError(f"hidden cells need a prior shape of {SHAPES[0]} or more")
    return _censored(low, high, exposure, prior)


def log_likelihood(table: pd.DataFrame, unit: str, prior: Prior) -> float:
    """How well a prior explains every county's cells, hidden ones included."""
    return sum(_unit(group, prior).log_marginal for _, group in table.groupby(unit))


def fit_prior(table: pd.DataFrame, unit: str = "county", mean: float | None = None) -> Prior:
    """The spread of the counties' ratios that best explains the cells.

    ``table`` has one row per cell with the columns ``unit``, ``low``,
    ``high`` and ``expected``.  All of a county's cells share one ratio.  The
    mean is fitted too unless given: when the expected counts come from
    statewide rates it is close to 1 but need not equal it.  A fitted shape at
    the top of ``SHAPES`` means the counties show no difference beyond chance.
    """
    _check(table, unit)
    if table[unit].nunique() < 10:
        raise ValueError("too few units to learn how much they differ")
    bounds = np.log(SHAPES)

    def prior(parameters: np.ndarray) -> Prior:
        centre = mean if mean is not None else float(np.exp(parameters[0]))
        return Prior(centre, float(np.exp(np.clip(parameters[-1], *bounds))))

    def loss(parameters: np.ndarray) -> float:
        value = -log_likelihood(table, unit, prior(parameters))
        # Outside the allowed shapes the loss rises, so the search turns back.
        return value + float(np.abs(parameters[-1] - np.clip(parameters[-1], *bounds)))

    if not table.high.any():
        raise ValueError("no cases anywhere: there is no spread to fit")
    middle = (table.low + table.high).sum() / 2 / table.expected.sum()
    start = np.log([5.0]) if mean is not None else np.log([middle, 5.0])
    found = optimize.minimize(
        loss, start, method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 2000}
    )
    if not found.success or not math.isfinite(found.fun):
        raise RuntimeError(f"the spread could not be fitted: {found.message}")
    return prior(found.x)


def posterior(
    table: pd.DataFrame, prior: Prior, unit: str = "county", reference: float | None = None
) -> pd.DataFrame:
    """Each county's ratio: best estimate, range and, given a reference, a call-out.

    Columns: ``expected`` (cases expected at statewide rates), ``low`` and
    ``high`` (what the source's cells add up to at least and at most),
    ``raw_low`` and ``raw_high`` (those divided by expected: the unshrunk
    ratio, a single number when nothing is hidden), ``ratio`` (the estimate),
    ``ratio_low`` and ``ratio_high`` (a 90% range).  With ``reference`` (1 for
    "the state", when expected counts come from statewide rates) there are
    also ``chance_above`` (the chance the county's true ratio is above it) and
    ``call`` ("higher" or "lower" when that chance is at least 95% either way).
    """
    _check(table, unit)
    if reference is not None and not (0 < reference < math.inf):
        raise ValueError("the reference must be a positive number")
    rows: dict[object, dict[str, float | str]] = {}
    for name, group in table.groupby(unit):
        found = _unit(group, prior)
        total = group.expected.sum()
        rows[name] = {
            "expected": total,
            "low": int(group.low.sum()),
            "high": int(group.high.sum()),
            "raw_low": group.low.sum() / total,
            "raw_high": group.high.sum() / total,
            "ratio": found.mean,
            "ratio_low": found.low,
            "ratio_high": found.high,
        }
        if reference is not None:
            above = found.chance_above(reference)
            rows[name]["chance_above"] = above
            rows[name]["call"] = (
                HIGHER if above >= CERTAIN else LOWER if above <= 1 - CERTAIN else UNCLEAR
            )
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis(unit)
