# UNTANGLE data contracts

These shapes are the agreement between the Python API and the React app.
The same fields exist in two places:

- Python: `backend/app/schemas/`
- TypeScript: `frontend/src/types/`

JSON uses `snake_case`. A few JSON keys are the words `from` and `to`. Python
stores those on an attribute named `from_` because `from` is a Python keyword.
The wire format still says `from`.

Times are ISO-8601 strings in JSON. Scores are numbers from 0 to 1.

The working rule for every later stage is: **exact match first, then rules, then AI help**.
Uncertain items stay in the data with a low confidence and a reason. They are not deleted.

## 1. Graph

A drawing in progress is a `DiagramGraph`: `nodes`, `edges`, and `groups`.

### Bounding box and point

| Field | Type | Meaning |
| --- | --- | --- |
| `page` | integer, at least 1 | PDF page |
| `x`, `y` | number | Top-left of the box, in the reader’s coordinates |
| `w`, `h` | number, 0 or more | Width and height |
| Point `x`, `y` | number | One vertex of a polyline |

### Node

| Field | Allowed values |
| --- | --- |
| `id` | non-empty string |
| `type` | `equipment`, `instrument`, `valve`, `junction`, `endpoint` |
| `tag`, `label`, `signal` | string, may be empty when the reader is not sure |
| `bbox` | box, or `null` when no page location is known yet |
| `kept` | `true` if the sketch should show it. `false` keeps it in the data and hides it |
| `detail_level` | `1`, `2`, or `3` |
| `confidence` | see Confidence |
| `reason` | why it was kept, hidden, or flagged |

### Edge

| Field | Allowed values |
| --- | --- |
| `id`, `from_id`, `to_id` | non-empty strings. `from_id` and `to_id` are node ids |
| `direction` | `forward` (from_id → to_id), `reverse`, `bidirectional`, `unknown` |
| `line_type` | `process`, `signal`, `other` |
| `color`, `style` | strings. Empty until a later stage assigns them |
| `crossing_mode` | `auto`, `avoid`, `keep` |
| `status` | `auto`, `user_added`, `user_edited`, `user_removed` |
| `polyline` | list of points. Empty until layout |
| `confidence` | see Confidence |
| `evidence` | list of `{source, description, page}` |
| `rule_results` | list of `{rule_id, passed, message}` |

`user_removed` does not delete the edge. The edge stays so a report can say it was removed.

### Group

| Field | Allowed values |
| --- | --- |
| `id` | non-empty string |
| `type` | `duty_standby`, `control_loop` |
| `member_node_ids` | node ids in the group |
| `shared_upstream`, `shared_downstream` | node ids shared by the members |

## 2. Confidence

```json
{ "level": "high", "score": 0.91, "reason": "tag text matched the IO list exactly" }
```

`level` is `high`, `medium`, or `low`. `score` is from 0 to 1. The level has to match the cutoffs in `backend/app/config.py` and `frontend/src/lib/confidence.ts`:

| Score | Level |
| --- | --- |
| 0.85 or higher | `high` |
| 0.60 up to but not including 0.85 | `medium` |
| below 0.60 | `low` |

A payload that says `high` with a score of 0.10 is rejected.

## 3. Processing stages

Canonical order, stored as `STAGE_ORDER`:

`Intake`, `Read`, `Detect`, `MatchTags`, `Trace`, `SelfCheck`, `Simplify`, `Patterns`, `Layout`, `Report`

Each `StageRecord` has:

| Field | Allowed values |
| --- | --- |
| `name` | one stage name |
| `status` | `pending`, `running`, `done`, `failed`, `skipped` |
| `started_at`, `ended_at` | timestamp or `null`. End cannot be before start |
| `duration_ms` | integer milliseconds, or `null` |
| `warnings` | list of strings. Warnings are kept |

A `ProcessingRun` is `{ "stages": [ ... ] }`. The same stage name cannot appear twice.

