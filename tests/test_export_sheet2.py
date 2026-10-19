import io
import unittest
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from zipfile import ZipFile

from openpyxl.utils.datetime import CALENDAR_MAC_1904, CALENDAR_WINDOWS_1900, to_excel

from tests.workbook_fixture import NS, column, sample_workbook
from tools.export_sheet2 import ExportError, extract_bytes, sheet_date

XML = {"s": NS}


def changed_workbook(change, sheet2_only=False):
    output = io.BytesIO()
    with ZipFile(io.BytesIO(sample_workbook(sheet2_only=sheet2_only))) as source, ZipFile(output, "w") as target:
        for entry in source.infolist():
            contents = source.read(entry.filename)
            if entry.filename.startswith("xl/worksheets/"):
                root = ET.fromstring(contents)
                change(entry.filename, root)
                contents = ET.tostring(root)
            target.writestr(entry, contents)
    return output.getvalue()


class Sheet2ImportTests(unittest.TestCase):
    def test_sheet2_alone_preserves_zero_blank_and_red_name_exclusion(self):
        def change(_part, root):
            row = root.find(".//s:row[@r='2']", XML)
            cell = ET.SubElement(row, f"{{{NS}}}c", r="Z2", t="e")
            ET.SubElement(cell, f"{{{NS}}}v").text = "#REF!"

        content = changed_workbook(change, sheet2_only=True)
        payload, audit = extract_bytes(content)
        self.assertEqual(audit["included_drivers"], 2)
        self.assertEqual(audit["excluded_red_drivers"], 2)
        self.assertEqual(audit["zero_cells"], 1)
        self.assertEqual(audit["blank_cells"], 14)
        self.assertEqual(audit["record_count"], 48)
        self.assertEqual(payload["sourceRange"], "Sheet2!A:Y")
        self.assertEqual({driver["name"] for driver in payload["drivers"]}, {"司机甲", "司机乙"})
        self.assertEqual(sum(record["amountCents"] == 0 for record in payload["records"]), 1)
        self.assertEqual(sum(record["amountCents"] is None for record in payload["records"]), 14)

    def test_dates_and_formula_results_come_only_from_sheet2(self):
        def change(part, root):
            if part.endswith("sheet1.xml"):
                # Unrelated source-sheet errors must have no effect.
                cell = root.find(".//s:c[@r='F1']", XML)
                cell.set("t", "e")
                cell.find("s:v", XML).text = "#REF!"
                return
            for index in range(24):
                day = date(2026, 10, 19) - timedelta(days=index)
                root.find(f".//s:c[@r='{column(index + 2)}1']/s:is/s:t", XML).text = f"{day.month}月{day.day}日总流水"
            root.find(".//s:c[@r='B2']/s:f", XML).text = "SUM(0)"
            root.find(".//s:c[@r='C2']/s:v", XML).text = "99.5"

        payload, audit = extract_bytes(changed_workbook(change))
        self.assertEqual(payload["dates"][0], "2026-10-19")
        self.assertEqual(payload["dates"][-1], "2026-09-26")
        driver = next(item["id"] for item in payload["drivers"] if item["name"] == "司机甲")
        amounts = {item["date"]: item["amountCents"] for item in payload["records"] if item["driverId"] == driver}
        self.assertEqual(amounts["2026-10-19"], 0)
        self.assertEqual(amounts["2026-10-18"], 9950)
        self.assertEqual(audit["cached_formula_cells"], 34)

    def test_header_formats_and_excel_date_systems(self):
        for value in ("10月19日总流水", "2026年10月19日总流水", "10月19日", "2026-10-19", "2026/10/19", date(2026, 10, 19), datetime(2026, 10, 19, 12)):
            with self.subTest(value=value):
                self.assertEqual(sheet_date(value, CALENDAR_WINDOWS_1900, "B1"), "2026-10-19")
        for epoch in (CALENDAR_WINDOWS_1900, CALENDAR_MAC_1904):
            with self.subTest(epoch=epoch):
                serial = to_excel(datetime(2026, 10, 19), epoch)
                self.assertEqual(sheet_date(serial, epoch, "B1"), "2026-10-19")

    def test_invalid_dates_are_rejected(self):
        for value in (None, True, "", "姓名", "2月30日总流水", "2026-13-01", float("inf")):
            with self.subTest(value=value), self.assertRaisesRegex(ExportError, "Sheet2!B1 日期无效"):
                sheet_date(value, CALENDAR_WINDOWS_1900, "B1")

    def test_duplicate_dates_are_rejected(self):
        def change(part, root):
            if part.endswith("sheet2.xml"):
                root.find(".//s:c[@r='C1']/s:is/s:t", XML).text = "10月17日总流水"

        with self.assertRaisesRegex(ExportError, "日期重复"):
            extract_bytes(changed_workbook(change))

    def test_sheet2_calculation_errors_still_rejected(self):
        def change(part, root):
            if part.endswith("sheet2.xml"):
                cell = root.find(".//s:c[@r='B2']", XML)
                cell.set("t", "e")
                cell.find("s:v", XML).text = "#VALUE!"

        with self.assertRaisesRegex(ExportError, "Sheet2!B2 包含计算错误"):
            extract_bytes(changed_workbook(change))
