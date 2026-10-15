"""Match drawing text to the checked IO list. Nothing is dropped or chosen silently."""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from app.config import level_for_score
from app.errors import AppError
from app.schemas.confidence import Confidence
from app.schemas.graph import BBox
from app.schemas.io_list import IoListResult, IoRow
from app.schemas.reports import TagReport, TagReportRow, TagReportSummary
from app.services.io_list import normalize_tag, normalize_tag_confusion, suffix_hint_for
from app.services.pdf_extract import ExtractionResult
from app.services.storage import TAG_REPORT_NAME, job_folder, read_json, write_json

_AMBIGUOUS_SCORE = 0.70
_CONFUSION_SCORE = 0.75


class PrerequisiteError(Exception):
    """Read or the checked IO list is not available."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class _Candidate:
    raw: str
    normalized: str | None
    confusion: str | None
    page: int
    bbox: list[float]

    @property
    def key(self) -> str | None:
        return self.normalized or self.confusion


def _confidence(score: float, reason: str) -> Confidence:
    return Confidence(level=level_for_score(score), score=score, reason=reason)  # type: ignore[arg-type]


def _location(page: int, bbox: list[float]) -> BBox:
    return BBox(
        page=page,
        x=bbox[0],
        y=bbox[1],
        w=max(0.0, bbox[2] - bbox[0]),
        h=max(0.0, bbox[3] - bbox[1]),
    )


def _union(boxes: list[list[float]]) -> list[float]:
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def _inside_circle(bbox: list[float], center: list[float], radius: float) -> bool:
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2
    dx = cx - center[0]
    dy = cy - center[1]
    limit = radius + 2
    return dx * dx + dy * dy <= limit * limit


def _candidate_from(raw: str, page: int, bbox: list[float]) -> _Candidate | None:
    normalized = normalize_tag(raw)
    confusion = normalize_tag_confusion(raw)
    if confusion == normalized:
        confusion = None
    if normalized is None and confusion is None:
        return None
    return _Candidate(raw=raw, normalized=normalized, confusion=confusion, page=page, bbox=bbox)


def _nearby(left: list[float], right: list[float]) -> bool:
    vertical_gap = max(0.0, max(left[1], right[1]) - min(left[3], right[3]))
    horizontal_gap = max(0.0, max(left[0], right[0]) - min(left[2], right[2]))
    height = max(left[3] - left[1], right[3] - right[1], 8)
    return vertical_gap <= height * 1.5 and horizontal_gap <= height * 2


def collect_candidates(extraction: ExtractionResult) -> list[_Candidate]:
    """Join split bubble text, then keep every remaining tag-like word."""
    found: list[_Candidate] = []
    for page in extraction.pages:
        used: set[int] = set()
        words = list(page.words)
        groups: list[list[int]] = []
        for circle in page.circles:
            group = [
                index
                for index, word in enumerate(words)
                if index not in used and _inside_circle(word.bbox, circle.center, circle.radius)
            ]
            if len(group) >= 2:
                groups.append(group)
        for index, word in enumerate(words):
            if index in used:
                continue
            for other in range(index + 1, len(words)):
                if other in used or not _nearby(word.bbox, words[other].bbox):
                    continue
                pair = [index, other]
                if pair not in groups:
                    groups.append(pair)
        for group in groups:
            if any(index in used for index in group):
                continue
            ordered = sorted(group, key=lambda index: (words[index].bbox[1], words[index].bbox[0]))
            raw = "".join(words[index].text for index in ordered)
            bbox = _union([words[index].bbox for index in ordered])
            candidate = _candidate_from(raw, page.page, bbox)
            if candidate is None:
                continue
            used.update(ordered)
            found.append(candidate)
        for index, word in enumerate(words):
            if index in used:
                continue
            candidate = _candidate_from(word.text, page.page, word.bbox)
            if candidate is not None:
                found.append(candidate)
    return found


def _row(entry: IoRow, status: str, score: float, reason: str, location: BBox | None, suggestion: str | None) -> TagReportRow:
    return TagReportRow(
        tag=entry.tag,
        signal=entry.signal,
        status=status,  # type: ignore[arg-type]
        confidence=_confidence(score, reason),
        location=location,
        suggestion=suggestion,
        suffix_hint=entry.suffix_hint,
    )


def _ambiguous(entry: IoRow, options: list[_Candidate]) -> TagReportRow:
    listed = ", ".join(f"{item.raw} (page {item.page})" for item in options)
    return _row(
        entry,
        "fuzzy",
        _AMBIGUOUS_SCORE,
        "Needs Review. This IO tag has more than one drawing candidate, or one drawing candidate matches more than one IO tag. No match was chosen.",
        None,
        f"Candidates: {listed}",
    )


def _pair_rows(
    entries: list[IoRow],
    candidates: list[_Candidate],
    accept,
    status: str,
    score_for,
    reason_for,
) -> tuple[dict[int, TagReportRow], set[int]]:
    proposals: dict[int, list[tuple[int, _Candidate]]] = {id(entry): [] for entry in entries}
    users: dict[int, list[IoRow]] = {}
    for entry in entries:
        for candidate in candidates:
            if not accept(entry, candidate):
                continue
            proposals[id(entry)].append((id(candidate), candidate))
            users.setdefault(id(candidate), []).append(entry)
    rows: dict[int, TagReportRow] = {}
    used: set[int] = set()
    for entry in entries:
        options = proposals[id(entry)]
        if not options:
            continue
        shared = any(len(users[candidate_id]) > 1 for candidate_id, _candidate in options)
        if len(options) > 1 or shared:
            rows[id(entry)] = _ambiguous(entry, [candidate for _candidate_id, candidate in options])
            used.update(candidate_id for candidate_id, _candidate in options)
            continue
        _candidate_id, candidate = options[0]
        rows[id(entry)] = _row(
            entry,
            status,
            score_for(entry, candidate),
            reason_for(entry, candidate),
            _location(candidate.page, candidate.bbox),
            None,
        )
        used.add(_candidate_id)
    return rows, used


def build_report(extraction: ExtractionResult, io_list: IoListResult, threshold: float) -> TagReport:
    """Match IO tags in order: exact, digit confusion, then fuzzy above the threshold."""
    if io_list.status != "validated":
        raise PrerequisiteError(
            "Prerequisite missing: MatchTags needs a checked IO list. Choose the tag and signal columns first."
        )
    entries = [row for row in io_list.rows if row.tag]
    candidates = collect_candidates(extraction)
    remaining = list(candidates)
    chosen: dict[int, TagReportRow] = {}

    exact_rows, exact_used = _pair_rows(
        entries,
        remaining,
        lambda entry, candidate: candidate.normalized == entry.tag,
        "found",
        lambda _entry, _candidate: 1.0,
        lambda _entry, _candidate: "Exact normalized match.",
    )
    chosen.update(exact_rows)
    remaining = [candidate for candidate in remaining if id(candidate) not in exact_used]
    open_entries = [entry for entry in entries if id(entry) not in chosen]

    confusion_rows, confusion_used = _pair_rows(
        open_entries,
        remaining,
        lambda entry, candidate: candidate.normalized is None and candidate.confusion == entry.tag,
        "fuzzy",
        lambda _entry, _candidate: _CONFUSION_SCORE,
        lambda entry, candidate: (
            f'Needs Review. Drawing text "{candidate.raw}" matches {entry.tag} after digit confusion '
            "(O/0, I/1, S/5, B/8) with score 0.75."
        ),
    )
    chosen.update(confusion_rows)
    remaining = [candidate for candidate in remaining if id(candidate) not in confusion_used]
    open_entries = [entry for entry in entries if id(entry) not in chosen]

    def fuzzy_score(entry: IoRow, candidate: _Candidate) -> float:
        text = candidate.key or ""
        return float(fuzz.ratio(text, entry.tag)) / 100

    fuzzy_rows, fuzzy_used = _pair_rows(
        open_entries,
        remaining,
        lambda entry, candidate: candidate.key is not None and fuzzy_score(entry, candidate) >= threshold,
        "fuzzy",
        fuzzy_score,
        lambda entry, candidate: (
            f'Needs Review. Drawing text "{candidate.raw}" fuzzy-matches {entry.tag} '
            f"with score {fuzzy_score(entry, candidate):.2f}."
        ),
    )
    chosen.update(fuzzy_rows)
    remaining = [candidate for candidate in remaining if id(candidate) not in fuzzy_used]

    rows: list[TagReportRow] = []
    for entry in entries:
        if id(entry) in chosen:
            rows.append(chosen[id(entry)])
            continue
        nearest = None
        nearest_score = -1.0
        for candidate in candidates:
            text = candidate.key or candidate.raw
            score = float(fuzz.ratio(text, entry.tag)) / 100
            if score > nearest_score:
                nearest = candidate
                nearest_score = score
        suggestion = None
        if nearest is not None:
            suggestion = f'Nearest drawing text is "{nearest.raw}" on page {nearest.page} (score {nearest_score:.2f}).'
        rows.append(
            _row(
                entry,
                "not_found",
                0.0,
                "No drawing text matched this IO tag.",
                None,
                suggestion,
            )
        )

    for candidate in remaining:
        tag = candidate.key or ""
        if not tag:
            continue
        rows.append(
            TagReportRow(
                tag=tag,
                signal="",
                status="extra",
                confidence=_confidence(1.0, "This tag-like text is on the drawing and is not in the IO list."),
                location=_location(candidate.page, candidate.bbox),
                suggestion=f'Drawing text was "{candidate.raw}".',
                suffix_hint=suffix_hint_for(tag),
            )
        )

    summary = TagReportSummary(
        total=len(entries),
        found=sum(1 for row in rows if row.status == "found"),
        fuzzy=sum(1 for row in rows if row.status == "fuzzy"),
        not_found=sum(1 for row in rows if row.status == "not_found"),
        extra=sum(1 for row in rows if row.status == "extra"),
    )
    return TagReport(rows=rows, summary=summary)


def load_tag_report(upload_dir: str, job_id: str) -> TagReport:
    """Return the saved Tag Check Report, or 404 when MatchTags has not produced one."""
    folder = job_folder(upload_dir, job_id)
    path = folder / TAG_REPORT_NAME
    if not path.is_file():
        raise AppError(404, "NOT_FOUND", "The tag check has not been run for this project.", {"job_id": job_id})
    return TagReport.model_validate(read_json(path))


def write_tag_report(upload_dir: str, job_id: str, report: TagReport) -> None:
    folder = job_folder(upload_dir, job_id)
    write_json(folder / TAG_REPORT_NAME, report.model_dump(mode="json"))
