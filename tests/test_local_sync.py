import io
import json
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from app import create_app
from tests.workbook_fixture import sample_workbook

ROOT = Path(__file__).resolve().parents[1]


class LocalSyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.watched = self.root / "watch.xlsx"
        self.original = sample_workbook()
        self.watched.write_bytes(self.original)
        self.app = create_app(dict(TESTING=True, SECRET_KEY="test-only", ADMIN_PASSWORD="test-admin", VIEW_PASSWORD="viewer", DATA_DIR=str(self.root / "data"), WATCH_FILE=str(self.watched)))
        self.watcher = self.app.extensions["local_sync"]

    def tearDown(self):
        self.directory.cleanup()

    def check_saved(self, now):
        self.watcher.check_once(now)
        self.watcher.check_once(now + 2)

    def current(self):
        return json.loads((self.root / "data" / "current.json").read_text(encoding="utf-8"))

    def test_save_updates_data_and_failed_save_preserves_it(self):
        self.watcher.check_once(0)
        self.assertFalse((self.root / "data" / "current.json").exists())
        self.watcher.check_once(2)
        self.assertEqual(self.current()["audit"]["included_drivers"], 2)
        output = io.BytesIO()
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with ZipFile(io.BytesIO(self.original)) as archive, ZipFile(output, "w") as changed:
            for entry in archive.infolist():
                content = archive.read(entry.filename)
                if entry.filename == "xl/worksheets/sheet2.xml":
                    xml = ET.fromstring(content)
                    xml.find(".//s:c[@r='A2']", ns).set("s", "1")
                    content = ET.tostring(xml)
                changed.writestr(entry, content)
        self.watched.write_bytes(output.getvalue())
        self.check_saved(4)
        self.assertEqual(self.current()["audit"]["included_drivers"], 1)
        self.assertEqual(self.current()["audit"]["total_amount_cents"], 5000)
        self.assertEqual(self.current()["source"]["kind"], "local")
        previous = self.current()
        self.watched.write_bytes(b"unfinished or damaged Excel")
        self.check_saved(8)
        self.assertEqual(self.current(), previous)
        self.assertEqual(self.watcher.status()["state"], "error")
        self.watched.write_bytes(self.original)
        self.check_saved(12)
        self.assertEqual(self.current()["audit"]["included_drivers"], 2)
        self.assertEqual(self.watcher.status()["state"], "synced")

    def test_identical_file_touch_does_not_republish(self):
        self.check_saved(0)
        first_version = self.current()["uploadedAt"]
        stat = self.watched.stat()
        os.utime(self.watched, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        self.check_saved(4)
        self.assertEqual(self.current()["uploadedAt"], first_version)

    def test_missing_file_recovers_and_status_requires_permission(self):
        self.watched.unlink()
        self.watcher.check_once(0)
        self.assertEqual(self.watcher.status()["state"], "error")
        self.watched.write_bytes(self.original)
        self.check_saved(4)
        self.assertEqual(self.current()["audit"]["included_drivers"], 2)
        with self.app.test_client() as client:
            self.assertEqual(client.get("/api/local-sync").status_code, 401)
            with client.session_transaction() as session:
                session["role"] = "viewer"
            self.assertEqual(client.get("/api/local-sync").status_code, 403)
            state = client.get("/api/data-status").get_json()
            self.assertEqual(state["version"], self.current()["uploadedAt"])
            with client.session_transaction() as session:
                session["role"] = "admin"
            self.assertEqual(client.get("/api/local-sync").get_json()["sync"]["state"], "synced")


if __name__ == "__main__":
    unittest.main()
