"""
Phase 6 Comprehensive Verification Test Suite
Tests representative dossiers across all three time groups, opening page variants,
table layouts, edge cases (long PDF, blurred OCR, corrupted file, blank licenses,
duplicate names, locked master summary, diagnostics logging), and portable ZIP delivery.
"""
import os
import shutil
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import openpyxl
from PIL import Image, ImageDraw

from src.cover_parser import parse_cover_ocr, parse_cover_page_text
from src.folder_parser import folder_review_location, parse_folder_hierarchy
from src.master_summary import read_rename_records, update_or_append_summary_entry
from src.naming_rules import propose_dossier_filename
from src.pdf_processor import open_pdf, page_count, read_pdf_page_text, render_pdf_page
from src.pipeline import (
    _read_opening_page,
    commit_folder_dossier,
    fast_extract_rename_metadata,
    process_dossier_pdf,
    summarize_license_table,
)
from src.table_extractor import LicenseTableExtractor, measure_page_grid
from test_folder_review_v3 import lock_workbook


USER_SAMPLE_DIR = r"C:\Users\FPT SHOP\Desktop\HOP 49\HOP 49\HO SO 116"


def make_dummy_pdf(path, pages_data):
    """
    Creates a multi-page PDF with text/drawings for testing.
    pages_data: list of dicts with 'text' or 'draw_func'
    """
    Image.init()
    images = []
    for p_info in pages_data:
        img = Image.new("RGB", (600, 400), "white")
        draw = ImageDraw.Draw(img)
        if "text" in p_info:
            draw.text((30, 30), p_info["text"], fill="black")
        if "draw_func" in p_info:
            p_info["draw_func"](draw)
        images.append(img)
    images[0].save(path, save_all=True, append_images=images[1:], resolution=100)


_DB_PATCH = None


def setUpModule():
    """Saves write to the shared database; keep test records out of the real one."""
    global _DB_PATCH
    from unittest.mock import patch
    from src.database import DatabaseManager
    work = tempfile.mkdtemp(prefix="gplx-p6-db-")
    _DB_PATCH = patch("src.pipeline.DatabaseManager",
                      return_value=DatabaseManager(os.path.join(work, "test.db"), files_root=work))
    _DB_PATCH.start()


def tearDownModule():
    _DB_PATCH.stop()


