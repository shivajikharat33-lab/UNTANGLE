"""Named tolerances and label maps for the graph, patterns, checks, and coverage.

Every cutoff used by those stages lives here. A number in a service file
should refer to one of these names.
"""

import math

# Same cutoffs as app.config high/medium/low. The graph also stores a word:
# confirmed, likely, or uncertain. The word never claims a higher score
# than the number it was mapped from.
CONFIRMED_MIN = 0.85
LIKELY_MIN = 0.60

# A vector stroke is not proof of a connection. 0.80 stays "likely".
VECTOR_EDGE_SCORE = 0.80
# Raster geometry is less reliable than vector geometry.
RASTER_EDGE_SCORE = 0.70
# D3 uses this cap when an error finding applies. D1 does not apply it.
UNCERTAIN_CAP = 0.59

# Pipe ends farther apart than this are not treated as the same point.
# Callers pass the job snap tolerance when they have one; this is the default.
DEFAULT_SNAP_TOLERANCE = 4.0
# A pipe end within this distance of a symbol boundary or a junction may attach.
DEFAULT_NODE_ATTACH_TOLERANCE = 8.0
# Two attachments this close in distance are a tie. Neither one is chosen.
TIE_EPSILON = 0.5
# Instrument center to a process line, in PDF points.
INSTRUMENT_PIPE_TOLERANCE = 18.0
# Instrument center to an equipment box.
INSTRUMENT_EQUIPMENT_TOLERANCE = 24.0
# An arrow whose center is farther than this from a line is not used.
ARROW_ON_PIPE_TOLERANCE = 12.0
# Arrow or nozzle direction must lie within this many degrees of the line.
DIRECTION_ANGLE_DEGREES = 35.0
# Two segments join only when they continue within this many degrees of a straight line.
COLLINEAR_MAX_DEGREES = 12.0
# Coordinates rounded to this many decimal places before an id is hashed.
ID_DECIMALS = 1
# Two symbol centers closer than this, on the same page, are duplicate candidates.
DUPLICATE_DISTANCE = 3.0

PROCESSING_VERSION = "D1"
PATTERN_VERSION = "D2"

# A and B on a tag are a duty/standby hint. The letter alone never confirms which pump is running.
DUTY_SUFFIXES = ("A", "B")
DUTY_WORD = "DUTY"
STANDBY_WORDS = ("STANDBY", "STAND-BY", "STAND BY")

# Longest prefix first so PIC is not read as a sensor.
SENSOR_PREFIXES = ("PDT", "PT", "FT", "LT", "TT", "AT")
CONTROLLER_PREFIXES = ("PIC", "FIC", "LIC", "TIC", "PC", "FC", "LC", "TC")
FINAL_PREFIXES = ("FV", "LV", "TV", "PV", "CV")

# Scores for a pattern. These do not mean the plant is correct.
PATTERN_STRUCTURE_SCORE = 0.80
PATTERN_ROLE_CONFIRMED_SCORE = 0.90
PATTERN_PARTIAL_SCORE = 0.70
CHECK_VERSION = "D3"
COVERAGE_VERSION = "D4"

# A drawing is "verified" only when tag recall meets this cutoff and the other
# criteria in services/coverage.py all pass. 1.0 means every extracted tag
# that we counted is on a node. This is not an accuracy claim.
TAG_RECALL_MIN = 1.0

# Ledger reason codes. Only the unexplained ones block the verified state.
UNEXPLAINED_REASON_CODES = ("segment_not_in_edge", "detection_not_in_graph")
VERIFICATION_DISCLAIMER = "Passed the defined automated checks. This is not an engineering or safety certification."
SIMPLIFY_VERSION = "E1"

# A junction is pass-through only when it has this many incident edges.
PASS_THROUGH_DEGREE = 2
LAYOUT_VERSION = "E2"
# Graphs larger than this do not get invented coordinates. The layout call returns an error.
MAX_LAYOUT_NODES = 200
# Fallback symbol box when a node has no bbox, in PDF points.
DEFAULT_NODE_WIDTH = 48.0
DEFAULT_NODE_HEIGHT = 32.0
# ELK spacing. Larger gaps keep orthogonal routes out of node boxes.
LAYOUT_NODE_GAP = 48
LAYOUT_LAYER_GAP = 70
# A route that would enter a node box is pushed outside by this many points.
LAYOUT_ROUTE_MARGIN = 10.0
# Flow trace will not walk farther than this many steps.
TRACE_MAX_DEPTH = 12
RENDER_VERSION = "E3"
PROCESS_COLOR = "#0f766e"
SIGNAL_COLOR = "#1d4ed8"
OTHER_COLOR = "#4b5563"
REVIEW_COLOR = "#b91c1c"
DISCLAIMER = VERIFICATION_DISCLAIMER

def capped_score(source_score: float, severities: list[str]) -> float:
    """Combine a source score with check severities.

    The result is never higher than source_score. An error caps it at
    UNCERTAIN_CAP so the label becomes uncertain. Warnings and info notes
    do not raise or lower the score.
    """
    score = min(1.0, max(0.0, source_score))
    if "error" in severities:
        return min(score, UNCERTAIN_CAP)
    return score

# Explicit phrases. A bare letter, or the left/right side of the page, is not a direction.
FLOW_OUT_PHRASES = ("FLOW OUT", "OUTLET")
FLOW_IN_PHRASES = ("FLOW IN", "INLET")
TERMINAL_MARKERS = ("OFF-PAGE", "OFF PAGE", "OPC")
NOZZLE_MARKER = "nozzle"

# Directions stored on Phase C arrow and valve items. Y increases downward.
DIRECTION_VECTORS = {
    "right": (1.0, 0.0),
    "left": (-1.0, 0.0),
    "down": (0.0, 1.0),
    "up": (0.0, -1.0),
}

COLLINEAR_COS_LIMIT = -math.cos(math.radians(COLLINEAR_MAX_DEGREES))
DIRECTION_COS_MIN = math.cos(math.radians(DIRECTION_ANGLE_DEGREES))


def certainty_for_score(score: float) -> str:
    """Map a score to confirmed, likely, or uncertain. This does not raise the score."""
    if score >= CONFIRMED_MIN:
        return "confirmed"
    if score >= LIKELY_MIN:
        return "likely"
    return "uncertain"
