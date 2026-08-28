from __future__ import annotations

import ctypes
import json
import os
import secrets
import sys
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.database import BACKEND_DIR, DATABASE_URL
from app.maintenance import backup_database

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
BACKUP_FOLDER_NAME = "CryptoSpend Backups"
BACKUP_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
CLIENT_SECRETS_ENV = "CRYPTOSPEND_GOOGLE_CLIENT_SECRETS_FILE"
TOKEN_FILE_ENV = "CRYPTOSPEND_GOOGLE_DRIVE_TOKEN_FILE"
REDIRECT_URI_ENV = "CRYPTOSPEND_GOOGLE_DRIVE_REDIRECT_URI"
DEFAULT_TOKEN_PATH = BACKEND_DIR / "data" / "google-drive-token.dpapi"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8000/api/backups/google-drive/oauth/callback"
OAUTH_STATE_TTL = timedelta(minutes=10)


class GoogleDriveError(RuntimeError):
    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


_pending_oauth: tuple[str, datetime] | None = None
_pending_oauth_lock = threading.Lock()


def _is_windows() -> bool:
    return sys.platform == "win32"


def _client_secrets_path() -> Path | None:
    value = os.getenv(CLIENT_SECRETS_ENV)
    return Path(value).expanduser() if value else None


def _token_path() -> Path:
    value = os.getenv(TOKEN_FILE_ENV)
    return Path(value).expanduser() if value else DEFAULT_TOKEN_PATH


def _redirect_uri() -> str:
    return os.getenv(REDIRECT_URI_ENV, DEFAULT_REDIRECT_URI)


def get_backup_status() -> dict[str, Any]:
    client_path = _client_secrets_path()
    configured = client_path is not None and client_path.is_file()
    supported = _is_windows()
    connected = False
    message: str | None = None

    if not supported:
        message = "Google Drive backup token storage requires Windows DPAPI."
    elif not configured:
        message = f"Set {CLIENT_SECRETS_ENV} to a valid Desktop OAuth JSON file."
    elif _token_path().exists():
        try:
            envelope = load_token_envelope()
            connected = bool(envelope and envelope.get("refresh_token"))
            if not connected:
                message = "Connect Google Drive to enable backups."
        except GoogleDriveError:
            message = "Google Drive authorization must be reconnected."
    else:
        message = "Connect Google Drive to enable backups."

    return {
        "configured": configured,
        "supported": supported,
        "connected": connected,
        "folder_name": BACKUP_FOLDER_NAME,
        "message": message,
    }


def _require_client_secrets() -> Path:
    path = _client_secrets_path()
    if path is None or not path.is_file():
        raise GoogleDriveError(f"Set {CLIENT_SECRETS_ENV} to a valid Desktop OAuth JSON file.")
    if not _is_windows():
        raise GoogleDriveError("Google Drive backup token storage requires Windows DPAPI.")
    return path


def configured_database_path() -> Path:
    if DATABASE_URL.endswith(":memory:"):
        raise GoogleDriveError("An in-memory database cannot be backed up.", 409)
    if not DATABASE_URL.startswith("sqlite:///"):
        raise GoogleDriveError("Google Drive backup currently supports SQLite databases only.", 409)
    path = Path(DATABASE_URL.removeprefix("sqlite:///"))
    return path if path.is_absolute() else path.resolve()


def _protect_data(data: bytes) -> bytes:
    if not _is_windows():
        raise GoogleDriveError("Google Drive backup token storage requires Windows DPAPI.")

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    input_blob = _DataBlob(len(data), input_buffer)
    output_blob = _DataBlob()
    protected = crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0x1,
        ctypes.byref(output_blob),
    )
    if not protected:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _unprotect_data(data: bytes) -> bytes:
    if not _is_windows():
        raise GoogleDriveError("Google Drive backup token storage requires Windows DPAPI.")

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    input_blob = _DataBlob(len(data), input_buffer)
    output_blob = _DataBlob()
    unprotected = crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0x1,
        ctypes.byref(output_blob),
    )
    if not unprotected:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def save_token_envelope(envelope: dict[str, Any], path: Path | None = None) -> None:
    destination = path or _token_path()
    try:
        payload = json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        protected = _protect_data(payload)
    except GoogleDriveError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise GoogleDriveError("Unable to protect Google Drive authorization data.") from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(protected)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, destination)
    except OSError as exc:
        raise GoogleDriveError("Unable to save Google Drive authorization data.") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_token_envelope(path: Path | None = None) -> dict[str, Any] | None:
    source = path or _token_path()
    if not source.exists():
        return None
    try:
        payload = _unprotect_data(source.read_bytes())
        envelope = json.loads(payload.decode("utf-8"))
    except GoogleDriveError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise GoogleDriveError("Google Drive authorization data is invalid; reconnect Google Drive.", 409) from exc
    if not isinstance(envelope, dict) or not isinstance(envelope.get("refresh_token"), str):
        raise GoogleDriveError("Google Drive authorization data is invalid; reconnect Google Drive.", 409)
    return envelope


