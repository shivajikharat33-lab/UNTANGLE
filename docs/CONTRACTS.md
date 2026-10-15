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
| `error` | a plain-English failure, or `null` when the stage has not failed |

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

`details` may be `null`. `error_code` and `request_id` cannot be empty. This is the only error body the API returns. Unknown routes use `NOT_FOUND` (404) and the message "No route matches this request." A missing project uses the same code with the message "No project exists with that id." Invalid payloads use `VALIDATION_ERROR` (422) and put the field errors in `details.errors`. Unexpected failures use `INTERNAL_ERROR` (500). Every response, including a successful one, sends that same id in the `X-Request-ID` header.

Upload failures use the same body. The codes are `MISSING_FILE`, `WRONG_FILE_TYPE`, `FILE_EMPTY`, `FILE_TOO_LARGE` (413), and `FILE_UNREADABLE`. `details.field` names `pid_pdf` or `io_list` when one file is the problem.

## 5. Tag Check Report row

| Field | Allowed values |
| --- | --- |
| `tag` | non-empty string |
| `signal` | string |
| `status` | `found`, `fuzzy`, `not_found`, `extra` |
| `confidence` | Confidence |
| `location` | box on the P&ID, or `null`. An ambiguous match stays `null` because no candidate is chosen |
| `suggestion` | a possible tag, nearest text, or candidate list, or `null` |
| `suffix_hint` | `A`, `B`, or `null`. Optional. A letter suffix is only a hint for a later duty/standby check |

`found` is an exact normalized match at score 1.0 (high). `fuzzy` is a digit-confusion match or a rapidfuzz match at or above `tag_fuzzy_threshold` (default 0.80), and the reason says Needs Review. `not_found` is an IO tag with no accepted candidate. `extra` is tag-like drawing text that is not in the IO list. `found + fuzzy + not_found` equals the number of normalized IO tags, and each of those tags appears once.

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

A `Job` always has `id` and `versions`. `versions` is empty until version 0 is stored. Uploading files does not create version 0, because there is no sketch yet.

The upload API also fills these fields. They have defaults, so a payload that only has `id` and `versions` still matches the model.

| Field | Meaning |
| --- | --- |
| `name` | project name, or an empty string |
| `status` | `uploaded` after the two files are stored |
| `created_at` | timestamp, or `null` on a job that has not been stored |
| `intake` | intake summary below, or `null` |
| `stages` | the ten stage records. Intake is `done` after a real upload. The others are `pending` |

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

## API health

`GET /api/health` is not one of the drawing contracts. Its body is:

| Field | Allowed values |
| --- | --- |
| `status` | `ok` when the process answered |
| `version` | application version string |
| `database` | `ok` after `SELECT 1` succeeds, otherwise `failed` |
| `time` | UTC timestamp |

`database: "failed"` still returns HTTP 200. The process is up; the database check is what failed.

## API config

`GET /api/config` returns `{ "max_upload_mb": 50 }` by default. The health check does not include this number. The new-project page uses it for the size check before upload.

## API jobs

`POST /api/jobs` is `multipart/form-data` with `pid_pdf`, `io_list`, and an optional `name`.

Both files are required, non-empty, and at most `max_upload_mb`. The PDF name must end in `.pdf` and the bytes must start with `%PDF-`. The workbook name must end in `.xlsx` and the bytes must start with `PK`. The size is checked while the file is read in chunks. A file over the limit is refused before the rest of it is stored.

The saved paths are `UPLOAD_DIR/<job id>/original.pdf` and `UPLOAD_DIR/<job id>/io_list.xlsx`. The user's filename is stored only as `original_name`. It is never used as a path. The files are not modified after they are written. Each file's SHA-256 is stored.

Intake then opens the PDF with PyMuPDF and the workbook with openpyxl. The summary is:

| Field | Meaning |
| --- | --- |
| `pdf`, `io_list` | `stored_name`, `original_name`, `sha256`, `byte_size` |
| `page_count` | pages in the PDF |
| `verdict` | `VECTOR`, `SCANNED`, or `MIXED` |
| `verdict_reason` | why that verdict was chosen |
| `sheets` | each sheet's `name`, `columns`, and `row_count` (the header counts as a row) |
| `warnings` | for example, a scanned PDF, because vector extraction will not be possible |

A PDF or workbook that cannot be opened is `FILE_UNREADABLE`. No job row is kept and no upload folder is left behind. Intake does not match tags and does not return text from the drawing.

`GET /api/jobs` lists projects newest first: `id`, `name`, `created_at`, `status`, `pdf_verdict`, `page_count`.

`GET /api/jobs/{id}` returns the full job, including `intake` and `stages`. An unknown id is a 404 `NOT_FOUND`.

## IO list check

`POST /api/jobs/{id}/io-list/validate` reads the stored workbook. The body may be empty, or it may name `sheet`, `tag_column`, and `signal_column`. Header names are matched without case sensitivity against tag, tag no, tag number, instrument tag, instrument, tag name, signal, description, service, and desc. If those names do not pick exactly one tag column and one signal column, the result status is `needs_columns` and no row is guessed. The caller then sends the column names. The two columns must be different.

A validated result keeps every non-empty data row. Tags are uppercased, trimmed, and written as letters, a hyphen, digits, and an optional letter suffix, so `pt101a`, `PT 101A`, and `PT-101A` all become `PT-101A`. `original_tag` keeps the cell text. Known prefixes map to pressure transmitter, flow transmitter, level transmitter, temperature transmitter, control valve, pump motor, tank, vessel, pump, and exchanger. Any other prefix has instrument type `unknown` and a warning. Empty tags and duplicates are errors. A pattern miss or a missing signal is a warning. Flagged rows stay in the list.

The file is `UPLOAD_DIR/<job id>/io_list.normalized.json`. The original `io_list.xlsx` is not changed. `GET /api/jobs/{id}/io-list` returns that file. If the check has not been run, the response is 404 `NOT_FOUND` with the message "The IO list has not been checked for this project."

## PDF read

`POST /api/jobs/{id}/process` returns 202 and the job snapshot taken when Read is marked `running`. A background task then reads the PDF. When Read succeeds, MatchTags runs. When MatchTags succeeds, Detect runs and then writes line geometry. Trace, SelfCheck, Simplify, Patterns, Layout, and Report stay `pending`. A second request while that job is running is 409 `JOB_ALREADY_RUNNING`. A failed stage stores `failed` and a plain-English `error`. If MatchTags fails, Detect is `failed` with an error that starts with "Prerequisite missing". If geometry cannot be saved, Detect stays `done` and a warning says the detections were kept. Earlier files, including `original.pdf` and `io_list.xlsx`, are not modified. Re-running replaces that stage's output only.

`GET /api/jobs/{id}/extraction` returns `UPLOAD_DIR/<job id>/extraction.json`, or 404 if Read has not written it. Coordinates use the top-left of the displayed page after rotation, in PDF points (1/72 inch), with Y downward. Word and drawing points are mapped with the page rotation matrix so they match `page.rect`. A page with no vector text, no drawings, and no image has status `no_vector_content` and empty counts. A page that contains only an image is read on the raster path: rendered at 300 DPI, binarized, and searched for lines, circles, and closed shapes. Those items have `source` `raster` and a base geometry confidence of 0.70. OCR words are stored with the engine confidence when the Tesseract program answers `pytesseract.get_tesseract_version()`. If it does not, the page status is `ocr_unavailable`, the message includes install instructions, and no OCR text is invented. Vector pages are unchanged. Mixed PDFs are handled page by page. Pixel positions map back by dividing by the render zoom (`300/72`). Every drawing primitive is counted as read, and `primitives_read = primitives_used + unused_primitives`. Collinear connected segments become one polyline; short segments that do not join are kept.

## Tag Check Report API