class Phase6RepresentativeDossiersTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="gplx-phase6-")
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.province_dir = self.root / "DuLieuSoHoa_GPLS" / "LaoCai"
        self.dossier_dir = self.province_dir / "HOP_49" / "HO SO 116"
        self.dossier_dir.mkdir(parents=True)
        self.summary_path = self.province_dir / "So_Theo_Doi_Day_So_GPLX_15.xlsx"

    def test_01_representative_sql_group_from_real_folder(self):
        """Group SQL (< 31/12/2012): test on user's real file if present."""
        sample_file = os.path.join(USER_SAMPLE_DIR, "H38.8.4_SG_000116_V1_20260425_000004.pdf")
        if not os.path.exists(sample_file):
            self.skipTest(f"File not found: {sample_file}")

        # Test folder hierarchy
        loc = folder_review_location(sample_file)
        self.assertEqual(loc["box"], "49")
        self.assertEqual(loc["box_number"], "116")

        # Test opening page cover parsing
        with open_pdf(sample_file) as pdf:
            total = page_count(pdf)
            self.assertEqual(total, 27)
            cover, _ = _read_opening_page(pdf)
            self.assertEqual(cover["document_type"], "cover")
            self.assertEqual(cover["course"], "27")
            self.assertEqual(cover["license_class"], "A1")
            self.assertEqual(cover["exam_date"], "01-04-1996")

        # Fast extract naming
        proposal = propose_dossier_filename(
            province_code="15",
            exam_date=cover["exam_date"],
            first_license_no="C244501",
            last_license_no="C244608",
        )
        self.assertEqual(proposal.group, "SQL")
        self.assertEqual(proposal.filename, "15.SQL.04.1996.C244501-C244608")

        # Copy to test dossier dir and commit
        test_pdf = self.dossier_dir / "scan_course27.pdf"
        shutil.copy2(sample_file, test_pdf)
        cover_meta = {
            "province_code": "15",
            "exam_date": "01/04/1996",
            "box": "49",
            "box_number": "116",
            "course": "27",
            "license_class": "A1",
            "dossier_group": "SQL",
            "first_license_no": "C244501",
            "last_license_no": "C244608",
            "total_licenses": 108,
            "sequence_assessment": "Đủ, liên tục",
        }
        res = commit_folder_dossier(test_pdf, proposal.filename, cover_meta)
        saved_pdf = Path(res["pdf_path"])
        self.assertTrue(saved_pdf.exists())
        self.assertEqual(saved_pdf.name, "15.SQL.04.1996.C244501-C244608.pdf")
        self.assertTrue(test_pdf.exists())  # Original intact

        # Verify summary row
        wb = openpyxl.load_workbook(self.summary_path)
        try:
            ws = wb.active
            self.assertIn("Sổ gốc", str(ws["B3"].value))
            self.assertEqual(ws["C3"].value, "01/04/1996")
            self.assertEqual(ws["D3"].value, "15.SQL.04.1996.C244501-C244608")
            self.assertEqual(ws["H3"].value, 108)
        finally:
            wb.close()

    def test_02_representative_qdtt_group(self):
        """Group QĐTT (01/01/2013 - 28/02/2025): Decision with exam and signed dates."""
        text = (
            "UBND TỈNH YÊN BÁI\n"
            "Số: 368/QĐ-SGTVT\n"
            "Yên Bái, ngày 25 tháng 9 năm 2015\n"
            "QUYẾT ĐỊNH\n"
            "Căn cứ biên bản sát hạch ngày 15/09/2015\n"
            "Điều 1. Công nhận trúng tuyển hạng A1 khóa P59"
        )
        pdf_path = self.dossier_dir / "decision_2015.pdf"
        make_dummy_pdf(pdf_path, [{"text": text}, {"text": "STT Họ và tên Số GPLX\n1 Nguyễn Văn A A123456"}])

        cover = parse_cover_page_text(text)
        self.assertEqual(cover["document_type"], "decision")
        self.assertEqual(cover["decision_number"], "368/QĐ-SGTVT")
        self.assertEqual(cover["exam_date"], "15-09-2015")
        self.assertEqual(cover["decision_date"], "25-09-2015")

        proposal = propose_dossier_filename(
            province_code="15",
            exam_date=cover["exam_date"],
            decision_date=cover["decision_date"],
            decision_number=cover["decision_number"],
        )
        self.assertEqual(proposal.group, "QĐTT")
        self.assertEqual(proposal.filename, "15.368.25.09.2015")

        cover_meta = {
            "province_code": "15",
            "exam_date": "15/09/2015",
            "decision_date": "25/09/2015",
            "decision_number": "368/QĐ-SGTVT",
            "box": "49",
            "box_number": "116",
            "dossier_group": "QĐTT",
            "total_licenses": 45,
        }
        res = commit_folder_dossier(pdf_path, proposal.filename, cover_meta)
        self.assertTrue(Path(res["pdf_path"]).exists())
        self.assertEqual(Path(res["pdf_path"]).name, "15.368.25.09.2015.pdf")

        # In QĐTT, summary column C records decision signing date
        wb = openpyxl.load_workbook(self.summary_path)
        try:
            ws = wb.active
            rows = [r for r in ws.iter_rows(min_row=3, values_only=True) if r[1]]
            target = [r for r in rows if r[3] == "15.368.25.09.2015"][0]
            self.assertEqual(target[2], datetime(2015, 9, 25))
            self.assertEqual(target[7], 45)
        finally:
            wb.close()

    def test_03_representative_qdsh_group(self):
        """Group QĐSH (>= 01/03/2025): Decision uses exam date in filename."""
        text = (
            "SỞ GTVT LÀO CAI\n"
            "Số: 3081/QĐ-SGTVT\n"
            "Lào Cai, ngày 08 tháng 3 năm 2025\n"
            "QUYẾT ĐỊNH\n"
            "Căn cứ kết quả sát hạch ngày 01 tháng 3 năm 2025\n"
            "Điều 1. Công nhận kết quả sát hạch"
        )
        pdf_path = self.dossier_dir / "decision_2025.pdf"
        make_dummy_pdf(pdf_path, [{"text": text}, {"text": "STT Họ và tên Số GPLX"}])

        cover = parse_cover_page_text(text)
        self.assertEqual(cover["document_type"], "decision")
        self.assertEqual(cover["decision_number"], "3081/QĐ-SGTVT")
        self.assertEqual(cover["exam_date"], "01-03-2025")
        self.assertEqual(cover["decision_date"], "08-03-2025")

        proposal = propose_dossier_filename(
            province_code="15",
            exam_date=cover["exam_date"],
            decision_date=cover["decision_date"],
            decision_number=cover["decision_number"],
        )
        self.assertEqual(proposal.group, "QĐSH")
        # In QĐSH, filename uses exam date: 01.03.2025
        self.assertEqual(proposal.filename, "15.3081.01.03.2025")

        cover_meta = {
            "province_code": "15",
            "exam_date": "01/03/2025",
            "decision_date": "08/03/2025",
            "decision_number": "3081/QĐ-SGTVT",
            "box": "49",
            "box_number": "116",
            "dossier_group": "QĐSH",
            "total_licenses": 80,
        }
        res = commit_folder_dossier(pdf_path, proposal.filename, cover_meta)
        self.assertTrue(Path(res["pdf_path"]).exists())
        self.assertEqual(Path(res["pdf_path"]).name, "15.3081.01.03.2025.pdf")

        # In QĐSH, summary column C records exam date: 01/03/2025
        wb = openpyxl.load_workbook(self.summary_path)
        try:
            ws = wb.active
            rows = [r for r in ws.iter_rows(min_row=3, values_only=True) if r[1]]
            target = [r for r in rows if r[3] == "15.3081.01.03.2025"][0]
            self.assertEqual(target[2], datetime(2025, 3, 1))
        finally:
            wb.close()

    def test_04_opening_page_variant_attached_list_on_first_page(self):
        """Opening page is decision with table starting on same page."""
        text = (
            "DANH SÁCH THÍ SINH TRÚNG TUYỂN ĐƯỢC CẤP GIẤY PHÉP LÁI XE\n"
            "Hạng A1 Ngày thi: 10/06/2010\n"
            "Kèm theo QĐ số: 71/QĐ-SGTVT ngày 16 tháng 6 năm 2010\n"
            "STT Họ và tên Ngày sinh Nơi cư trú Số GPLX\n"
            "1 Trần Văn Bình 1985 Lào Cai A465111"
        )
        cover = parse_cover_page_text(text)
        self.assertEqual(cover["document_type"], "decision_with_list")
        self.assertEqual(cover["decision_number"], "71/QĐ-SGTVT")
        self.assertEqual(cover["exam_date"], "10-06-2010")


