"""Province summary follows the reference workbook "File tổng soát số hóa GPLX.xlsx"."""
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import openpyxl
from openpyxl.styles import Border, Side
from openpyxl.worksheet.table import Table, TableStyleInfo

from src.master_summary import HEADERS, update_or_append_summary_entry

REFERENCE_HEADERS = [
    "STT", "Loại sổ", "Ngày tại bìa sổ", "Tên file PDF ", "HỘP", "HỘP SỐ ", "Hạng",
    "Tổng số lượng GPLX ", "Số GPLX trong file", "Tổng số trang PDF ", "Ghi chú / nhận định", "Ngày cập nhật",
]


def record(name, **extra):
    return {
        "book_type": "Sổ gốc cấp bằng lái xe cơ giới đường bộ", "cover_date": "22-03-1996", "pdf_filename": name,
        "box": "49", "box_number": "116", "license_class": "A1", "total_licenses": 10,
        "license_sequence": "C244337-C244346", "total_pages": 4, "status_note": "Đủ", **extra,
    }


class MasterSummaryFormatTest(unittest.TestCase):
    def setUp(self):
        work = TemporaryDirectory(prefix="gplx-summary-")
        self.addCleanup(work.cleanup)
        self.path = Path(work.name) / "So_Theo_Doi_Day_So_GPLX_15.xlsx"

    def make_reference_like(self):
        """Rows 3-4 and 6 hold records, row 5 separates boxes, column L is formatted far below the data."""
        workbook = openpyxl.Workbook()
        ws = workbook.active
        ws.title = "DANH SACH SO GOC"
        ws.merge_cells("A1:L1")
        ws["A1"] = "SỔ THEO DÕI, RÀ SOÁT DÃY SỐ GPLX TRONG SỔ GỐC"
        for col, name in enumerate(REFERENCE_HEADERS, 1):
            ws.cell(2, col, name)
        for row, (stt, name, box) in {3: (1, "first", 48), 4: (2, "second", 48), 6: (3, "third", 49)}.items():
            ws.cell(row, 1, stt)
            ws.cell(row, 4, name)
            ws.cell(row, 5, box)
        thin = Side(style="thin")
        for col in range(1, 13):
            ws.cell(5, col).border = Border(top=thin, bottom=thin)
        for row in range(7, 198):
            ws.cell(row, 12).number_format = "dd/mm/yyyy"
        table = Table(displayName="SoGocTongHop", ref="A2:L4")
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        ws.add_table(table)
        workbook.save(self.path)

    def load(self):
        workbook = openpyxl.load_workbook(self.path)
        self.addCleanup(workbook.close)
        return workbook.active

    def test_new_workbook_uses_reference_layout(self):
        update_or_append_summary_entry(self.path, record("15.SQL.03.1996.C244337-C244346"))
        ws = self.load()
        self.assertEqual(ws.title, "DANH SACH SO GOC")
        self.assertEqual(ws["A1"].value, "SỔ THEO DÕI, RÀ SOÁT DÃY SỐ GPLX TRONG SỔ GỐC")
        self.assertIn("A1:L1", {str(r) for r in ws.merged_cells.ranges})
        self.assertEqual([ws.cell(2, c).value for c in range(1, 13)], [name for name, _ in HEADERS])
        self.assertEqual(ws["A2"].fill.fgColor.rgb, "000D766E")
        self.assertEqual(ws.freeze_panes, "B3")
        self.assertEqual(ws.tables["SoGocTongHop"].ref, "A2:L3")
        row = [c.value for c in ws[3]]
        self.assertEqual(row[:7], [1, "Sổ gốc cấp bằng lái xe cơ giới đường bộ", datetime(1996, 3, 22),
                                   "15.SQL.03.1996.C244337-C244346", 49, 116, "A1"])
        self.assertEqual(row[7:11], [10, "C244337-C244346", 4, "Đủ"])
        self.assertIsInstance(row[11], datetime)
        self.assertEqual(ws["C3"].number_format, "dd/mm/yyyy")

    def test_appends_after_last_record_and_extends_existing_table(self):
        self.make_reference_like()
        update_or_append_summary_entry(self.path, record("fourth"))
        ws = self.load()
        self.assertEqual(ws["D7"].value, "fourth")
        self.assertEqual(ws.max_row, 197)
        self.assertEqual([ws.cell(r, 1).value for r in range(3, 8)], [1, 2, None, 3, 4])
        self.assertEqual(ws.tables["SoGocTongHop"].ref, "A2:L7")
        # Existing headers, including the trailing spaces Excel keeps as table column names, stay unchanged.
        self.assertEqual([ws.cell(2, c).value for c in range(1, 13)], REFERENCE_HEADERS)

    def test_update_keeps_row_and_stt_is_renumbered_after_manual_edits(self):
        self.make_reference_like()
        workbook = openpyxl.load_workbook(self.path)
        ws = workbook.active
        ws["A3"] = 7
        ws.delete_rows(4)  # Someone removes a record by hand.
        workbook.save(self.path)
        workbook.close()
        update_or_append_summary_entry(self.path, record("first", total_licenses=99))
        ws = self.load()
        self.assertEqual(ws["H3"].value, 99)
        self.assertEqual([(ws.cell(r, 1).value, ws.cell(r, 4).value) for r in (3, 5)], [(1, "first"), (2, "third")])
        self.assertEqual(ws.cell(6, 4).value, None)

    def test_unparsed_date_and_box_codes_stay_text(self):
        update_or_append_summary_entry(self.path, record("x", cover_date="", box="01", box_number="HS-A"))
        ws = self.load()
        self.assertEqual((ws["C3"].value, ws["E3"].value, ws["F3"].value), (None, "01", "HS-A"))


if __name__ == "__main__":
    unittest.main()
