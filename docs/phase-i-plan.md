# Phase I plan

Quality and deployment. Graph rules, stage names, and the Verified badge stay as they are. The badge still means: "Passed the defined automated checks. This is not an engineering or safety certification."

Checked on 15 October 2026 from this working tree.

## What is already here

- API on `127.0.0.1:8000`, website on `127.0.0.1:5173`, CORS origin `http://127.0.0.1:5173`.
- SQLite file at `data/untangle.db` (`DATABASE_URL`). Uploads in `data/uploads` (`UPLOAD_DIR`). Derived files in `data/cache` (`CACHE_DIR`).
- `GET /api/health` reports process status, version, and a live database check. There is no separate liveness or readiness route yet.
- Upload already checks size (`MAX_UPLOAD_MB`, default 50), extension, and magic bytes (`%PDF` and `PK`). Stored names are `original.pdf` and `io_list.xlsx`. Display names are not used as paths.
- Excel reads use `data_only=True`. Export cells that start with `=`, `+`, `-`, or `@` are prefixed so a spreadsheet does not treat them as formulas.
- Errors use the shared JSON schema. A request id is already on each response.
- OCR uses pytesseract. If the Tesseract program is missing, the status is `ocr_unavailable` and no text is invented. CairoSVG cannot draw on this Windows machine because `libcairo-2.dll` is missing. Print PDFs use ReportLab. Layout uses elkjs, not Graphviz `dot`.
- Flags: `MODIFY_ENABLED` defaults true. `ASK_GRAPH_LLM_ENABLED`, `FEWSHOT_SYMBOLS_ENABLED`, `DARK_THEME_ENABLED`, `FLOW_ANIMATION_ENABLED`, and `BATCH_UPLOAD_ENABLED` default false. There is no batch-upload route and no few-shot upload route.
- Frontend `VITE_API_URL` defaults to `http://127.0.0.1:8000`.
- Checks today: `python -m pytest` from `backend`, and `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build` from `frontend`.

## Secret scan

`git ls-files` does not track `.env`, keys, PDFs, or Excel workbooks. `data/samples/` is ignored except `data/samples/README.md`. Nothing confidential is in git history that this pass can see from the file list. History was not rewritten.

## This phase

1. Harden uploads, failure recovery, rate limits, security headers, and a demo access code. Add tests, including an API-level end-to-end script. Playwright is not set up here, so the end-to-end check is an API test plus `scripts/smoke_test.py`.
2. Docker images and Compose. The default image is vector-only. OCR is a build argument.
3. GitHub Actions for backend, frontend, and image build. Dependency audit reports and does not block.
4. Deployment notes from current host docs, with a manual checklist. This machine cannot open hosting dashboards.
5. Demo runbook, README, approach note, and an honest submission checklist.

## Limits we will not pretend to fix

- The demo code is a shared gate, not user accounts.
- Rate limits live in each process. Two processes do not share a counter.
- Upload inspection runs in a child process with a timeout. A stage that is already inside a native library call is not killed mid-call. The job is marked failed when that call returns or the next stage sees the clock.
- Cancel is not a product route. Retry is `POST /api/jobs/{id}/process?retry=true`.
- SQLite and the upload folder need a persistent disk. This phase will not switch the database.
