"""How a crash's reported movements fit together, for its collision diagram.

This is the sorting half of ``plan`` in ``movement_map.html``, in metres:

- ``"fits"``: as the record puts the cyclist (keeping right unless it says
  otherwise), the paths cross, or run parallel in the same half of the road;
- ``"against"``: they meet only with the cyclist on the other side: against
  traffic, on the sidewalk or in the crosswalk;
- ``"nomeet"``: they do not meet at all, so a direction or movement on the
  report may be wrong;
- ``None``: the crash has no cyclist with a direction.

The page reads this value from each crash rather than working it out, so the
map and the tables built on it agree.  The geometry follows the page's
functions of the same names; ``tests/test_movement_diagram.py`` checks the two
give the same answer.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

Party = dict[str, Any]
Legs = Sequence[Sequence[float]]
Point = tuple[float, float]

TURN = {"D": "R", "E": "L", "M": "T", "F": "U"}
STILL = {"A", "O"}
KERB = {"L": "out", "K": "in"}
DRIFT = {"J", "P"}
ROAD, RUN, CLOSE = 10.0, 60.0, 5.0
# Slack in the geometry tests, so a path that ends exactly on another, or two candidate
# points that tie, sort the same way whatever the compass bearing.
EDGE = 1e-6

FIT_LABELS = {
    "fits": "fit as reported",
    "against": "fit only against traffic",
    "nomeet": "do not meet as reported",
}


def _sign(x: float) -> float:
    return (x > 0) - (x < 0)


def half(legs: Legs, b: float, along: bool) -> float:
    """Half width of the street a party on bearing ``b`` travels along (or crosses)."""

    def sep(lb: float) -> float:
        d = (lb - b) % 180
        return min(d, 180 - d)

    most = max([sep(lb) for lb, _ in legs] + [0])
    hs = [
        h for lb, h in legs if (sep(lb) <= 30 if along else sep(lb) > 30 and sep(lb) >= most - 30)
    ]
    return max(hs) if hs else ROAD


def lane(kind: str, move: str, h: float) -> float:
    """Distance of a party's path from the centre line of a street of half width ``h``."""
    turn = TURN.get(move)
    if kind == "bicycle":
        o = h - 1.5
    elif move == "O":
        o = h - 1
    elif turn == "R":
        o = h - 3.5
    elif turn == "L":
        o = 1.7
    else:
        o = (h - 2) / 2
    return max(1.5, min(o, h - 0.5))


def against(p: Party, wrong_suggested: bool) -> bool:
    """Whether the record puts this party on the other side of its street.

    By its own movement ("travelling wrong way", or "crossed into opposing
    lane", which is drawn across the centre line and is not wrong-side
    riding); a cyclist coded as riding on the wrong side (``wr``, see
    ``movement.wrong_side_coded``); or the one cyclist whose movements suggest
    it.  A wrong-side code moves only the cyclist it belongs to.
    """
    return p["m"] in ("Q", "N") or (p["k"] == "bicycle" and (bool(p.get("wr")) or wrong_suggested))


def route(p: Party, o: float, legs: Legs) -> list[Point]:
    """A party's path, in metres from the intersection centre (x east, y south)."""
    t = math.radians(p["b"])
    f, rt = (math.sin(t), -math.cos(t)), (math.cos(t), math.sin(t))

    def at(a: float, b: float) -> Point:  # a along the travel, b to the right of it
        return (a * f[0] + b * rt[0], a * f[1] + b * rt[1])

    def bend(e: Point, c: Point, x: Point) -> list[Point]:
        pts = []
        for i in range(9):
            u = i / 8
            v = 1 - u
            pts.append(
                at(
                    v * v * e[0] + 2 * u * v * c[0] + u * u * x[0],
                    v * v * e[1] + 2 * u * v * c[1] + u * u * x[1],
                )
            )
        return pts

    box, own = half(legs, p["b"], False), half(legs, p["b"], True)
    side_of = _sign(o) or 1
    out = side_of * lane(p["k"], "B", box)
    turn = TURN.get(p["m"])
    if p["m"] in STILL:
        return [at(-box - RUN, o), at(-box - 4, o)]
    kb = side_of * max(1.5, own - 1)
    bike = p["k"] == "bicycle"

    def across(a: float, b: float) -> list[Point]:
        return [at(-box - RUN, a), at(-box - 12, a), at(-box - 6, b), at(box, b), at(box + RUN, b)]

    if not bike and KERB.get(p["m"]) == "out":
        return across(kb, o)
    if not bike and KERB.get(p["m"]) == "in":
        return [at(-box - RUN, o), at(-box - 12, o), at(-box - 6, kb), at(-box - 4, kb)]
    if p["m"] in DRIFT:
        return across(o, side_of * max(1.5, (own - 2) / 2 - 1) if bike else kb)
    if turn in ("R", "L"):
        side = 1 if turn == "R" else -1
        rel = None
        for lb, _ in legs:
            x = side * (((lb - p["b"]) % 360 + 540) % 360 - 180)
            if 30 < x < 150 and (rel is None or abs(x - 90) < abs(rel - 90)):
                rel = x
        g = math.radians(side * (90 if rel is None else rel))
        d, n = (math.cos(g), math.sin(g)), (-math.sin(g), math.cos(g))
        sc = (o - out * n[1]) / d[1]
        c = (out * n[0] + sc * d[0], o)
        sx = max(own, sc + 2)
        x_ = (out * n[0] + sx * d[0], out * n[1] + sx * d[1])
        return [
            at(-box - RUN, o),
            *bend((min(-box, c[0] - 2), o), c, x_),
            at(x_[0] + RUN * d[0], x_[1] + RUN * d[1]),
        ]
    if turn == "U":
        return [
            at(-box - RUN, o),
            *bend((-box / 2, o), (-box / 2 + 2 * abs(o), 0), (-box / 2, -o)),
            at(-box - RUN, -o),
        ]
    return [at(-box - RUN, o), at(-box, o), at(box, o), at(box + RUN, o)]


