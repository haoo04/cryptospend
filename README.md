# CryptoSpend

Local-first personal crypto accounting for MYR reporting. The backend is the authority for all financial calculations; decimal API values are strings and MYR book amounts are stored as integer micros.

## Local development

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.maintenance migrate
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
npm.cmd run dev
```

Run verification with `pytest` and `ruff check .` from `backend`, then `npm.cmd run test`, `npm.cmd run lint`, and `npm.cmd run build` from `frontend`.
