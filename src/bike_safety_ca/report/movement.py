"""Crash movement map: each cyclist crash with an arrow per party.

The arrow shows the direction of travel the officer recorded, turned to the
bearing of the nearest street, and the movement before the crash; its colour
is the kind of road user.  The page is a single HTML file with a built-in
street map, so it opens from disk without a web server.

The detail grows with the zoom: intersections sized by their crash count,
then one dot per crash, then a collision diagram at each intersection, with
each party's path drawn in its own lane up to where they met.  A side panel lists
the crashes in view, their repeated patterns and the streets they are on, and "Print this view"
prints the map at its current zoom with those tables.

It shows individual police records (month, hour, streets, movements, fault and
the cyclist's age band) and carries the TIMS and CCRS credits.
"""

from __future__ import annotations

import html
import json
import re
from importlib import resources
from pathlib import Path
from typing import Any, cast

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from shapely.geometry import Point, box
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from bike_safety_ca import ADULT, CHILD
from bike_safety_ca.config import Config
from bike_safety_ca.crashes.groups import BICYCLE as BICYCLE_PARTY
from bike_safety_ca.crashes.groups import MAX_AGE
from bike_safety_ca.io import CRS_WGS84
from bike_safety_ca.network import junctions
from bike_safety_ca.network.names import corridor
from bike_safety_ca.report import codes, diagram
from bike_safety_ca.report.crashes import cyclists

PARTY_COLUMNS = [
    "CASE_ID",
    "ccrs_collision_id",
    "PARTY_NUMBER",
    "PARTY_TYPE",
    "AT_FAULT",
    "PARTY_AGE",
    "DIR_OF_TRAVEL",
    "MOVE_PRE_ACC",
    "STWD_VEHICLE_TYPE",
    "source",
]
# Characters that could end a <script> block or open an HTML comment inside one,
# and the two line separators JavaScript treats as line ends, as JSON escapes.
SCRIPT_SAFE = {
    "<": "\\u003c",
    ">": "\\u003e",
    "&": "\\u0026",
    "\u2028": "\\u2028",
    "\u2029": "\\u2029",
}
PEDESTRIAN_PARTY, DRIVER_PARTY, PARKED_PARTY = "2", "1", "3"
SNAP_WITHIN_DEG = 50.0
# The map credit for real records; they carry no banner.
REAL_CREDIT = (
    "crash records: Transportation Injury Mapping System (TIMS), Safe Transportation Research"
    " and Education Center, University of California, Berkeley; and California Crash"
    " Reporting System (CCRS), California Highway Patrol, via data.ca.gov"
)
# (banner, map credit) for the made-up demo city.
SYNTHETIC_NOTICE = (
    "Synthetic data. Every crash here is made up and placed on real streets; none is a real crash.",
    "crashes: made up by bike_safety_ca.demo, not real records",
)
MOTOR = (codes.CAR, codes.MOTORCYCLE, codes.OTHER)
STREET_CLASSES = {
    "M": "motorway|trunk|primary|secondary",
    "T": "tertiary",
    "L": "residential|unclassified|living_street",
    "S": "service",
}

# Collision diagrams draw each street at its width: lanes of LANE_M, plus a bike lane,
# shoulder or parking beyond the last lane.  Ways with no lanes tag get a typical count.
LANE_M = 3.3
EDGE_M = {"M": 2.0, "T": 2.0, "L": 2.5, "S": 0.5}
TYPICAL_LANES = {"M": 4, "T": 2, "L": 2, "S": 2}
LEG_STUB_M = 10.0  # a street reaching less than this past a corner does not leave it that way
LEG_LOOK_M = 25.0  # a street's direction at a point: toward where it is this far along
# Naming a corridor as the map does (street_names): the compass word dropped from a mapped name,
# and the share of the corridor's mapped length one name needs when the map has several.
COMPASS_PREFIX = r"^(North|South|East|West|N|S|E|W)\.? (?=\S)"
NAME_SHARE = 0.9