def meet(
    a_path: list[Point], b_path: list[Point], near: Point, turn_a: bool, turn_b: bool
) -> dict[str, Any] | None:
    """Where path A first crosses path B; failing that, their closest approach nearest ``near``."""
    best: dict[str, Any] | None = None
    for i in range(1 if turn_a else 0, len(a_path) - 1):
        for j in range(1 if turn_b else 0, len(b_path) - 1):
            a, b, c, d = a_path[i], a_path[i + 1], b_path[j], b_path[j + 1]
            den = (b[0] - a[0]) * (d[1] - c[1]) - (b[1] - a[1]) * (d[0] - c[0])
            if abs(den) < 1e-9:
                continue
            la, lb = math.hypot(b[0] - a[0], b[1] - a[1]), math.hypot(d[0] - c[0], d[1] - c[1])
            if abs(den) < 0.5 * la * lb and la > 10 and lb > 10:
                continue  # long near-parallel runs meet only far down the street
            u = ((c[0] - a[0]) * (d[1] - c[1]) - (c[1] - a[1]) * (d[0] - c[0])) / den
            v = ((c[0] - a[0]) * (b[1] - a[1]) - (c[1] - a[1]) * (b[0] - a[0])) / den
            inside = -EDGE <= u <= 1 + EDGE and -EDGE <= v <= 1 + EDGE
            if inside and (best is None or i + u < best["i"] + best["u"] - EDGE):
                best = {"i": i, "u": u, "crossed": True}
    if best:
        return best
    score = math.inf
    for i in range(len(a_path) - 1):
        for j in range(len(b_path) - 1):
            # The angle between the two segments, 0 when parallel either way.
            ha = math.atan2(a_path[i + 1][1] - a_path[i][1], a_path[i + 1][0] - a_path[i][0])
            hb = math.atan2(b_path[j + 1][1] - b_path[j][1], b_path[j + 1][0] - b_path[j][0])
            g = math.degrees(ha - hb) % 180
            sep = min(g, 180 - g)
            for s in range(11):
                u = s / 10
                q = (
                    a_path[i][0] + u * (a_path[i + 1][0] - a_path[i][0]),
                    a_path[i][1] + u * (a_path[i + 1][1] - a_path[i][1]),
                )
                for w in range(11):
                    v = w / 10
                    z = (
                        b_path[j][0] + v * (b_path[j + 1][0] - b_path[j][0]),
                        b_path[j][1] + v * (b_path[j + 1][1] - b_path[j][1]),
                    )
                    dist = math.hypot(q[0] - z[0], q[1] - z[1])
                    sc = dist + 0.05 * math.hypot(q[0] - near[0], q[1] - near[1])
                    # A point where a path bends ends one segment and starts the next, with the
                    # same score; the more parallel segment wins, whatever the compass bearing.
                    tied = best is not None and abs(sc - score) <= EDGE and sep < best["sep"] - EDGE
                    if sc < score - EDGE or tied:
                        score = sc
                        best = {
                            "i": i,
                            "u": u,
                            "j": j,
                            "d": dist,
                            "crossed": False,
                            "sep": sep,
                            "same": math.cos(ha - hb) > 0,
                        }
    return best


def fit(parties: list[Party], legs: Legs, wrong_suggested: bool, infer: bool = True) -> str | None:
    """How the crash's reported movements fit (see the module docstring).

    ``infer`` is false for a crash whose record already says who was on the
    wrong side, or cites the wrong side with the party unclear: no cyclist is
    then put against traffic to make the movements meet, so the answer is
    never ``"against"``.
    """
    bike = next((p for p in parties if p["k"] == "bicycle" and p["b"] is not None), None)
    if bike is None:
        return None
    others = [p for p in parties if p is not bike and p["b"] is not None]

    def offset(p: Party) -> float:
        o = lane(p["k"], p["m"], half(legs, p["b"], True))
        return -o if against(p, wrong_suggested) else o

    routes = [(p, route(p, offset(p), legs)) for p in others]
    t = math.radians(bike["b"])

    def turns(p: Party) -> bool:
        return TURN.get(p["m"]) in ("R", "L", "U")

    reach = max(CLOSE, half(legs, bike["b"], True) - 1)

    def meets(o: float) -> bool:
        path = route(bike, o, legs)
        a = half(legs, bike["b"], False) + 4
        near = (-math.sin(t) * a + math.cos(t) * o, math.cos(t) * a + math.sin(t) * o)
        for q, other in routes:
            m = meet(path, other, near, turns(bike), turns(q))
            if m is None:
                continue
            if m["crossed"]:
                return True
            # Side by side only where parallel within reach and in the same half of the road.
            near_enough = m["sep"] <= 30 + EDGE and m["d"] <= reach + EDGE
            if near_enough and m["same"] == (_sign(o) == _sign(offset(q))):
                return True
        return False

    if not routes or meets(offset(bike)):
        return "fits"
    if infer and not against(bike, wrong_suggested) and meets(-offset(bike)):
        return "against"
    return "nomeet"
