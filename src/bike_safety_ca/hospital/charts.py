"""The charts in the reports, as SVG text.

Drawn by hand so the reports need no plotting library.  Colours are a blue and
an orange that stay apart for colour-blind readers; text is always ink, never
the series colour.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import pandas as pd

INK, MUTED, GRID, SURFACE = "#16222a", "#566772", "#d5dde2", "#ffffff"
FIRST, SECOND = "#2a78b5", "#c46b1d"
WIDTH = 640
FONT = 'font-family="Helvetica Neue, Arial, sans-serif"'


def _text(x: float, y: float, words: str, anchor: str = "middle", strong: bool = False) -> str:
    look = (
        f'fill="{INK}" font-size="12" font-weight="600"'
        if strong
        else f'fill="{MUTED}" font-size="11"'
    )
    return f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" {look}>{words}</text>'


def _top(value: float, step: int) -> int:
    """The first gridline at or above the largest value."""
    return max(step, math.ceil(value / step) * step)


def yearly(table: pd.DataFrame, what: str) -> str:
    """A rate by year as a line, with its range as a band.

    ``table`` is indexed by year with columns rate, rate_low and rate_high.
    """
    height, left, right, top, bottom = 210, 44, 20, 22, 30
    highest = _top(table.rate_high.max(), 50)
    span = WIDTH - left - right

    def x(i: int) -> float:
        return left + span * (i + 0.5) / len(table)

    def y(value: float) -> float:
        return top + (height - top - bottom) * (1 - value / highest)

    parts = [
        f'<svg viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" height="{height}" role="img" {FONT} aria-label="{what} by year: '
        + ", ".join(f"{year} {row.rate:.0f}" for year, row in table.iterrows())
        + '.">'
    ]
    for tick in range(0, highest + 1, 50):
        parts.append(
            f'<line x1="{left}" x2="{WIDTH - right}" y1="{y(tick):.1f}" y2="{y(tick):.1f}" '
            f'stroke="{GRID}"/>' + _text(left - 8, y(tick) + 4, f"{tick}", "end")
        )
    rate, low, high = (table[c].to_numpy(float).tolist() for c in ("rate", "rate_low", "rate_high"))
    places = range(len(rate))
    upper = " ".join(f"{x(i):.1f},{y(high[i]):.1f}" for i in places)
    lower = " ".join(f"{x(i):.1f},{y(low[i]):.1f}" for i in reversed(places))
    parts.append(f'<polygon points="{upper} {lower}" fill="{FIRST}" opacity="0.16"/>')
    line = " ".join(f"{x(i):.1f},{y(rate[i]):.1f}" for i in places)
    parts.append(
        f'<polyline points="{line}" fill="none" stroke="{FIRST}" stroke-width="2" '
        'stroke-linejoin="round"/>'
    )
    labelled = {0, len(rate) - 1, rate.index(max(rate))}
    for i, year in enumerate(table.index):
        parts.append(
            f'<circle cx="{x(i):.1f}" cy="{y(rate[i]):.1f}" r="4" fill="{FIRST}" '
            f'stroke="{SURFACE}" stroke-width="2"/>' + _text(x(i), height - 10, str(year))
        )
        if i in labelled:
            parts.append(_text(x(i), y(high[i]) - 8, f"{rate[i]:.0f}", strong=True))
    return "".join(parts) + "</svg>"


def shares(rows: pd.DataFrame) -> str:
    """The share admitted by age group, e-bikes against other bicycles, each as a range bar.

    ``rows`` is indexed by age group with ebike_admitted_low/high and
    bike_admitted_low/high as fractions.
    """
    left, right, top, each, bar = 56, 20, 34, 32, 9
    height = top + each * len(rows) + 28
    columns = ["ebike_admitted_high", "bike_admitted_high"]
    highest = _top(float(rows[columns].max().max()) * 100, 10)
    span = WIDTH - left - right

    def x(share: float) -> float:
        return left + span * share * 100 / highest

    parts = [
        f'<svg viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" height="{height}" role="img" {FONT} aria-label="Share of '
        "hospital-treated injuries admitted, by age group, for e-bikes and other bicycles. "
        'Each bar runs from the lowest to the highest share the counts allow.">',
        f'<rect x="{left}" y="4" width="10" height="10" rx="2" fill="{FIRST}"/>',
        _text(left + 16, 13, "E-bikes", "start"),
        f'<rect x="{left + 80}" y="4" width="10" height="10" rx="2" fill="{SECOND}"/>',
        _text(left + 96, 13, "Other bicycles", "start"),
    ]
    for tick in range(0, highest + 1, 10):
        parts.append(
            f'<line x1="{x(tick / 100):.1f}" x2="{x(tick / 100):.1f}" y1="{top - 6}" '
            f'y2="{height - 24}" stroke="{GRID}"/>' + _text(x(tick / 100), height - 8, f"{tick}%")
        )
    for i, (age, row) in enumerate(rows.iterrows()):
        middle = top + each * i + each / 2
        parts.append(_text(left - 10, middle + 4, str(age).replace("-", "–"), "end", strong=True))
        for kind, colour, offset in (("ebike", FIRST, -bar - 1), ("bike", SECOND, 1)):
            low, high = (float(row[f"{kind}_admitted_{bound}"]) for bound in ("low", "high"))
            if math.isnan(low) or math.isnan(high):
                continue
            parts.append(
                f'<rect x="{x(low):.1f}" y="{middle + offset:.1f}" '
                f'width="{max(x(high) - x(low), 2):.1f}" height="{bar}" rx="4" fill="{colour}"/>'
            )
    return "".join(parts) + "</svg>"


def _step(value: float) -> float:
    """A round gridline step that puts three to six lines under ``value``."""
    scale = 10 ** math.floor(math.log10(max(value, 1e-9)))
    for unit in (1, 2, 2.5, 5, 10):
        if value / (unit * scale) <= 5:
            return unit * scale
    return 10 * scale


def _label(value: float, places: int | None = None) -> str:
    if places is None:
        places = 0 if value >= 10 else 1
    return f"{value:,.{places}f}"


def by_age(panels: list[tuple[str, pd.DataFrame, int]]) -> str:
    """Rates by age group as horizontal bars, one panel per outcome, side by side.

    Each panel's rows are indexed by age group with ``status`` ("published",
    "suppressed" or "not shown"), ``rate_low`` and ``rate_high``.  A published
    rate is a bar; a suppressed one is a pale bar over the range that 1 to 10
    cases allow; a group held back is named but not drawn.  Each panel's
    rates are labelled to its given number of decimal places, as in its table.
    """
    ages = list(panels[0][1].index)
    left, gap, right, top, each, bar = 52, 28, 46, 30, 26, 14
    height = top + each * len(ages) + 26
    width = (WIDTH - left - right - gap * (len(panels) - 1)) / len(panels)
    summary = "; ".join(
        f"{title}: "
        + ", ".join(
            f"{str(age).replace('-', ' to ')} {_label(row.rate_low, places)}"
            if row.status == "published"
            else f"{str(age).replace('-', ' to ')} {row.status}"
            for age, row in rows.iterrows()
        )
        for title, rows, places in panels
    )
    parts = [
        f'<svg viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" height="{height}" role="img" '
        f'{FONT} aria-label="Rates per 100,000 residents a year by age group. {summary}.">'
    ]
    for i, age in enumerate(ages):
        middle = top + each * i + each / 2
        parts.append(_text(left - 10, middle + 4, str(age).replace("-", "–"), "end", strong=True))
    for p, (title, rows, places) in enumerate(panels):
        start = left + p * (width + gap)
        drawn = rows[rows.status != "not shown"]
        highest = float(drawn.rate_high.max()) if len(drawn) else 0.0
        if not highest > 0:  # nothing drawn, or every rate zero: a scale of 0 to 1
            highest = 1.0
        step = _step(highest)
        last = math.ceil(highest / step) * step

        def x(value: float, start: float = start, last: float = last) -> float:
            return start + width * value / last

        parts.append(_text(start, 14, title, "start", strong=True))
        ticks = int(round(last / step))
        for t in range(ticks + 1):
            value = t * step
            parts.append(
                f'<line x1="{x(value):.1f}" x2="{x(value):.1f}" y1="{top - 6}" '
                f'y2="{height - 24}" stroke="{GRID}"/>'
                + _text(x(value), height - 8, _label(value) if value else "0")
            )
        for i, (_, row) in enumerate(rows.iterrows()):
            middle = top + each * i + each / 2
            if row.status == "not shown":
                parts.append(_text(start + 4, middle + 4, "not shown", "start"))
                continue
            low, high = float(row.rate_low), float(row.rate_high)
            if row.status == "suppressed":
                parts.append(
                    f'<rect x="{x(low):.1f}" y="{middle - bar / 2:.1f}" '
                    f'width="{max(x(high) - x(low), 2):.1f}" height="{bar}" rx="3" '
                    f'fill="{FIRST}" opacity="0.25"/>'
                    + _text(x(high) + 4, middle + 4, "suppressed", "start")
                )
            else:
                parts.append(
                    f'<rect x="{start:.1f}" y="{middle - bar / 2:.1f}" '
                    f'width="{max(x(low) - start, 1):.1f}" height="{bar}" rx="3" fill="{FIRST}"/>'
                    + _text(x(low) + 4, middle + 4, _label(low, places), "start")
                )
    return "".join(parts) + "</svg>"


# For charts with more than two series (the trend lines).
THIRD, FOURTH = "#2e8b62", "#9b4f96"
Ranged = dict[str, pd.DataFrame]


def ranged(
    panels: list[tuple[str, Ranged, Callable[[float, float], str], bool]],
    series: list[tuple[str, str, str]],
) -> str:
    """Figures by row as horizontal bars, one panel per title, side by side.

    ``panels`` gives a title, a frame per series key, how to write a figure
    from its range, and whether the figures are fractions shown as %; every frame is
    indexed by the same rows, with low and high (the range hidden counts
    allow) and ci_low and ci_high (a 95% interval for chance).  ``series`` is
    (key, legend label, colour) in drawing order; a panel draws the keys it
    has.  The bar runs to ``low`` and, paler, on to ``high``; a thin line with
    end ticks spans the interval, and the figure is written beside it.  A row
    with no figure (no cases in the group) is named but not drawn.
    """
    rows = list(next(iter(panels[0][1].values())).index)
    left, gap, right = 64, 30, 50
    top = 44 if len(series) > 1 else 30
    bar = 9
    widest = max(len(panel[1]) for panel in panels)
    each = bar * widest + 8 + 4 * widest
    height = top + each * len(rows) + 26
    width = (WIDTH - left - right - gap * (len(panels) - 1)) / len(panels)
    summary = "; ".join(
        f"{title}, {name}: "
        + ", ".join(
            f"{str(row).replace('-', ' to ')} {label(r.low, r.high)}" for row, r in frame.iterrows()
        )
        for title, frames, label, _percent in panels
        for key, frame in frames.items()
        for k, name, _colour in series
        if k == key
    )
    parts = [
        f'<svg viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" height="{height}" role="img" '
        f'{FONT} aria-label="{summary}. Thin lines: 95% interval for chance.">'
    ]
    if len(series) > 1:
        at: float = left
        for _key, name, colour in series:
            parts.append(
                f'<rect x="{at}" y="4" width="10" height="10" rx="2" fill="{colour}"/>'
                + _text(at + 16, 13, name, "start")
            )
            at += 28 + 6.5 * len(name)
    for i, row in enumerate(rows):
        middle = top + each * i + each / 2
        parts.append(_text(left - 10, middle + 4, str(row).replace("-", "–"), "end", strong=True))
    for p, (title, frames, label, percent) in enumerate(panels):
        start = left + p * (width + gap)
        factor = 100 if percent else 1
        tops = [float(f[["high", "ci_high"]].max().max()) for f in frames.values()]
        highest = max([t for t in tops if not math.isnan(t)] or [0.0]) * factor
        if not highest > 0:
            highest = 1.0
        step = _step(highest)
        last = math.ceil(highest / step) * step

        def x(value: float, start: float = start, last: float = last, k: int = factor) -> float:
            return start + width * value * k / last

        parts.append(_text(start, top - 14, title, "start", strong=True))
        for t in range(int(round(last / step)) + 1):
            value = t * step
            at = start + width * value / last
            tick = (_label(value) if value else "0") + ("%" if percent else "")
            parts.append(
                f'<line x1="{at:.1f}" x2="{at:.1f}" y1="{top - 6}" y2="{height - 24}" '
                f'stroke="{GRID}"/>' + _text(at, height - 8, tick)
            )
        drawn = [(k, c) for k, _name, c in series if k in frames]
        for i, row in enumerate(rows):
            band = top + each * i + (each - (bar + 4) * len(drawn) + 4) / 2
            for j, (key, colour) in enumerate(drawn):
                r = frames[key].loc[row]
                y = band + j * (bar + 4)
                if math.isnan(r.low) or math.isnan(r.high):
                    continue
                parts.append(
                    f'<rect x="{start:.1f}" y="{y:.1f}" width="{max(x(r.low) - start, 1):.1f}" '
                    f'height="{bar}" fill="{colour}"/>'
                )
                if r.high > r.low:
                    parts.append(
                        f'<rect x="{x(r.low):.1f}" y="{y:.1f}" '
                        f'width="{max(x(r.high) - x(r.low), 1):.1f}" height="{bar}" '
                        f'fill="{colour}" opacity="0.35"/>'
                    )
                mid = y + bar / 2
                one, two = x(r.ci_low), x(r.ci_high)
                parts.append(
                    f'<path d="M{one:.1f},{mid - 3:.1f}v6M{one:.1f},{mid:.1f}H{two:.1f}'
                    f'M{two:.1f},{mid - 3:.1f}v6" stroke="{INK}" stroke-width="1" fill="none"/>'
                )
                parts.append(
                    f'<text x="{two + 4:.1f}" y="{mid + 3.5:.1f}" fill="{MUTED}" font-size="9.5">'
                    f"{label(r.low, r.high)}</text>"
                )
    return "".join(parts) + "</svg>"


def lines(
    panels: list[tuple[str, dict[str, pd.DataFrame]]],
    colours: dict[str, str],
    places: int = 0,
    percent: bool = False,
) -> str:
    """Figures by year as lines, one per series, each named at its right end.

    Each panel pairs a title with a frame per series name, indexed by year,
    with low, high, ci_low and ci_high.  The line runs through the middle of
    each year's range, with the chance interval as a pale band around it.
    """
    years = list(next(iter(panels[0][1].values())).index)
    left, gap, right, top, bottom = 44, 96, 92, 26, 28
    height = 230
    width = (WIDTH - left - right - gap * (len(panels) - 1)) / len(panels)
    factor = 100 if percent else 1
    summary = "; ".join(
        f"{title}, {name}: "
        + ", ".join(
            f"{year} {(r.low + r.high) / 2 * factor:.{places}f}" for year, r in f.iterrows()
        )
        for title, frames in panels
        for name, f in frames.items()
    )
    parts = [
        f'<svg viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" height="{height}" role="img" '
        f'{FONT} aria-label="{summary}. Bands: 95% interval for chance.">'
    ]
    for p, (title, frames) in enumerate(panels):
        start = left + p * (width + gap)
        highest = max(float(f.ci_high.max()) for f in frames.values()) * factor
        step = _step(highest if highest > 0 else 1.0)
        last = math.ceil(highest / step) * step or step

        def x(i: int, start: float = start) -> float:
            return start + width * (i + 0.5) / len(years)

        def y(value: float, last: float = last) -> float:
            return top + (height - top - bottom) * (1 - value * factor / last)

        parts.append(_text(start, 14, title, "start", strong=True))
        for t in range(int(round(last / step)) + 1):
            value = t * step / factor
            tick = (_label(t * step) if t else "0") + ("%" if percent else "")
            parts.append(
                f'<line x1="{start:.1f}" x2="{start + width:.1f}" y1="{y(value):.1f}" '
                f'y2="{y(value):.1f}" stroke="{GRID}"/>'
                + _text(start - 6, y(value) + 4, tick, "end")
            )
        for i, year in enumerate(years):
            if len(years) <= 5 or i in (0, len(years) - 1) or year % 2 == 0:
                parts.append(_text(x(i), height - 10, str(year)))
        ends: list[tuple[float, str]] = []
        for name, f in frames.items():
            colour = colours[name]
            middle = ((f.low + f.high) / 2).tolist()
            band = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(f.ci_high)) + " "
            band += " ".join(
                f"{x(i):.1f},{y(v):.1f}" for i, v in reversed(list(enumerate(f.ci_low)))
            )
            parts.append(f'<polygon points="{band}" fill="{colour}" opacity="0.15"/>')
            line = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(middle))
            parts.append(
                f'<polyline points="{line}" fill="none" stroke="{colour}" stroke-width="2" '
                'stroke-linejoin="round"/>'
            )
            for i, v in enumerate(middle):
                parts.append(
                    f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="3" fill="{colour}" '
                    f'stroke="{SURFACE}" stroke-width="1.5"/>'
                )
            ends.append((y(middle[-1]), str(name)))
        # Names at the right end, nudged apart so none overlap.
        placed: list[float] = []
        for at, name in sorted(ends):
            placed.append(max(at, placed[-1] + 13) if placed else at)
            parts.append(_text(x(len(years) - 1) + 10, placed[-1] + 4, name, "start", strong=True))
    return "".join(parts) + "</svg>"