def half_widths(roads: gpd.GeoDataFrame) -> pd.Series:
    """Half the width of each road in metres, kerb to centre line, from its lanes and class.

    A road mapped as two one-way ways counts the lanes of both
    (``junctions.road_lanes``).  ``roads`` holds only street classes.
    """
    highway = roads.highway.astype(str)
    kind = pd.Series("S", index=roads.index)
    for key in reversed(list(STREET_CLASSES)):  # the first class that matches wins
        kind[highway.str.contains(STREET_CLASSES[key])] = key
    tagged = junctions.road_lanes(roads) if "lanes" in roads else pd.Series(np.nan, roads.index)
    lanes = tagged.fillna(kind.map(TYPICAL_LANES)).clip(lower=1)
    return lanes * LANE_M / 2 + kind.map(EDGE_M)


class Bearings:
    """Bearings of the streets near a point, both ways along each, and their widths.

    Footpaths and other ways that are not streets are left out, so a crash is
    not turned to the bearing of a path beside the road.
    """

    def __init__(self, streets: gpd.GeoDataFrame) -> None:
        roads = streets[streets.highway.astype(str).str.contains("|".join(STREET_CLASSES.values()))]
        self.geoms = roads.geometry.to_numpy()
        self.half = half_widths(roads).to_numpy(dtype=float) if len(roads) else np.array([])
        self.tree = STRtree(self.geoms)
        # Each named street joined into whole lines, so a street mapped as several short ways
        # still leaves a corner; unnamed ways stand alone.
        names = (
            roads["name"] if "name" in roads else pd.Series(None, index=roads.index, dtype=object)
        )
        self.names = names.to_numpy()
        joined: list[Any] = []
        joined_names: list[str | None] = []
        joined_half: list[float] = []
        for i, (geometry, name) in enumerate(zip(self.geoms, self.names, strict=True)):
            if not isinstance(name, str):
                joined.append(geometry)
                joined_names.append(None)
                joined_half.append(float(self.half[i]))
        for name, group in roads.groupby(names, sort=True):
            for part in shapely.get_parts(shapely.line_merge(shapely.union_all(group.geometry))):
                joined.append(part)
                joined_names.append(str(name))
                joined_half.append(float("nan"))
        self.joined = np.array(joined, dtype=object)
        self.joined_names = joined_names
        self.joined_half = joined_half
        self.joined_tree = STRtree(self.joined)

    def legs(self, point: Point, radius: float = 35.0) -> list[list[float]]:
        """``[bearing, half width]`` for each way a street leaves ``point``.

        A street that ends at ``point`` (within ``LEG_STUB_M``) leaves it one
        way only, so at a T or an offset junction there is no leg where no
        street goes.
        """
        found = set()
        ways_here = self.tree.query(point, predicate="dwithin", distance=radius)
        for ahead, behind, j, before, after in self._near(point, radius, joined=True):
            name = self.joined_names[j]
            half = (  # a named street is as wide as its widest way here
                max(
                    float(self.half[i])
                    for i in ways_here
                    if isinstance(self.names[i], str) and self.names[i] == name
                )
                if name is not None
                else self.joined_half[j]
            )
            ways = ([ahead] if after > LEG_STUB_M else []) + (
                [behind] if before > LEG_STUB_M else []
            )
            for b in ways:
                found.add((round(b, 1), round(half, 1)))
        return [list(leg) for leg in sorted(found)]

    def near(self, point: Point, radius: float = 35.0) -> list[float]:
        found = []
        for ahead, behind, _, _, _ in self._near(point, radius):
            found += [ahead, behind]
        return found

    def _near(
        self, point: Point, radius: float, joined: bool = False
    ) -> list[tuple[float, float, int, float, float]]:
        """For each street within ``radius`` of ``point``: the bearing from where it
        passes closest to a point ``LEG_LOOK_M`` along it, each way (a street that
        bends just past a corner takes the way it goes, not its first few metres),
        its row, and its length before and after the closest point.  With
        ``joined``, the streets are the whole named lines rather than single ways."""
        found = []
        tree, geoms = (self.joined_tree, self.joined) if joined else (self.tree, self.geoms)
        for i in tree.query(point, predicate="dwithin", distance=radius):
            line = geoms[i]
            pos = float(line.project(point))
            before, after = pos, float(line.length) - pos
            ring = bool(line.is_ring)
            if ring:  # a closed street goes on both ways past its seam
                before = after = float(line.length)
            at = line.interpolate(pos)

            def toward(d: float, line: Any = line, at: Any = at, ring: bool = ring) -> float | None:
                size = float(line.length)
                q = line.interpolate(d % size if ring else min(max(d, 0.0), size))
                east, north = q.x - at.x, q.y - at.y
                return float(np.degrees(np.arctan2(east, north)) % 360) if east or north else None

            ahead, behind = toward(pos + LEG_LOOK_M), toward(pos - LEG_LOOK_M)
            if ahead is None and behind is None:
                continue
            ahead = ahead if ahead is not None else (behind + 180) % 360  # type: ignore[operator]
            behind = behind if behind is not None else (ahead + 180) % 360
            found.append((ahead, behind, int(i), before, after))
        return found


