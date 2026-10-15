# Demo access and upload limits

This is a lightweight shared gate for a public demo. It is not user login, and it is not a certification boundary.

## What is protected

- Uploads check the extension and the file contents. A PDF must start with `%PDF`. An `.xlsx` file must be a zip with the workbook parts. `.xlsm`, `.xls`, macros, and external links are refused.
- Declared uncompressed size and zip entry count are capped before the workbook is opened.
- PDF page count is capped. Password-protected and empty PDFs are refused.
- Inspection of those two files runs in a child process with `INSPECT_TIMEOUT_SECONDS`. If that child stops responding, it is killed and the API keeps running.
- Stored files use random folder ids and fixed names (`original.pdf`, `io_list.xlsx`). The browser name is display text only.
- Downloads send a content type and a `Content-Disposition` name that cannot be a path.
- Excel is read with `data_only=True`, so formulas are not evaluated. Export cells that start with `=`, `+`, `-`, or `@` are prefixed.
- Error JSON does not include stack traces or filesystem paths. The server log keeps the exception type.
- `DEMO_ACCESS_CODE`, when set, requires a token. The code is compared by hashing both sides first. The token lives in process memory and in an HttpOnly cookie. The code is not in the frontend bundle.
- When the code is unset, local development has no gate.
- `PUBLIC_DEMO_MODE=true` refuses uploads and Modify, and seeds one synthetic project.
- Security headers are set on API responses. CORS allows only the configured origins, with credentials. It is never `*`.
- Upload, re-import, processing, export, and print routes are counted per process.

## What is not protected

- There are no user accounts. Anyone who has the demo code can use the server.
- The rate limit is inside one process. A restart clears it. Two processes do not share it.
- A drawing stage that is already inside a native library call is not killed mid-call. The job is marked failed when that call returns or the next stage sees the clock. The original files stay in place.
- There is no cancel route. Retry is `POST /api/jobs/{id}/process?retry=true`.
- The gate token in the browser is kept in `sessionStorage` so the site on port 5173 can call the API on port 8000. A script running in the page can read that token. That is acceptable for this demo gate and is not a substitute for a login system.
- SQLite and the upload folder are only as durable as the disk they sit on.

## Dependency audit

Checked on 15 October 2026.

- `pip-audit -r backend/requirements.txt`: no known vulnerabilities.
- `npm audit` in `frontend`: 7 findings, all through Tailwind CSS 3 and its build tools (braces, chokidar, micromatch, postcss-selector-parser). The suggested fix is Tailwind 4, which is a major upgrade. Those packages are used while building the site. They are not a reason to rewrite the interface in this phase. The findings stay documented rather than force-upgraded.
