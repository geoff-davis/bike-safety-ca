"""Streets cut from a regional OpenStreetMap extract, in place of an Overpass download.

The public Overpass servers refuse a large box (San Diego's, for one) and ask
heavy users to go elsewhere.  A regional extract, such as Geofabrik's
``california-latest.osm.pbf``, holds the same map: this reads it and writes the
three files an Overpass download would (``overpass_streets.json``,
``overpass_query.txt`` and the metadata note), in the same shape, so the
network step's build reads them as it reads a download.

A way is taken when its line touches the padded box (a node inside it, or a
segment crossing it), as Overpass does.  The extract must cover the box: if
its header says it does not, nothing is written.  Ways with a node the extract
does not hold, at its edge, are left out and counted.

Needs the optional ``osmium`` package: ``uv sync --extra extract``.
OpenStreetMap data is (c) OpenStreetMap contributors under the ODbL 1.0.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from shapely import LineString, prepare
from shapely import box as rectangle

from bike_safety_ca.download import osm

log = logging.getLogger(__name__)


def read(pbf: Path, box: osm.Bounds) -> tuple[dict[str, Any], int]:
    """The streets in ``box`` (west, south, east, north) as an Overpass answer, and ways dropped.

    The answer matches ``way["highway"](box); out meta; >; out skel;``: the
    ways with their tags and metadata, then their nodes with coordinates only.
    """
    try:
        import osmium
    except ImportError as error:
        raise RuntimeError(
            "reading an extract needs the osmium package: uv sync --extra extract"
        ) from error

    reader = osmium.io.Reader(str(pbf), osmium.osm.osm_entity_bits.NOTHING)
    header = reader.header()
    reader.close()
    west, south, east, north = box
    covered = header.box()
    if covered.valid():
        low, high = covered.bottom_left, covered.top_right
        if not (low.lon <= west and low.lat <= south and east <= high.lon and north <= high.lat):
            raise ValueError(f"the box {box} reaches outside the extract {pbf} ({covered})")
    else:
        log.warning("%s gives no box in its header; cannot check that it covers %s", pbf, box)
    area = rectangle(*box)
    prepare(area)
    ways: list[dict[str, Any]] = []
    nodes: dict[int, dict[str, Any]] = {}
    dropped = 0
    processor = (
        osmium.FileProcessor(str(pbf))
        .with_locations()
        .with_filter(osmium.filter.KeyFilter("highway"))
    )
    for item in processor:
        if not isinstance(item, osmium.osm.Way):
            continue
        try:
            points = [(node.ref, node.lon, node.lat) for node in item.nodes]
        except osmium.InvalidLocationError:
            dropped += 1
            continue
        if len(points) < 2:
            continue
        xs, ys = [p[1] for p in points], [p[2] for p in points]
        if max(xs) < west or min(xs) > east or max(ys) < south or min(ys) > north:
            continue
        if not area.intersects(LineString([(x, y) for _, x, y in points])):
            continue
        ways.append(
            {
                "type": "way",
                "id": item.id,
                "timestamp": item.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "version": item.version,
                "changeset": item.changeset,
                "user": item.user,
                "uid": item.uid,
                "nodes": [p[0] for p in points],
                "tags": {tag.k: tag.v for tag in item.tags},
            }
        )
        for ref, x, y in points:
            nodes[ref] = {"type": "node", "id": ref, "lat": y, "lon": x}
    base = header.get("osmosis_replication_timestamp") or header.get("timestamp") or ""
    answer = {
        "version": 0.6,
        "generator": f"cut from {pbf.name} with pyosmium",
        "osm3s": {
            "timestamp_osm_base": base,
            "copyright": "The data included in this document is from www.openstreetmap.org. "
            "The data is made available under ODbL.",
        },
        "elements": ways + list(nodes.values()),
    }
    return answer, dropped


def cut(pbf: Path, bounds: osm.Bounds, out: Path, overwrite: bool = False) -> Path:
    """Write the streets in ``bounds`` (degrees, padded here) from ``pbf`` into ``out``.

    Reuses or refuses files already in ``out`` exactly as ``osm.download`` does.
    """
    box = osm.padded(bounds)
    if not overwrite and osm.reuse(out, box, None):
        return out / "overpass_streets.json"
    data, dropped = read(pbf, box)
    osm.check(data)
    if dropped:
        log.warning("left out %d highway ways with a node missing from %s", dropped, pbf)
    west, south, east, north = box
    query = (
        f"[cut locally from {pbf.name}]\n"
        f'way["highway"]({south},{west},{north},{east});\nout meta;\n>;\nout skel;\n'
    )
    source = f"{pbf.name} (regional extract), ways touching the box"
    return osm.save(out, query, data, box, None, source=source)