def snap(nominal: float, candidates: list[float]) -> tuple[float, bool]:
    """The street bearing closest to a compass direction, if one is within 50 degrees."""
    if not candidates:
        return nominal, False
    off = [abs((b - nominal + 180) % 360 - 180) for b in candidates]
    k = int(np.argmin(off))
    return (candidates[k], True) if off[k] <= SNAP_WITHIN_DEG else (nominal, False)


def party_kind(party_type: str, vehicle: str) -> str:
    if party_type == BICYCLE_PARTY or vehicle == "L":
        return codes.BICYCLE
    if party_type == PEDESTRIAN_PARTY or vehicle == "N":
        return codes.PEDESTRIAN
    return codes.VEHICLES.get(vehicle, codes.CAR if party_type == DRIVER_PARTY else codes.OTHER)


def party_entry(party: Any, street_bearings: list[float], child_max_age: int) -> dict[str, Any]:
    kind = party_kind(str(party.PARTY_TYPE), str(party.STWD_VEHICLE_TYPE))
    direction = str(party.DIR_OF_TRAVEL)
    bearing, along_street = None, False
    if direction in codes.BEARINGS:
        turned, along_street = snap(codes.BEARINGS[direction], street_bearings)
        bearing = round(turned, 1)
    move = str(party.MOVE_PRE_ACC)
    move = "O" if str(party.PARTY_TYPE) == PARKED_PARTY else move if move in codes.MOVES else "-"
    age = pd.to_numeric(party.PARTY_AGE, errors="coerce")
    band = ""
    # The same ages as the crash's group (crashes.groups.load), so the pop-up and the filter agree.
    if kind == codes.BICYCLE and pd.notna(age) and 0 <= age <= MAX_AGE:
        band = f"{child_max_age} or under" if age <= child_max_age else "adult"
    return {
        "k": kind,
        "b": bearing,
        "d": direction if direction in codes.BEARINGS else "",
        "m": move,
        "f": str(party.AT_FAULT) == "Y",
        "a": band,
        # False: no mapped street runs that way, so the arrow is the bare compass direction.
        "s": bool(along_street),
    }


def wrong_side_coded(cause: str, parties: list[dict[str, Any]]) -> tuple[bool, bool]:
    """Whether the record codes a cyclist as riding on the wrong side, and whether it
    cites the wrong side with the party unclear.  Marks each such cyclist (``wr``).

    The cause "Wrong side of road" belongs to the party at fault, so it counts
    against a cyclist only when that cyclist is at fault (``AT_FAULT`` is
    exactly "Y"); another cyclist in the crash is not marked.  A cyclist's own
    movement "travelling wrong way" always counts.  A wrong-side cause with no
    such cyclist, because another party is at fault or because no party is
    marked, is the second value: wrong side cited, party unclear.  The
    movement "crossed into opposing lane" is neither.
    """
    cited = "wrong side" in cause.lower()
    coded = False
    for p in parties:
        if p["k"] != codes.BICYCLE:
            continue
        if cited and p["f"]:
            p["wr"] = True
        coded = coded or p["m"] == "Q" or bool(p.get("wr"))
    return coded, cited and not coded


def wrong_side(row: dict[str, Any]) -> str:
    """The one wrong-side category a crash is counted in, or empty.

    ``"coded"``: a cyclist's wrong-side riding is coded; ``"unclear"``: wrong
    side cited, party unclear; ``"suggested"``: neither, and the movements
    suggest it or meet only with the cyclist against traffic.  The page's
    ``side`` gives the same answer.
    """
    if row["wc"]:
        return "coded"
    if row["wu"]:
        return "unclear"
    return "suggested" if row["ws"] or row.get("fit") == "against" else ""