## 4. Error response

```json
{
  "error_code": "NOT_FOUND",
  "message": "That job does not exist.",
  "details": { "job_id": "missing" },
  "request_id": "req-1"
}
```

`details` may be `null`. `error_code` and `request_id` cannot be empty. This is the only error body the API will return.

## 5. Tag Check Report row

| Field | Allowed values |
| --- | --- |
| `tag` | non-empty string |
| `signal` | string |
| `status` | `found`, `fuzzy`, `not_found`, `extra` |
| `confidence` | Confidence |
| `location` | box on the P&ID, or `null` |
| `suggestion` | a possible tag, or `null` |

## 6. Connection Report row

JSON keys `from` and `to` are the endpoint labels (a tag or a node id, decided by the report stage).

| Field | Meaning |
| --- | --- |
| `from`, `to` | the two ends |
| `direction`, `line_type` | same values as an edge |
| `confidence` | Confidence |
| `evidence` | same evidence objects as an edge |
| `rules_passed`, `rules_failed` | rule ids |
| `source_location` | box on the P&ID, or `null` |

## 7. Verification result

| Field | Meaning |
| --- | --- |
| `connections_added`, `connections_removed` | counts, 0 or more |
| `tags_placed`, `tags_total` | counts, 0 or more. Placed cannot exceed total |
| `rule_results` | every defined check |
| `verified` | `true` or `false` |

`verified: true` is rejected unless `rule_results` has at least one check and every check has `passed: true`. An empty check list is not a pass. `verified: false` is allowed when checks fail. That is how uncertainty is shown.

## 8. Job and version

A `Job` is `{ "id", "versions" }`.

A `Version`:

| Field | Meaning |
| --- | --- |
| `id` | version id |
| `number` | `0` for the original, then 1, 2, … |
| `parent` | parent version id. `null` only for number 0 |
| `status` | `auto`, `accepted`, `edited` |
| `connection_list_snapshot` | saved connections: `from`, `to`, `direction`, `line_type` |
| `svg` | SVG markup, or `null` if it has not been drawn |
| `verification` | a verification result, or `null` |
| `change_log` | list of `{who, when, what, note}` |

Rules enforced by the models:

- Version 0 has no parent.
- Version 0 cannot have status `edited`. A person saves a change as a new version.
- Version 1 and later must name a parent.
- Inside one job, version numbers are unique.
- If a job has any versions, version 0 is still in the list. It is not removed and its stored content is not replaced.

`note` may be an empty string. `who`, `when`, and `what` may not.

## 9. Export metadata

Describes a download. The file bytes are not part of this object.

| Field | Allowed values |
| --- | --- |
| `id`, `job_id`, `filename`, `media_type` | non-empty strings |
| `version_number` | 0 or more |
| `format` | `svg`, `pdf`, `png`, `json`, `excel` |
| `created_at` | timestamp |
| `byte_size` | integer, or `null` when the size is not known yet |

## 10. Answer key

A person writes this JSON before node ids exist, so connections use tags.

```json
{
  "drawing_id": "sample-a",
  "expected_tags": [{ "tag": "FT-101", "signal": "FT" }],
  "expected_equipment": [{ "tag": "P-101", "label": "Feed pump" }],
  "expected_connections": [
    { "from": "P-101", "to": "FT-101", "direction": "forward", "line_type": "process" }
  ],
  "expected_duty_standby_groups": [
    {
      "id": "pumps",
      "member_tags": ["P-101", "P-102"],
      "shared_upstream": ["TK-101"],
      "shared_downstream": ["FT-101"]
    }
  ]
}
```

`direction` uses the same four values as an edge. `line_type` defaults to `process` when it is omitted in Python. In the TypeScript type it is still a required field on a complete object.

Group `shared_upstream` and `shared_downstream` are tags in an answer key. In a `DiagramGraph` group they are node ids.
