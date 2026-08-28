import re
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import google_drive
from app.google_drive import GoogleDriveError, upload_database_backup


class FakeRequest:
    def __init__(self, result: dict, media=None, failure: Exception | None = None) -> None:
        self.result = result
        self.media = media
        self.failure = failure

    def execute(self) -> dict:
        if self.failure:
            raise self.failure
        if self.media is not None:
            assert self.media.path.exists()
            self.media.uploaded_bytes = self.media.path.read_bytes()
        return self.result


class FakeMedia:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.uploaded_bytes = b""


class FakeFiles:
    def __init__(self, *, folder_id: str | None, upload_failure: Exception | None = None) -> None:
        self.folder_id = folder_id
        self.upload_failure = upload_failure
        self.folder_body: dict | None = None
        self.upload_body: dict | None = None
        self.media: FakeMedia | None = None

    def get(self, **_kwargs):
        if self.folder_id is None:
            raise RuntimeError("folder lookup should not happen without a stored folder")
        return FakeRequest({"id": self.folder_id, "mimeType": "application/vnd.google-apps.folder"})

    def create(self, *, body: dict, media_body=None, **_kwargs):
        if media_body is None:
            self.folder_body = body
            self.folder_id = "new-folder"
            return FakeRequest({"id": self.folder_id, "mimeType": "application/vnd.google-apps.folder"})
        self.upload_body = body
        self.media = media_body
        return FakeRequest(
            {"id": "file-1", "name": body["name"], "webViewLink": "https://drive.google.com/file/file-1"},
            media=media_body,
            failure=self.upload_failure,
        )


class FakeService:
    def __init__(self, files: FakeFiles) -> None:
        self.files_resource = files

    def files(self) -> FakeFiles:
        return self.files_resource


def make_source_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES ('preserved')")


def test_status_reports_missing_configuration(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(google_drive.CLIENT_SECRETS_ENV, raising=False)
    response = client.get("/api/backups/google-drive/status")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert response.json()["connected"] is False
    assert google_drive.CLIENT_SECRETS_ENV in response.json()["message"]


def test_upload_requires_connection(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(google_drive.CLIENT_SECRETS_ENV, raising=False)
    response = client.post("/api/backups/google-drive/upload")

    assert response.status_code == 503
    assert google_drive.CLIENT_SECRETS_ENV in response.json()["detail"]


def test_oauth_callback_validates_state_and_saves_refresh_token(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client_json = tmp_path / "client.json"
    client_json.write_text("{}", encoding="utf-8")
    monkeypatch.setenv(google_drive.CLIENT_SECRETS_ENV, str(client_json))

    class FakeCredentials:
        refresh_token = "refresh-token"

    class FakeFlow:
        credentials = FakeCredentials()

        def authorization_url(self, **_kwargs):
            return "https://accounts.google.com/o/oauth2/auth", "state-123"

        def fetch_token(self, *, code: str):
            assert code == "auth-code"

    saved: dict = {}
    monkeypatch.setattr(google_drive, "_new_oauth_flow", lambda _state=None: FakeFlow())
    monkeypatch.setattr(google_drive, "save_token_envelope", lambda envelope, path=None: saved.update(envelope))

    start = client.get("/api/backups/google-drive/connect", follow_redirects=False)
    assert start.status_code == 302
    assert start.headers["location"] == "https://accounts.google.com/o/oauth2/auth"

    rejected = client.get(
        "/api/backups/google-drive/oauth/callback", params={"code": "auth-code", "state": "wrong-state"}
    )
    assert rejected.status_code == 400
    assert "wrong-state" not in rejected.text
    assert saved == {}

    completed = client.get(
        "/api/backups/google-drive/oauth/callback", params={"code": "auth-code", "state": "state-123"}
    )
    assert completed.status_code == 200
    assert saved == {"refresh_token": "refresh-token", "scopes": [google_drive.DRIVE_SCOPE]}


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI is required")
def test_dpapi_token_roundtrip(tmp_path: Path) -> None:
    token_path = tmp_path / "token.dpapi"
    envelope = {"refresh_token": "secret-refresh-token", "folder_id": "folder-1"}

    google_drive.save_token_envelope(envelope, token_path)

    assert b"secret-refresh-token" not in token_path.read_bytes()
    assert google_drive.load_token_envelope(token_path) == envelope


def test_upload_creates_sqlite_snapshot_and_drive_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.db"
    make_source_database(source)
    files = FakeFiles(folder_id=None)
    service = FakeService(files)
    envelope = {"refresh_token": "refresh-token"}
    saved: dict = {}
    monkeypatch.setattr(google_drive, "create_drive_service", lambda: (service, envelope))
    monkeypatch.setattr(google_drive, "create_media_upload", lambda path: FakeMedia(path))
    monkeypatch.setattr(google_drive, "save_token_envelope", lambda value, path=None: saved.update(value))

    result = upload_database_backup(source)

    assert files.folder_body == {
        "name": google_drive.BACKUP_FOLDER_NAME,
        "mimeType": google_drive.BACKUP_FOLDER_MIME_TYPE,
        "parents": ["root"],
    }
    assert files.upload_body is not None
    assert files.upload_body["parents"] == ["new-folder"]
    assert re.fullmatch(r"cryptospend-backup-\d{8}T\d{6}Z\.db", result["name"] or "")
    assert result["id"] == "file-1"
    assert result["web_view_link"] == "https://drive.google.com/file/file-1"
    assert b"preserved" in (files.media.uploaded_bytes if files.media else b"")
    assert saved["folder_id"] == "new-folder"
    assert files.media is not None
    assert not files.media.path.exists()


def test_upload_reuses_folder_and_cleans_snapshot_after_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.db"
    make_source_database(source)
    files = FakeFiles(folder_id="existing-folder", upload_failure=RuntimeError("network down"))
    service = FakeService(files)
    envelope = {"refresh_token": "refresh-token", "folder_id": "existing-folder"}
    monkeypatch.setattr(google_drive, "create_drive_service", lambda: (service, envelope))
    monkeypatch.setattr(google_drive, "create_media_upload", lambda path: FakeMedia(path))

    with pytest.raises(GoogleDriveError, match="upload the SQLite backup"):
        upload_database_backup(source)

    assert files.folder_body is None
    assert files.media is not None
    assert not files.media.path.exists()