def street_names(streets: gpd.GeoDataFrame) -> dict[str, str]:
    """The map's name for each corridor, such as "Foothill" to "Foothill Boulevard".

    A leading compass word aside.  Where the mapped streets give a corridor two
    names (an avenue and a drive of one name), it takes the one with nearly
    all the mapped length (``NAME_SHARE``), and otherwise keeps its short name.
    """
    if "name" not in streets:
        return {}
    named = streets[streets["name"].notna()]
    full = named["name"].astype(str).str.strip().str.replace(COMPASS_PREFIX, "", regex=True)
    length = named.geometry.length.groupby(full.to_numpy()).sum()
    found: dict[str, dict[str, float]] = {}
    for name, metres in length.items():
        key = corridor(str(name))
        if key:
            found.setdefault(key, {})[str(name)] = float(metres)
    names = {}
    for key, lengths in found.items():
        most = max(sorted(lengths), key=lambda name: lengths[name])
        if len(lengths) == 1 or lengths[most] >= NAME_SHARE * sum(lengths.values()):
            names[key] = most
    return names


def wrong_side_pattern(parties: list[dict[str, Any]]) -> str:
    """Movements that suggest the cyclist rode against traffic or on the sidewalk.

    Only for a crash with two parties, one cyclist and one motor vehicle, with both
    directions recorded.  With anyone else in the crash (a pedestrian, say) the pair's
    movements do not show that the cyclist's own side meets nobody, so nothing is suggested.
    """
    bikes = [p for p in parties if p["k"] == codes.BICYCLE]
    motors = [p for p in parties if p["k"] in MOTOR]
    pair = len(parties) == 2 and len(bikes) == 1 and len(motors) == 1
    if not (pair and bikes[0]["d"] and motors[0]["d"]):
        return ""
    bike, motor = bikes[0], motors[0]
    turn = (codes.BEARINGS[bike["d"]] - codes.BEARINGS[motor["d"]]) % 360
    if bike["m"] == "D" and motor["m"] == "B" and turn == 0:
        return "cyclist turned right across a car going the same way"
    if motor["m"] == "D" and bike["m"] == "B" and turn == 270:
        return "car turning right met a cyclist coming from its right"
    if motor["m"] == "D" and bike["m"] == "B" and turn == 180:
        return "car turning right met an oncoming cyclist"
    if motor["m"] == "E" and bike["m"] == "B" and turn == 0:
        return "car turning left met a cyclist going the same way"
    return ""


# How the other party was travelling, from its heading less the cyclist's.
# The end of a pattern with only the cyclist; the page lists these on their own.
NO_OTHER = "; no other party"
RELATION = {
    0: "same direction",
    90: "from the cyclist's left",
    180: "opposite direction",
    270: "from the cyclist's right",
}


def pattern(parties: list[dict[str, Any]]) -> str:
    """The crash's pattern: the cyclist's direction and movement and the other party's.

    For example "cyclist going straight; car or truck right turn, same
    direction".  It is relative, so the same conflict on two approaches, or
    along a street in both directions, is one pattern; the compass direction
    stays in the crash's own entry (see ``approach``).  Crashes with the same
    pattern are the repeats an engineer looks for.  Empty unless there is one
    cyclist.
    """
    bikes = [p for p in parties if p["k"] == codes.BICYCLE]
    if len(bikes) != 1:
        return ""
    bike = bikes[0]
    who = "cyclist" if bike["d"] else "cyclist, direction not stated,"
    head = f"{who} {codes.MOVES[bike['m']]}"
    others = [p for p in parties if p is not bike]
    if not others:
        return head + NO_OTHER
    if len(others) > 1:
        return f"{head}; {len(others)} other parties"
    other = others[0]
    relation = "direction not stated"
    if bike["d"] and other["d"]:
        turn = int(codes.BEARINGS[other["d"]] - codes.BEARINGS[bike["d"]]) % 360
        relation = RELATION[turn]
    return f"{head}; {other['k']} {codes.MOVES[other['m']]}, {relation}"


def approach(parties: list[dict[str, Any]]) -> str:
    """The one cyclist's compass direction of travel, such as "northbound", or empty."""
    bikes = [p for p in parties if p["k"] == codes.BICYCLE]
    return codes.TRAVEL[bikes[0]["d"]] if len(bikes) == 1 and bikes[0]["d"] else ""


