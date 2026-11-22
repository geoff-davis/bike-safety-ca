"""Intersections for the crash model: geometry, road classes, control and crashes.

An intersection is a cluster of OSM nodes where three or more street arms meet.
Each gets the classes of its two largest roads, a lane count, a control type
(signal, all-way stop, minor-road stop, none mapped) and the crashes assigned
to it.  Everything here works on in-memory frames in a projected CRS (metres),
so it can be tested on small synthetic networks.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial.distance import pdist
from shapely.geometry.base import BaseGeometry

from bike_safety_ca.crashes.merge import _road_key

_COMPASS = {"N", "S", "E", "W", "NORTH", "SOUTH", "EAST", "WEST"}
# Street types, each under one spelling.  The first three rows are the types
# the shared normalizer strips, the last the police abbreviations ``_road_key``
# strips besides.
_STREET_TYPES = {
    **dict.fromkeys(("AVENUE", "AVE", "AV"), "AVENUE"),
    **dict.fromkeys(("STREET", "ST"), "STREET"),
    **dict.fromkeys(("ROAD", "RD"), "ROAD"),
    **dict.fromkeys(("DRIVE", "DR"), "DRIVE"),
    **dict.fromkeys(("COURT", "CT"), "COURT"),
    **dict.fromkeys(("WAY", "WY"), "WAY"),
    **dict.fromkeys(("LANE", "LN"), "LANE"),
    **dict.fromkeys(("TERRACE", "TER"), "TERRACE"),
    **dict.fromkeys(("PLACE", "PL"), "PLACE"),
    **dict.fromkeys(("CIRCLE", "CIR"), "CIRCLE"),
    **dict.fromkeys(("PARKWAY", "PKWY"), "PARKWAY"),
    **dict.fromkeys(("BOULEVARD", "BLVD", "BL"), "BOULEVARD"),
    **dict.fromkeys(("EXPRESSWAY", "EXPWY", "EXPY", "EXPR", "EXP", "EX"), "EXPRESSWAY"),
}


def _words(value: object) -> list[str]:
    """The words of a road name, without brackets, punctuation or a trailing direction."""
    text = re.sub(r"\([^)]*\)", " ", str(value).upper())
    # "S/B" and "southbound" are directions of travel; "West B Street" is B Street.
    text = re.sub(r"\b(NORTH|SOUTH|EAST|WEST|N|S|E|W)(/B|[ /-]*BOUND)\b", " ", text)
    words = re.sub(r"[^A-Z0-9]+", " ", text).split()
    while len(words) > 2 and words[-1] in _COMPASS:  # "Main St N"
        words.pop()
    return words


def road_key(value: object) -> str:
    """Street name for matching, without directions or street type; a missing name is no name.

    Police abbreviate, and often leave out the type, so "N Main St", "Main
    Street" and "MAIN" are one name.  This is the key the crash merge uses
    (``merge._road_key``), so a street named by a direction or type word
    keeps that word: "South Street" is "SOUTH", "Court Street" is "COURT".
    """
    if value is None or value is pd.NA or value != value:  # noqa: PLR0124
        return ""
    return _road_key(value)


def street_key(value: object) -> str:
    """Street for grouping: its ``road_key`` and its street type, written out.

    "Park Avenue", "Park Place" and "Park Way" are three streets here, and
    "1st Street" is not "1st Avenue"; "N Park Av" and "Park Avenue" are still
    one.  A name without a type is its own street ("Park").  The model's
    street averages and the corridor table group mapped streets by this key.  ``road_key`` of a street key is the street's
    ``road_key``, which is how crash reports are matched to it.
    """
    name = road_key(value)
    words = _words(value) if name else []
    kind = None
    if len(words) > 1:  # the type comes last, or first as in "Avenue 12"
        kind = _STREET_TYPES.get(words[-1])
        if kind is None and words[0] != "ST":  # a leading ST is Saint
            kind = _STREET_TYPES.get(words[0])
    return f"{name} {kind}" if kind else name


def _joined(keys: Iterable[str]) -> dict[str, str]:
    """Each street key's street among ``keys``, a way mapped without its type joined to its street.

    "MAIN" is "MAIN STREET" when that is the only typed street of the name
    among the keys.  With two (Park Avenue, Park Place) it cannot be told
    which it belongs to and stays on its own; typed streets never join.
    """
    keys = set(keys)
    out = {key: key for key in keys}
    for key in keys:
        typed = [k for k in keys if k != key and road_key(k) == key]
        if len(typed) == 1:
            out[key] = typed[0]
    return out


HIGHWAY_RANK = {
    "trunk": 5,
    "primary": 5,
    "trunk_link": 4,
    "primary_link": 4,
    "secondary": 4,
    "secondary_link": 3,
    "tertiary": 3,
    "tertiary_link": 3,
    "residential": 1,
    "unclassified": 1,
    "living_street": 1,
}
ROAD_CLASS = {5: "Major arterial", 4: "Arterial", 3: "Collector", 1: "Local"}

SIGNAL = "Signal"
ALL_WAY = "All-way stop"
MINOR_STOP = "Minor-road stop"
NO_CONTROL = "None mapped"


PAIR_GAP_M = 40.0  # the two halves of a divided road are closer than this
LANE_WINDOW_M = 150.0  # a road's lane count is taken over this distance from the intersection
WIDE = "4+"
NOT_WIDE = "≤3 or untagged"


def road_lanes(ways: gpd.GeoDataFrame) -> pd.Series:
    """Lanes of the whole road each way belongs to, both directions together.

    OSM maps a road with a median as two one-way ways, each tagged with its own
    lanes, so the tag alone gives half the road.  A one-way way gets the lanes of
    the nearest same-named one-way way running the other direction within
    ``PAIR_GAP_M`` added to its own.  Ways without such a partner (two-way roads,
    true one-way streets) keep their tag; untagged ways stay missing.
    """
    lanes = pd.to_numeric(ways.lanes.astype("string").str.extract(r"(\d+)")[0], errors="coerce")
    lanes = lanes.astype(float)
    if "oneway" not in ways:
        return lanes
    half = ways[
        ways.oneway.astype("string").eq("yes")
        & ways.name.notna()
        & ~ways.highway.str.endswith("_link")
        & ways.length.gt(0)
    ]
    if half.empty:
        return lanes
    road = half.name.map(street_key)  # Park Avenue is not the other half of Park Place
    total = lanes.copy()

    def heading(line: BaseGeometry, at: float) -> np.ndarray:
        a, b = line.interpolate(max(at - 10, 0)), line.interpolate(min(at + 10, line.length))
        return np.array([b.x - a.x, b.y - a.y])

    tree = half.sindex
    for i, line in zip(half.index, half.geometry):
        middle = line.interpolate(line.length / 2)
        mine = heading(line, line.length / 2)
        best = None
        for j in half.index[tree.query(middle.buffer(PAIR_GAP_M))]:
            other = half.geometry.loc[j]
            gap = other.distance(middle)
            if j == i or gap > PAIR_GAP_M:
                continue
            if road.loc[j] != road.loc[i]:
                pair = _joined({road.loc[i], road.loc[j]})
                if pair[road.loc[i]] != pair[road.loc[j]]:
                    continue
            theirs = heading(other, other.project(middle))
            norm = np.linalg.norm(mine) * np.linalg.norm(theirs)
            if norm and mine @ theirs / norm < -0.5 and (best is None or gap < best[0]):
                best = (gap, j)
        if best is not None:
            partner = lanes.loc[best[1]]
            total.loc[i] = lanes.loc[i] + (lanes.loc[i] if np.isnan(partner) else partner)
    return total


def lanes_near(
    ways: gpd.GeoDataFrame, lanes: pd.Series, centres: gpd.GeoSeries, roads: pd.Series
) -> pd.Series:
    """Typical lane count of the widest named road at each intersection.

    OSM splits a road into short ways, and the few metres widened for turn pockets
    carry a higher ``lanes`` tag than the road on either side.  So each road gets
    the lane count that covers half or more of its length within
    ``LANE_WINDOW_M`` of the intersection (a length-weighted median of its tagged
    ways), and the intersection gets the largest of those.  A road whose tagged
    ways cover less than half of that length counts as untagged.

    ``lanes`` is aligned with ``ways``; ``roads`` holds, per intersection, the set
    of street keys that meet there.
    """
    keys = ways.name.map(lambda n: street_key(n) if isinstance(n, str) else "")
    by_road = {
        k: (gpd.GeoSeries(ways.geometry.loc[idx]), lanes.loc[idx].to_numpy(float))
        for k, idx in keys.groupby(keys).groups.items()
        if k
    }
    out = {}
    for i, centre in centres.items():
        window = centre.buffer(LANE_WINDOW_M)
        best = np.nan
        for k in roads.get(i, ()):
            if k not in by_road:
                continue
            geoms, values = by_road[k]
            length = geoms.intersection(window).length.to_numpy()
            tagged = ~np.isnan(values) & (length > 0)
            if not tagged.any() or length[tagged].sum() < 0.5 * length.sum():
                continue
            order = np.argsort(values[tagged])
            v, w = values[tagged][order], length[tagged][order]
            typical = v[np.searchsorted(np.cumsum(w), 0.5 * w.sum())]
            best = np.nanmax([best, typical])
        out[i] = best
    return pd.Series(out, dtype=float)


def _widest(xy: np.ndarray) -> float:
    """Greatest distance between any two of the points (0 for one point)."""
    return float(pdist(xy).max()) if len(xy) > 1 else 0.0


def _split_chains(pts: gpd.GeoDataFrame, limit: float) -> pd.Series:
    """New cluster numbers in which no two nodes are more than ``limit`` apart."""
    from scipy.cluster.hierarchy import fcluster, linkage

    out = pd.Series(0, index=pts.index)
    start = 0
    for _, group in pts.groupby("iid"):
        if len(group) < 3:  # two touching circles are within 25 m already
            xy = np.c_[group.geometry.x, group.geometry.y]
            far = len(group) == 2 and float(np.hypot(*(xy[0] - xy[1]))) > limit
            labels = np.arange(1, len(group) + 1) if far else np.ones(len(group), dtype=int)
        else:
            xy = np.c_[group.geometry.x, group.geometry.y]
            labels = fcluster(linkage(xy, "complete"), limit, "distance")
        out.loc[group.index] = start + labels
        start += int(labels.max())
    return out


def build_junctions(
    ways: gpd.GeoDataFrame, area: BaseGeometry, max_cluster_m: float | None = None
) -> tuple[gpd.GeoDataFrame, pd.Series]:
    """Find intersections on ``ways`` inside ``area`` and describe their roads.

    ``ways`` needs ``osm_id``, ``highway``, ``name``, ``lanes``, ``node_ids``
    (a JSON list matching the geometry's vertices) and line geometry; with
    ``oneway`` too, the lanes of a divided road's two halves are added together
    (see ``road_lanes``).  Nodes
    within 25 m are one intersection, and the two nodes where a divided road
    meets a cross street are merged when they share street names and lie within
    60 m.

    Nodes within 25 m of each other are one intersection, and so are clusters
    with the same street names within 60 m (the two halves of a divided road).
    Touching clusters chain, so a few intersections come out wide: ``span_m``
    is the greatest distance between two of the joined nodes and ``nodes``
    their number, for checking.  ``max_cluster_m`` splits chains so that no
    first-stage cluster is wider than that; clusters with the same street
    names within 60 m are still joined afterwards.  It is off by default.

    Returns the intersections (point geometry at the cluster centre, with
    ``major``, ``minor``, ``lanes`` and ``name``) and, per intersection, the
    set of street keys (``street_key``: the name with its street type, so
    "Park Avenue" and "Park Place" stay two streets) of the streets that meet
    there.  ``lanes`` is ``WIDE`` when
    the widest road is typically four lanes or more near the intersection (see
    ``lanes_near``) and ``NOT_WIDE`` otherwise; OSM does not separate two lanes
    from two lanes plus a centre turn lane reliably enough for a third group.
    """
    crs = ways.crs
    ways = ways[ways.highway.isin(HIGHWAY_RANK) & ways.intersects(area)]
    lanes = road_lanes(ways)
    rows = []
    for way, rank, n_lanes, name, ids, geom, link in zip(
        ways.osm_id,
        ways.highway.map(HIGHWAY_RANK),
        lanes.astype(float),
        ways.name,
        ways.node_ids,
        ways.geometry,
        ways.highway.str.endswith("_link"),
    ):
        ids, xy = json.loads(ids), list(geom.coords)
        if len(ids) != len(xy):
            continue
        for i, (node, (x, y)) in enumerate(zip(ids, xy)):
            arms = 1 if i in (0, len(ids) - 1) else 2
            rows.append((node, x, y, arms, way, rank, n_lanes, name, link))
    nodes = pd.DataFrame(
        rows, columns=["node", "x", "y", "arms", "way", "rank", "lanes", "name", "link"]
    )
    nodes = nodes[nodes.node.isin(nodes.groupby("node").arms.sum().loc[lambda s: s.ge(3)].index)]
    pts = nodes.drop_duplicates("node")
    pts = gpd.GeoDataFrame(pts[["node"]], geometry=gpd.points_from_xy(pts.x, pts.y), crs=crs)
    pts = pts[pts.within(area)]
    merged = pts.buffer(12.5).union_all()
    blobs = gpd.GeoDataFrame(geometry=list(getattr(merged, "geoms", [merged])), crs=crs)
    pts = gpd.sjoin(pts, blobs, predicate="within").rename(columns={"index_right": "iid"})
    if max_cluster_m is not None:
        # Circles that touch chain: a row of nodes 20 m apart would become one
        # intersection.  Split each chain so that no two nodes in a cluster are
        # farther apart than the limit.
        pts["iid"] = _split_chains(pts, max_cluster_m)
        blobs = gpd.GeoDataFrame(geometry=pts.dissolve("iid").geometry.buffer(12.5), crs=crs)
        blobs.index.name = None
    nodes = nodes.merge(pts[["node", "iid"]], on="node")

    # Divided roads meet a cross street at two nodes; merge blobs with the same street
    # names whose centres are within 60 m.
    key = pd.Series(
        {i: tuple(sorted({str(n) for n in s.dropna()})) for i, s in nodes.groupby("iid").name}
    )
    centre = gpd.GeoSeries(blobs.geometry.reindex(key.index)).centroid
    merge: dict[int, int] = {}
    for names, ids in key.groupby(key).groups.items():
        if not names or len(ids) < 2:
            continue
        union = gpd.GeoSeries(centre[centre.index.isin(ids)]).buffer(30).union_all()
        for part in getattr(union, "geoms", [union]):
            members = [i for i in ids if part.contains(centre.loc[i])]
            merge.update({i: min(members) for i in members})
    nodes["iid"] = nodes.iid.map(lambda i: merge.get(i, i))
    blobs = blobs.assign(iid=blobs.index.map(lambda i: merge.get(i, i))).dissolve("iid")

    def describe(g: pd.DataFrame) -> dict[str, object]:
        # Rank roads, not OSM ways: a street split into several ways at the junction
        # (divided carriageways, a name change, a mid-block split) counts once.
        road = g.name.map(lambda n: street_key(n) if isinstance(n, str) else "")
        # .get, not .map(dict): with no named way the dict is empty and map gives floats.
        joined = _joined(set(road) - {""})
        road = road.map(lambda k: joined.get(k, ""))
        # Unnamed ramp ways (trunk_link and the like) are one road: the on and off halves
        # of an expressway ramp would otherwise count as two arterials crossing.
        road = road.where(road.ne("") | ~g.link, "ramps")
        road = road.where(road.ne(""), "way " + g.way.astype(str))
        ranks = sorted(g.groupby(road)["rank"].max(), reverse=True) + [1]
        names = sorted({str(n) for n in g.name.dropna()})
        return {
            "major": ranks[0],
            "minor": ranks[1],
            # Unnamed ways (ramps) have no road to average over; named roads are
            # replaced below by their typical lane count near the intersection.
            "lanes": g.lanes[g.name.isna()].max(),
            "name": " / ".join(names[:3]),
        }

    x = pd.DataFrame.from_dict(
        {k: describe(g) for k, g in nodes.groupby("iid")},
        orient="index",
        columns=["major", "minor", "lanes", "name"],
    )
    x["major"] = x.major.astype(int).map(ROAD_CLASS)
    x["minor"] = x.minor.astype(int).map(ROAD_CLASS)
    junctions = gpd.GeoDataFrame(x, geometry=blobs.loc[x.index].centroid, crs=crs)
    # How far apart the joined nodes are: a wide one may be several corners in one.
    joined = nodes.drop_duplicates("node")
    span = {i: _widest(g[["x", "y"]].to_numpy()) for i, g in joined.groupby("iid")}
    junctions["span_m"] = pd.Series(span).reindex(x.index)
    junctions["nodes"] = joined.groupby("iid").size().reindex(x.index)
    by_junction = {i: {street_key(n) for n in s.dropna()} for i, s in nodes.groupby("iid").name}
    streets = pd.Series({i: by_junction.get(i, set()) for i in junctions.index}, dtype=object)
    typical = lanes_near(ways, lanes, junctions.geometry, streets)
    widest = pd.concat([junctions.lanes.astype(float), typical], axis=1).max(axis=1)
    junctions["lanes"] = np.where(widest.ge(4), WIDE, NOT_WIDE)
    return junctions, streets


def osm_control(points: gpd.GeoSeries, tags: gpd.GeoDataFrame) -> pd.Series:
    """Control type of each point from tagged OSM nodes (``highway``, ``stop``).

    A signal within 35 m wins.  Otherwise a stop or yield sign within 30 m makes
    a stop-controlled intersection.  OSM tags about half its stop signs
    ``stop=all`` or ``stop=minor``: an all-way tag nearby makes an all-way stop,
    and where no minor tag is near, three or more mapped stop signs do too.
    Yield signs go with minor-road stops.
    """

    def within(nodes: gpd.GeoDataFrame, metres: float = 30) -> pd.Series:
        if nodes.empty:
            return pd.Series(False, index=points.index)
        return points.distance(nodes.union_all()).le(metres)

    stop_nodes = tags[tags.highway.eq("stop")]
    n_stops = (
        gpd.sjoin(
            gpd.GeoDataFrame(geometry=points.buffer(30), crs=points.crs), stop_nodes[["geometry"]]
        )
        .groupby(level=0)
        .size()
        .reindex(points.index, fill_value=0)
    )
    all_way = within(stop_nodes[stop_nodes["stop"].eq("all")]) | (
        ~within(stop_nodes[stop_nodes["stop"].eq("minor")]) & n_stops.ge(3)
    )
    control = np.select(
        [
            within(tags[tags.highway.eq("traffic_signals")], 35),
            all_way,
            within(tags[tags.highway.isin(["stop", "give_way"])]),
        ],
        [SIGNAL, ALL_WAY, MINOR_STOP],
        NO_CONTROL,
    )
    return pd.Series(control, index=points.index)


def nearest_school(points: gpd.GeoSeries, schools: gpd.GeoDataFrame) -> pd.DataFrame:
    """Nearest school, its straight-line distance and the model's distance band."""
    near = gpd.sjoin_nearest(
        gpd.GeoDataFrame(geometry=points, crs=points.crs),
        schools[["school", "geometry"]],
        distance_col="d",
    )
    first = near.groupby(level=0).first()
    band = pd.cut(first.d, [-1, 400, 800, 1e9], labels=["<400 m", "400–800 m", ">800 m"])
    return pd.DataFrame(
        {"school": first.school, "school_m": first.d, "school_band": band.astype(str)}
    )


def assign_crashes(
    crashes: gpd.GeoDataFrame,
    points: gpd.GeoSeries,
    streets: pd.Series,
    check_names: bool = True,
) -> pd.DataFrame:
    """Give each crash the intersection it happened at, in a ``site`` column.

    A crash counts at an intersection if it lies within 35 m of it, or if police
    coded it as at the intersection (``INTERSECTION`` = Y, or ``DISTANCE`` within
    50 ft) of two streets that meet there, within 100 m: police coordinates can
    sit some way off the mapped junction.  A name match takes precedence over
    the nearest junction.  Nearness does not count for a report that names two
    streets of which neither meets at that intersection (``check_names``): it
    describes somewhere else, such as a freeway above a surface street, and
    goes to the nearest intersection within 35 m that it could describe.  A
    crash placed at a corner for want of a direction
    (``offset_direction_missing``) counts, by nearness or by name, only if its
    reported distance is within 35 m.  Crashes at no intersection are dropped; the
    result is indexed by ``merged_id``.

    ``streets`` holds the street keys at each intersection.  Reports are
    matched to them by name alone (``road_key``), since police abbreviate and
    drop street types.
    """
    # Tolerant on purpose, and unchanged by the street keys keeping the type:
    # a report of "PARK / OAK", or of "PARK AV / OAK", fits a corner of Park
    # Place and Oak as well as one of Park Avenue and Oak.  Which of two such
    # corners it gets is decided by distance, as before.
    streets = streets.map(lambda keys: {road_key(k) for k in keys})
    # A crash put at a corner only because its report gave a distance from it
    # and no direction is really that far along one of the streets.  Beyond
    # 35 m it did not happen at this intersection, so nearness does not count.
    placed_at_corner = pd.Series(False, index=crashes.index)
    if {"offset_direction_missing", "reported_offset_m"} <= set(crashes.columns):
        placed_at_corner = crashes.offset_direction_missing.fillna(False).astype(bool) & (
            pd.to_numeric(crashes.reported_offset_m, errors="coerce") > 35
        )
    # Every intersection within 35 m, nearest first.
    near = gpd.sjoin(
        crashes.loc[~placed_at_corner, ["merged_id", "PRIMARY_RD", "SECONDARY_RD", "geometry"]],
        gpd.GeoDataFrame(geometry=points.buffer(35), crs=points.crs),
        predicate="within",
    )
    spot = gpd.GeoSeries(list(points.reindex(near.index_right)), index=near.index, crs=points.crs)
    near = near.assign(d=near.distance(spot)).sort_values(["d", "index_right"], kind="stable")
    if check_names:
        # A report that names two streets, neither of them at an intersection,
        # describes somewhere else: a freeway crash above a surface street, or
        # a wrong coordinate.  It is not counted there; the next nearest
        # intersection within 35 m is tried instead.
        elsewhere = []
        for first, second, site in zip(near.PRIMARY_RD, near.SECONDARY_RD, near.index_right):
            reported = {road_key(first), road_key(second)} - {""}
            here = streets.get(site, set())
            elsewhere.append(len(reported) == 2 and bool(here) and not (reported & here))
        near = near.loc[~np.array(elsewhere, dtype=bool)]
    near = near.drop_duplicates("merged_id")
    # The same holds for the name match: a point that far from where the
    # crash happened is not "at the intersection", whatever the flag says.
    at = crashes[
        ~placed_at_corner
        & (
            crashes.INTERSECTION.astype("string").str.strip().eq("Y")
            | pd.to_numeric(crashes.DISTANCE, errors="coerce").between(0, 50)
        )
    ]
    cand = gpd.sjoin(
        at[["merged_id", "PRIMARY_RD", "SECONDARY_RD", "geometry"]],
        gpd.GeoDataFrame(geometry=points.buffer(100), crs=points.crs),
        predicate="within",
    )
    coded = ({road_key(p), road_key(q)} - {""} for p, q in zip(cand.PRIMARY_RD, cand.SECONDARY_RD))
    # Both coded streets must be named and different: one name alone would match
    # every intersection along that street within 100 m.
    matched = [len(k) == 2 and k <= streets.get(i, set()) for k, i in zip(coded, cand.index_right)]
    cand = cand.loc[np.array(matched, dtype=bool)]  # an array: an empty list would pick columns
    there = gpd.GeoSeries(list(points.reindex(cand.index_right)), index=cand.index, crs=points.crs)
    cand = cand.assign(d=cand.distance(there)).sort_values("d")
    named = cand.drop_duplicates("merged_id").set_index("merged_id").index_right
    site = named.combine_first(near.set_index("merged_id").index_right).astype(int)
    return crashes.set_index("merged_id").loc[site.index].assign(site=site)


def count_at(hits: pd.DataFrame, index: Iterable[object]) -> pd.Series:
    """Number of assigned crashes per intersection, zero where there are none."""
    return hits.groupby("site").size().reindex(pd.Index(index)).fillna(0).astype(int)
