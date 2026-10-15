@echo off
cd /d C:\Users\Admin\untangle\backend
set FRONTEND_ORIGIN=https://untangle-coral.vercel.app
set CORS_ORIGINS=http://127.0.0.1:5173
set PUBLIC_DEMO_MODE=false
set DEMO_SEED_PROCESS=false
C:\Users\Admin\untangle\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