def _new_oauth_flow(state: str | None = None) -> Any:
    client_path = _require_client_secrets()
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:
        raise GoogleDriveError("Install the Google Drive Python dependencies before connecting.") from exc

    try:
        flow = Flow.from_client_secrets_file(str(client_path), scopes=[DRIVE_SCOPE], state=state)
    except Exception as exc:
        raise GoogleDriveError("The Google OAuth client JSON file is invalid.") from exc
    flow.redirect_uri = _redirect_uri()
    return flow


def begin_authorization() -> str:
    flow = _new_oauth_flow()
    try:
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
    except Exception as exc:
        raise GoogleDriveError("Unable to start Google Drive authorization.") from exc

    global _pending_oauth
    with _pending_oauth_lock:
        _pending_oauth = (state, datetime.now(UTC) + OAUTH_STATE_TTL)
    return authorization_url


def _consume_oauth_state(state: str) -> bool:
    global _pending_oauth
    with _pending_oauth_lock:
        pending = _pending_oauth
        if pending is None:
            return False
        expected_state, expires_at = pending
        if expires_at <= datetime.now(UTC):
            _pending_oauth = None
            return False
        if not secrets.compare_digest(expected_state, state):
            return False
        _pending_oauth = None
        return True


def complete_authorization(code: str | None, state: str | None, error: str | None = None) -> None:
    if not state or not _consume_oauth_state(state):
        raise GoogleDriveError("Google authorization session expired; start the connection again.", 400)
    if error:
        raise GoogleDriveError("Google Drive authorization was cancelled.", 400)
    if not code:
        raise GoogleDriveError("Google Drive authorization did not return a code.", 400)

    flow = _new_oauth_flow(state)
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise GoogleDriveError("Google Drive authorization could not be completed.", 400) from exc

    refresh_token = getattr(flow.credentials, "refresh_token", None)
    if not refresh_token:
        raise GoogleDriveError("Google did not return a refresh token; connect again.", 400)

    existing_folder_id: str | None = None
    try:
        existing = load_token_envelope()
        if existing and isinstance(existing.get("folder_id"), str):
            existing_folder_id = existing["folder_id"]
    except GoogleDriveError:
        pass

    envelope: dict[str, Any] = {"refresh_token": refresh_token, "scopes": [DRIVE_SCOPE]}
    if existing_folder_id:
        envelope["folder_id"] = existing_folder_id
    save_token_envelope(envelope)


def _build_credentials(envelope: dict[str, Any]) -> Any:
    client_path = _require_client_secrets()
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise GoogleDriveError("Install the Google Drive Python dependencies before uploading.") from exc

    try:
        config = json.loads(client_path.read_text(encoding="utf-8"))
        client = config.get("installed") or config.get("web")
        credentials = Credentials(
            token=None,
            refresh_token=envelope["refresh_token"],
            token_uri=client["token_uri"],
            client_id=client["client_id"],
            client_secret=client.get("client_secret"),
            scopes=[DRIVE_SCOPE],
        )
        credentials.refresh(Request())
        return credentials
    except GoogleDriveError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise GoogleDriveError("The Google OAuth client JSON file is invalid.") from exc
    except Exception as exc:
        raise GoogleDriveError(
            "Google Drive authorization expired or was revoked; reconnect Google Drive.", 409
        ) from exc


