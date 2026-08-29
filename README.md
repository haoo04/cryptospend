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

## Google Drive database backups

Google Drive backup is optional. The application continues to work locally when Google Drive is not configured.

1. In Google Cloud, create or select a project, enable the Google Drive API, configure the OAuth consent screen, and create a **Desktop app** OAuth client.
2. Download the OAuth client JSON to a location outside the repository.
3. Install the backend requirements from `backend`:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   ```

4. Edit `backend/.env` and set the client path:

   ```dotenv
   CRYPTOSPEND_GOOGLE_CLIENT_SECRETS_FILE=C:/private/google-drive-client.json
   ```

   The backend loads this file at startup. An environment variable already set in the process takes precedence over the `.env` value.
   The default callback is `http://127.0.0.1:8000/api/backups/google-drive/oauth/callback`. Set `CRYPTOSPEND_GOOGLE_DRIVE_REDIRECT_URI` if the backend uses another local URL.
5. Start CryptoSpend, open **Settings**, and choose **Connect Google Drive**.
6. After approving access in the browser, choose **Backup database**. Each backup is uploaded as a new timestamped file in the `CryptoSpend Backups` folder.

The app requests the limited `drive.file` scope. The refresh token is stored in `backend/data/google-drive-token.dpapi`, protected by Windows DPAPI. Do not commit the OAuth client JSON or token file.
