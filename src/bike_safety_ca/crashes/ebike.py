"""Classify SWITRS bicycle parties as e-bikes from vehicle codes and recorded makes.

SWITRS has no reliable e-bike field. CHP vehicle type 91, "Electric Bicycle
(Class 1, 2, 3)", has been used since about 2021, but officers often code an
e-bike as an ordinary bicycle (statewide type L, CHP type 04). The free-text
``VEHICLE_MAKE`` is the main remaining evidence: some brands sell only
e-bikes, some sell both, and some (road-racing marques, BMX and kids' bikes)
sell essentially none.

Each bicycle-like party gets one evidence tier. ``ebike`` is True only for
``TIER_EBIKE``. Counts are a floor: about 80% of bicycle parties have no
recorded make, and makes from brands that sell both kinds stay undetermined.

Rules are ordered; the first match wins. Code 91 wins unless the make is a
motor vehicle, since a bus or car make coded 91 is a coding error. A model name
that identifies a conventional bike (e.g. "SPECIALIZED TARMAC") is checked
before the brand that makes both kinds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

TIER_EBIKE = "ebike"
TIER_EMOTO = "electric_motorcycle"
TIER_OTHER_ELECTRIC = "other_electric_device"
TIER_CONVENTIONAL = "likely_conventional"
TIER_MIXED = "brand_sells_both"
TIER_CAR_MAKE = "car_make_entered"
TIER_NO_MAKE = "no_make_recorded"
TIER_UNRECOGNISED = "unrecognised"

TIER_LABELS = {
    TIER_EBIKE: "E-bike (code 91 or e-bike-only brand)",
    TIER_EMOTO: "Electric motorcycle coded as bicycle",
    TIER_OTHER_ELECTRIC: "Other electric device coded as bicycle",
    TIER_CONVENTIONAL: "Likely conventional bicycle",
    TIER_MIXED: "Brand sells both; undetermined",
    TIER_CAR_MAKE: "Car make entered (data-entry error)",
    TIER_NO_MAKE: "No make recorded",
    TIER_UNRECOGNISED: "Unrecognised make",
}

CHP_ELECTRIC_BICYCLE = "91"


@dataclass(frozen=True)
class BrandRule:
    """One make pattern, its tier, and why."""

    pattern: str
    tier: str
    note: str


# Patterns match the normalized make (upper case, single spaces). Anchored
# patterns (^...$) avoid matching inside longer words. Spelling variants are
# taken from the 2014-2026 Los Altos study-area TIMS export.
BRAND_RULES: tuple[BrandRule, ...] = (
    # Explicit electric wording.
    BrandRule(r"E-?BIKE|ELECTRIC BI", TIER_EBIKE, "make text says e-bike"),
    # Brands that sell only e-bikes.
    BrandRule(r"SUPER ?73|^SUPER$", TIER_EBIKE, "Super73; 'SUPER' is the truncated form"),
    BrandRule(r"^RAD$|RAD ?POWER", TIER_EBIKE, "Rad Power Bikes"),
    BrandRule(r"AVENTON", TIER_EBIKE, "Aventon"),
    BrandRule(r"\bLECTRIC\b", TIER_EBIKE, "Lectric eBikes"),
    BrandRule(r"JUICED", TIER_EBIKE, "Juiced Bikes"),
    BrandRule(r"SONDORS", TIER_EBIKE, "Sondors"),
    BrandRule(r"JETSON", TIER_EBIKE, "Jetson"),
    BrandRule(r"ANCHEER", TIER_EBIKE, "Ancheer"),
    BrandRule(r"CYRUSHER", TIER_EBIKE, "Cyrusher"),
    BrandRule(r"ISINWHEEL", TIER_EBIKE, "isinwheel; also sells e-scooters"),
    BrandRule(r"^VIVI$", TIER_EBIKE, "Vivi"),
    BrandRule(r"BOSCH", TIER_EBIKE, "Bosch e-bike drive systems"),
    BrandRule(r"JUPITER", TIER_EBIKE, "Jupiter Bike folding e-bikes"),
    BrandRule(r"MACFOX", TIER_EBIKE, "Macfox"),
    BrandRule(r"TOTGUARD", TIER_EBIKE, "Totguard"),
    BrandRule(r"HAPPY ?RUN", TIER_EBIKE, "Happyrun"),
    BrandRule(r"SMLRO", TIER_EBIKE, "SMLRO"),
    BrandRule(r"E-?FLOW", TIER_EBIKE, "E-Flow"),
    BrandRule(r"RIDEPANDA", TIER_EBIKE, "Ridepanda e-bike subscriptions"),
    BrandRule(r"ECOBIKE", TIER_EBIKE, "Ecobike"),
    BrandRule(r"^MOTIV$", TIER_EBIKE, "Motiv Electric Bikes"),
    BrandRule(r"ENGWE|ENGUIE", TIER_EBIKE, "Engwe; 'ENGUIE' is a recorded misspelling"),
    BrandRule(r"ORAIMO", TIER_EBIKE, "Oraimo"),
    BrandRule(r"^HMP$", TIER_EBIKE, "HMP Bikes e-bikes and e-mopeds"),
    BrandRule(r"^E-?STAR$", TIER_EBIKE, "E-Star folding e-bike"),
    BrandRule(r"HIMIWAY|HEYBIKE|VELOTRIC|PEDEGO|ARIEL RIDER", TIER_EBIKE, "e-bike-only brands"),
    # E-bike model names from brands that also sell conventional bikes.
    BrandRule(
        r"\bTURBO\b|\bLEVO\b|\bVADO\b|\bCOMO\b|KENEVO|ALLANT\+|\bRAIL\b|\bPOWERFLY\b",
        TIER_EBIKE,
        "e-bike model name (Specialized Turbo, Trek Allant+/Rail/Powerfly)",
    ),
    # Not legal e-bikes.
    BrandRule(r"TALARIA|SUR-?RON", TIER_EMOTO, "off-road electric motorcycle"),
    BrandRule(r"KINGSONG", TIER_OTHER_ELECTRIC, "electric unicycle"),
    # Model names that identify a conventional bike; checked before brands.
    BrandRule(
        r"TARMAC|ROUBAIX|S-?WORKS|S WORKS|HARDROCK|^TCR$|ADDICT|ENDURACE|T MACHINE",
        TIER_CONVENTIONAL,
        "conventional road or mountain model name",
    ),
    # Brands that sell both conventional bikes and e-bikes.
    BrandRule(
        r"^(TREK|TREX|TRECK|DUOMANE|SPECIALI[SZ]ED|SPECIALI|SPECIAL|SPEC\.?|SPECIALZ|SPCLZD|"
        r"SPZD|SPECLZ|SPCLZED|SPCLIZD|SPECALIZ|SPECILAIZED|SPECIALIST|SPE|SPCL|SPCN|SPCNS|"
        r"GIANT|GAINT|GIAA|LIV|LIV/GIANT|CANNONDALE|CANNONDA|CANONDALE|CANONDAL|"
        r"CANODALE|CANNDLE|CANN|CADDONDALE|SCHWINN?|ELECTRA|TOWNIE|RETROSPEC|HYPER|HUFFY?|"
        r"SCOTT|ORBEA|CANYON|MARIN|NORCO|RALEIGH|KONA|GT|DIAMONDBACK|DIAMNDBK|"
        r"DIAMOND BACK|DIAMOND|MOMENTUM|BREEZER|GENESIS|FOCUS|FUJI|FUWI|JAMIS|SANTA CRUZ|IBIS|"
        r"BH|KHS|NOVARA|NOVARO|PRIORITY|MOTOBECANE|MOTOBECA|MOTORBEC|CO-OP|BIANCHI|FELT|BMC|"
        r"CENTURION|GARY FISHER|LEMOND|INTENSE|NINER|THRONE|EVO|REID)(?![A-Z0-9])",
        TIER_MIXED,
        "brand sells both conventional bikes and e-bikes (Domane recorded as DUOMANE)",
    ),
    # Brands that sell essentially only conventional bikes.
    BrandRule(
        r"CERVELO|CERVICA|PINARELL|^PINA$|PINEROLLO|COLNAGO|CONLAGO|^SEVEN$|MOOTS|LYNSKEY|"
        r"CALFEE|KESTREL|LITE ?SPEED|SEROTTA|RITCHEY|RICHEY|SURLY|^SOMA$|FIREFLY|ENVE|FACTOR|"
        r"ARGON 18|RIDLEY|CINELLI|PREVELO|^6KU$|PURE CITY|^SUN$|MONGOOSE|^KENT$|^KEND$|ROADMAST|"
        r"DYNACRAFT|HILAND|VILANO|NISHIKI|UNIVEGA|PEUG|SCATTANTE|VOLAGI|^ORRO$|BENNO|REDLINE|"
        r"FREE SPIRIT|OZARK|BARRON|TRICYCLE|CRUZBIKE|EASTWOOD|FAIRLIGHT|REYNOLDS|CAMPAGNOLO|"
        r"SHIMANO|^GIRO$|COLUMBUS|TITANIUM|CONDOR|DOCIO|CICLI|^LEADER$|^K2$|INFINITY|MORATI|"
        r"HARPER|REBOUND|AUSTRIAL|BOBBIN|GAULZETT|LD LABS|PERFORMANCE|ROCK LOBSTER|^BATCH$|"
        r"^CUSTOM$|CRUISER|TAWAN|PATHFIND|BRENTWOO|CLARITY|CYCLE TRACK|^ROAD$|HYBRID|"
        r"MOUNTAIN BIKE|MTN BIKE|CITIZEN|SMART TRAVEL|BOMMA|THRUSTER|^CRUZ$|YAPHET|RUNDO|RONDO",
        TIER_CONVENTIONAL,
        "brand or generic description of a conventional bike (Yaphet: Cubsala BMX; "
        "RUNDO: Rondo gravel bikes)",
    ),
    BrandRule(
        r"^(LEXUS|MITSUBISHI|MERC|TESLA|CAN-AM|TOYT|TOYOTA|HONDA|FORD|CHEV|BUS|OTHER - BUS)$",
        TIER_CAR_MAKE,
        "a motor-vehicle make, probably copied from the other party",
    ),
    BrandRule(r"^(|-|UNK|UNKNOWN|BICYCLE|BIKE|OTHER|OTHER - DOMESTIC)$", TIER_NO_MAKE, "no make"),
)

_COMPILED = tuple((re.compile(rule.pattern), rule) for rule in BRAND_RULES)


def normalize_make(value: object) -> str:
    """Upper-case and collapse whitespace; missing values become an empty string."""
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NA:
        return ""
    return " ".join(str(value).upper().split())


def classify_make(make: object, chp_vehicle_type: object = None) -> tuple[str, str]:
    """Return (tier, evidence) for one bicycle-like party."""
    text = normalize_make(make)
    tier, evidence = next(
        ((rule.tier, rule.note) for pattern, rule in _COMPILED if pattern.search(text)),
        (TIER_UNRECOGNISED, "no rule matched"),
    )
    if normalize_make(chp_vehicle_type) != CHP_ELECTRIC_BICYCLE:
        return tier, evidence
    if tier == TIER_CAR_MAKE:
        return tier, "CHP vehicle type 91 conflicts with a motor-vehicle make"
    return TIER_EBIKE, "CHP vehicle type 91"


def bicycle_parties(parties: pd.DataFrame) -> pd.DataFrame:
    """Classify every party coded as a bicycle (type L) or an electric bicycle (CHP 91)."""
    stwd = parties.STWD_VEHICLE_TYPE.fillna("").str.strip()
    chp = parties.CHP_VEH_TYPE_TOWING.fillna("").str.strip()
    selected = parties[stwd.eq("L") | chp.eq(CHP_ELECTRIC_BICYCLE)].copy()
    results = [
        classify_make(make, code)
        for make, code in zip(selected.VEHICLE_MAKE, selected.CHP_VEH_TYPE_TOWING)
    ]
    selected["make_normalized"] = selected.VEHICLE_MAKE.map(normalize_make)
    selected["ebike_tier"] = [tier for tier, _ in results]
    selected["ebike_tier_label"] = selected.ebike_tier.map(TIER_LABELS)
    selected["ebike_evidence"] = [evidence for _, evidence in results]
    selected["ebike"] = selected.ebike_tier.eq(TIER_EBIKE)
    return selected