def create_drive_service() -> tuple[Any, dict[str, Any]]:
    _require_client_secrets()
    envelope = load_token_envelope()
    if envelope is None:
        raise GoogleDriveError("Connect Google Drive before creating a backup.", 409)
    credentials = _build_credentials(envelope)
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GoogleDriveError("Install the Google Drive Python dependencies before uploading.") from exc
    try:
        return build("drive", "v3", credentials=credentials, cache_discovery=False), envelope
    except Exception as exc:
        raise GoogleDriveError("Unable to connect to Google Drive.") from exc


def create_media_upload(path: Path) -> Any:
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise GoogleDriveError("Install the Google Drive Python dependencies before uploading.") from exc
    return MediaFileUpload(str(path), mimetype="application/x-sqlite3", resumable=True)


def _http_status(error: BaseException) -> int | None:
    response = getattr(error, "resp", None)
    status = getattr(response, "status", None) or getattr(error, "status_code", None)
    return status if isinstance(status, int) else None


def _drive_request_error(error: BaseException, fallback: str) -> GoogleDriveError:
    status = _http_status(error)
    if status == 401:
        return GoogleDriveError("Google Drive authorization expired or was revoked; reconnect Google Drive.", 409)
    if status == 403:
        return GoogleDriveError("Google Drive denied this operation; check the granted permissions.", 403)
    if status == 404:
        return GoogleDriveError("The Google Drive backup folder is unavailable; try again.", 409)
    return GoogleDriveError(fallback, 502)


def _ensure_backup_folder(service: Any, envelope: dict[str, Any]) -> str:
    folder_id = envelope.get("folder_id")
    if isinstance(folder_id, str) and folder_id:
        try:
            folder = service.files().get(fileId=folder_id, fields="id,name,mimeType").execute()
            if folder.get("mimeType") == BACKUP_FOLDER_MIME_TYPE:
                return folder_id
        except Exception as exc:
            if _http_status(exc) != 404:
                raise _drive_request_error(exc, "Unable to access the Google Drive backup folder.") from exc

    try:
        folder = (
            service.files()
            .create(
                body={
                    "name": BACKUP_FOLDER_NAME,
                    "mimeType": BACKUP_FOLDER_MIME_TYPE,
                    "parents": ["root"],
                },
                fields="id,name,mimeType",
            )
            .execute()
        )
    except Exception as exc:
        raise _drive_request_error(exc, "Unable to create the Google Drive backup folder.") from exc

    folder_id = folder.get("id")
    if not isinstance(folder_id, str) or not folder_id:
        raise GoogleDriveError("Google Drive did not return a backup folder ID.", 502)
    envelope["folder_id"] = folder_id
    save_token_envelope(envelope)
    return folder_id


def upload_database_backup(database_path: Path | None = None) -> dict[str, str | None]:
    service, envelope = create_drive_service()
    source = database_path or configured_database_path()
    if not source.exists() or not source.is_file():
        raise GoogleDriveError("The SQLite database is not available for backup.", 409)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    file_name = f"cryptospend-backup-{timestamp}.db"

    with tempfile.TemporaryDirectory(prefix="cryptospend-db-backup-") as temporary_directory:
        snapshot = Path(temporary_directory) / "database.db"
        try:
            backup_database(source, snapshot)
        except GoogleDriveError:
            raise
        except Exception as exc:
            raise GoogleDriveError("Unable to create a consistent SQLite backup.", 409) from exc

        folder_id = _ensure_backup_folder(service, envelope)
        media = create_media_upload(snapshot)
        try:
            uploaded = (
                service.files()
                .create(
                    body={"name": file_name, "parents": [folder_id]},
                    media_body=media,
                    fields="id,name,webViewLink,createdTime",
                )
                .execute()
            )
        except Exception as exc:
            raise _drive_request_error(exc, "Unable to upload the SQLite backup to Google Drive.") from exc

    file_id = uploaded.get("id")
    if not isinstance(file_id, str) or not file_id:
        raise GoogleDriveError("Google Drive did not return an uploaded file ID.", 502)
    return {
        "id": file_id,
        "name": uploaded.get("name") if isinstance(uploaded.get("name"), str) else file_name,
        "web_view_link": uploaded.get("webViewLink") if isinstance(uploaded.get("webViewLink"), str) else None,
        "created_at": uploaded.get("createdTime")
        if isinstance(uploaded.get("createdTime"), str)
        else datetime.now(UTC).isoformat(),
    }
