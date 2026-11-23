"""The two charts in the sample reports, as SVG text.

Drawn by hand so the reports need no plotting library.  Colours are a blue and
an orange that stay apart for colour-blind readers; text is always ink, never
the series colour.
"""

from __future__ import annotations

import math

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
