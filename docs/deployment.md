# Deploy UNTANGLE

This file is a manual checklist. The website is already live on Vercel. The FastAPI API on Render is **pending** until a real `*.onrender.com` URL exists and is verified. Do not treat a Cloudflare tunnel (`trycloudflare.com`) as the permanent API. The public site must not depend on anyone's local PC.

Checked against host docs on 15 October 2026. This machine may not be logged into the Render dashboard and may have no `RENDER_API_KEY`.

The website is the Vite app in `frontend/`. The API is the FastAPI app in `backend/`. Layout for the sketch calls `node` on `tools/layout/elk_layout.mjs` (elkjs). Print PDFs use ReportLab. This app does not use Graphviz `dot`. `backend/requirements.txt` does not install CairoSVG, and the Render service must not be built as if a Windows `libcairo` DLL were present.

`data/samples/` and `data/uploads/` stay gitignored. Do not commit customer P&IDs, IO lists, `backend/.env`, `frontend/.env`, or any secret. Do not upload a confidential customer drawing to the public free service.

## Where each host fits

| Piece | Host | Why |
| --- | --- | --- |
| React site | Vercel (`https://untangle-coral.vercel.app`) | Static Vite build. The browser then calls the API. |
| FastAPI API | Render web service | Python process, SQLite file, upload folder. |

## Database: SQLite only (no MongoDB)

UNTANGLE stores jobs and versions in **SQLite**. There is no MongoDB driver, no MongoDB connection string, and no MongoDB step in this deploy. Do not add MongoDB. Free Render Postgres is also unused. On the free Render plan the SQLite file and upload folder sit on an **ephemeral** disk: a restart, redeploy, or spin-down deletes them.

## What the docs confirmed on 15 October 2026

### Vercel