def _code(value: Any) -> str:
    return "" if value is None or value is pd.NA or value != value else str(value).strip()  # noqa: PLR0124


def crash_rows(
    crashes: gpd.GeoDataFrame,
    parties: pd.DataFrame,
    streets: gpd.GeoDataFrame,
    child_max_age: int,
    sites: pd.Series | None = None,
    site_legs: dict[int, list[list[float]]] | None = None,
) -> list[dict[str, Any]]:
    """One entry per cyclist crash, with its parties, for the page.

    ``sites`` gives the intersection each crash was placed at, by
    ``merged_id`` (see ``place``); crashes not in it are mid-block.
    ``site_legs`` gives the streets at each intersection (``place``'s ``w``);
    without it a crash placed at one has no stored ``fit`` (see ``diagram``);
    a crash placed there has its parties turned to those streets, as its
    collision diagram is drawn on them, rather than to streets near the
    reported point.
    """
    crashes = cyclists(crashes)
    tims = parties[parties.source.eq("tims")]
    ccrs = parties[parties.source.eq("ccrs")].dropna(subset="ccrs_collision_id")
    by_case = dict(iter(tims.groupby(tims.CASE_ID.astype("string"))))
    by_ccrs = dict(iter(ccrs.groupby(ccrs.ccrs_collision_id.astype("string"))))
    bearings = Bearings(streets)
    mapped = street_names(streets)
    where = crashes.geometry.to_crs(CRS_WGS84)
    rows = []
    records: list[Any] = list(crashes.itertuples())
    for i, crash in enumerate(records):
        found = by_case.get(str(crash.CASE_ID)) if pd.notna(crash.CASE_ID) else None
        if found is None and pd.notna(crash.ccrs_collision_id):
            found = by_ccrs.get(str(crash.ccrs_collision_id))
        if found is None:
            found = by_case.get(str(crash.merged_id))
        entries = []
        site = sites.get(crash.merged_id) if sites is not None else None
        legs = (site_legs or {}).get(int(site)) if site is not None and pd.notna(site) else None
        if found is not None:
            # A party travelling one way comes from the leg the other way.
            near = [(b + 180) % 360 for b, _ in legs] if legs else bearings.near(crash.geometry)
            entries = [
                party_entry(p, near, child_max_age)
                for p in found.sort_values("PARTY_NUMBER").itertuples()
            ]
        coded, unclear = wrong_side_coded(crash.cause, entries)
        roads = [
            "" if s in ("None", "nan", "<NA>") else s
            for s in (str(crash.PRIMARY_RD), str(crash.SECONDARY_RD))
        ]
        placed = site is not None and pd.notna(site)
        severity = _code(getattr(crash, "COLLISION_SEVERITY", None))
        light = _code(getattr(crash, "LIGHTING", None))
        row = {
            # Not for a crash that cites the wrong side with the party unclear: nothing then
            # puts the cyclist against traffic, and the crash is not counted as suggested too.
            "ws": "" if unclear else wrong_side_pattern(entries),
            "wc": bool(coded),
            "wu": bool(unclear),
            "lat": round(float(where.y.iloc[i]), 6),
            "lon": round(float(where.x.iloc[i]), 6),
            "y": int(crash.year),
            "ym": crash.date.strftime("%b %Y"),
            "h": None if pd.isna(crash.hour) else int(crash.hour),
            # As the map names the street where it has one name for it, else as reported.
            "st": " / ".join(mapped.get(corridor(s), s.title()) for s in roads if s),
            "cause": crash.cause,
            "coll": codes.COLLISIONS.get(str(crash.TYPE_OF_COLLISION), "not stated"),
            "child": crash.group == CHILD,
            "adult": crash.group == ADULT,
            "com": bool(crash.commute),
            "la": bool(crash.in_city),
            # Placed at the corner because the report gave a distance and no direction.
            "ap": getattr(crash, "offset_direction_missing", False) is True,
            "p": entries,
            "sv": severity if severity in codes.SEVERITY else "",
            "lt": light if light in codes.LIGHTING else "",
            "pk": pattern(entries),
            "pd": approach(entries),
            # The streets the crash counts for: both at an intersection, else the one it was on
            # (a report names the nearest cross street for a mid-block crash too).
            "cs": sorted(
                {mapped.get(c, c) for c in map(corridor, roads if placed else roads[:1]) if c}
            ),
            "si": None if site is None or pd.isna(site) else int(site),
        }
        if row["si"] is None and entries:  # a corner's streets are on its site entry (place)
            row["w"] = bearings.legs(crash.geometry)
        # How the movements fit the diagram's streets; the page reads it rather than working it out.
        # Left out for a corner whose streets were not given, so nothing is stored on the wrong widths.
        if row["si"] is None or legs is not None:
            row["fit"] = diagram.fit(
                entries, legs or row.get("w") or [], bool(row["ws"]), not (coded or unclear)
            )
        rows.append(row)
    return rows


