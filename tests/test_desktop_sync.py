import contextlib
import hashlib
import io
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from werkzeug.serving import make_server

from app import create_app
from desktop_sync import LocalPreview, QuietRequestHandler, desktop_config, server_settings, workbook_path
from tests.workbook_fixture import sample_workbook


class DesktopSyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.local = self.root / ".local"
        self.local.mkdir()
        self.workbook = sample_workbook()
        self.source = self.root / "虚构流水表 含空格.xlsx"
        self.source.write_bytes(self.workbook)
        self.digest = hashlib.sha256(self.workbook).hexdigest()

    def tearDown(self):
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.digest)
        self.directory.cleanup()

    def test_quoted_relative_path_and_bom_configuration(self):
        config = self.local / "remote-sync.txt"
        config.write_text(f'url=http://127.0.0.1\ntoken=test-only\nwatch="{self.source.name}"\n', encoding="utf-8-sig")
        watch, values = desktop_config("remote", self.root)
        self.assertEqual(watch, self.source.resolve())
        self.assertEqual(values["url"], "http://127.0.0.1")
        self.assertEqual(workbook_path(f'"{self.source}"'), self.source.resolve())

    def test_local_configuration_takes_precedence_and_remote_is_fallback(self):
        (self.local / "remote-sync.txt").write_text(f"watch={self.source}\n", encoding="utf-8")
        self.assertEqual(desktop_config("local", self.root)[0], self.source.resolve())
        second = self.root / "第二份虚构表.xlsx"
        second.write_bytes(self.workbook)
        (self.local / "local-sync.txt").write_text(f"watch={second}\n", encoding="utf-8")
        self.assertEqual(desktop_config("local", self.root)[0], second.resolve())

    def test_invalid_files_are_rejected_without_creating_or_modifying_them(self):
        for source in [self.root / "missing.xlsx", self.root, self.root / "wrong.csv"]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                workbook_path(source)
        large = self.root / "large.xlsx"
        large.write_bytes(b"x" * (10 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, "10 MB"):
            workbook_path(large)
        self.assertFalse((self.root / "missing.xlsx").exists())

    def test_remote_address_and_token_validation(self):
        self.assertEqual(server_settings({"url": "https://example.com/", "token": "test-only"}), ("https://example.com", "test-only"))
        for url in ["", "file:///tmp/test", "https://user:secret@example.com", "https://example.com/?q=x", "https://example.com/#fragment", "http://example.com:99999"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                server_settings({"url": url, "token": "test-only"})
        with self.assertRaises(ValueError):
            server_settings({"url": "https://example.com", "token": ""})

    def test_local_preview_imports_read_only_and_serves_public_query(self):
        preview = LocalPreview(self.root, self.source, port=0)
        try:
            preview.start()
            deadline = time.monotonic() + 7
            data = None
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(preview.url + "/data/sheet2.json", timeout=2) as response:
                        data = json.load(response)
                    break
                except urllib.error.HTTPError as error:
                    self.assertEqual(error.code, 404)
                    time.sleep(0.1)
            self.assertIsNotNone(data)
            self.assertEqual(len(data["drivers"]), 2)
            snapshot = json.loads((self.local / "server" / "current.json").read_text(encoding="utf-8"))
            self.assertEqual(snapshot["audit"]["sourceSha256"], self.digest)
        finally:
            preview.stop()

    def test_occupied_port_does_not_stop_existing_server(self):
        preview = LocalPreview(self.root, self.source, port=0)
        try:
            preview.start()
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaisesRegex(RuntimeError, "端口已被占用"):
                LocalPreview(self.root, self.source, port=preview.server.server_port)
            with urllib.request.urlopen(preview.url, timeout=2) as response:
                self.assertEqual(response.status, 200)
        finally:
            preview.stop()

    def test_gui_worker_protocol_pushes_to_a_test_server(self):
        server_data = self.root / "test-server-data"
        app = create_app(dict(TESTING=True, SECRET_KEY="test-only", ADMIN_PASSWORD="test-admin", SYNC_TOKEN="test-token", DATA_DIR=str(server_data)))
        server = make_server("127.0.0.1", 0, app, threaded=True, request_handler=QuietRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        config = self.local / "worker-test.txt"
        config.write_text(f"watch={self.source}\nurl=http://127.0.0.1:{server.server_port}\ntoken=test-token\n", encoding="utf-8")
        worker_script = Path(__file__).resolve().parents[1] / "desktop_sync.py"
        process = subprocess.Popen([sys.executable, "-u", str(worker_script), "--mode", "remote", "--config", str(config)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        events = queue.Queue()

        def read_events():
            for line in process.stdout:
                events.put(json.loads(line))

        reader = threading.Thread(target=read_events, daemon=True)
        reader.start()
        try:
            states = []
            deadline = time.monotonic() + 9
            while time.monotonic() < deadline:
                event = events.get(timeout=max(0.1, deadline - time.monotonic()))
                states.append(event["state"])
                self.assertNotIn("test-token", event["message"])
                if event["state"] == "synced":
                    break
            self.assertIn("synced", states)
            snapshot = json.loads((server_data / "current.json").read_text(encoding="utf-8"))
            self.assertEqual(snapshot["source"]["kind"], "remote-sync")
            self.assertEqual(snapshot["audit"]["included_drivers"], 2)
        finally:
            process.terminate()
            process.wait(timeout=5)
            reader.join(timeout=2)
            process.stdout.close()
            process.stderr.close()
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
