"""One polygon layer from a public ArcGIS map service, saved as GeoJSON.

Used for a city's own city-limit layer.  The file stays in the git-ignored
data folder: a city's terms may not allow passing its map data on, so each
user fetches their own copy.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from bike_safety_ca.io import atomic_write_text

log = logging.getLogger(__name__)


class FetchError(RuntimeError):
    """The map service answered, but not with the whole layer."""


def _encloses(shape: object) -> bool:
    """True for a GeoJSON polygon or multipolygon with at least one closed ring."""
    if not isinstance(shape, dict) or not isinstance(shape.get("coordinates"), list):
        return False
    if shape.get("type") == "Polygon":
        polygons = [shape["coordinates"]]
    elif shape.get("type") == "MultiPolygon":
        polygons = shape["coordinates"]
    else:
        return False
    return any(
        isinstance(ring, list) and len(ring) >= 4
        for rings in polygons
        if isinstance(rings, list)
        for ring in rings
    )


def check(text: str, layer_url: str) -> None:
    """Refuse a reply that is an error, holds no polygon or was cut short."""
    try:
        body = json.loads(text)
    except ValueError as error:
        raise FetchError(f"the reply from {layer_url} is not JSON") from error
    if not isinstance(body, dict):
        raise FetchError(f"the reply from {layer_url} is not a layer")
    if "error" in body:
        problem = body["error"]
        message = problem.get("message") if isinstance(problem, dict) else problem
        raise FetchError(f"{layer_url} answered with an error: {message}")
    # ArcGIS puts the flag at the top of the reply or under "properties".
    properties = body.get("properties")
    cut = body.get("exceededTransferLimit") or (
        isinstance(properties, dict) and properties.get("exceededTransferLimit")
    )
    if cut:
        raise FetchError(
            f"{layer_url} holds more features than the server sends in one reply "
            "(exceededTransferLimit), and paging is not supported here; the cut-short "
            "layer was not saved. Save the whole layer to a file and set city_limit_file."
        )
    features = body.get("features")
    shapes = [
        feature.get("geometry")
        for feature in (features if isinstance(features, list) else [])
        if isinstance(feature, dict)
    ]
    if not any(_encloses(shape) for shape in shapes):
        raise FetchError(f"the layer is empty: no polygon features in the reply from {layer_url}")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=30),
    retry=retry_if_not_exception_type(FetchError),
    reraise=True,
)
def _query(layer_url: str) -> str:
    response = httpx.get(
        f"{layer_url.rstrip('/')}/query",
        params={"where": "1=1", "outFields": "*", "outSR": 4326, "f": "geojson"},
        timeout=120,
        headers={"User-Agent": "bike-safety-ca/0.1"},
    )
    response.raise_for_status()
    check(response.text, layer_url)
    return response.text


def download(layer_url: str, dest: Path, overwrite: bool = False) -> Path:
    """Fetch every feature of the layer at ``layer_url`` into ``dest``.

    A layer too large for one reply is refused, not saved cut short.
    """
    source = dest.with_name(dest.name + ".source.txt")
    if not overwrite and dest.exists():
        if not source.exists():
            log.warning("%s has no record of where it came from; using it as it is", dest)
            return dest
        had = source.read_text().strip()
        if had != layer_url:
            raise ValueError(
                f"{dest} was fetched from {had}, not {layer_url}. "
                "Use another folder for this city, or pass --overwrite to replace it."
            )
        return dest
    atomic_write_text(dest, _query(layer_url))
    atomic_write_text(source, layer_url + "\n")
    log.info("saved %s", dest)
    return dest
