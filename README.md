# UNTANGLE

UNTANGLE is a web app that reads a customer P&ID PDF and an instrument IO list (Excel) and builds a simpler left-to-right control-room sketch.

It also produces a Tag Check Report, a Connection Report, confidence and verification results, and downloads (SVG, PDF, PNG, JSON, Excel). Those product features are not built yet. This repository currently holds the project layout and the shared data contracts.

Decisions follow one order: exact file data first, then rules, then AI help. Uncertain items are flagged. They are not dropped, and a result is not marked verified unless every defined check passed.

## What is in the repo

| Path | Contents |
| --- | --- |
| `docs/CONTRACTS.md` | Field-by-field data contracts |
| `docs/FEATURES.md` | Master feature list and status |
| `docs/TRACEABILITY.md` | Requirement, code, and test |
| `docs/ARCHITECTURE.md` | Pipeline and folder guide |
| `backend/app/schemas/` | Pydantic models for those contracts |
| `frontend/src/types/` | Matching TypeScript types |
| `data/samples/` | Your local drawings. This folder is gitignored |
| `data/uploads/` | Future uploads. This folder is gitignored |

`backend/app/main.py` is not a server yet. The React app is not created yet. Both come in later steps.

## Setup

You need Python 3.11 or newer. The frontend toolchain is not required for this step.

### Windows (PowerShell)

```powershell
cd untangle
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
cd backend
python -m pytest
```

### macOS

```bash
cd untangle
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
python -m pytest
```

Copy `backend/.env.example` to `backend/.env` only when you are told the API reads it. Do not commit `.env`.

## Samples

Put real P&ID PDFs and IO workbooks in `data/samples/` on your own machine. Those files are confidential. Do not commit them, and do not send them to a public cloud AI tool. `data/samples/` and `data/uploads/` are listed in `.gitignore`.

## Current checks

From `backend/` with the virtual environment active:

```bash
python -m pytest
```

There is no frontend build yet, so there is no TypeScript or lint command in this step.
