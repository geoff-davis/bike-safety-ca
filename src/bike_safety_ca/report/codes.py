"""Labels for the SWITRS / CCRS codes used in the summaries and the map."""

from __future__ import annotations

# Primary collision factor categories (PCF_VIOL_CATEGORY).
CAUSES = {
    "03": "Unsafe speed",
    "05": "Wrong side of road",
    "07": "Unsafe lane change",
    "08": "Improper turning",
    "09": "Failure to yield (vehicle right-of-way)",
    "12": "Traffic signals and signs",
    "17": "Other hazardous violation",
    "18": "Other than driver",
    "21": "Unsafe starting or backing",
}
OTHER_CAUSE = "Other / unknown"

# Movement before the crash (MOVE_PRE_ACC).
MOVES = {
    "A": "stopped",
    "B": "going straight",
    "C": "ran off road",
    "D": "right turn",
    "E": "left turn",
    "F": "U-turn",
    "G": "backing",
    "H": "slowing or stopping",
    "I": "passing",
    "J": "changing lanes",
    "K": "parking",
    "L": "entering traffic",
    "M": "other unsafe turn",
    "N": "crossed into opposing lane",
    "O": "parked",
    "P": "merging",
    "Q": "travelling wrong way",
    "R": "other",
    "-": "not stated",
}

# Type of collision (TYPE_OF_COLLISION).
COLLISIONS = {
    "A": "head-on",
    "B": "sideswipe",
    "C": "rear end",
    "D": "broadside",
    "E": "hit object",
    "F": "overturned",
    "G": "vehicle and pedestrian",
    "H": "other",
    "-": "not stated",
}

# Statewide vehicle type (STWD_VEHICLE_TYPE) to the map's five kinds.
BICYCLE, PEDESTRIAN, CAR, MOTORCYCLE, OTHER = (
    "bicycle",
    "pedestrian",
    "car or truck",
    "motorcycle",
    "bus or other",
)
VEHICLES = {
    "L": BICYCLE,
    "N": PEDESTRIAN,
    **dict.fromkeys("ABDEFG", CAR),
    **dict.fromkeys("CO", MOTORCYCLE),
    **dict.fromkeys("HIJKM", OTHER),
}

# Direction of travel (DIR_OF_TRAVEL) as a compass bearing.
BEARINGS = {"N": 0.0, "E": 90.0, "S": 180.0, "W": 270.0}

# Direction of travel as words.
TRAVEL = {"N": "northbound", "S": "southbound", "E": "eastbound", "W": "westbound"}

# Lighting (LIGHTING). TIMS and CCRS use the same letters.
LIGHTING = {
    "A": "daylight",
    "B": "dusk or dawn",
    "C": "dark, street lights",
    "D": "dark, no street lights",
    "E": "dark, street lights not working",
}
DARK = ("C", "D", "E")

# Crash severity (COLLISION_SEVERITY): the worst injury in the crash.
SEVERITY = {
    "1": "fatal",
    "2": "serious injury",
    "3": "other visible injury",
    "4": "complaint of pain",
    "0": "no injury recorded",
}
