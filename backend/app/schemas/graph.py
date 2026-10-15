"""The working diagram: nodes, edges, and groups.

Nothing in this schema deletes an element. Callers set kept=false and a
reason when an item stays in the data but is hidden from the sketch.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.confidence import Confidence
from app.schemas.rules import RuleResult

NodeType = Literal["equipment", "instrument", "valve", "junction", "endpoint", "terminal"]
Direction = Literal["forward", "reverse", "bidirectional", "unknown"]
LineType = Literal["process", "signal", "other"]
CrossingMode = Literal["auto", "avoid", "keep"]
EdgeStatus = Literal["auto", "user_added", "user_edited", "user_removed"]
GroupType = Literal["duty_standby", "control_loop"]
# confirmed / likely / uncertain follow the same cutoffs as high / medium / low.
Certainty = Literal["confirmed", "likely", "uncertain"]


class BBox(BaseModel):
    """A rectangle on one PDF page. Origin and units are decided by the reader."""

    page: int = Field(ge=1)
    x: float
    y: float
    w: float = Field(ge=0)
    h: float = Field(ge=0)


class Point(BaseModel):
    """One point on a drawn line."""

    x: float
    y: float


class Evidence(BaseModel):
    """A fact that supports an edge or a report row."""

    source: str = Field(min_length=1)
    description: str
    page: int | None = Field(default=None, ge=1)


class Node(BaseModel):
    """One symbol or junction on the diagram."""

    id: str = Field(min_length=1)
    type: NodeType
    tag: str = ""
    label: str = ""
    signal: str = ""
    bbox: BBox | None = None
    kept: bool = True
    detail_level: Literal[1, 2, 3] = 2
    confidence: Confidence
    reason: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    certainty: Certainty = "uncertain"
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    subtype: str = ""
    attachment: str = ""
    attachment_target: str = ""
    source_id: str = ""
    pointing: str = ""


class Edge(BaseModel):
    """A connection from one node to another.

    direction "forward" means flow runs from from_id to to_id.
    direction "reverse" means flow runs from to_id to from_id.
    """

    id: str = Field(min_length=1)
    from_id: str = Field(min_length=1)
    to_id: str = Field(min_length=1)
    direction: Direction
    line_type: LineType
    color: str = ""
    style: str = ""
    crossing_mode: CrossingMode = "auto"
    status: EdgeStatus = "auto"
    polyline: list[Point] = Field(default_factory=list)
    confidence: Confidence
    evidence: list[Evidence] = Field(default_factory=list)
    rule_results: list[RuleResult] = Field(default_factory=list)
    direction_evidence: list[Evidence] = Field(default_factory=list)
    segment_ids: list[str] = Field(default_factory=list)
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)
    certainty: Certainty = "uncertain"


class Group(BaseModel):
    """Nodes that belong together, such as a duty/standby pair or a control loop.

    shared_upstream and shared_downstream are node ids, not tags.
    """

    id: str = Field(min_length=1)
    type: GroupType
    member_node_ids: list[str] = Field(default_factory=list)
    shared_upstream: list[str] = Field(default_factory=list)
    shared_downstream: list[str] = Field(default_factory=list)


class StructureNote(BaseModel):
    """A structural observation. It does not delete the items it names."""

    kind: str = Field(min_length=1)
    item_ids: list[str] = Field(default_factory=list)
    message: str


class PreservedMeeting(BaseModel):
    """A crossing or an ambiguous meeting kept for a later stage. It is not a connection."""

    id: str = Field(min_length=1)
    page: int = Field(ge=1)
    position: list[float]
    line_ids: list[str] = Field(default_factory=list)
    decision: str
    reason: str


class CoverageMetric(BaseModel):
    """A count with its denominator. percentage is null when the denominator is zero."""

    name: str
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    percentage: float | None = None
    missing_ids: list[str] = Field(default_factory=list)


class LedgerEntry(BaseModel):
    """One extracted item that is not represented as a connected graph member."""

    item_id: str
    item_type: str
    page: int | None = None
    position: list[float] = Field(default_factory=list)
    reason_code: str
    reason_text: str
    stage: str


class VerificationStatus(BaseModel):
    """Automated criteria only. verified is not an engineering or safety approval."""

    state: Literal["verified", "not_verified", "needs_review"]
    failing: list[str] = Field(default_factory=list)
    disclaimer: str


class SimplifiedNode(Node):
    """A kept node. original_ids lists the graph ids it stands for."""

    original_ids: list[str] = Field(default_factory=list)


class SimplifiedEdge(Edge):
    """A kept or merged edge. original_ids lists the graph edge ids inside it."""

    original_ids: list[str] = Field(default_factory=list)


class SimplifiedGraph(BaseModel):
    """A separate copy. It does not replace graph.json."""

    nodes: list[SimplifiedNode] = Field(default_factory=list)
    edges: list[SimplifiedEdge] = Field(default_factory=list)
    ledger: list[LedgerEntry] = Field(default_factory=list)
    id_map: dict[str, str] = Field(default_factory=dict)
    connectivity_ok: bool = False
    failed_check: bool = False
    processing_version: str = ""


class LedgerPage(BaseModel):
    """One page of the hidden-item ledger."""

    items: list[LedgerEntry] = Field(default_factory=list)
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)


class Finding(BaseModel):
    """One check result. The message describes the rule, not a certified fault."""

    id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    category: str
    severity: Literal["error", "warning", "info"]
    title: str
    message: str
    affected_ids: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    review_action: str = ""


class Pattern(BaseModel):
    """A pump group or a control loop. A flag means the rules did not finish the pattern."""

    id: str = Field(min_length=1)
    type: Literal["pump_group", "control_loop"]
    member_node_ids: list[str] = Field(default_factory=list)
    member_edge_ids: list[str] = Field(default_factory=list)
    confidence: Confidence
    certainty: Certainty = "uncertain"
    evidence: list[Evidence] = Field(default_factory=list)
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    role: str = "unknown"
    role_certainty: Certainty = "uncertain"
    member_roles: dict[str, str] = Field(default_factory=dict)
    header_ids: list[str] = Field(default_factory=list)
    suction_ids: list[str] = Field(default_factory=list)
    discharge_ids: list[str] = Field(default_factory=list)
    valve_ids: list[str] = Field(default_factory=list)
    check_valve_ids: list[str] = Field(default_factory=list)
    sensor_id: str = ""
    controller_id: str = ""
    final_element_id: str = ""
    missing_parts: list[str] = Field(default_factory=list)


class GraphSummary(BaseModel):
    """Counts only. This is not a claim that the connections are correct."""

    nodes: int = 0
    edges: int = 0
    junctions: int = 0
    terminals: int = 0
    orphans: int = 0
    dead_ends: int = 0
    unattached_instruments: int = 0
    disconnected_components: int = 0
    duplicates: int = 0
    unknown_direction: int = 0
    needs_review: int = 0
    crossings: int = 0


class DiagramGraph(BaseModel):
    """The whole working graph for one drawing."""

    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    groups: list[Group] = Field(default_factory=list)
    patterns: list[Pattern] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    coverage: list[CoverageMetric] = Field(default_factory=list)
    ledger: list[LedgerEntry] = Field(default_factory=list)
    verification: VerificationStatus | None = None
    structure: list[StructureNote] = Field(default_factory=list)
    crossings: list[PreservedMeeting] = Field(default_factory=list)
    ambiguous_meetings: list[PreservedMeeting] = Field(default_factory=list)
    source_sha256: str = ""
    processing_version: str = ""