Sources: [Limits](https://vercel.com/docs/limits), [Pricing](https://vercel.com/pricing), [vercel.json](https://vercel.com/docs/project-configuration/vercel-json), [Monorepos](https://vercel.com/docs/monorepos), [Rewrites](https://vercel.com/docs/routing/rewrites).

- Hobby is listed at $0/month. Pro is listed at $20/month.
- Hobby limits on the limits page: 200 projects, 100 deployments created per day, 45 minutes build time, 1 concurrent deployment, 32 GB build-machine disk, 2,048 routes per deployment, 120 second proxied-request timeout, 100 MB CLI source upload, runtime logs kept 1 hour, up to 1,000 environment variables per environment and 64 KB total for those runtimes.
- The monthly Hobby bandwidth allotment is not on that limits table. It points at a usage page this check did not open. Treat the bandwidth number as **unconfirmed**.
- `vercel.json` belongs in the project root. For this repo that root is `frontend/` after you set Root Directory. The SPA example in the vercel.json docs is a rewrite from `/(.*)` to `/index.html`. Existing files are served first, so JS and CSS are not replaced by that rewrite. Do not turn on `cleanUrls`. A community report showed that `cleanUrls: true` makes a rewrite to `/index.html` miss.
- Root Directory is a project setting in the Vercel dashboard, not a key this checklist puts in `vercel.json`.

### Render

Sources: [Free](https://render.com/docs/free), [Disks](https://render.com/docs/disks), [Pricing](https://render.com/pricing), [Blueprint spec](https://render.com/docs/blueprint-spec), [Health checks](https://render.com/docs/health-checks), [Native runtimes](https://render.com/docs/native-runtimes), [Python version](https://render.com/docs/python-version), [Environment variables](https://render.com/docs/configure-environment-variables).

- A new web service with **no** `plan` uses paid plan `0.5c-512mb`. `render.yaml` sets `plan: free` so the blueprint does not pick that paid plan.
- Free web service: 0.1 CPU, 512 MB RAM, $0 compute. It spins down after 15 minutes without inbound traffic. The next request takes about a minute while it starts. Render may restart it at any time. Each workspace gets 750 Free instance hours per calendar month. Spun-down time does not use those hours. Using all of them suspends Free web services until next month.
- Every Render service disk is ephemeral unless a persistent disk is attached. Free web services cannot attach a persistent disk. A restart, redeploy, or spin-down deletes SQLite and uploaded files.
- Persistent disks are for paid web services, private services, and background workers. Only files under the mount path are kept. A disk blocks zero-downtime deploys. Published disk price: $0.25 per GB per month. Published web-service prices on the same pricing page: `0.5c-512mb` is $7/month (512 MB) and `1c-2g` is $25/month (2 GB). This checklist does not buy either plan.
- HTTP health checks expect a path starting with `/` and a 2xx or 3xx response within 5 seconds. A new deploy is cancelled if instances are not healthy within 15 minutes.
- Blueprint `sync: false` asks for a value during the first create. Later blueprint updates ignore that variable. Preview environments do not receive `sync: false` variables. This file does not turn previews on.
- Python source on a native runtime is `/opt/render/project/src`. Native runtimes include `node`, `npm`, and `sqlite3`. The published tool list does not include Tesseract or libcairo. Whether those can be added with a system package is **unconfirmed**. Do not add them for this service.
- New services created on or after 11 February 2026 default to Python `3.14.3` if `PYTHON_VERSION` is unset. This Windows machine is Python 3.14.6. Whether Render's installer offers the 3.14.6 patch is **unconfirmed**, so `render.yaml` pins the documented default `3.14.3`.

## Database and files on Render

SQLite and the upload folder live on the service disk. On the free plan that disk is wiped when the service redeploys, restarts, or spins down.

`render.yaml` leaves uploads on (`PUBLIC_DEMO_MODE=false`) so a visitor can send a PDF and an Excel IO list. The API does not seed a synthetic project in that mode.

User uploads are not durable on a free instance. A restart, redeploy, or spin-down deletes the SQLite file and the upload folder. Do not put a confidential customer drawing on this public free service.

Cost trade-off, from the prices above, if you later want files to survive a restart:

- Stay on Free: $0, 512 MB, uploads work until the next restart, then the files disappear. This is what `render.yaml` selects.
- A paid compute plan can mount a persistent disk at `/var/data` ($0.25 per GB per month, plus the instance price). Point `DATABASE_URL`, `UPLOAD_DIR`, and `CACHE_DIR` at that mount. The database would still be SQLite. The smallest paid web plan on the pricing page is 512 MB at $7/month, which may still be tight for OpenCV, pandas, and a processing job. The 2 GB plan is listed at $25/month. Adding a disk also disables zero-downtime deploys. Do not add a `disk` block while `plan` is `free`. Render will reject it.

Free Render Postgres is a different product (it expires 30 days after creation). This app does not use it.

## Vercel project settings

Set these in the dashboard when you import the GitHub repo. `frontend/vercel.json` matches the build, output, and SPA rewrite.

| Setting | Value |
| --- | --- |
| Root Directory | `frontend` |
| Framework Preset | Vite |
| Install Command | `npm install` (default) |
| Build Command | `npm run build` |
| Output Directory | `dist` |

`npm run build` runs `tsc -b && vite build`. The output directory is `frontend/dist`.

Environment variable, set for Production before the first production build:

| Name | Example (not a secret) |
| --- | --- |
| `VITE_API_URL` | `https://YOUR-SERVICE.onrender.com` (real Render origin after deploy) |

Vite copies `VITE_API_URL` into the browser bundle at build time. Changing it later requires a new Vercel deployment. Do not put API keys or secrets in any `VITE_` variable. The frontend only needs this public API origin.

`frontend/src/api/client.ts` already reads it:

- Unset or missing: `http://127.0.0.1:8000`, so local `npm run dev` keeps working.
- A non-empty URL: that origin, with one trailing slash removed.
- A value of empty or `/`: the site calls the same host as the page. On Vercel that is the static site, not the API. Do not leave `VITE_API_URL` blank.

The browser sends `credentials: include` and, after an access code, `Authorization: Bearer`. The API allows credentials and refuses origin `*`. `FRONTEND_ORIGIN` plus `CORS_ORIGINS` must list the real site origin.

## Render service settings

`render.yaml` is the blueprint. You can also create a Web Service by hand with the same commands.

| Setting | Value |
| --- | --- |
| Root directory | repository root (not `backend/`) |
| Runtime | Python |
| Plan | `free` |
| Build command | `pip install -r backend/requirements.txt && npm ci --prefix tools/layout` |
| Start command | `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT` |
| Health check path | `/api/health` |

The start command runs on Render's Linux shell. It must listen on `0.0.0.0` and `$PORT`. The local command (`127.0.0.1` and port `8000`) is only for your machine.

Health routes that already exist:

| Path | What it does |
| --- | --- |
| `GET /api/health` | The check the website uses. HTTP 200 with `status`, `version`, `database` (`ok` or `failed`), and `time`. `status` stays `ok` even when `database` is `failed`, so Render will not restart the process for a bad SQLite file. The website badge is where that shows. |
| `GET /health` | Liveness only. HTTP 200 and `{"status":"ok"}`. It does not check SQLite. |
| `GET /ready` and `GET /api/ready` | HTTP 200 `ready` only when SQLite answers and the upload and cache folders are writable. Otherwise HTTP 503. |

Render is pointed at `/api/health` so the same check the UI uses can answer within the 5 second probe. `render.yaml` already sets `DEMO_SEED_PROCESS=false` and `PUBLIC_DEMO_MODE=false` so startup does not run a heavy seed.

## Environment variables

No secret values belong in git. Examples below are placeholders.

### Vercel (Production, then redeploy)

| Name | Example |
| --- | --- |
| `VITE_API_URL` | `https://YOUR-SERVICE.onrender.com` |

### Render

| Name | Example for the free synthetic demo | Notes |
| --- | --- | --- |
| `PYTHON_VERSION` | `3.14.3` | Set in `render.yaml`. |
| `PUBLIC_DEMO_MODE` | `false` | `true` refuses uploads. Leave `false` so a visitor can upload a PDF and an Excel file. |
| `DEMO_SEED_PROCESS` | `false` | Only used when public demo mode is on. |
| `OCR_IN_BUILD` | `false` | Tesseract is not part of this Render build. Vector pages still work. The synthetic demo is vector text. |
| `DATABASE_URL` | `sqlite:////opt/render/project/src/data/untangle.db` | Ephemeral on Free. |
| `UPLOAD_DIR` | `/opt/render/project/src/data/uploads` | Ephemeral on Free. |
| `CACHE_DIR` | `/opt/render/project/src/data/cache` | Ephemeral on Free. |
| `MAX_UPLOAD_MB` | `50` | Uploads are refused while public demo mode is on. |
| `CORS_ORIGINS` | `http://127.0.0.1:5173` | Extra origins, comma-separated. Never `*`. |
| `FRONTEND_ORIGIN` | `https://untangle-coral.vercel.app` | Exact Vercel origin. `https`, no path, no trailing slash. Set in `render.yaml`. |
| `DEMO_ACCESS_CODE` | leave empty | Optional. If set, the site asks for it. Do not commit the code. |

Uploads (PDF + Excel), analysis/processing, and exports use the same Render process and the env vars above. No extra secret is required for those paths on the public demo. Other names already in `backend/.env.example` (`MAX_PDF_PAGES`, rate limits, `MODIFY_ENABLED`, `ASK_GRAPH_LLM_ENABLED`, `FEWSHOT_SYMBOLS_ENABLED`, `DARK_THEME_ENABLED`, `FLOW_ANIMATION_ENABLED`, `BATCH_UPLOAD_ENABLED`, `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`, stroke and snap thresholds) keep their defaults when unset. `LLM_API_KEY` is not required. This build does not call a model with it. Leave it unset on the public demo.

Local development: copy the example files to `.env` only when you want to override defaults. With the variables unset, the API allows `http://127.0.0.1:5173` and the site calls `http://127.0.0.1:8000`.

Paid disk, only after you choose a paid compute plan yourself:

```yaml
disk:
  name: untangle-data
  mountPath: /var/data
  sizeGB: 1
```

Then set `DATABASE_URL` to `sqlite:////var/data/untangle.db`, `UPLOAD_DIR` to `/var/data/uploads`, and `CACHE_DIR` to `/var/data/cache`. Turn `PUBLIC_DEMO_MODE` off only if you accept that those files are still a single disk on one instance, and still do not upload customer drawings to a demo you do not control. `sizeGB` is shown as optional in the blueprint example. The default size number is **unconfirmed** here, so the example uses 1 GB, which matches the published $0.25 per GB price for one gigabyte.

## Manual checklist (Render API + reconnect Vercel)

GitHub repo: `https://github.com/shivajikharat33-lab/UNTANGLE` (branch `main`). Website already: `https://untangle-coral.vercel.app`.

1. Confirm `render.yaml` and `docs/deployment.md` are on `origin/main`. Do not commit `backend/.env`, `frontend/.env`, `data/uploads`, `*.db`, or `tools/cloudflared.exe`.
2. Open [Render Dashboard](https://dashboard.render.com/) and sign in (GitHub login is fine).
3. **New** → **Blueprint** → connect `shivajikharat33-lab/UNTANGLE`. Blueprint path: `render.yaml` at the repo root. Confirm plan **Free**. Leave `DEMO_ACCESS_CODE` empty when prompted. Apply.
4. Or create a **Web Service** by hand: connect the same repo, **Root Directory** blank (repository root), Runtime Python, plan Free, build/start/health as in the table above, copy env vars from `render.yaml`, set `FRONTEND_ORIGIN=https://untangle-coral.vercel.app`.
5. Wait until the deploy is Live. Open Logs if the build fails. First cold start after spin-down can take about a minute.
6. Copy the service URL (`https://….onrender.com`, no trailing slash). Verify:

```powershell
curl.exe -sS https://YOUR-SERVICE.onrender.com/api/health
```

You want HTTP 200 with `"status":"ok"` and `"database":"ok"`. **pending** until that response is real.

7. Reconnect the frontend (Vercel team `spa-i-nsight`, project `untangle`):
   - Settings → Environment Variables → set Production `VITE_API_URL` to that Render origin (replace any old `trycloudflare` URL).
   - Redeploy Production so the browser bundle picks up the new value.
8. Open `https://untangle-coral.vercel.app/app`. Health should show Connected / online with database `ok`. Do not point Vercel at `http://127.0.0.1:8000` or at a temporary tunnel.

### How to read Render logs

Dashboard → service `untangle-api` → **Logs**. Build failures show during deploy; runtime errors show after Live. Use **Events** for deploy history.

## How to test the public site

`scripts/smoke_test.py` is not in this repo. Use the checks below. There is no separate harness.

From PowerShell, after the API deploy (step 6). Replace the host. **pending manual verification**:

```powershell
curl.exe -sS https://YOUR-SERVICE.onrender.com/api/health
curl.exe -sS https://YOUR-SERVICE.onrender.com/health
```

`/api/health` should include `"status":"ok"` and `"database":"ok"`. `/health` should be `{"status":"ok"}`.

In the browser, after steps 8 and 10. **pending manual verification**:

1. Open `https://YOUR-APP.vercel.app/`. The landing page should load.
2. Open `https://YOUR-APP.vercel.app/app`. The dashboard should load, not a Vercel 404.
3. Open `https://YOUR-APP.vercel.app/app/settings`. The API address should be the Render `https` origin, not `http://127.0.0.1:8000`. Health should show online and database `ok`.
4. Open `https://YOUR-APP.vercel.app/app/edit` and `https://YOUR-APP.vercel.app/app/versions`. Those routes are the Edit and History pages. They should not be a "not built" page.
5. Open New project and upload a non-confidential PDF plus an `.xlsx` IO list. Processing can take a few minutes. The first request after spin-down can take about a minute before the upload starts. Do not upload a customer P&ID or IO list.
6. If you left `DEMO_ACCESS_CODE` empty, the site should not ask for a code. If you set one, enter it in the gate. The code stays in the Render dashboard only.

Local check, unchanged, on your machine: site `http://127.0.0.1:5173`, API `http://127.0.0.1:8000/api/health`. This deploy prep did not start or stop those processes.

## Five deploy failures and what to change

1. **The public site still calls `http://127.0.0.1:8000`.** `VITE_API_URL` was missing at build time, or it was blank. Set it on Vercel to the Render `https` origin and redeploy. Local dev can keep the variable unset.
2. **The browser console says the request was blocked by CORS.** `FRONTEND_ORIGIN` is not the exact Vercel origin (scheme, host, no path, no trailing slash), or a preview URL was never added. Set `FRONTEND_ORIGIN` to the production origin and put any extra origins in `CORS_ORIGINS`, comma-separated, including `http://127.0.0.1:5173`. Never use `*`. The API rejects `*` because the browser sends credentials.
3. **Render never goes live, or the health check fails.** The start command must be `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT`. The health path must be `/api/health`. Binding to `127.0.0.1` or port `8000` fails on Render. A blank `FRONTEND_ORIGIN` also stops startup, because an origin is required.
4. **The project you created is gone after a while, or the first click sits on a loading page.** That is the free instance. The disk is ephemeral, and the service spins down after 15 minutes. Uploads are not kept. A persistent disk requires a paid compute plan. See the cost trade-off above.
5. **The build fails, or the API is up but the synthetic project never appears.** Read the Render logs. `npm ci --prefix tools/layout` must succeed or elkjs layout cannot run. If pip fails on Python `3.14.3`, set `PYTHON_VERSION` to a fully qualified release Render accepts (this PC uses `3.14.6`; that patch on Render is unconfirmed). If the log shows the process was killed, the free 512 MB plan ran out of memory during install or during demo processing. Set `DEMO_SEED_PROCESS` to `false`, or move the service to a larger plan you choose to pay for. Do not install libcairo or Graphviz to fix that. OCR stays off (`OCR_IN_BUILD=false`) because the Tesseract program is not in this image. A seed error is logged and the API can still answer `/api/health`.
