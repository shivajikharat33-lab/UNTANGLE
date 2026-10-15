"""The working diagram: nodes, edges, and groups.

Nothing in this schema deletes an element. Callers set kept=false and a
reason when an item stays in the data but is hidden from the sketch.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.confidence import Confidence
from app.schemas.rules import RuleResult

NodeType = Literal["equipment", "instrument", "valve", "junction", "endpoint"]
Direction = Literal["forward", "reverse", "bidirectional", "unknown"]
LineType = Literal["process", "signal", "other"]
CrossingMode = Literal["auto", "avoid", "keep"]
EdgeStatus = Literal["auto", "user_added", "user_edited", "user_removed"]
GroupType = Literal["duty_standby", "control_loop"]


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


class Group(BaseModel):
    """Nodes that belong together, such as a duty/standby pair or a control loop.

    shared_upstream and shared_downstream are node ids, not tags.
    """

    id: str = Field(min_length=1)
    type: GroupType
    member_node_ids: list[str] = Field(default_factory=list)
    shared_upstream: list[str] = Field(default_factory=list)
    shared_downstream: list[str] = Field(default_factory=list)


class DiagramGraph(BaseModel):
    """The whole working graph for one drawing."""

    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    groups: list[Group] = Field(default_factory=list)
