"""Configured checks over the graph. Adding a rule does not require an engine edit.

A passing check is not a statement that the plant is correct.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from app import graph_config as cfg
from app.config import level_for_score
from app.errors import AppError
from app.schemas.confidence import Confidence
from app.schemas.graph import DiagramGraph, Evidence, Finding, Node
from app.schemas.reports import TagReport
from app.services.pdf_extract import ExtractionResult
from app.services.storage import GRAPH_NAME, job_folder, read_json, write_json


@dataclass
class CheckContext:
    """Earlier results the rules may read. They do not match tags again."""

    report: TagReport
    extraction: ExtractionResult | None = None


class CheckRule(Protocol):
    """One named check."""

    rule_id: str
    category: str
    severity: str
    title: str
    explanation: str

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        """Return findings. An empty list means this rule found nothing."""


RULES: list[CheckRule] = []


def register(rule: CheckRule) -> CheckRule:
    """Add a rule. The runner iterates the registry and does not name the rule."""
    RULES.append(rule)
    return rule


def apply_checks(graph: DiagramGraph, report: TagReport, extraction: ExtractionResult | None = None) -> DiagramGraph:
    """Run every registered rule, then cap confidence and store review reasons."""
    context = CheckContext(report=report, extraction=extraction)
    findings: list[Finding] = []
    for rule in RULES:
        findings.extend(rule.run(graph, context))
    graph.findings = findings
    _apply_review(graph, findings)
    graph.processing_version = cfg.CHECK_VERSION
    return graph


def load_findings(upload_dir: str, job_id: str) -> list[Finding]:
    """Read findings from graph.json. A missing check run is a 404."""
    graph = _load_checked_graph(upload_dir, job_id)
    return graph.findings


def load_finding(upload_dir: str, job_id: str, finding_id: str) -> Finding:
    """Return one finding. An unknown id is a 404."""
    for finding in load_findings(upload_dir, job_id):
        if finding.id == finding_id:
            return finding
    raise AppError(404, "NOT_FOUND", "That finding does not exist.", {"finding_id": finding_id})


def write_graph(upload_dir: str, job_id: str, graph: DiagramGraph) -> None:
    """Replace graph.json after checks. Original uploads stay untouched."""
    write_json(job_folder(upload_dir, job_id) / GRAPH_NAME, graph.model_dump(mode="json"))


def _load_checked_graph(upload_dir: str, job_id: str) -> DiagramGraph:
    path = job_folder(upload_dir, job_id) / GRAPH_NAME
    if not path.is_file():
        raise AppError(404, "NOT_FOUND", "Checks have not been run for this project.", {"job_id": job_id})
    graph = DiagramGraph.model_validate(read_json(path))
    if graph.processing_version not in {cfg.CHECK_VERSION, "D4"}:
        raise AppError(404, "NOT_FOUND", "Checks have not been run for this project.", {"job_id": job_id})
    return graph


def _finding(rule: CheckRule, message: str, affected: list[str], evidence: list[Evidence], action: str) -> Finding:
    raw = "|".join([rule.rule_id, message, *sorted(affected)])
    return Finding(
        id=f"finding-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}",
        rule_id=rule.rule_id,
        category=rule.category,
        severity=rule.severity,  # type: ignore[arg-type]
        title=rule.title,
        message=message,
        affected_ids=affected,
        evidence=evidence,
        review_action=action,
    )


def _apply_review(graph: DiagramGraph, findings: list[Finding]) -> None:
    by_item: dict[str, list[Finding]] = {}
    for finding in findings:
        if finding.severity == "info":
            continue
        for item_id in finding.affected_ids:
            by_item.setdefault(item_id, []).append(finding)
    for item in [*graph.nodes, *graph.edges]:
        related = by_item.get(item.id, [])
        severities = [finding.severity for finding in related]
        score = cfg.capped_score(item.confidence.score, severities)
        if score != item.confidence.score:
            item.confidence = Confidence(
                level=level_for_score(score),  # type: ignore[arg-type]
                score=score,
                reason=f"{item.confidence.reason} An error check capped the score at {score:.2f}. It was not raised.",
            )
        item.certainty = cfg.certainty_for_score(item.confidence.score)  # type: ignore[assignment]
        reasons = list(item.review_reasons)
        if item.certainty == "uncertain" and "The confidence label is uncertain." not in reasons:
            reasons.append("The confidence label is uncertain.")
        for finding in related:
            if finding.message not in reasons:
                reasons.append(finding.message)
        if item.needs_review and "An earlier stage flagged this item." not in reasons:
            reasons.append("An earlier stage flagged this item.")
        item.review_reasons = reasons
        item.needs_review = item.needs_review or bool(related) or item.certainty == "uncertain"


class _Orphans:
    rule_id = "R-GRAPH-001"
    category = "graph"
    severity = "warning"
    title = "Orphan node"
    explanation = "A symbol or junction has no pipe or signal edge."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = context
        note = next((item for item in graph.structure if item.kind == "orphan"), None)
        if note is None or not note.item_ids:
            return []
        return [_finding(self, note.message, note.item_ids, [_ev("graph", note.message)], "Look at each listed node and see whether a line should reach it.")]


class _DeadEnds:
    rule_id = "R-GRAPH-002"
    category = "graph"
    severity = "warning"
    title = "Dead end"
    explanation = "A pipe end does not meet a symbol or a junction."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = context
        note = next((item for item in graph.structure if item.kind == "dead_end"), None)
        if note is None or not note.item_ids:
            return []
        return [_finding(self, note.message, note.item_ids, [_ev("graph", note.message)], "Check whether the end is an off-page connector or a gap in the line read.")]


class _Disconnected:
    rule_id = "R-GRAPH-003"
    category = "graph"
    severity = "warning"
    title = "Disconnected components"
    explanation = "The graph has more than one separate piece."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = context
        note = next((item for item in graph.structure if item.kind == "disconnected"), None)
        if note is None:
            return []
        return [_finding(self, note.message, note.item_ids, [_ev("graph", note.message)], "Do not join the pieces unless a line between them is on the drawing.")]


class _Duplicates:
    rule_id = "R-GRAPH-004"
    category = "graph"
    severity = "warning"
    title = "Duplicate nodes"
    explanation = "Two nodes of the same type sit on the same spot."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = context
        note = next((item for item in graph.structure if item.kind == "duplicate"), None)
        if note is None or not note.item_ids:
            return []
        return [_finding(self, note.message, note.item_ids, [_ev("graph", note.message)], "Keep both until a person decides which symbol is the real one.")]


class _TiedEnds:
    rule_id = "R-GRAPH-005"
    category = "graph"
    severity = "warning"
    title = "Tied attachment"
    explanation = "An edge end had two equally close nodes, so neither was chosen."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = context
        findings: list[Finding] = []
        for edge in graph.edges:
            if not edge.candidate_ids:
                continue
            findings.append(_finding(self, "This edge had two equally close nodes and was not attached to either.", [edge.id, *edge.candidate_ids], edge.evidence, "Choose the node only if the drawing shows which one the line touches."))
        return findings


class _UnknownDirection:
    rule_id = "R-FLOW-001"
    category = "flow"
    severity = "info"
    title = "Unknown direction"
    explanation = "No arrow, check valve, nozzle, or terminal phrase set the direction."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = context
        affected = [edge.id for edge in graph.edges if edge.direction == "unknown" and not any("disagrees" in reason for reason in edge.review_reasons)]
        if not affected:
            return []
        return [_finding(self, "These edges have no explicit direction evidence.", affected, [_ev("graph", "Direction was left unknown.")], "Add direction only from an arrow or another explicit symbol.")]


class _ConflictingDirection:
    rule_id = "R-FLOW-002"
    category = "flow"
    severity = "warning"
    title = "Conflicting direction"
    explanation = "Direction evidence on one edge does not agree."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = context
        findings: list[Finding] = []
        for edge in graph.edges:
            if any("disagrees" in reason for reason in edge.review_reasons):
                findings.append(_finding(self, "Direction evidence disagrees, so the direction was left unknown.", [edge.id], edge.direction_evidence, "Read the arrows or valve symbol again before choosing a direction."))
        return findings


class _PumpDischarge:
    rule_id = "R-FLOW-003"
    category = "flow"
    severity = "warning"
    title = "Pump discharge not resolved"
    explanation = "No explicit direction leaves the pump."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = context
        findings: list[Finding] = []
        for node in graph.nodes:
            if node.subtype != "pump" and not (node.tag.startswith("P-") or node.tag.startswith("P")):
                continue
            if node.type != "equipment":
                continue
            if _leaves(node.id, graph):
                continue
            findings.append(_finding(self, f"{node.tag or node.id} has no edge whose direction leaves the pump.", [node.id], node.evidence, "Do not invent a discharge direction from the side of the page."))
        return findings


class _DeadEndFlow:
    rule_id = "R-FLOW-004"
    category = "flow"
    severity = "warning"
    title = "Flow ends at equipment"
    explanation = "Known flow stops on equipment that is not a terminal."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = context
        by_id = {node.id: node for node in graph.nodes}
        findings: list[Finding] = []
        for edge in graph.edges:
            if edge.direction not in {"forward", "reverse"}:
                continue
            downstream = edge.to_id if edge.direction == "forward" else edge.from_id
            node = by_id.get(downstream)
            if node is None or node.type != "equipment":
                continue
            if _leaves(node.id, graph):
                continue
            findings.append(_finding(self, f"Flow reaches {node.tag or node.id} and no explicit direction leaves it.", [edge.id, node.id], edge.direction_evidence, "Check the drawing before treating this equipment as the end of the line."))
        return findings


class _Unattached:
    rule_id = "R-INST-001"
    category = "instrument"
    severity = "warning"
    title = "Unattached instrument"
    explanation = "An instrument was kept because no line or equipment was close enough."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = context
        affected = [node.id for node in graph.nodes if node.type == "instrument" and node.attachment == "unattached"]
        if not affected:
            return []
        return [_finding(self, "These instruments are not attached to a pipe, a piece of equipment, or a signal line.", affected, [_ev("graph", "Attachment was not found within the configured tolerance.")], "Look for a leader or a signal line before attaching the instrument.")]


class _LowAttachment:
    rule_id = "R-INST-002"
    category = "instrument"
    severity = "warning"
    title = "Low-confidence attachment"
    explanation = "An instrument is attached, but its own confidence is uncertain."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = context
        affected = [node.id for node in graph.nodes if node.type == "instrument" and node.attachment not in {"", "unattached"} and node.certainty == "uncertain"]
        if not affected:
            return []
        return [_finding(self, "These instruments are attached, and their source confidence is uncertain.", affected, [_ev("graph", "The attachment used proximity or a signal line.")], "Confirm the leader on the drawing.")]


class _MissingLoopPart:
    rule_id = "R-INST-003"
    category = "instrument"
    severity = "warning"
    title = "Incomplete control loop"
    explanation = "A loop is missing a sensor or a final element."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = context
        findings: list[Finding] = []
        for pattern in graph.patterns:
            if pattern.type != "control_loop":
                continue
            missing = [part for part in pattern.missing_parts if part in {"sensor", "final element"}]
            if not missing:
                continue
            findings.append(_finding(self, f"This loop is missing: {', '.join(missing)}.", pattern.member_node_ids, pattern.evidence, "Do not add the missing instrument unless it is on the drawing or in the IO list."))
        return findings


class _TagNotInIo:
    rule_id = "R-INST-004"
    category = "instrument"
    severity = "warning"
    title = "Instrument tag not in the IO list"
    explanation = "The existing tag check did not find this instrument tag."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        rows = {row.tag.upper(): row.status for row in context.report.rows}
        findings: list[Finding] = []
        for node in graph.nodes:
            if node.type != "instrument" or not node.tag:
                continue
            status = rows.get(node.tag.upper())
            if status in {None, "not_found", "extra"}:
                findings.append(_finding(self, f"{node.tag} is not a found IO-list row in the existing tag check.", [node.id], [_ev("tag_report", f"Tag check status: {status or 'no row'}.")], "Do not copy the tag into the IO list from this screen."))
        return findings


class _IoWithoutDrawing:
    rule_id = "R-INST-005"
    category = "instrument"
    severity = "warning"
    title = "IO row without a drawing match"
    explanation = "The existing tag check marked an IO-list row not found on the drawing."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = graph
        findings: list[Finding] = []
        for row in context.report.rows:
            if row.status != "not_found":
                continue
            findings.append(_finding(self, f"{row.tag} is on the IO list and the tag check did not find it on the drawing.", [row.tag], [_ev("tag_report", "Status not_found from the existing tag check.")], "Search the drawing before treating the row as drawn."))
        return findings


class _DuplicateTags:
    rule_id = "R-TAG-001"
    category = "tag"
    severity = "warning"
    title = "Duplicate tag"
    explanation = "The same tag is on more than one node."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = context
        seen: dict[str, list[str]] = {}
        for node in graph.nodes:
            if not node.tag:
                continue
            seen.setdefault(node.tag.upper(), []).append(node.id)
        findings: list[Finding] = []
        for tag, ids in seen.items():
            if len(ids) < 2:
                continue
            findings.append(_finding(self, f"{tag} is used on more than one node.", ids, [_ev("graph", "Duplicate tag text.")], "Keep both nodes until the drawing shows which one owns the tag."))
        return findings


class _UncertainOcr:
    rule_id = "R-TAG-002"
    category = "tag"
    severity = "warning"
    title = "Uncertain OCR tag"
    explanation = "OCR text was stored below the likely cutoff."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = graph
        if context.extraction is None:
            return []
        findings: list[Finding] = []
        for page in context.extraction.pages:
            for word in page.words:
                if word.ocr_confidence is None or word.ocr_confidence >= cfg.LIKELY_MIN:
                    continue
                word_id = f"ocr-{page.page}-{round(word.bbox[0], 1)}-{round(word.bbox[1], 1)}"
                findings.append(_finding(self, f"OCR text '{word.text}' has confidence {word.ocr_confidence:.2f}, below the likely cutoff.", [word_id], [_ev("ocr", "The OCR score was stored with the word.")], "Read the drawing text. Do not treat the OCR word as exact."))
        return findings


class _PatternFlags:
    rule_id = "R-PAT-001"
    category = "pattern"
    severity = "warning"
    title = "Incomplete pump group"
    explanation = "A pump group has a partial header or a leg without a valve."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = context
        findings: list[Finding] = []
        for pattern in graph.patterns:
            if pattern.type != "pump_group":
                continue
            interesting = [reason for reason in pattern.review_reasons if "header" in reason or "valve" in reason or "odd" in reason]
            if not interesting:
                continue
            findings.append(_finding(self, " ".join(interesting), pattern.member_node_ids, pattern.evidence, "Check the headers and valves on the drawing before using this group."))
        return findings


class _UnknownRoles:
    rule_id = "R-PAT-002"
    category = "pattern"
    severity = "info"
    title = "Pump role unknown"
    explanation = "No duty or standby evidence was found for a pump group."

    def run(self, graph: DiagramGraph, context: CheckContext) -> list[Finding]:
        _ = context
        findings: list[Finding] = []
        for pattern in graph.patterns:
            if pattern.type == "pump_group" and pattern.role == "unknown":
                findings.append(_finding(self, "This pump group has no duty or standby evidence.", pattern.member_node_ids, pattern.evidence, "Leave the role unknown unless a note or the IO list names it."))
        return findings


def _leaves(node_id: str, graph: DiagramGraph) -> bool:
    for edge in graph.edges:
        if edge.direction == "forward" and edge.from_id == node_id:
            return True
        if edge.direction == "reverse" and edge.to_id == node_id:
            return True
    return False


def _ev(source: str, description: str) -> Evidence:
    return Evidence(source=source, description=description)


def _node_tag_prefix(node: Node) -> str:
    return node.tag.split("-", 1)[0]


for rule in (
    _Orphans(),
    _DeadEnds(),
    _Disconnected(),
    _Duplicates(),
    _TiedEnds(),
    _UnknownDirection(),
    _ConflictingDirection(),
    _PumpDischarge(),
    _DeadEndFlow(),
    _Unattached(),
    _LowAttachment(),
    _MissingLoopPart(),
    _TagNotInIo(),
    _IoWithoutDrawing(),
    _DuplicateTags(),
    _UncertainOcr(),
    _PatternFlags(),
    _UnknownRoles(),
):
    register(rule)
