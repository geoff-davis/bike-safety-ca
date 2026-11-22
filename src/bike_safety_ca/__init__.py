"""Rank intersections for bicycle crash risk from California police crash records."""

CHILD = "Cyclist 18 or under"
ADULT = "Cyclist over 18"
UNKNOWN_AGE = "Cyclist, age not recorded"
CAR = "Motor vehicles only"
CYCLISTS = [CHILD, ADULT, UNKNOWN_AGE]  # every cyclist crash, whatever the age


def age_label(text: str, child_max_age: int) -> str:
    """A group or outcome name with the config's child age in place of 18.

    The names above are fixed keys; this is for what people read.
    """
    return text.replace(" 18", f" {child_max_age}") if child_max_age != 18 else text
