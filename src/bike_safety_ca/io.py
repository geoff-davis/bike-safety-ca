"""File helpers: atomic text writes and GeoParquet in two coordinate systems."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

CRS_WGS84 = "EPSG:4326"


def crs_tag(crs: str) -> str:
    """File-name tag for a coordinate system: "EPSG:26910" gives "26910"."""
    return crs.rsplit(":", 1)[-1]


def read_shapes(path: Path) -> gpd.GeoDataFrame:
    """Read a GeoParquet file, or anything else GeoPandas reads (GeoJSON, shapefile...)."""
    if Path(path).suffix == ".parquet":
        return gpd.read_parquet(path)
    return gpd.read_file(path)


def write_dual(gdf: gpd.GeoDataFrame, out: Path, stem: str, crs: str) -> dict[str, Path]:
    """Write ``<stem>_4326.parquet`` (interchange) and ``<stem>_<local>.parquet`` (metres)."""
    out.mkdir(parents=True, exist_ok=True)
    if gdf.crs is None:
        raise ValueError(f"{stem}: CRS not set")
    paths = {}
    for target in (CRS_WGS84, crs):
        path = out / f"{stem}_{crs_tag(target)}.parquet"
        gdf.to_crs(target).to_parquet(path, index=False)
        paths[crs_tag(target)] = path
    return paths


def write_table(df: pd.DataFrame, out: Path, stem: str) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{stem}.parquet"
    df.to_parquet(path, index=False)
    return path


def atomic_write_text(dest: Path, content: str, encoding: str | None = None) -> Path:
    """Write text to a sibling staging file and atomically publish it."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    staged = dest.with_name(dest.name + ".part")
    staged.write_text(content, encoding=encoding)
    staged.replace(dest)
    return dest


def atomic_write_json(dest: Path, value: object, *, indent: int | None = 2) -> Path:
    return atomic_write_text(dest, json.dumps(value, indent=indent))
