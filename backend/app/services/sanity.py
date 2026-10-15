"""Read-only sanity warnings. They are not facts and they do not edit the graph."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.graph import DiagramGraph


class SanityWarning(BaseModel):
    id: str
    rule: str
    severity: str
    reason: str
    item_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


def sanity_warnings(graph: DiagramGraph) -> list[SanityWarning]:
    """Return warnings. A clean graph returns an empty list."""
    found: list[SanityWarning] = []
    found.extend(_ab_symmetry(graph))
    found.extend(_unattached_instruments(graph))
    found.extend(_duplicate_tags(graph))
    found.extend(_prefix_mismatch(graph))
    return found


def _ab_symmetry(graph: DiagramGraph) -> list[SanityWarning]:
    tags = {node.tag.upper() for node in graph.nodes if node.tag}
    warnings: list[SanityWarning] = []
    for tag in sorted(tags):
        if tag.endswith("A") and f"{tag[:-1]}B" not in tags:
            node_ids = [node.id for node in graph.nodes if node.tag.upper() == tag]
            warnings.append(SanityWarning(
                id=f"sanity-ab-{tag}",
                rule="ab-symmetry",
                severity="warning",
                reason=f"{tag} has no matching B tag. This is a warning, not a fact that B is missing from the plant.",
                item_ids=node_ids,
                evidence=[f"Tag {tag} is on the graph and {tag[:-1]}B is not."],
            ))
    return warnings


def _unattached_instruments(graph: DiagramGraph) -> list[SanityWarning]:
    loose = [node for node in graph.nodes if node.type == "instrument" and node.attachment == "unattached"]
    if not loose:
        return []
    return [SanityWarning(
        id="sanity-unattached",
        rule="unattached-instrument",
        severity="warning",
        reason="An instrument is not attached to a pipe or a piece of equipment. This is a warning, not proof it is unused.",
        item_ids=[node.id for node in loose],
        evidence=[node.tag or node.id for node in loose],
    )]


def _duplicate_tags(graph: DiagramGraph) -> list[SanityWarning]:
    seen: dict[str, list[str]] = {}
    for node in graph.nodes:
        if node.tag:
            seen.setdefault(node.tag.upper(), []).append(node.id)
    warnings = []
    for tag, ids in sorted(seen.items()):
        if len(ids) > 1:
            warnings.append(SanityWarning(
                id=f"sanity-duplicate-{tag}",
                rule="duplicate-tag",
                severity="warning",
                reason=f"{tag} is on more than one node. This is a warning, not a decision about which node owns it.",
                item_ids=ids,
                evidence=[tag],
            ))
    return warnings


def _prefix_mismatch(graph: DiagramGraph) -> list[SanityWarning]:
    warnings = []
    for node in graph.nodes:
        prefix = node.tag.split("-", 1)[0].upper() if node.tag else ""
        if prefix in {"PT", "FT", "LT", "TT"} and node.type == "equipment":
            warnings.append(SanityWarning(
                id=f"sanity-prefix-{node.id}",
                rule="prefix-mismatch",
                severity="info",
                reason=f"{node.tag} uses an instrument prefix but the node type is equipment. This is a warning, not a retag.",
                item_ids=[node.id],
                evidence=[f"prefix {prefix}", f"type {node.type}"],
            ))
    return warnings
