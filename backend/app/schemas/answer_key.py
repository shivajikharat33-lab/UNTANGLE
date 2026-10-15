"""Hand-built expected results for one drawing.

Answer keys use tags, because a person writes them before node ids exist.
"""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.graph import Direction, LineType


class ExpectedTag(BaseModel):
    """A tag that must appear."""

    tag: str = Field(min_length=1)
    signal: str = ""


class ExpectedEquipment(BaseModel):
    """A piece of equipment that must appear."""

    tag: str = Field(min_length=1)
    label: str = ""


class ExpectedConnection(BaseModel):
    """A connection that must appear, including flow direction.

    JSON uses "from" and "to". The Python attribute is from_.
    """

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)
    direction: Direction
    line_type: LineType = "process"


class ExpectedDutyStandbyGroup(BaseModel):
    """Equipment that should be drawn as parallel duty/standby lines.

    member_tags, shared_upstream, and shared_downstream are tags.
    """

    id: str = Field(min_length=1)
    member_tags: list[str] = Field(default_factory=list)
    shared_upstream: list[str] = Field(default_factory=list)
    shared_downstream: list[str] = Field(default_factory=list)


class AnswerKey(BaseModel):
    """The expected tags, equipment, connections, and duty/standby groups."""

    drawing_id: str = Field(min_length=1)
    expected_tags: list[ExpectedTag] = Field(default_factory=list)
    expected_equipment: list[ExpectedEquipment] = Field(default_factory=list)
    expected_connections: list[ExpectedConnection] = Field(default_factory=list)
    expected_duty_standby_groups: list[ExpectedDutyStandbyGroup] = Field(
        default_factory=list
    )
