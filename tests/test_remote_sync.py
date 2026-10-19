import io
import json
import tempfile
import threading
import unittest
from pathlib import Path

from werkzeug.serving import make_server

from app import create_app
from local_sync import LocalWorkbookSync, RetryableSyncError, SyncRejected
from remote_sync import RemoteUploader
from tests.workbook_fixture import sample_workbook


class RemoteSyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.watched = self.root / "watch.xlsx"
        self.workbook = sample_workbook()
        self.watched.write_bytes(self.workbook)
        self.data_dir = self.root / "data"
        self.app = create_app(dict(TESTING=True, SECRET_KEY="test-only", ADMIN_PASSWORD="admin", VIEW_PASSWORD="viewer", DATA_DIR=str(self.data_dir), SYNC_TOKEN="sync-token"))
        self.server = make_server("127.0.0.1", 0, self.app, threaded=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.directory.cleanup()

    def current(self):
        return json.loads((self.data_dir / "current.json").read_text(encoding="utf-8"))

    def test_token_upload_and_rejection_keep_previous_data(self):
        result = RemoteUploader(self.url, "sync-token").upload("watch.xlsx", self.workbook)
        self.assertTrue(result["ok"])
        self.assertEqual(self.current()["audit"]["included_drivers"], 2)
        self.assertEqual(self.current()["source"]["kind"], "remote-sync")
        previous = self.current()
        with self.assertRaises(SyncRejected):
            RemoteUploader(self.url, "wrong-token").upload("watch.xlsx", self.workbook)
        with self.assertRaises(SyncRejected):
            RemoteUploader(self.url, "sync-token").upload("broken.xlsx", b"not an Excel file")
        self.assertEqual(self.current(), previous)

    def test_bearer_token_is_accepted(self):
        client = self.app.test_client()
        response = client.post("/api/sync", data={"workbook": (io.BytesIO(self.workbook), "x.xlsx")}, headers={"Authorization": "Bearer sync-token"})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertTrue(response.get_json()["ok"])

    def test_endpoint_is_disabled_without_configured_token(self):
        app = create_app(dict(TESTING=True, SECRET_KEY="x", ADMIN_PASSWORD="admin", VIEW_PASSWORD="viewer", DATA_DIR=str(self.root / "disabled")))
        with app.test_client() as client:
            response = client.post("/api/sync", data={"workbook": (io.BytesIO(self.workbook), "x.xlsx")}, headers={"X-Sync-Token": "anything"})
            self.assertEqual(response.status_code, 404)
            self.assertFalse((self.root / "disabled" / "current.json").exists())

    def test_transient_failure_retries_same_save(self):
        calls = []

        def publish(_payload, _audit, _source, _contents):
            calls.append(1)
            if len(calls) == 1:
                raise RetryableSyncError("network down")

        sync = LocalWorkbookSync(self.watched, publish, stable_seconds=1.5, retry_seconds=5)
        sync.check_once(0)
        sync.check_once(2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sync.status()["state"], "error")
        sync.check_once(4)
        self.assertEqual(len(calls), 1)
        sync.check_once(7)
        self.assertEqual(len(calls), 2)
        self.assertEqual(sync.status()["state"], "synced")

    def test_watcher_pushes_through_http(self):
        uploader = RemoteUploader(self.url, "sync-token")
        sync = LocalWorkbookSync(self.watched, lambda _payload, _audit, _source, contents: uploader.upload(self.watched.name, contents))
        sync.check_once(0)
        sync.check_once(2)
        self.assertEqual(sync.status()["state"], "synced")
        self.assertEqual(self.current()["audit"]["included_drivers"], 2)
        self.assertEqual(self.current()["source"]["kind"], "remote-sync")


if __name__ == "__main__":
    unittest.main()
