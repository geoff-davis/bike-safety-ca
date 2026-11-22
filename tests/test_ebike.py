"""E-bike evidence tiers for SWITRS bicycle parties and collision-time parsing."""

import pandas as pd
import pytest

from bike_safety_ca.crashes import ebike
from bike_safety_ca.crashes.tims import parse_collision_time


@pytest.mark.parametrize(
    ("make", "expected"),
    [
        # Explicit wording and e-bike-only brands, including recorded spellings.
        ("ISINWHEEL (E-BIKE) ZX9", ebike.TIER_EBIKE),
        ("SUPER 73 QZ", ebike.TIER_EBIKE),
        ("SUPER73", ebike.TIER_EBIKE),
        ("SUPER", ebike.TIER_EBIKE),
        ("RAD POWER BIKES", ebike.TIER_EBIKE),
        ("RAD", ebike.TIER_EBIKE),
        ("HAPPY RUN", ebike.TIER_EBIKE),
        ("JUPITER BIKE", ebike.TIER_EBIKE),
        ("ENGUIE", ebike.TIER_EBIKE),
        ("BOSCH", ebike.TIER_EBIKE),
        ("SPECIALIZED TURBO VADO", ebike.TIER_EBIKE),
        # Not legal e-bikes.
        ("TALARIA", ebike.TIER_EMOTO),
        ("KINGSONG", ebike.TIER_OTHER_ELECTRIC),
        # A conventional model name beats its mixed brand.
        ("SPECIALIZED TARMAC", ebike.TIER_CONVENTIONAL),
        ("SCOTT ADDICT", ebike.TIER_CONVENTIONAL),
        ("CERVELO", ebike.TIER_CONVENTIONAL),
        ("YAPHET", ebike.TIER_CONVENTIONAL),
        # Brands that sell both stay undetermined, including misspellings.
        ("TREK", ebike.TIER_MIXED),
        ("DUOMANE", ebike.TIER_MIXED),
        ("SPCLZD", ebike.TIER_MIXED),
        ("SPECIALIZED PLAID", ebike.TIER_MIXED),
        ("GIANT PLAID", ebike.TIER_MIXED),
        ("ELECTRA", ebike.TIER_MIXED),
        # Data-entry errors and missing makes.
        ("TESLA", ebike.TIER_CAR_MAKE),
        ("-", ebike.TIER_NO_MAKE),
        (None, ebike.TIER_NO_MAKE),
        ("  bicycle ", ebike.TIER_NO_MAKE),
        ("QWERTY 7", ebike.TIER_UNRECOGNISED),
    ],
)
def test_make_tiers(make, expected):
    assert ebike.classify_make(make)[0] == expected


def test_anchored_brands_do_not_match_inside_other_words():
    assert ebike.classify_make("RADIANT")[0] == ebike.TIER_UNRECOGNISED
    assert ebike.classify_make("SUPERIOR")[0] == ebike.TIER_UNRECOGNISED
    assert ebike.classify_make("GTX FRAMEWORKS")[0] == ebike.TIER_UNRECOGNISED


def test_the_word_electric_is_not_the_lectric_brand():
    assert ebike.classify_make("LECTRIC XQ") == (ebike.TIER_EBIKE, "Lectric eBikes")
    # Only "electric bicycle" says e-bike; other electric devices keep their own tiers.
    assert ebike.classify_make("ELECTRIC BICYCLE")[0] == ebike.TIER_EBIKE
    assert ebike.classify_make("ELECTRIC SCOOTER")[0] == ebike.TIER_UNRECOGNISED
    assert ebike.classify_make("ELECTRIC")[0] == ebike.TIER_UNRECOGNISED
    assert ebike.classify_make("ELECTRIC UNICYCLE KINGSONG")[0] == ebike.TIER_OTHER_ELECTRIC
    assert ebike.classify_make("ELECTRIC MOTORCYCLE TALARIA")[0] == ebike.TIER_EMOTO


def test_code_91_wins_over_any_make():
    assert ebike.classify_make("TREK", "91") == (ebike.TIER_EBIKE, "CHP vehicle type 91")
    assert ebike.classify_make("-", " 91 ")[0] == ebike.TIER_EBIKE
    assert ebike.classify_make("TREK", "04")[0] == ebike.TIER_MIXED


def test_code_91_on_a_motor_vehicle_make_is_a_data_entry_conflict():
    tier, evidence = ebike.classify_make("OTHER - BUS", "91")
    assert tier == ebike.TIER_CAR_MAKE and "conflicts" in evidence


def test_every_tier_has_a_label_and_every_rule_names_a_known_tier():
    assert set(ebike.TIER_LABELS) >= {rule.tier for rule in ebike.BRAND_RULES}
    assert all(rule.note for rule in ebike.BRAND_RULES)


def test_bicycle_parties_selects_bicycles_and_code_91_only():
    parties = pd.DataFrame(
        {
            "CASE_ID": ["1", "1", "2", "3", "4"],
            "PARTY_NUMBER": ["1", "2", "1", "1", "1"],
            "STWD_VEHICLE_TYPE": ["L", "A", "M", "L", "C"],
            "CHP_VEH_TYPE_TOWING": ["04", "01", "91", "04", "02"],
            "VEHICLE_MAKE": ["LECTRIC", "TOYT", "-", "TREK", "TALARIA"],
        }
    )
    result = ebike.bicycle_parties(parties)
    assert result.CASE_ID.tolist() == ["1", "2", "3"]
    assert result.ebike.tolist() == [True, True, False]
    assert result.ebike_tier_label.notna().all()


def test_collision_time_handles_missing_zero_and_trailing_space():
    parsed = parse_collision_time(
        pd.Series(["849 ", "0826", "1535", "45", "2500", "", None, "12x4"])
    )
    assert parsed.collision_hour.tolist()[:4] == [8, 8, 15, 0]
    assert parsed.collision_time.tolist()[:4] == ["08:49", "08:26", "15:35", "00:45"]
    assert parsed.collision_hour.iloc[4:].isna().all()