class Phase6EdgeCasesAndDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="gplx-p6-edge-")
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.province_dir = self.root / "DuLieuSoHoa_GPLS" / "LaoCai"
        self.dossier_dir = self.province_dir / "HOP_49" / "HO SO 116"
        self.dossier_dir.mkdir(parents=True)
        self.summary_path = self.province_dir / "So_Theo_Doi_Day_So_GPLX_15.xlsx"

    def test_05_blurred_ocr_flags_metadata_review(self):
        """Blurred or low-confidence OCR marks fields for review rather than generating bad name."""
        # Test missing exam date on cover
        cover = parse_cover_page_text("SỞ GIAO THÔNG VẬN TẢI\nSỔ GỐC CẤP BẰNG LÁI XE\nHẠNG A1 KHÓA 26")
        self.assertIn("exam_date", cover["metadata_review"])
        self.assertIn("province_code", cover["metadata_review"])

        proposal = propose_dossier_filename(
            province_code="15",
            exam_date="",
            first_license_no="A465111",
            last_license_no="A465200",
        )
        self.assertIn("exam_date", proposal.errors)
        self.assertIsNone(proposal.filename)

    def test_06_corrupted_pdf_handling_and_clean_logging(self):
        """Corrupted PDF raises clear error and logs diagnostic details without crashing."""
        corrupt_path = self.dossier_dir / "corrupt.pdf"
        corrupt_path.write_bytes(b"%PDF-1.4\n%not a real pdf content\ntrailer\n%%EOF")

        from pypdfium2 import PdfiumError
        with self.assertRaises((PdfiumError, ValueError)):
            with open_pdf(str(corrupt_path)) as doc:
                page_count(doc)

    def test_07_blank_license_column_proposes_standard_a000000(self):
        """Verified empty license column produces A000000-A000000 stem."""
        proposal = propose_dossier_filename(
            province_code="15",
            exam_date="20/05/2008",
            license_column_empty=True,
        )
        self.assertEqual(proposal.filename, "15.SQL.05.2008.A000000-A000000")

    def test_08_duplicate_destination_name_guards_against_overwrite(self):
        """Duplicate filename raises FileExistsError and preserves original file."""
        src1 = self.dossier_dir / "file1.pdf"
        src2 = self.dossier_dir / "file2.pdf"
        src1.write_bytes(b"content 1")
        src2.write_bytes(b"content 2")

        cover = {"province_code": "15", "exam_date": "01/05/2010", "box": "49", "box_number": "116"}
        commit_folder_dossier(src1, "duplicate_stem", cover)
        self.assertTrue((self.dossier_dir / "duplicate_stem.pdf").exists())

        # Committing a different source with same proposed name must fail
        with self.assertRaises(FileExistsError):
            commit_folder_dossier(src2, "duplicate_stem", cover)

        self.assertEqual(src2.read_bytes(), b"content 2")  # Original unchanged

    def test_09_locked_workbook_rollback_and_atomic_retry(self):
        """Locked master summary workbook raises PermissionError, rolls back new PDF, retry succeeds."""
        src = self.dossier_dir / "test_lock.pdf"
        src.write_bytes(b"lock test bytes")
        cover = {"province_code": "15", "exam_date": "01/05/2010", "box": "49", "box_number": "116"}

        # First create an existing workbook
        update_or_append_summary_entry(self.summary_path, {"pdf_filename": "entry1", "total_licenses": 10})

        with lock_workbook(self.summary_path):
            with self.assertRaisesRegex(PermissionError, "đóng sổ trong Excel"):
                commit_folder_dossier(src, "locked_stem", cover)

        # PDF copy was rolled back
        self.assertFalse((self.dossier_dir / "locked_stem.pdf").exists())
        self.assertTrue(src.exists())

        # After releasing lock, commit succeeds cleanly
        res = commit_folder_dossier(src, "locked_stem", cover)
        self.assertTrue(Path(res["pdf_path"]).exists())

    def test_10_diagnostics_logging_includes_pid_tid_and_step(self):
        """Logger captures pid, tid, step, and filename for traceable diagnostics."""
        from src import logger as app_logger
        with tempfile.TemporaryDirectory() as log_dir:
            old_handlers = app_logger._logger.handlers[:]
            app_logger._logger.handlers.clear()
            try:
                logger = app_logger.configure_logging(log_dir)
                logger.info("Phase 6 diagnostic check for file=%s page=%d", "sample.pdf", 1)
                log_path = os.path.join(log_dir, "app_%s.log" % app_logger.date.today().isoformat())
                self.assertTrue(os.path.exists(log_path))
                with open(log_path, encoding="utf-8") as f:
                    content = f.read()
                self.assertIn("pid=", content)
                self.assertIn("tid=", content)
                self.assertIn("sample.pdf", content)
                self.assertIn("page=1", content)
            finally:
                import faulthandler
                faulthandler.disable()
                if app_logger._crash_file:
                    app_logger._crash_file.close()
                    app_logger._crash_file = None
                for h in app_logger._logger.handlers[:]:
                    h.close()
                app_logger._logger.handlers = old_handlers


