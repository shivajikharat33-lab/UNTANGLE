# UNTANGLE

UNTANGLE is a web app that reads a customer P&ID PDF and an instrument IO list (Excel) and builds a simpler left-to-right control-room sketch.

It also produces a Tag Check Report, a Connection Report, a coverage summary, a hidden-item ledger, and downloads (SVG, PDF, PNG, JSON, Excel). Upload stores the two original files and does not change them. Later stages write derived JSON and SVG beside those files. Edit, version history, and settings changes are not built yet.

Decisions follow one order: exact file data first, then rules, then AI help. Uncertain items are flagged. They are not dropped, and a result is not marked verified unless every defined check passed.

## What is in the repo

| Path | Contents |
| --- | --- |
| `docs/CONTRACTS.md` | Field-by-field data contracts |
| `docs/FEATURES.md` | Master feature list and status |
| `docs/TRACEABILITY.md` | Requirement, code, and test |
| `docs/ARCHITECTURE.md` | Pipeline and folder guide |
| `backend/app/schemas/` | Pydantic models for those contracts |
| `backend/app/main.py` | FastAPI app. Start it with uvicorn from the `backend` folder |
| `frontend/src/types/` | Matching TypeScript types |
| `data/samples/` | Your local drawings. This folder is gitignored |
| `data/uploads/` | Stored PDFs and workbooks. This folder is gitignored |

The website is at http://127.0.0.1:5173 . `/` is the landing page. The app starts at `/app`.

## Setup

You need Python 3.11 or newer, plus Node.js for the website.

### Windows (PowerShell)

```powershell
cd untangle
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
cd tools\layout
npm install
cd ..\backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### macOS

```bash
cd untangle
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd tools/layout
npm install
cd ../../backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The API listens on http://127.0.0.1:8000. Open http://127.0.0.1:8000/api/health to see the check. Copy `backend/.env.example` to `backend/.env` only when you want to override the defaults. Do not commit `.env`.

### Frontend

In a second terminal, from the repository root:

#### Windows (PowerShell)

```powershell
cd untangle\frontend
npm install
npm run dev -- --host 127.0.0.1
```

#### macOS

```bash
cd untangle/frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173 . That address matches the API CORS setting. Copy `frontend/.env.example` to `frontend/.env` if you need a different API address.

### Tests

From the `backend` folder, with the virtual environment active:

```bash
python -m pytest
```

## Samples

Put real P&ID PDFs and IO workbooks in `data/samples/` on your own machine. Read `data/samples/README.md`. Those files are confidential. Do not commit them, and do not send them to a public cloud AI tool. Git ignores the files in `data/samples/` and everything in `data/uploads/`. The samples README is the only file from that folder that is meant to be committed.

From the repository root, after the backend packages are installed:

```bash
python scripts/inspect_pdf.py data/samples/your-drawing.pdf
python scripts/inspect_excel.py data/samples/your-io-list.xlsx
```

If the file is missing, the script tells you where to put it and does not create one. `data/answer_keys/README.md` explains how to hand-build an answer key from `TEMPLATE.json`.

## Current checks

From `backend/`:

```bash
python -m pytest
```

From `frontend/`:

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```