`GET /api/jobs/{id}/tag-report` returns `tag_report.json`: `rows` (Tag Check Report rows) and `summary` counts `total`, `found`, `fuzzy`, `not_found`, and `extra`. If MatchTags has not written the file, the response is 404. MatchTags requires a finished Read and a validated IO list. If either is missing, the stage is `failed` and the error starts with "Prerequisite missing". A scanned page can still be matched; IO tags then stay `not_found` rather than being filled in.

## Detections

`GET /api/jobs/{id}/detections` returns `detections.json`. If Detect has not written it, the response is 404 with the message "Symbol detection has not been run for this project." Each item has `id`, `kind`, optional `subtype`, `bbox`, `page`, `label`, `tag`, a Confidence object, an evidence list, and `source` (`vector` or `raster`). Kinds are `instrument`, `equipment`, `valve`, `arrow`, and `unclassified`. A shape that matches no rule stays as `unclassified`. Rules use shape and label together: an instrument bubble needs a circle and tag text whose prefix is PT, FT, LT, or TT; equipment needs a large closed shape and a T-, V-, or E- label, or a circle-plus-triangle pump with a P- label; a bow-tie is a valve, and it is a control valve only when the label is FV or LV or an actuator circle sits on the stem. Arrows are small filled triangles near a line end. `direction` is a pointing hint. Flow is not decided. The census counts each kind and how many items link to an IO tag whose tag-report status is `found` or `fuzzy`. Confidence levels follow the existing cutoffs: 0.85 and above is high, 0.60 to 0.85 is medium, below 0.60 is low. `GET /api/jobs/{id}/pages/{page}` returns a PNG of that page. The response headers `X-Page-Width` and `X-Page-Height` are the displayed page size in PDF points.

## Line geometry

`GET /api/jobs/{id}/geometry` returns `geometry.json`, or 404 with the message "Line geometry has not been run for this project." It is written after Detect in the same process run. A dashed stroke is `signal`. A solid stroke at or below `signal_max_stroke` (default 0.75) is also `signal`. A solid stroke between that cutoff and `process_min_stroke` (default 1.0) is `other`. A thicker solid stroke is `process`. A dotted pattern is not separated from a dashed pattern yet, so a dotted stroke is classified as `signal` and the reason says it is dashed. Endpoints of different lines within `snap_tolerance` (default 4 PDF points) move to their cluster center, and each move is stored in `snaps` with the original and snapped coordinates. Meetings are `junction` (a T-joint, or a crossing with a filled dot of radius 8 or less), `crossing` (a plain X, or a crossing with a hop vertex 4 to 16 points away), or `ambiguous`. An ambiguous meeting is kept, its reason says Needs Review, and it is not resolved. Endpoints that do not meet another line and do not touch a detected symbol are `free_endpoints`. Coverage stores `total_length`, `explained_length`, and `unexplained_length`. Explained length plus unexplained length equals total length. This file is not a graph and it does not set flow direction.

## Graph

The stored stage name for building the graph remains `Trace`. The screen label is "Building graph". `Trace` runs after line geometry is saved. `GET /api/jobs/{id}/graph` returns `graph.json`. `GET /api/jobs/{id}/graph/summary` returns counts only. A missing file is 404 with the message "The graph has not been built for this project."

Node types stay `equipment`, `instrument`, `valve`, `junction`, and `endpoint`. `terminal` was added for a label that says off-page, inlet, or outlet. A pipe end with no symbol is an `endpoint`, not a terminal. New optional fields on nodes and edges (`evidence`, `certainty`, `needs_review`, `review_reasons`, `segment_ids`, `direction_evidence`, `candidate_ids`, `attachment`, `pointing`) default so older graph JSON still loads. `certainty` uses the same cutoffs as confidence: 0.85 and above is confirmed, 0.60 to 0.85 is likely, and below 0.60 is uncertain. A vector edge is stored at 0.80, which is likely, not confirmed.

