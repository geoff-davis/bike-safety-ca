"""Street names as police and OpenStreetMap write them, grouped into corridors.

``corridor`` tidies a reported road name for the crash map's streets table and
gives the corridor forecast its readable labels.  The two do not group streets
the same way.  The crash map groups by ``corridor``, which works on police
text and so drops the generic street types (avenue, street, road, drive,
boulevard, expressway) that reports abbreviate or leave out: there "1st
Street" and "1st Avenue" are one row.  The corridor forecast and the
intersection model group mapped streets by ``junctions.street_key``, which
keeps every street type, and match crash reports to them by
``junctions.road_key``, which drops them all.
"""

from __future__ import annotations

import re

# Generic street types dropped from a corridor name.  Circle, court, lane,
# place, terrace and way stay, so "Distel Drive" ("Distel") and "Distel
# Circle" have two names; "Distel Drive" and "Distel Road" have one.
_STREET_TYPE = re.compile(
    r"\s(AVENUE|AVE|AV|STREET|ST|ROAD|RD|DRIVE|DR|BOULEVARD|BLVD|BL|EXPRESSWAY|EXPY|EXPWY|EXPR)\s*$"
)
# Kept street types, written out so "Ln" and "Lane" group together.
_KEPT_TYPE = {
    "WY": "WAY",
    "LN": "LANE",
    "CT": "COURT",
    "PL": "PLACE",
    "CIR": "CIRCLE",
    "TER": "TERRACE",
}
# Generic types written out, for a street named by a compass word alone.
_GENERIC_TYPE = {
    **dict.fromkeys(("AVENUE", "AVE", "AV"), "AVENUE"),
    **dict.fromkeys(("STREET", "ST"), "STREET"),
    **dict.fromkeys(("ROAD", "RD"), "ROAD"),
    **dict.fromkeys(("DRIVE", "DR"), "DRIVE"),
    **dict.fromkeys(("BOULEVARD", "BLVD", "BL"), "BOULEVARD"),
    **dict.fromkeys(("EXPRESSWAY", "EXPY", "EXPWY", "EXPR"), "EXPRESSWAY"),
    **{kind: kind for kind in _KEPT_TYPE.values()},
    **_KEPT_TYPE,
}
_STATE_ROUTE = re.compile(r"\b(RT|RTE|SR|ROUTE|HWY|HIGHWAY|STATE ROUTE)\s*(\d+)\b")
_ROUTE_NAMES = {"82": "El Camino Real"}


def corridor(raw: str) -> str:
    """The street a reported road name belongs to, for grouping crashes by corridor.

    Police write the same street many ways: "FOOTHILL EXPY", "Foothill
    Expressway", "N SAN ANTONIO RD", "RT 82".  This drops punctuation, a
    leading compass prefix and a trailing generic street type, reads a leading
    "ST" as Saint, and names state routes that have a common name.  A street
    named by a compass word alone keeps the word and its type, written out:
    "SOUTH ST" is "South Street" and "N Street" is "N Street", not "Street".
    Empty when nothing is left.
    """
    s = re.sub(r"[^A-Z0-9 ]", " ", str(raw).upper())
    if s.strip() in ("", "NONE", "NAN", "NA"):
        return ""
    route = _STATE_ROUTE.search(s)
    if route and route.group(2) in _ROUTE_NAMES:
        return _ROUTE_NAMES[route.group(2)]
    s = re.sub(r"\s+", " ", s).strip()
    compass_named = re.fullmatch(r"(N|S|E|W|NORTH|SOUTH|EAST|WEST) (\w+)", s)
    if compass_named and compass_named.group(2) in _GENERIC_TYPE:
        return f"{compass_named.group(1)} {_GENERIC_TYPE[compass_named.group(2)]}".title()
    s = re.sub(r"^(N|S|E|W|NORTH|SOUTH|EAST|WEST) (?=\S)", "", s)
    if re.fullmatch(r"EL CAMINO( REAL)?|ECR", s):
        return "El Camino Real"
    s = re.sub(r"^ST (?=\S)", "SAINT ", s)  # a leading ST is a saint, not a street
    s = re.sub(r"\s(\w+)$", lambda m: " " + _KEPT_TYPE.get(m.group(1), m.group(1)), s)
    s = _STREET_TYPE.sub("", s).strip().title()
    return re.sub(r"\b(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), s)
