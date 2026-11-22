"""Turn raw Overpass JSON into the street table the intersection code reads."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import LineString

from bike_safety_ca.io import CRS_WGS84, crs_tag, read_shapes

COLUMNS = ["osm_id", "highway", "name", "lanes", "oneway", "node_ids", "geometry"]
STEM = "streets"


def streets(raw: dict[str, Any]) -> gpd.GeoDataFrame:
    """One row per way tagged ``highway``, in longitude and latitude.

    ``node_ids`` is a JSON list of the way's node ids, one per vertex of the
    line; the intersection code uses shared ids to tell a real junction from a
    bridge.  Ways with a node missing from the download are dropped, since
    their ids and vertices would not line up.
    """
    nodes = {e["id"]: (e["lon"], e["lat"]) for e in raw["elements"] if e["type"] == "node"}
    seen: set[int] = set()
    rows, lines = [], []
    for element in raw["elements"]:
        tags = element.get("tags", {})
        if element["type"] != "way" or "highway" not in tags or element["id"] in seen:
            continue
        seen.add(element["id"])
        ids = element["nodes"]
        if len(ids) < 2 or any(n not in nodes for n in ids):
            continue
        rows.append(
            {
                "osm_id": element["id"],
                "highway": tags["highway"],
                "name": tags.get("name"),
                "lanes": tags.get("lanes"),
                "oneway": tags.get("oneway"),
                "node_ids": json.dumps(ids),
            }
        )
        lines.append(LineString([nodes[n] for n in ids]))
    return gpd.GeoDataFrame(rows, geometry=lines, crs=CRS_WGS84)


def path(out: Path, crs: str) -> Path:
    return out / f"{STEM}_{crs_tag(crs)}.parquet"


def read_raw(raw: Path) -> dict[str, Any]:
    """Overpass JSON from a plain or gzipped file."""
    opener = gzip.open if raw.suffix == ".gz" else open
    with opener(raw, "rt", encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    return data


def build(raw: Path, out: Path, crs: str) -> Path:
    """Read ``raw`` (Overpass JSON, plain or gzipped) and write the street table in ``crs``."""
    table = streets(read_raw(raw)).to_crs(crs)
    out.mkdir(parents=True, exist_ok=True)
    table[COLUMNS].to_parquet(path(out, crs), index=False)
    return path(out, crs)


def area_bounds(area: Path) -> tuple[float, float, float, float]:
    """(west, south, east, north) of an outline file, in degrees."""
    west, south, east, north = read_shapes(area).to_crs(CRS_WGS84).total_bounds
    return (float(west), float(south), float(east), float(north))