def place(
    crashes: gpd.GeoDataFrame, streets: gpd.GeoDataFrame, area: BaseGeometry
) -> tuple[pd.Series, list[dict[str, Any]]]:
    """The intersection each cyclist crash happened at, and those intersections.

    Uses the same intersections and rules as the hold-out check
    (``junctions.build_junctions`` and ``junctions.assign_crashes``).  Returns
    the intersection id by ``merged_id`` (mid-block crashes are left out), and
    an entry for each intersection with a crash: id, position, street names and
    the streets meeting there (``Bearings.legs``).
    """
    sites, names = junctions.build_junctions(streets, area)
    if sites.empty:
        return pd.Series(dtype="int64"), []
    hits = junctions.assign_crashes(cyclists(crashes), sites.geometry, names)
    used = sites.loc[sorted(set(hits.site))]
    where = used.geometry.to_crs(CRS_WGS84)
    bearings = Bearings(streets)
    entries = [
        {
            "i": int(i),
            "lat": round(float(lat), 6),
            "lon": round(float(lon), 6),
            "n": name,
            "w": bearings.legs(cast(Point, point)),
        }
        for i, lat, lon, name, point in zip(
            used.index, where.y, where.x, used.name, used.geometry, strict=True
        )
    ]
    return hits.site.astype("int64"), entries