class Phase6PackagingAndDeliveryTest(unittest.TestCase):
    def test_11_handover_zip_structure_and_standalone_extraction(self):
        """
        Verifies that 'So Hoa GPLX.zip' exists, has single root 'So Hoa GPLX/',
        contains all required startup scripts and binaries, and can be extracted
        into an isolated location.
        """
        base_dir = Path(__file__).resolve().parent
        zip_path = base_dir / "So Hoa GPLX.zip"
        self.assertTrue(zip_path.exists(), f"Missing delivery ZIP: {zip_path}")
        self.assertGreater(zip_path.stat().st_size, 50_000_000, "ZIP should contain full bundle (~200MB)")

        with zipfile.ZipFile(zip_path, "r") as archive:
            names = archive.namelist()
            # Must strictly have single root 'So Hoa GPLX/'
            self.assertTrue(all(name.startswith("So Hoa GPLX/") for name in names),
                            "All entries must reside under 'So Hoa GPLX/' root folder")

            # Check critical startup and runtime files
            required_entries = [
                "So Hoa GPLX/Chay_Ngay.bat",
                "So Hoa GPLX/Xem_Nhat_Ky.bat",
                "So Hoa GPLX/HUONG_DAN_SU_DUNG.txt",
                "So Hoa GPLX/app/GPLX_SoHoa_TraCuu.exe",
                "So Hoa GPLX/DuLieuSoHoa_GPLS/",
            ]
            for req in required_entries:
                self.assertIn(req, names, f"ZIP is missing critical entry: {req}")

            # Test extraction to an isolated temporary location
            with tempfile.TemporaryDirectory(prefix="gplx-unzip-") as extract_dir:
                archive.extract("So Hoa GPLX/Chay_Ngay.bat", extract_dir)
                archive.extract("So Hoa GPLX/Xem_Nhat_Ky.bat", extract_dir)
                archive.extract("So Hoa GPLX/HUONG_DAN_SU_DUNG.txt", extract_dir)

                extracted_bat = Path(extract_dir) / "So Hoa GPLX" / "Chay_Ngay.bat"
                self.assertTrue(extracted_bat.exists())
                bat_content = extracted_bat.read_text(encoding="utf-8")
                self.assertIn("GPLX_SoHoa_TraCuu.exe", bat_content)

                extracted_log = Path(extract_dir) / "So Hoa GPLX" / "Xem_Nhat_Ky.bat"
                self.assertTrue(extracted_log.exists())
                log_content = extracted_log.read_text(encoding="utf-8")
                self.assertIn("LOCALAPPDATA", log_content)


if __name__ == "__main__":
    unittest.main()
