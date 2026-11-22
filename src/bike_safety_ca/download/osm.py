"""Streets from OpenStreetMap for an area, through the Overpass API.

Asks for every way tagged ``highway`` inside the area's bounding box, padded so
streets that leave the area are not cut short, and saves the raw Overpass JSON
with a note of when it was fetched.  OpenStreetMap data is (c) OpenStreetMap
contributors under the ODbL 1.0 licence: credit them wherever it is used.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from bike_safety_ca.io import atomic_write_json, atomic_write_text

OVERPASS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
PAD_DEG = 0.01  # about 1 km
LICENCE = "ODbL 1.0 (c) OpenStreetMap contributors"

log = logging.getLogger(__name__)
Bounds = tuple[float, float, float, float]


def padded(bounds: Bounds, pad: float = PAD_DEG) -> Bounds:
    """(west, south, east, north) in degrees, widened by ``pad`` on every side."""
    west, south, east, north = bounds
    return (west - pad, south - pad, east + pad, north + pad)


def build_query(bounds: Bounds, date: str | None = None) -> str:
    """Overpass query for the streets in (west, south, east, north), with their nodes.

    ``date`` ("2026-08-22T23:47:01Z") asks for the map as it stood then, so a
    past analysis can be repeated on the same streets.
    """
    west, south, east, north = bounds
    when = f'[date:"{date}"]' if date else ""
    return (
        f"[out:json][timeout:600][maxsize:1073741824]{when};\n"
        f'way["highway"]({south},{west},{north},{east});\n'
        "out meta;\n>;\nout skel;\n"
    )


def check(body: dict[str, Any], require_elements: bool = True) -> None:
    """Refuse a reply that is not a whole street extract.

    Overpass answers a query that timed out or ran out of memory with HTTP 200:
    a ``remark`` giving the reason, and whatever elements it had by then.
    ``require_elements`` False accepts an empty answer, for a query that may
    rightly find nothing.
    """
    if body.get("remark"):
        raise ValueError(f"Overpass did not finish the query ({body['remark']})")
    if require_elements and not body.get("elements"):
        raise ValueError("Overpass returned no streets for the area")


@retry(stop=stop_after_attempt(4), wait=wait_exponential(min=10, max=120), reraise=True)
def run(query: str, require_elements: bool = True) -> dict[str, Any]:
    last: Exception | None = None
    for url in OVERPASS:
        try:
            with httpx.Client(timeout=httpx.Timeout(900, connect=30)) as client:
                response = client.post(
                    url, data={"data": query}, headers={"User-Agent": "bike-safety-ca/0.1"}
                )
                response.raise_for_status()
                body: dict[str, Any] = response.json()
                check(body, require_elements)
                return body
        except Exception as error:  # noqa: BLE001
            last = error
            log.warning("overpass %s failed: %s", url, error)
    raise RuntimeError(f"all overpass endpoints failed, nothing was saved: {last}")


def reuse(out: Path, box: Bounds, date: str | None) -> bool:
    """Whether ``out`` already holds the streets for ``box`` (padded) at ``date``.

    Refuses a saved file fetched for another box or map date, so one city's
    streets are never read as another's.
    """
    dest, note = out / "overpass_streets.json", out / "overpass_streets.metadata.json"
    if not dest.exists():
        return False
    saved = json.loads(note.read_text()) if note.exists() else {}
    had = (saved.get("bounds_west_south_east_north"), saved.get("map_as_of"))
    if had[0] is None:
        log.warning("%s has no record of its area; using it as it is", dest)
        return True
    if (list(had[0]), had[1]) == (list(box), date or "latest"):
        log.info("exists, skipping %s", dest)
        return True
    raise ValueError(
        f"{dest} was fetched for another area or map date ({had[0]}, {had[1]}). "
        "Use another folder for this city, or pass --overwrite to replace it."
    )


def save(
    out: Path,
    query: str,
    data: dict[str, Any],
    box: Bounds,
    date: str | None,
    source: str | None = None,
) -> Path:
    """Write the streets, the query that asked for them and a note of both."""
    dest = out / "overpass_streets.json"
    payload = json.dumps(data)
    atomic_write_text(out / "overpass_query.txt", query)
    atomic_write_text(dest, payload)
    note: dict[str, Any] = {
        "retrieved_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "osm3s": data.get("osm3s"),
        "map_as_of": date or "latest",
        "bounds_west_south_east_north": box,
        "elements": len(data.get("elements", [])),
        "sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "license": LICENCE,
    }
    if source:
        note["source"] = source
    atomic_write_json(out / "overpass_streets.metadata.json", note)
    log.info("saved %d elements", len(data.get("elements", [])))
    return dest


def download(bounds: Bounds, out: Path, overwrite: bool = False, date: str | None = None) -> Path:
    """Fetch the streets in ``bounds`` (degrees, padded here) into ``out``."""
    box = padded(bounds)
    if not overwrite and reuse(out, box, date):
        return out / "overpass_streets.json"
    query = build_query(box, date)
    return save(out, query, run(query), box, date)
