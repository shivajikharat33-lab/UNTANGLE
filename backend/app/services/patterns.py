"""Pump groups and control loops. Drawing position is not used.

A detector is a class with detect(). Register it to add a pattern type
without changing the runner.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Protocol

from app import graph_config as cfg
from app.config import level_for_score
from app.errors import AppError
from app.schemas.confidence import Confidence
from app.schemas.graph import DiagramGraph, Edge, Evidence, Group, Node, Pattern
from app.schemas.reports import TagReport
from app.services.io_list import suffix_hint_for
from app.services.storage import GRAPH_NAME, job_folder, read_json, write_json


@dataclass
class PatternContext:
    """Facts the detectors are allowed to read. They do not invent new ones."""

    report: TagReport
    notes: list[str] = field(default_factory=list)


class PatternDetector(Protocol):
    """One pattern type."""

    name: str

    def detect(self, graph: DiagramGraph, context: PatternContext) -> list[Pattern]:
        """Return the patterns this detector can support. An empty list is allowed."""


DETECTORS: list[PatternDetector] = []


def register(detector: PatternDetector) -> PatternDetector:
    """Add a detector. The runner does not need an edit for the new type to run."""
    DETECTORS.append(detector)
    return detector


def apply_patterns(graph: DiagramGraph, report: TagReport, notes: list[str] | None = None) -> DiagramGraph:
    """Fill patterns and the older groups list. The same graph comes back."""
    context = PatternContext(report=report, notes=list(notes or []))
    found: list[Pattern] = []
    for detector in DETECTORS:
        found.extend(detector.detect(graph, context))
    graph.patterns = found
    graph.groups = [_group_from_pattern(pattern) for pattern in found]
    graph.processing_version = cfg.PATTERN_VERSION
    return graph


def load_patterns(upload_dir: str, job_id: str) -> list[Pattern]:
    """Read patterns from graph.json. A missing graph is a 404."""
    path = job_folder(upload_dir, job_id) / GRAPH_NAME
    if not path.is_file():
        raise AppError(404, "NOT_FOUND", "Patterns have not been run for this project.", {"job_id": job_id})
    graph = DiagramGraph.model_validate(read_json(path))
    if graph.processing_version not in {cfg.PATTERN_VERSION, "D3", "D4"}:
        raise AppError(404, "NOT_FOUND", "Patterns have not been run for this project.", {"job_id": job_id})
    return graph.patterns


def write_graph(upload_dir: str, job_id: str, graph: DiagramGraph) -> None:
    """Replace graph.json after patterns are added. Originals stay untouched."""
    write_json(job_folder(upload_dir, job_id) / GRAPH_NAME, graph.model_dump(mode="json"))


def _confidence(score: float, reason: str) -> Confidence:
    bounded = min(1.0, max(0.0, score))
    return Confidence(level=level_for_score(bounded), score=bounded, reason=reason)  # type: ignore[arg-type]


def _pattern_id(kind: str, member_ids: list[str]) -> str:
    raw = kind + "|" + "|".join(sorted(member_ids))
    return f"{kind}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _prefix(tag: str) -> str:
    return tag.split("-", 1)[0].upper()


def _loop_number(tag: str) -> str:
    digits = "".join(character for character in tag if character.isdigit())
    return digits


def _matches(prefix: str, choices: tuple[str, ...]) -> bool:
    return any(prefix == choice for choice in choices)


class PumpGroupDetector:
    """Pumps that reach the same header nodes. Page position is ignored."""

    name = "pump_group"

    def detect(self, graph: DiagramGraph, context: PatternContext) -> list[Pattern]:
        pumps = [node for node in graph.nodes if node.type == "equipment" and (node.subtype == "pump" or _prefix(node.tag) == "P")]
        if len(pumps) < 2:
            return []
        by_id = {node.id: node for node in graph.nodes}
        reached = {pump.id: _headers_and_valves(pump.id, graph, by_id) for pump in pumps}
        parent = {pump.id: pump.id for pump in pumps}

        def find(item: str) -> str:
            while parent[item] != item:
                parent[item] = parent[parent[item]]
                item = parent[item]
            return item

        for left in pumps:
            for right in pumps:
                if left.id >= right.id:
                    continue
                if reached[left.id][0] & reached[right.id][0]:
                    parent[find(left.id)] = find(right.id)
        groups: dict[str, list[Node]] = {}
        for pump in pumps:
            groups.setdefault(find(pump.id), []).append(pump)
        patterns: list[Pattern] = []
        for members in groups.values():
            if len(members) < 2:
                continue
            common: set[str] = set.intersection(*(reached[member.id][0] for member in members))
            if not common:
                continue
            reasons: list[str] = []
            if len(common) < 2:
                reasons.append("The pumps share only one header, so suction and discharge are not both shared.")
            if len(members) % 2 == 1:
                reasons.append("The group has an odd number of pumps.")
            valve_ids: list[str] = []
            check_ids: list[str] = []
            edge_ids: list[str] = []
            for member in members:
                headers, valves, edges, missing_valve = reached[member.id]
                _ = headers
                edge_ids.extend(edges)
                if missing_valve:
                    reasons.append(f"{member.tag or member.id} has a leg with no valve.")
                for valve in valves:
                    valve_ids.append(valve.id)
                    if valve.subtype == "check":
                        check_ids.append(valve.id)
            role, role_certainty, member_roles = _roles(members, context)
            score = cfg.PATTERN_ROLE_CONFIRMED_SCORE if role_certainty == "confirmed" else (
                cfg.PATTERN_PARTIAL_SCORE if reasons else cfg.PATTERN_STRUCTURE_SCORE
            )
            patterns.append(
                Pattern(
                    id=_pattern_id("pump_group", [member.id for member in members]),
                    type="pump_group",
                    member_node_ids=[member.id for member in members],
                    member_edge_ids=sorted(set(edge_ids)),
                    confidence=_confidence(score, "The pumps reach the same header nodes. This does not prove which pump runs."),
                    certainty=cfg.certainty_for_score(score),  # type: ignore[arg-type]
                    evidence=[_evidence("graph", "Shared headers were found by walking process edges, not by page position.")],
                    needs_review=bool(reasons),
                    review_reasons=list(dict.fromkeys(reasons)),
                    role=role,
                    role_certainty=role_certainty,  # type: ignore[arg-type]
                    member_roles=member_roles,
                    header_ids=sorted(common),
                    valve_ids=sorted(set(valve_ids)),
                    check_valve_ids=sorted(set(check_ids)),
                    suction_ids=_sided_headers(members, reached, "suction"),
                    discharge_ids=_sided_headers(members, reached, "discharge"),
                )
            )
        return patterns


class ControlLoopDetector:
    """Loops from a shared loop number, then from signal lines. ISA letters only label parts."""

    name = "control_loop"

    def detect(self, graph: DiagramGraph, context: PatternContext) -> list[Pattern]:
        candidates = [node for node in graph.nodes if node.tag and _part_kind(node) is not None]
        by_number: dict[str, list[Node]] = {}
        for node in candidates:
            number = _loop_number(node.tag)
            if not number:
                continue
            by_number.setdefault(number, []).append(node)
        used: set[str] = set()
        patterns: list[Pattern] = []
        for number, members in sorted(by_number.items()):
            if len(members) < 2:
                continue
            patterns.append(_loop_pattern(members, f"Loop number {number} is shared. ISA letters only name the parts.", context))
            used.update(node.id for node in members)
        components = _signal_components(graph, [node for node in candidates if node.id not in used])
        for members in components:
            if len(members) < 2:
                continue
            patterns.append(_loop_pattern(members, "A signal line connects these tags. ISA letters only name the parts.", context))
        return patterns


def _loop_pattern(members: list[Node], reason: str, context: PatternContext) -> Pattern:
    _ = context
    sensor = next((node for node in members if _part_kind(node) == "sensor"), None)
    controller = next((node for node in members if _part_kind(node) == "controller"), None)
    final = next((node for node in members if _part_kind(node) == "final"), None)
    missing = [name for name, node in (("sensor", sensor), ("controller", controller), ("final element", final)) if node is None]
    score = cfg.PATTERN_STRUCTURE_SCORE if not missing else cfg.PATTERN_PARTIAL_SCORE
    return Pattern(
        id=_pattern_id("control_loop", [node.id for node in members]),
        type="control_loop",
        member_node_ids=[node.id for node in members],
        confidence=_confidence(score, "The loop lists only parts that were found. Missing parts were not invented."),
        certainty=cfg.certainty_for_score(score),  # type: ignore[arg-type]
        evidence=[_evidence("tag", reason)],
        needs_review=bool(missing),
        review_reasons=[f"The loop has no {part}." for part in missing],
        sensor_id=sensor.id if sensor else "",
        controller_id=controller.id if controller else "",
        final_element_id=final.id if final else "",
        missing_parts=missing,
    )


def _part_kind(node: Node) -> str | None:
    prefix = _prefix(node.tag)
    if _matches(prefix, cfg.SENSOR_PREFIXES):
        return "sensor"
    if _matches(prefix, cfg.CONTROLLER_PREFIXES):
        return "controller"
    if _matches(prefix, cfg.FINAL_PREFIXES):
        return "final"
    return None


def _signal_components(graph: DiagramGraph, nodes: list[Node]) -> list[list[Node]]:
    by_id = {node.id: node for node in nodes}
    parent = {node.id: node.id for node in nodes}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for edge in graph.edges:
        if edge.line_type != "signal":
            continue
        if edge.from_id in parent and edge.to_id in parent:
            parent[find(edge.from_id)] = find(edge.to_id)
    groups: dict[str, list[Node]] = {}
    for node in nodes:
        groups.setdefault(find(node.id), []).append(node)
    return list(groups.values())


def _process_neighbors(node_id: str, edges: list[Edge]) -> list[tuple[str, Edge]]:
    found: list[tuple[str, Edge]] = []
    for edge in edges:
        if edge.line_type != "process":
            continue
        if edge.from_id == node_id:
            found.append((edge.to_id, edge))
        elif edge.to_id == node_id:
            found.append((edge.from_id, edge))
    return found


def _headers_and_valves(pump_id: str, graph: DiagramGraph, by_id: dict[str, Node]) -> tuple[set[str], list[Node], list[str], bool]:
    headers: set[str] = set()
    valves: list[Node] = []
    edge_ids: list[str] = []
    missing_valve = False
    for start_id, start_edge in _process_neighbors(pump_id, graph.edges):
        seen = {pump_id}
        current = start_id
        current_edge = start_edge
        leg_valves: list[Node] = []
        while current not in seen and current in by_id:
            seen.add(current)
            edge_ids.append(current_edge.id)
            node = by_id[current]
            if node.type == "valve":
                leg_valves.append(node)
            nxt = [(other, edge) for other, edge in _process_neighbors(current, graph.edges) if other not in seen]
            degree = len(_process_neighbors(current, graph.edges))
            if node.type == "junction" and degree >= 3:
                headers.add(current)
                valves.extend(leg_valves)
                missing_valve = missing_valve or not leg_valves
                break
            if node.type in {"equipment", "terminal"}:
                headers.add(current)
                valves.extend(leg_valves)
                missing_valve = missing_valve or not leg_valves
                break
            if len(nxt) != 1:
                if node.type == "junction":
                    headers.add(current)
                    valves.extend(leg_valves)
                    missing_valve = missing_valve or not leg_valves
                break
            current, current_edge = nxt[0]
    return headers, valves, edge_ids, missing_valve


def _sided_headers(members: list[Node], reached: dict[str, tuple[set[str], list[Node], list[str], bool]], side: str) -> list[str]:
    _ = members, reached, side
    # Direction is not used to rename a header unless every leg agrees.
    # That check is left empty until a later rule has explicit flow on every leg.
    return []


def _roles(members: list[Node], context: PatternContext) -> tuple[str, str, dict[str, str]]:
    member_roles: dict[str, str] = {}
    certainties: list[str] = []
    for member in members:
        role, certainty = _one_role(member, context)
        member_roles[member.id] = role
        certainties.append(certainty)
    if "confirmed" in certainties:
        pattern_certainty = "confirmed"
    elif "likely" in certainties:
        pattern_certainty = "likely"
    else:
        pattern_certainty = "uncertain"
    named = any(role in {"duty", "standby"} for role in member_roles.values())
    suffix = any(suffix_hint_for(member.tag or "") for member in members)
    group_role = "duty_standby" if named or suffix else "unknown"
    return group_role, pattern_certainty, member_roles


def _one_role(node: Node, context: PatternContext) -> tuple[str, str]:
    tag = (node.tag or "").upper()
    suffix = suffix_hint_for(tag or "")
    texts = list(context.notes)
    for row in context.report.rows:
        if row.tag.upper() == tag:
            texts.append(f"{tag} {row.signal}")
    explicit = ""
    for text in texts:
        upper = text.upper()
        if tag and tag not in upper and (not suffix or suffix not in upper):
            continue
        if tag and tag not in upper:
            continue
        if cfg.DUTY_WORD in upper and not any(word in upper for word in cfg.STANDBY_WORDS):
            explicit = "duty"
        elif any(word in upper for word in cfg.STANDBY_WORDS):
            explicit = "standby"
    if explicit:
        return explicit, "confirmed"
    if suffix:
        return "unknown", "likely"
    return "unknown", "uncertain"


def _evidence(source: str, description: str) -> Evidence:
    return Evidence(source=source, description=description, page=None)


def _group_from_pattern(pattern: Pattern) -> Group:
    group_type = "duty_standby" if pattern.type == "pump_group" else "control_loop"
    return Group(
        id=pattern.id,
        type=group_type,  # type: ignore[arg-type]
        member_node_ids=list(pattern.member_node_ids),
        shared_upstream=list(pattern.suction_ids),
        shared_downstream=list(pattern.discharge_ids),
    )


register(PumpGroupDetector())
register(ControlLoopDetector())