Junction meetings become junction nodes and the pipes connect through them. Crossing and ambiguous meetings are stored and do not connect lines. Collinear pipes merge and keep the original line ids. If two nodes are equally close to an end, neither is chosen. Direction is unknown unless an arrow, a check-valve direction, a recorded nozzle direction, or a terminal phrase supplies it. Conflicting evidence stays unknown and is flagged. Instruments that cannot be attached stay in the graph. Matching is read from the tag check and is not run again.

## Patterns

The stored stage name remains `Patterns`. The screen label is "Detecting patterns". It runs after Trace and rewrites `graph.json` with a `patterns` list and the older `groups` list. `processing_version` becomes `D2`. `GET /api/jobs/{id}/patterns` returns that list, or 404 with "Patterns have not been run for this project." A pump group requires shared header nodes reached along process edges. A tag suffix A or B alone is role certainty `likely` and does not name duty or standby. A suffix plus a duty or standby note, or an IO-list signal that says duty or standby, can name the role. A control loop groups tags that share a loop number, or that a signal line connects. ISA letters only name sensor, controller, and final element. A missing part stays missing.

## Checks

The stored stage name remains `SelfCheck`. The screen label is "Running checks". It runs after Patterns and stores `findings` on `graph.json`. `processing_version` becomes `D3`. `GET /api/jobs/{id}/findings` accepts optional `severity`, `rule_id`, and `category` filters. `GET /api/jobs/{id}/findings/{finding_id}` returns one finding. A missing run is 404 with "Checks have not been run for this project." An error finding caps that item's score at 0.59 and does not raise any score. Needs review is set when an error or warning names the item, when the label is uncertain, or when an earlier stage already flagged it. Info findings are recorded and do not by themselves mark the item. Zero findings is shown as "No issues found by the configured checks".

## Coverage

The stored stage name remains `Report`. The screen label is "Computing coverage". It runs after SelfCheck and adds `coverage`, `ledger`, and `verification` to `graph.json`. `processing_version` becomes `D4`. `GET /api/jobs/{id}/coverage` returns each metric with a numerator, a denominator, a percentage or null, and missing ids. `GET /api/jobs/{id}/ledger` accepts `item_type`, `reason_code`, `offset`, and `limit`. `GET /api/jobs/{id}/verification` returns `verified`, `not_verified`, or `needs_review`, the failing criterion names, and the disclaimer "Passed the defined automated checks. This is not an engineering or safety certification." A missing run is 404 with "Coverage has not been computed for this project." The word Verified is shown only when the state is `verified` and the stage is done.

## Simplified graph

The stored stage name remains `Simplify`. The screen label is "Simplifying graph". It writes `simplified.json` and does not change `graph.json`. `GET /api/jobs/{id}/simplified` returns that copy. A pass-through junction collapses only when it is untagged, not a valve, instrument, equipment, terminal, pattern member, or review item, and the two edge directions do not conflict. Identical parallel edges merge. Removed ids are in the simplified ledger with `collapsed_passthrough` or `merged_parallel_edge`. If kept-node connectivity changes, `failed_check` is true and the copy is not treated as verified.

## Layout, sketch, and cache

`Layout` is labeled "Laying out the sketch". It calls elkjs (`tools/layout`). Graphs with more than `MAX_LAYOUT_NODES` (200) return `LAYOUT_TOO_LARGE` and no coordinates. Unknown direction stays unknown and has no arrowhead. `GET /api/jobs/{id}/layout` returns the coordinates. `GET /api/jobs/{id}/sketch` returns the SVG and `GET /api/jobs/{id}/sketch/meta` returns the hidden count and legend. `GET /api/jobs/{id}/sketch/draft` returns the early draft, which always says "DRAFT, not final, not verified" and never says Verified.

`cache_dir` defaults to `data/cache` and can be set with the `CACHE_DIR` environment variable. The cache key is the PDF hash, the IO-list hash, the processing versions, and the named thresholds. `POST /api/jobs/{id}/process?force=true` ignores the cache. `POST /api/jobs/{id}/process?retry=true` continues from the failed stage and does not delete `original.pdf` or `io_list.xlsx`.