def basemap(
    streets: gpd.GeoDataFrame, bounds: tuple[float, float, float, float]
) -> tuple[dict[str, list[Any]], list[list[Any]]]:
    """Street lines by class and street-name labels, in latitude and longitude."""
    west, south, east, north = bounds
    streets = streets[streets.intersects(box(west - 400, south - 400, east + 400, north + 400))]
    to_degrees = Transformer.from_crs(streets.crs, CRS_WGS84, always_xy=True)
    highway = streets.highway.astype(str)
    kind = pd.Series("P", index=streets.index)
    for key, pattern in reversed(list(STREET_CLASSES.items())):
        kind[highway.str.contains(pattern)] = key
    lines: dict[str, list[Any]] = {key: [] for key in "MTLSP"}
    labels: dict[tuple[str, int, int], tuple[float, list[Any]]] = {}
    for line, name, key in zip(streets.geometry.simplify(1.5), streets.name, kind, strict=True):
        xy = np.asarray(line.coords)
        lon, lat = to_degrees.transform(xy[:, 0], xy[:, 1])
        lines[key].append(
            [[round(float(a), 5), round(float(b), 5)] for a, b in zip(lat, lon, strict=True)]
        )
        if not (isinstance(name, str) and name and key != "P" and line.length > 40):
            continue
        middle = line.interpolate(0.5, normalized=True)
        cell = (name, int(middle.x // 300), int(middle.y // 300))
        if cell in labels and line.length <= labels[cell][0]:
            continue
        a, b = line.interpolate(0.4, normalized=True), line.interpolate(0.6, normalized=True)
        angle = (np.degrees(np.arctan2(b.x - a.x, b.y - a.y))) % 180 - 90
        mid_lon, mid_lat = to_degrees.transform(middle.x, middle.y)
        labels[cell] = (
            line.length,
            [name, round(mid_lat, 5), round(mid_lon, 5), round(float(angle), 1), key],
        )
    return lines, [entry for _, entry in labels.values()]


def page(
    rows: list[dict[str, Any]],
    lines: dict[str, list[Any]],
    labels: list[list[Any]],
    config: Config,
    centre: tuple[float, float],
    sites: list[dict[str, Any]] | None = None,
    offline: bool = False,
) -> str:
    """Fill the page template.

    ``offline`` builds the map library into the page instead of loading it
    from the internet.  Only the demo city has a banner, saying its crashes
    are made up.
    """

    def compact(value: Any) -> str:
        # Inside a <script> block: text from a crash report or a street name
        # must not be able to close the block or start a comment.
        text = json.dumps(value, separators=(",", ":"))
        for mark, safe in SCRIPT_SAFE.items():
            text = text.replace(mark, safe)
        return text

    template = resources.files("bike_safety_ca.report").joinpath("movement_map.html").read_text()
    warn, credit = SYNTHETIC_NOTICE if config.synthetic else ("", REAL_CREDIT)
    fills = {
        "/*WARN*/": f'<div class="warn">{html.escape(warn)}</div>' if warn else "",
        "/*CREDIT*/": html.escape(credit),
        "/*SITES*/": compact(sites or []),
        "/*SEVERITY*/": compact(codes.SEVERITY),
        "/*LIGHT*/": compact(codes.LIGHTING),
        "/*DARK*/": compact(list(codes.DARK)),
        "/*STREETS*/": compact(lines),
        "/*LABELS*/": compact(labels),
        "/*DATA*/": compact(rows),
        "/*MOVE*/": compact(codes.MOVES),
        "/*CENTRE*/": compact([round(centre[0], 4), round(centre[1], 4)]),
        "/*CITY*/": html.escape(config.city),
        "/*CHILD*/": html.escape(f"{config.child_max_age} or under"),
    }
    # One pass, so a mark inside a street name or record is not filled in turn.
    filled = re.sub("|".join(map(re.escape, fills)), lambda m: fills[m.group(0)], template)
    return inline_leaflet(filled) if offline else filled


LEAFLET_CSS = '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">'
LEAFLET_JS = (
    '<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>'
)


def inline_leaflet(html_text: str) -> str:
    """Replace the page's links to Leaflet with the copy in ``report/vendor``."""
    vendor = resources.files("bike_safety_ca.report").joinpath("vendor")
    css = vendor.joinpath("leaflet.css").read_text()
    js = vendor.joinpath("leaflet.js").read_text()
    for tag in (LEAFLET_CSS, LEAFLET_JS):
        if html_text.count(tag) != 1:
            raise ValueError(f"the map template does not link Leaflet as expected: {tag}")
    if "</style" in css.lower() or "</script" in js.lower():
        raise ValueError("the vendored Leaflet would close its own block")
    html_text = html_text.replace(LEAFLET_CSS, f"<style>{css}</style>", 1)
    return html_text.replace(LEAFLET_JS, f"<script>{js}</script>", 1)


def build(
    crashes: gpd.GeoDataFrame,
    parties: pd.DataFrame,
    streets: gpd.GeoDataFrame,
    config: Config,
    out: Path,
    centre_on: gpd.GeoSeries | None = None,
    area: BaseGeometry | None = None,
    offline: bool = False,
) -> Path:
    """Write the map of ``crashes`` (as loaded by ``report.crashes.load``) to ``out``.

    With ``area``, crashes are placed at the intersections in it and drawn as
    collision diagrams when zoomed in; ``streets`` then needs the columns
    ``junctions.build_junctions`` reads.  Without it every crash is drawn
    where it was recorded.
    """
    bike = cyclists(crashes)
    at: pd.Series | None = None
    sites: list[dict[str, Any]] = []
    if area is not None and len(bike):
        at, sites = place(bike, streets, area)
    legs = {s["i"]: s["w"] for s in sites}
    rows = crash_rows(bike, parties, streets, config.child_max_age, at, legs) if len(bike) else []
    # With no cyclist crash to show, the map is the streets alone.
    extent = bike if len(bike) else streets
    west, south, east, north = (float(v) for v in extent.total_bounds)
    lines, labels = basemap(streets, (west, south, east, north))
    middle = (centre_on if centre_on is not None else extent.geometry).to_crs(CRS_WGS84).union_all()
    html = page(
        rows,
        lines,
        labels,
        config,
        (middle.centroid.y, middle.centroid.x),
        sites,
        offline=offline,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return out
