# Phase G plan

Version 0 already exists in `versions`. A database trigger rejects every update of that row, and its status may only be `auto`, `accepted`, or `edited`. The working copy is therefore a `draft.json` file in the job folder, not a new status value inside the constrained table. Saving the draft inserts version 1, 2, and so on. Accepting version 0 changes only `status` and `accepted_at`. The trigger is narrowed so those two fields may change and the snapshot, SVG, verification, and change log may not.

## Already present

- Edge `status` and `crossing_mode` on the graph contract.
- `Version` and `VersionRow`, plus triggers that protect version 0.
- Excel export of reports, SVG render, simplify, and layout.
- Results page and stable SVG element ids.

## Missing before this phase

- No version 0 is written when processing finishes.
- No Keep as is / Modify flow.
- No connection-list editor, validated re-import, or edit operations.
- No undo log, version compare, or restore.
- No per-link crossing redraw and no vector print PDF. CairoSVG installs, but the Cairo DLL is not on this machine, so print uses ReportLab to draw the same lines and text as vectors.

## Files

- `backend/app/services/edits.py` — versions, operations, import, diff, print.
- `backend/app/api/edits.py` — HTTP routes.
- `frontend/src/pages/EditPage.tsx`, `HistoryPage.tsx`, banner on `ResultsPage.tsx`.
- Tests: `backend/tests/test_edits.py`, `frontend/src/components/EditBanner.test.tsx`.

## Risks

- A line the graph never attached still cannot be edited into existence except by an explicit add.
- Print text is vector. It is not CairoSVG output.
- There is no login, so the author stored on a change is `local user`.
