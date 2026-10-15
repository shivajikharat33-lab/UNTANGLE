# How UNTANGLE is put together

UNTANGLE turns two customer files into a simpler left-to-right control-room sketch:

1. A P&ID drawing (PDF).
2. An instrument IO list (Excel).

It also writes a Tag Check Report, a Connection Report, a verification result, and downloadable files. If it is not sure, it says so. It does not drop a symbol or invent a “verified” badge.

The order of decisions is fixed:

1. **Exact first.** Use the text, lines, and tags that are actually in the files.
2. **Rules decide.** Named checks accept, flag, or ask for another trace.
3. **AI assists.** A model may suggest a match only after the first two steps, and the suggestion stays labeled with a confidence and a reason.

## Pipeline

Each pass records the ten stages below. A stage ends as `pending`, `running`, `done`, `failed`, or `skipped`. Warnings stay on the stage record.

| Stage | What it is for |
| --- | --- |
| Intake | Accept the PDF and the Excel file and open a job. Version 0 is the original and is never overwritten. |
| Read | Open the PDF pages and the spreadsheet. Decide whether the drawing is vector, scanned, or mixed. |
| Detect | Find equipment, instruments, valves, junctions, and endpoints. Keep the tag text that was read. |
| MatchTags | Compare those tags with the IO list. Exact matches win. Fuzzy matches are marked fuzzy. |
| Trace | Follow lines to build connections and a flow direction. |
| SelfCheck | Run the rules. If a check fails, trace again or flag the item. Do not delete it. |
| Simplify | Choose what the sketch shows. Hidden items stay in the graph with `kept` set to false and a reason. |
| Patterns | Group duty/standby pairs and control loops. |
| Layout | Place the sketch left to right. |
| Report | Build the tag report, the connection report, verification, and export metadata. |

`verified` can be true only when every defined check passed. No checks means not verified.

## Folders

| Path | Role |
| --- | --- |
| `backend/app/schemas/` | The data contracts, as Pydantic models. |
| `backend/app/api/` | HTTP routes. Empty until the API step. |
| `backend/app/services/` | The stage code. Empty until processing starts. |
| `backend/app/models/` | Database tables. Empty until the API step. |
| `backend/app/config.py` | Shared cutoffs. Confidence thresholds live here now. |
| `backend/app/main.py` | Reserved for the FastAPI app. It is not a server yet. |
| `backend/app/database.py` | Reserved for SQLite. It does not connect yet. |
| `backend/tests/` | pytest. |
| `frontend/src/types/` | The same contracts in TypeScript. |
| `frontend/src/lib/` | Small shared helpers. Confidence cutoffs live here so they can be checked against the backend. |
| `frontend/src/api/`, `components/`, `pages/` | Reserved for the React app. |
| `docs/` | Contracts, the feature list, traceability, and this note. |
| `data/samples/` | Local customer PDFs and spreadsheets. Git ignores this folder. |
| `data/answer_keys/` | Hand-built expected results. A template comes in a later step. |
| `data/uploads/` | Files the API will store. Git ignores this folder. |
| `scripts/` | One-off inspection scripts. Empty for now. |

## What is deliberately not here yet

There is no website, no upload route, and no PDF reader. Those are later steps. Calling `backend/app/main.py` or `init_db()` fails on purpose so it cannot look like a working server.
