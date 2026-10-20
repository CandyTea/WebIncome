import hashlib
import io
import json
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from app import create_app
from tools.export_sheet2 import extract_bytes
from tests.workbook_fixture import sample_workbook

ROOT = Path(__file__).resolve().parents[1]


class PortalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workbook = sample_workbook()
        cls.before = hashlib.sha256(cls.workbook).hexdigest()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.config = dict(TESTING=True, SECRET_KEY="test-only", DATA_DIR=self.directory.name,
                           ADMIN_PASSWORD="test-admin", VIEW_PASSWORD="test-viewer")
        self.app = create_app(self.config)
        self.client = self.app.test_client()

    def tearDown(self):
        self.directory.cleanup()
        self.assertEqual(hashlib.sha256(self.workbook).hexdigest(), self.before)

    def login(self, password="test-admin"):
        page = self.client.get("/login")
        token = re.search(rb'name="csrf" value="([^"]+)"', page.data).group(1).decode()
        return self.client.post("/login", data={"password": password, "csrf": token})

    def upload(self, content=None, token=True):
        self.client.get("/admin")
        with self.client.session_transaction() as session:
            csrf = session.get("csrf", "")
        return self.client.post("/api/upload", data={"workbook": (io.BytesIO(content if content is not None else self.workbook), "流水.xlsx")},
                                headers={"X-CSRF-Token": csrf} if token else {})

    def test_login_and_unauthed_data_protection(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertEqual(self.client.get("/data/sheet2.json").status_code, 401)
        self.assertEqual(self.login("wrong").status_code, 401)
        self.assertEqual(self.login().status_code, 302)
        with self.client.get("/") as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/.git/config").status_code, 404)
        self.assertEqual(self.client.get("/全部流水表(1).xlsx").status_code, 404)

    def test_viewer_cannot_upload(self):
        self.login("test-viewer")
        self.assertEqual(self.client.get("/admin").status_code, 403)
        self.assertEqual(self.upload().status_code, 403)

    def test_local_pinyin_module_is_served_without_exposing_private_files(self):
        with self.client.get("/pinyin-pro.mjs") as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn(response.mimetype, ("text/javascript", "application/javascript"))
            self.assertEqual(response.data, (ROOT / "dist" / "pinyin-pro.mjs").read_bytes())
            self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
        for path in ("/.local/remote-sync.txt", "/../app.py", "/vendor/../../.env"):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_csrf_is_required(self):
        self.login()
        self.assertEqual(self.upload(token=False).status_code, 400)
        self.assertFalse((Path(self.directory.name) / "current.json").exists())

    def test_excel_upload_and_persistence(self):
        self.login()
        response = self.upload()
        self.assertEqual(response.status_code, 200, response.get_json())
        audit = response.get_json()["audit"]
        for name, value in {"included_drivers":2,"excluded_red_drivers":2,"numeric_cells":34,"blank_cells":14,"zero_cells":1,"total_amount_cents":32600,"cached_formula_cells":34,"record_count":48}.items():
            self.assertEqual(audit[name], value, name)
        payload = self.client.get("/data/sheet2.json").get_json()
        self.assertEqual(len(payload["dates"]), 24)
        self.assertEqual(min(payload["dates"]), "2026-09-24")
        self.assertEqual(max(payload["dates"]), "2026-10-17")
        names = {driver["name"] for driver in payload["drivers"]}
        self.assertIn("司机甲", names)
        self.assertNotIn("司机丙", names)
        self.assertNotIn("司机丁", names)  # Theme dark-red name, not direct FF0000.
        self.assertEqual(sum(record["amountCents"] is None for record in payload["records"]), 14)
        self.assertEqual(list(Path(self.directory.name).glob("*.xlsx")), [])
        second_app = create_app(self.config)
        with second_app.test_client() as client:
            with client.session_transaction() as session:
                session["role"] = "viewer"
            self.assertEqual(client.get("/data/sheet2.json").get_json(), payload)

    def test_failed_upload_retains_good_data(self):
        self.login()
        self.assertEqual(self.upload().status_code, 200)
        previous = (Path(self.directory.name) / "current.json").read_bytes()
        self.assertEqual(self.upload(b"This is not Excel").status_code, 400)
        self.assertEqual((Path(self.directory.name) / "current.json").read_bytes(), previous)

    def test_missing_formula_caches_rejected(self):
        namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        for missing_value in (None, ""):
            modified = io.BytesIO()
            with ZipFile(io.BytesIO(self.workbook)) as source, ZipFile(modified, "w") as output:
                for entry in source.infolist():
                    contents = source.read(entry.filename)
                    if entry.filename == "xl/worksheets/sheet2.xml":
                        sheet = ET.fromstring(contents)
                        value = sheet.find(".//s:c[@r='B2']/s:v", namespace)
                        value.text = missing_value
                        contents = ET.tostring(sheet)
                    output.writestr(entry, contents)
            with self.assertRaises(ValueError):
                extract_bytes(modified.getvalue())


class PublicViewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.config = dict(TESTING=True, SECRET_KEY="test-only", DATA_DIR=self.directory.name,
                           ADMIN_PASSWORD="test-admin", PUBLIC_VIEW=True, VIEW_PASSWORD="")
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.workbook = sample_workbook()

    def tearDown(self):
        self.directory.cleanup()

    def login(self, password="test-admin"):
        page = self.client.get("/login")
        self.assertIn("管理员登录".encode(), page.data)
        token = re.search(rb'name="csrf" value="([^"]+)"', page.data).group(1).decode()
        return self.client.post("/login", data={"password": password, "csrf": token})

    def upload(self):
        self.client.get("/admin")
        with self.client.session_transaction() as session:
            csrf = session.get("csrf", "")
        return self.client.post("/api/upload", data={"workbook": (io.BytesIO(self.workbook), "流水.xlsx")},
                                headers={"X-CSRF-Token": csrf})

    def test_query_is_public_but_admin_is_not(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/api/data-status").status_code, 200)
        self.assertEqual(self.client.get("/admin").status_code, 302)
        self.assertEqual(self.client.get("/api/local-sync").status_code, 401)
        self.assertEqual(self.upload().status_code, 401)
        self.assertFalse((Path(self.directory.name) / "current.json").exists())

    def test_admin_can_login_and_upload(self):
        self.assertEqual(self.login().status_code, 302)
        response = self.upload()
        self.assertEqual(response.status_code, 200, response.get_json())
        data = self.client.get("/data/sheet2.json")
        self.assertEqual(data.status_code, 200)
        self.assertEqual(len(data.get_json()["dates"]), 24)

    def test_old_view_password_is_not_accepted_when_public(self):
        app = create_app(dict(TESTING=True, SECRET_KEY="test-only", DATA_DIR=self.directory.name,
                              ADMIN_PASSWORD="test-admin", VIEW_PASSWORD="legacy-view", PUBLIC_VIEW=True))
        with app.test_client() as client:
            page = client.get("/login")
            token = re.search(rb'name="csrf" value="([^"]+)"', page.data).group(1).decode()
            response = client.post("/login", data={"password": "legacy-view", "csrf": token})
            self.assertEqual(response.status_code, 401)
            self.assertEqual(client.get("/admin").status_code, 302)


if __name__ == "__main__":
    unittest.main()
