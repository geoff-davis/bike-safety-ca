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
