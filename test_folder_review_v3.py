import ctypes
import json
import os
import time
import tkinter as tk
import unittest
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import sqlite3

import customtkinter as ctk
import openpyxl

from src.config import find_province_code_by_text
from src.database import DatabaseManager
from src.folder_parser import folder_review_location
from src.gui.app import GPLXApp
from src.gui.batch_queue import BatchQueueFrame
from src.gui.review_panel import ReviewPanel
from src.gui.search_screen import SearchScreenFrame
from src.master_summary import SummaryBusyError, lock_path, read_rename_records, update_or_append_summary_entry
from src.naming_rules import propose_dossier_filename
from src.pipeline import (
    StalePdfError, _pdf_cache_key, commit_folder_dossier, list_folder_review_pdfs, process_dossier_pdf,
    summarize_license_table, summarize_license_tables,
)


@contextmanager
def lock_workbook(path):
    if os.name != "nt":
        with patch("src.master_summary.os.replace", side_effect=PermissionError("Workbook locked")):
            yield
        return

    from ctypes import wintypes

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    open_file = api.CreateFileW
    open_file.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    open_file.restype = wintypes.HANDLE
    # Allow reading while preventing replacement of the open workbook.
    handle = open_file(str(path), 0x80000000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        api.CloseHandle(wintypes.HANDLE(handle))


class FolderReviewV3Test(unittest.TestCase):
    def setUp(self):
        work = TemporaryDirectory(prefix="gplx-review-")
        self.addCleanup(work.cleanup)
        self.province = Path(work.name) / "DuLieuSoHoa_GPLS" / "Tỉnh Yên Bái"
        self.folder = self.province / "HOP 49" / "HO SO 116"
        self.folder.mkdir(parents=True)
        self.summary = self.province / "So_Theo_Doi_Day_So_GPLX_15.xlsx"
        self.cover = {"province_code": "15", "exam_date": "01/05/2010", "box": "49", "box_number": "116"}
        self.db = DatabaseManager(str(Path(work.name) / "test.db"), files_root=work.name)
        db_patch = patch("src.pipeline.DatabaseManager", return_value=self.db)
        db_patch.start()
        self.addCleanup(db_patch.stop)

    def source(self, filename="scan.pdf", content=b"original"):
        pdf = self.folder / filename
        pdf.write_bytes(content)
        return pdf

    def rows(self):
        workbook = openpyxl.load_workbook(self.summary)
        try:
            ws = workbook.active
            return [[ws.cell(r, c).value for c in (1, 4, 8)] for r in range(3, ws.max_row + 1)
                    if ws.cell(r, 4).value], read_rename_records(workbook)
        finally:
            workbook.close()

    def test_three_groups_rename_pdf_and_update_same_province_workbook(self):
        cases = (
            ({"exam_date": "01/05/2010", "first_license_no": "A465211", "last_license_no": "A465212"},
             "15.SQL.05.2010.A465211-A465212"),
            ({"exam_date": "15/09/2015", "decision_number": "368/QĐ-SGTVT", "decision_date": "25/09/2015"},
             "15.368.25.09.2015"),
            ({"exam_date": "04/03/2025", "decision_number": "3081"}, "15.3081.04.03.2025"),
        )
        for i, (fields, expected) in enumerate(cases):
            with self.subTest(name=expected):
                source = self.source(f"scan-{i}.pdf", bytes([i]))
                proposal = propose_dossier_filename(province_code="15", **fields)
                self.assertEqual(proposal.filename, expected)
                cover = {**self.cover, **fields, "dossier_group": proposal.group, "total_licenses": i + 1}
                result = commit_folder_dossier(source, proposal.filename, cover)
                self.assertEqual(Path(result["pdf_path"]).parent.resolve(), source.parent.resolve())
                self.assertEqual(Path(result["pdf_path"]).read_bytes(), bytes([i]))
                self.assertFalse(source.exists(), "the scan is renamed, not copied")
                self.assertEqual(Path(result["master_summary_path"]).resolve(), self.summary.resolve())
                self.assertIsNone(result["db_error"])
        self.assertEqual(list(self.folder.glob("*.xlsx")), [])
        self.assertEqual(list(self.province.glob(".*.lock")), [])
        workbook = openpyxl.load_workbook(self.summary)
        try:
            self.assertEqual([workbook.active.cell(r, 4).value for r in (3, 4, 5)], [name for _, name in cases])
            self.assertEqual(workbook.active["C4"].value, datetime(2015, 9, 25))
            self.assertEqual(workbook.active["C4"].number_format, "dd/mm/yyyy")
            self.assertEqual(workbook.active.title, "DANH SACH SO GOC")
            self.assertEqual([workbook.active.cell(r, 1).value for r in (3, 4, 5)], [1, 2, 3])
            self.assertEqual(workbook.active.tables["SoGocTongHop"].ref, "A2:L5")
            self.assertEqual(workbook.active["H5"].value, 3)
            self.assertEqual(workbook["_GPLX_Rename"].sheet_state, "hidden")
            self.assertEqual(read_rename_records(workbook)[0][1:], (
                os.path.join("HOP 49", "HO SO 116", "scan-0.pdf"),
                os.path.join("HOP 49", "HO SO 116", "15.SQL.05.2010.A465211-A465212.pdf"),
            ))
        finally:
            workbook.close()
        dossiers = self.db.get_all_dossiers()
        self.assertEqual(sorted(d["final_filename"] for d in dossiers), sorted(name for _, name in cases))
        self.assertTrue(all(Path(d["pdf_path"]).is_file() and d["excel_path"] == "" for d in dossiers))
        with closing(sqlite3.connect(self.db.db_path)) as conn:
            stored = conn.execute("SELECT pdf_path FROM dossiers").fetchone()[0]
        self.assertFalse(os.path.isabs(stored), "paths inside the shared folder are stored relative")

    def test_locked_summary_restores_name_and_retry_is_idempotent(self):
        source = self.source()
        update_or_append_summary_entry(self.summary, {"pdf_filename": "older", "total_licenses": 99})
        workbook = openpyxl.load_workbook(self.summary)
        workbook.active["N3"] = "=H3*2"
        workbook.active["D3"].style = "Title"
        workbook.save(self.summary)
        workbook.close()
        before = self.summary.read_bytes()
        with lock_workbook(self.summary):
            with self.assertRaisesRegex(PermissionError, "đóng sổ trong Excel"):
                commit_folder_dossier(source, "custom-name", self.cover)
        self.assertEqual(self.summary.read_bytes(), before)
        self.assertEqual(source.read_bytes(), b"original")
        self.assertFalse((self.folder / "custom-name.pdf").exists())
        self.assertEqual(list(self.province.glob(".gplx-*")), [])
        self.assertEqual(self.db.get_all_dossiers(), [])
        renamed = self.folder / "custom-name.pdf"
        commit_folder_dossier(source, "custom-name", self.cover)
        commit_folder_dossier(renamed, "custom-name", self.cover)
        workbook = openpyxl.load_workbook(self.summary)
        try:
            self.assertEqual(workbook.active.max_row, 4)
            self.assertEqual(workbook.active["H3"].value, 99)
            self.assertEqual(workbook.active["N3"].value, "=H3*2")
            self.assertEqual(workbook.active["D3"].style, "Title")
            self.assertEqual(len(read_rename_records(workbook)), 1)
        finally:
            workbook.close()
        self.assertEqual(list_folder_review_pdfs(self.folder), [(str(renamed.resolve()), str(renamed.resolve()))])

    def test_saving_again_under_new_name_renames_record_row_and_excel(self):
        source = self.source()
        first = commit_folder_dossier(source, "15.3081.04.03.2025", {**self.cover, "total_licenses": 5})
        companion = self.folder / "15.3081.04.03.2025.xlsx"
        companion.write_bytes(b"excel")
        second = commit_folder_dossier(first["pdf_path"], "15.3082.04.03.2025", {**self.cover, "total_licenses": 6})
        self.assertEqual(second["previous_filename"], "15.3081.04.03.2025")
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()),
                         ["15.3082.04.03.2025.pdf", "15.3082.04.03.2025.xlsx"])
        rows, records = self.rows()
        self.assertEqual(rows, [[1, "15.3082.04.03.2025", 6]])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][1], os.path.join("HOP 49", "HO SO 116", "scan.pdf"))
        self.assertEqual([d["final_filename"] for d in self.db.get_all_dossiers()], ["15.3082.04.03.2025"])

    def test_name_claimed_by_other_pdf_or_existing_file_is_refused(self):
        source = self.source("first.pdf")
        different_source = self.source("second.pdf")
        self.source("unknown-copy.pdf")
        with self.assertRaises(FileExistsError):
            commit_folder_dossier(source, "unknown-copy", self.cover)
        self.assertTrue(source.exists())
        commit_folder_dossier(source, "chosen", self.cover)
        with self.assertRaises(FileExistsError):
            commit_folder_dossier(different_source, "chosen", self.cover)
        self.assertEqual(different_source.read_bytes(), b"original")
        self.assertEqual(len(self.rows()[0]), 1)

    def test_quick_rename_keeps_citizens_of_earlier_digitization(self):
        source = self.source()
        renamed = self.folder / "15.SQL.05.2010.A1-A2.pdf"
        source.rename(renamed)
        self.db.insert_or_update_dossier(
            "15.SQL.05.2010.A1-A2", {"province_code": "15"},
            [{"full_name": "Nguyễn Văn A", "license_number": "A000001", "stt": 1, "page_number": 1}],
            str(renamed), str(self.folder / "x.xlsx"))
        update_or_append_summary_entry(self.summary, {"pdf_filename": "15.SQL.05.2010.A1-A2"})
        commit_folder_dossier(renamed, "15.SQL.05.2010.A1-A2", {**self.cover, "total_licenses": 9})
        dossier, = self.db.get_all_dossiers()
        self.assertEqual(dossier["total_citizens"], 1)
        self.assertEqual(len(self.db.search("A000001")), 1)

    def test_sync_from_excel_restores_quick_rename_dossiers_from_summary(self):
        fields = {"exam_date": "15/09/2015", "decision_number": "368", "decision_date": "25/09/2015"}
        proposal = propose_dossier_filename(province_code="15", **fields)
        cover = {**self.cover, **fields, "dossier_group": proposal.group, "license_class": "A1",
                 "total_licenses": 47, "license_sequence": "Đầu AA1 · Cuối AA47", "status_note": "Đủ"}
        renamed = commit_folder_dossier(self.source("scan-a.pdf"), proposal.filename, cover)["pdf_path"]
        # A PDF moved by hand after saving is still found by its name inside the province folder.
        other = commit_folder_dossier(self.source("scan-b.pdf", b"b"), "15.369.26.09.2015", {**cover, **fields})
        moved = self.province / "HOP 49" / "15.369.26.09.2015.pdf"
        os.replace(other["pdf_path"], moved)
        update_or_append_summary_entry(self.summary, {"pdf_filename": "15.999.01.01.2016"})  # no PDF any more

        fresh = DatabaseManager(str(Path(self.db.db_path).with_name("rebuilt.db")), files_root=self.db.files_root)
        errors = []
        self.assertEqual(fresh.reindex_from_directory(str(self.province.parent), errors=errors), 2)
        self.assertEqual(errors, [])
        dossiers = {d["final_filename"]: d for d in fresh.get_all_dossiers()}
        self.assertEqual(set(dossiers), {"15.368.25.09.2015", "15.369.26.09.2015"})
        first = dossiers["15.368.25.09.2015"]
        self.assertEqual(Path(first["pdf_path"]).resolve(), Path(renamed).resolve())
        self.assertEqual(Path(dossiers["15.369.26.09.2015"]["pdf_path"]).resolve(), moved.resolve())
        self.assertEqual((first["province_code"], first["box"], first["box_number"], first["license_class"]),
                         ("15", "49", "116", "A1"))
        # QĐTT: the summary's cover date is the signing date; the exam date comes from the rename record.
        self.assertEqual(self.summary_dates()["15.368.25.09.2015"], "25/09/2015")
        self.assertEqual((first["exam_date"], first["total_citizens"], first["excel_path"]), ("15/09/2015", 47, ""))
        self.assertEqual(fresh.reindex_from_directory(str(self.province.parent)), 2, "running again is idempotent")
        self.assertEqual(len(fresh.get_all_dossiers()), 2)

    def summary_dates(self):
        workbook = openpyxl.load_workbook(self.summary)
        try:
            ws = workbook.active
            return {ws.cell(r, 4).value: ws.cell(r, 3).value.strftime("%d/%m/%Y") for r in range(3, ws.max_row + 1)
                    if ws.cell(r, 4).value and ws.cell(r, 3).value}
        finally:
            workbook.close()

    def test_sync_of_older_qdtt_record_does_not_use_signing_date_as_exam_date(self):
        # Saved by an earlier version: the rename record has no group and no exam date.
        fields = {"exam_date": "15/09/2015", "decision_number": "368", "decision_date": "25/09/2015"}
        cover = {**self.cover, **fields, "dossier_group": "QĐTT"}
        commit_folder_dossier(self.source("scan-a.pdf"), "15.368.25.09.2015", cover)
        sql = {**self.cover, "exam_date": "29/03/1996", "dossier_group": "SQL"}
        commit_folder_dossier(self.source("scan-b.pdf", b"b"), "15.SQL.03.1996.C244337-C244498", sql)
        workbook = openpyxl.load_workbook(self.summary)
        links = workbook["_GPLX_Rename"]
        links.delete_cols(4, 2)
        workbook.save(self.summary)
        workbook.close()
        fresh = DatabaseManager(str(Path(self.db.db_path).with_name("old.db")), files_root=self.db.files_root)
        self.assertEqual(fresh.reindex_from_directory(str(self.province.parent)), 2)
        dates = {d["final_filename"]: d["exam_date"] for d in fresh.get_all_dossiers()}
        self.assertEqual(dates, {"15.368.25.09.2015": "", "15.SQL.03.1996.C244337-C244498": "29/03/1996"})

    def test_new_scan_with_the_name_of_a_saved_scan_can_be_saved(self):
        first = self.source("scan.pdf", b"first book")
        saved = commit_folder_dossier(first, "15.3081.04.03.2025", self.cover)["pdf_path"]
        second = self.source("scan.pdf", b"second book")
        listed = dict(list_folder_review_pdfs(str(self.folder)))
        self.assertIsNone(listed[str(second.resolve())])
        commit_folder_dossier(second, "15.3090.05.03.2025", self.cover)
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["15.3081.04.03.2025.pdf", "15.3090.05.03.2025.pdf"])
        self.assertEqual(len(self.rows()[1]), 2)
        # A copy left next to its saved PDF by an older version is still refused.
        leftover = self.source("scan.pdf", Path(saved).read_bytes())
        with self.assertRaisesRegex(FileExistsError, "đã được lưu thành 15.3081.04.03.2025.pdf"):
            commit_folder_dossier(leftover, "15.3099.06.03.2025", self.cover)
        self.assertTrue(leftover.exists())

    def test_other_machine_lock_blocks_then_stale_lock_is_taken_over(self):
        source = self.source()
        lock = Path(lock_path(self.summary))
        lock.write_text("MAY-02 21/11/2026 10:00:00", encoding="utf-8")
        with patch("src.master_summary.LOCK_WAIT_SECONDS", 0.2):
            with self.assertRaisesRegex(SummaryBusyError, "MAY-02"):
                commit_folder_dossier(source, "chosen", self.cover)
        self.assertTrue(source.exists())
        old = datetime.now().timestamp() - 600
        os.utime(lock, (old, old))
        commit_folder_dossier(source, "chosen", self.cover)
        self.assertFalse(lock.exists())

    def test_source_changes_after_ocr_are_detected(self):
        source = self.source()
        stamp = _pdf_cache_key(source)[1:]
        source.write_bytes(b"replacement PDF file")
        with self.assertRaisesRegex(StalePdfError, "PDF đã thay đổi"):
            commit_folder_dossier(source, "chosen", self.cover, source_stamp=stamp)
        self.assertFalse(self.summary.exists())

    def test_quick_rename_reads_opening_page_only(self):
        source = self.source()
        opening = {"province_code": "15", "exam_date": "01/05/2010", "decision_number": "", "decision_date": ""}
        with (patch("src.pipeline._cached_opening", return_value=(opening, 1, None)),
              patch("src.pipeline._cached_tables") as tables):
            data = process_dossier_pdf(str(source), "15", rename_only=True)
        tables.assert_not_called()
        self.assertEqual(data["citizens"], [])
        self.assertEqual(data["tables"], [])
        self.assertEqual(data["cover_meta"]["box_number"], "116")
        self.assertEqual(data["cover_meta"]["first_license_no"], "")
        self.assertEqual(data["cover_meta"]["status_note"], "")
        self.assertEqual(data["proposed_filename"], "", "the SQL range is typed by the user")
        self.assertEqual(Path(folder_review_location(source)["province_root"]).resolve(), self.province.resolve())

    def test_daily_backup_keeps_newest_copies(self):
        backups = Path(self.db.db_path).parent / "SaoLuu"
        backups.mkdir()
        for day in range(1, 9):
            (backups / f"gplx_index_202611{day:02d}.db").write_bytes(b"old")
        made = self.db.backup_daily(keep=7, backup_dir=str(backups))
        self.assertTrue(made and Path(made).is_file())
        self.assertIsNone(self.db.backup_daily(keep=7, backup_dir=str(backups)))
        self.assertEqual(len(list(backups.glob("gplx_index_*.db"))), 7)
        conn = sqlite3.connect(made)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM dossiers").fetchone()[0], 0)
        finally:
            conn.close()

    def test_province_keywords_match_whole_words_and_merged_provinces(self):
        self.assertEqual(find_province_code_by_text("Cục thuế tỉnh Yên Bái"), "15")
        self.assertEqual(find_province_code_by_text("Sở GTVT tỉnh Hòa Bình"), "25")
        self.assertEqual(find_province_code_by_text("Thừa Thiên Huế"), "46")
        self.assertEqual(find_province_code_by_text("Gia Lai - Kon Tum"), "")


    def test_resync_drops_dossiers_whose_pdf_is_gone(self):
        # Saved again under a new name while the database write failed: the database keeps the old name.
        kept, renamed = self.source("kept.pdf"), self.source("old.pdf")
        outside = Path(self.province.parent.parent) / "elsewhere" / "far.pdf"
        self.db.upsert_dossier_info("kept", self.cover, str(kept))
        self.db.upsert_dossier_info("old", self.cover, str(renamed))
        self.db.upsert_dossier_info("far", self.cover, str(outside))  # not inside the scanned folder
        renamed.rename(self.folder / "new.pdf")
        removed = []
        self.db.reindex_from_directory(str(self.province), removed=removed)
        self.assertEqual(removed, ["old"])
        names = {row["final_filename"] for row in self.db.get_all_dossiers()}
        self.assertEqual(names, {"kept", "far"})
        # A folder that cannot be reached removes nothing.
        self.assertEqual(self.db._drop_missing_dossiers(str(self.province / "missing")), [])

    def test_folder_listing_does_not_block_a_save_of_the_summary(self):
        update_or_append_summary_entry(str(self.summary), {"pdf_filename": "first", "total_licenses": 1})
        self.source()
        from src import pipeline
        real_rows = pipeline.summary_rows_by_name

        def rows_while_another_machine_saves(workbook):
            # Another machine saves while this one is reading the summary for the file list.
            update_or_append_summary_entry(str(self.summary), {"pdf_filename": "second", "total_licenses": 2})
            return real_rows(workbook)

        with patch.object(pipeline, "summary_rows_by_name", rows_while_another_machine_saves):
            list_folder_review_pdfs(str(self.folder))
        workbook = openpyxl.load_workbook(self.summary)
        self.assertIn("second", [row[3] for row in workbook.worksheets[0].iter_rows(min_row=3, values_only=True)])
        workbook.close()

    def test_search_counts_all_matches_beyond_the_shown_rows(self):
        for book in range(3):
            citizens = [{"stt": i + 1, "full_name": f"Nguyễn Văn {book}{i}", "birth_year": "1970",
                         "license_number": f"AP{book}{i:05d}", "page_number": 2} for i in range(100)]
            self.db.insert_or_update_dossier(f"book{book}", {"province_code": "15", "box": "49"}, citizens,
                                             str(self.folder / f"b{book}.pdf"), str(self.folder / f"b{book}.xlsx"))
        self.assertEqual(len(self.db.search("Nguyễn Văn", limit=200)), 200)
        self.assertEqual(self.db.count_search("nguyen van"), 300)
        self.assertEqual(self.db.count_search("Nguyễn Văn", province_code="79"), 0)
        self.assertEqual(len(self.db.get_all_dossiers(limit=2)), 2)
        self.assertEqual(self.db.count_dossiers(), 3)
        self.assertEqual(self.db.count_dossiers(box="50"), 0)


class FolderReviewControllerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import customtkinter as ctk
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def sidebar(self):
        frame = BatchQueueFrame(self.root, on_select_file_callback=Mock(), on_batch_start_callback=Mock(),
                                dispatch_to_ui=lambda callback, *args: callback(*args),
                                on_worker_start=Mock(), on_worker_finish=Mock())
        self.addCleanup(frame.destroy)
        return frame

    @staticmethod
    def shown(panel):
        return [panel.file_tree.item(row, "values")[1] for row in panel.file_tree.get_children()]

    def test_done_files_have_their_own_list(self):
        panel = self.sidebar()
        token = panel._folder_scan = object()
        panel._finish_folder_scan(token, [("a.pdf", "a.pdf"), ("b.pdf", None), ("c.pdf", None)], None, False)
        self.assertEqual(panel.view_switch.cget("values"), ["Đang xử lý (2)", "Đã xong (1)"])
        self.assertEqual((panel.view_switch.get(), self.shown(panel)), ("Đang xử lý (2)", ["b", "c"]))
        self.assertEqual(panel.lbl_stats.cget("text"), "Đã duyệt: 1 / 3 file")
        self.assertEqual(panel.btn_refresh_all.winfo_manager(), "", "only shown with the done files")

        panel._on_view_switch("Đã xong (1)")
        self.assertEqual(self.shown(panel), ["a"])
        self.assertEqual(panel.btn_refresh_all.winfo_manager(), "pack")
        panel._on_view_switch("Đang xử lý (2)")

        b = panel.get_item("b.pdf")
        panel.update_entry(b, "COMPLETED")  # saved
        self.assertEqual(panel.view_switch.cget("values"), ["Đang xử lý (1)", "Đã xong (2)"])
        self.assertEqual(self.shown(panel), ["c"])

        # The file shown in the viewer is always in the list on screen.
        panel.show_active(panel.get_item("a.pdf"))
        self.assertEqual((panel.view_switch.get(), self.shown(panel)), ("Đã xong (2)", ["a", "b"]))
        self.assertEqual(panel.file_tree.selection(), (panel.file_tree.get_children()[0],))
        panel._on_file_enter()
        panel.on_select_file_callback.assert_called_with("a.pdf")

        # A done file read again to be corrected is worked on in the first list.
        panel.update_entry(panel.get_item("a.pdf"), "PROCESSING")
        panel.show_active(panel.get_item("a.pdf"))
        self.assertEqual(panel.view_switch.get(), "Đang xử lý (2)")
        self.assertIn("a", self.shown(panel))

    def test_a_folder_of_saved_files_opens_on_the_done_list(self):
        panel = self.sidebar()
        token = panel._folder_scan = object()
        panel._finish_folder_scan(token, [("a.pdf", "a.pdf"), ("b.pdf", "b.pdf")], None, False)
        self.assertEqual((panel.view_switch.get(), self.shown(panel)), ("Đã xong (2)", ["a", "b"]))

    def test_refresh_all_sends_the_done_digitized_files(self):
        refresh = Mock()
        panel = BatchQueueFrame(self.root, on_select_file_callback=Mock(), on_batch_start_callback=Mock(),
                                dispatch_to_ui=lambda callback, *args: callback(*args),
                                on_worker_start=Mock(), on_worker_finish=Mock(), on_refresh_all_callback=refresh)
        self.addCleanup(panel.destroy)
        token = panel._folder_scan = object()
        panel._finish_folder_scan(token, [("a.pdf", "a.pdf"), ("b.pdf", None), ("c.pdf", "c.pdf")], None, False)
        panel._on_view_switch("Đã xong (2)")
        panel.btn_refresh_all.invoke()
        refresh.assert_called_once_with([panel.get_item("a.pdf"), panel.get_item("c.pdf")])
        # Quick rename keeps no Excel: nothing to update from.
        token = panel._folder_scan = object()
        panel._finish_folder_scan(token, [("a.pdf", "a.pdf")], None, True)
        self.assertEqual(panel.btn_refresh_all.winfo_manager(), "")

    def test_rename_button_label(self):
        self.assertEqual(self.sidebar().btn_rename_folder.cget("text"), "📑 Đổi tên file nhanh (chọn theo folder)")

    def test_each_chooser_replaces_the_list_and_cancels_old_ocr(self):
        panel = self.sidebar()
        token = panel._folder_scan = object()
        panel._finish_folder_scan(token, [("a.pdf", "a.pdf"), ("b.pdf", None)], None, True)
        self.assertTrue(panel.rename_mode)
        self.assertEqual([item["status"] for item in panel.queue_items], ["COMPLETED", "PENDING"])
        panel.on_select_file_callback.assert_called_with("b.pdf")
        old = panel.queue_items
        token = panel._folder_scan = object()
        panel._finish_folder_scan(token, [("c.pdf", None)], None, False)
        self.assertFalse(panel.rename_mode)
        self.assertEqual([item["path"] for item in panel.queue_items], ["c.pdf"])
        self.assertTrue(all(item["cancelled"] for item in old))
        self.assertEqual(panel.btn_run_batch.cget("state"), "normal")
        token = panel._folder_scan = object()
        panel._finish_folder_scan(token, [("d.pdf", None), ("e.pdf", None)], None, False)
        self.assertEqual([item["path"] for item in panel.queue_items], ["d.pdf", "e.pdf"], "not appended")

    def test_list_is_kept_while_a_dossier_is_saving(self):
        panel = self.sidebar()
        token = panel._folder_scan = object()
        panel._finish_folder_scan(token, [("a.pdf", None)], None, True)
        panel.queue_items[0]["status"] = "SAVING"
        token = panel._folder_scan = object()
        with patch("src.gui.batch_queue.messagebox.showinfo") as info:
            panel._finish_folder_scan(token, [("z.pdf", None)], None, False)
        info.assert_called_once()
        self.assertEqual([item["path"] for item in panel.queue_items], ["a.pdf"])

    def test_late_ocr_for_old_entry_with_same_path_does_not_load_panel(self):
        new_item = {"path": "same.pdf", "rename_only": True}
        old_item = {"path": "same.pdf", "rename_only": False}
        app = SimpleNamespace(active_item=new_item, review=Mock(),
                              sidebar=SimpleNamespace(show_active=Mock(), get_item=lambda path: new_item, update_entry=Mock()))
        app._is_active = lambda item: GPLXApp._is_active(app, item)
        GPLXApp._on_single_file_processed(app, old_item, {"cover_meta": {}})
        app.review.load_data.assert_not_called()
        GPLXApp._on_single_file_processed(app, new_item, {"rename_only": True})
        app.review.load_data.assert_called_once_with({"rename_only": True})

    def test_save_failure_reopens_pdf_then_success_follows_renamed_file(self):
        current = {"path": "b.pdf", "filename": "b.pdf", "rename_only": True}
        items = [{"path": "a.pdf", "status": "PENDING"}, current, {"path": "c.pdf", "status": "PENDING"}]

        def get_item(path):
            return next((item for item in items if item["path"] == path), None)

        app = SimpleNamespace(
            active_item=current, active_file_path="b.pdf", review=Mock(), viewer=Mock(), on_file_selected=Mock(),
            search_screen=Mock(), lan_screen=Mock(),
            sidebar=SimpleNamespace(show_active=Mock(), get_item=get_item, update_entry=Mock(), queue_items=items),
        )
        app._is_active = lambda item: GPLXApp._is_active(app, item)
        app._select_next_item = lambda after: GPLXApp._select_next_item(app, after=after)
        with patch("src.gui.app.messagebox.showerror") as error:
            GPLXApp._finish_save(app, current, None, "Workbook locked", 3)
        app.sidebar.update_entry.assert_called_once_with(current, "READY")
        app.viewer.load_pdf.assert_called_once_with("b.pdf", initial_page=3)
        app.on_file_selected.assert_not_called()
        error.assert_called_once()
        GPLXApp._finish_save(app, current, {"pdf_path": "15.3081.04.03.2025.pdf"}, None, 3)
        app.search_screen.refresh_results.assert_called_once()  # a listed row may show the old name
        self.assertEqual(current["path"], "15.3081.04.03.2025.pdf")
        self.assertEqual(current["saved_pdf"], "15.3081.04.03.2025.pdf")
        app.on_file_selected.assert_called_once_with("c.pdf")

    def test_pdf_changed_after_reading_is_read_again(self):
        item = {"path": "b.pdf", "filename": "b.pdf", "status": "SAVING", "rename_only": True,
                "data": {"source_stamp": (1, 2), "cover_meta": {}}}
        app = SimpleNamespace(active_item=item, active_file_path="b.pdf", review=Mock(), viewer=Mock(),
                              _process_single_file_async=Mock(),
                              sidebar=SimpleNamespace(show_active=Mock(), get_item=lambda path: item if path == "b.pdf" else None,
                                                      update_entry=lambda it, status, data=None: it.update(status=status)))
        app._is_active = lambda it: GPLXApp._is_active(app, it)
        with patch("src.gui.app.messagebox.showerror") as error:
            GPLXApp._finish_save(app, item, None, "PDF đã thay đổi sau khi đọc.", 2, reread=True)
        error.assert_called_once()
        self.assertEqual((item["status"], item["data"]), ("PENDING", None))
        app.viewer.load_pdf.assert_called_once_with("b.pdf", initial_page=2)
        app._process_single_file_async.assert_called_once_with("b.pdf")
        # Selecting it later also reads the PDF again instead of reusing the old review data.
        app._process_single_file_async.reset_mock()
        GPLXApp.on_file_selected(app, "b.pdf")
        app._process_single_file_async.assert_called_once_with("b.pdf")
        app.review.load_data.assert_not_called()

    def test_confirm_applies_the_cell_being_edited_before_naming(self):
        import tkinter as tk
        confirm = Mock()
        panel = ReviewPanel(self.root, on_confirm_callback=confirm, on_page_jump_callback=Mock())
        self.addCleanup(panel.destroy)
        columns = [{"label": "STT", "role": "stt"}, {"label": "Họ và tên", "role": "full_name"},
                   {"label": "Năm sinh", "role": "birth_year"}, {"label": "Số GPLX", "role": "license_number"}]

        def person(stt, name, code):
            return {"cells": [str(stt), name, "1980", code], "scores": [1.0] * 4, "bounds": [(0, 0, 1, 1)] * 4,
                    "page_number": 2, "stt": stt, "identity_confident": True, "license_number": code,
                    "license_state": "valid"}

        table = {"columns": columns, "rows": [person(1, "Nguyễn Văn A", "AP014542"), person(2, "Trần Văn B", "AP014543")]}
        stats = summarize_license_table(table)
        stats.pop("sequence_analysis")
        panel.load_data({"original_path": "x.pdf", "tables": [table], "rename_only": False,
                         "cover_meta": {"province_code": "15", "exam_date": "10/06/2010", "license_class": "A1",
                                        "course": "N29", "box": "49", "box_number": "113", **stats}})
        self.assertEqual(panel.txt_proposed_filename.get(), "15.SQL.06.2010.AP014542-AP014543")
        # The last GPLX cell is being corrected; Confirm is pressed without Enter.
        editor = tk.Entry(panel.grid_tree)
        editor.insert(0, "AP014549")
        panel._cell_editor = (editor, 1, 3)
        panel._handle_confirm()
        saved = confirm.call_args.kwargs
        self.assertEqual(saved["final_filename"], "15.SQL.06.2010.AP014542-AP014549")
        self.assertEqual(saved["cover_meta"]["last_license_no"], "AP014549")
        self.assertEqual(saved["citizens"][-1]["license_number"], "AP014549")

    def _quick_rename_panel(self, confirm=None):
        panel = ReviewPanel(self.root, on_confirm_callback=confirm or Mock(), on_page_jump_callback=Mock())
        self.addCleanup(panel.destroy)
        data = {"original_path": "a.pdf", "tables": [], "rename_only": True,
                "cover_meta": {"province_code": "15", "exam_date": "15/09/2015", "decision_date": "25/09/2015",
                               "decision_number": "368/QĐ-SGTVT", "book_type": "Quyết định", "box": "49",
                               "box_number": "113", "license_class": "A1", "course": "", "total_licenses": None,
                               "license_sequence": "", "status_note": ""}}
        panel.load_data(data)
        return panel, data

    def saved_panel(self, rename_only=False):
        action = Mock()
        panel = ReviewPanel(self.root, on_confirm_callback=Mock(), on_page_jump_callback=Mock(),
                            on_saved_action_callback=action)
        self.addCleanup(panel.destroy)
        rows = [] if rename_only else [{
            "cells": ["1", "Nguyễn Văn A", "C244537"], "page_number": 2, "stt": None, "identity_confident": True,
            "license_number": "C244537", "license_state": "valid", "scores": [], "bounds": []}]
        tables = [] if rename_only else [{"columns": [{"label": "STT", "role": "stt"},
                                                      {"label": "Họ và tên", "role": "full_name"},
                                                      {"label": "Số GPLX", "role": "license_number"}], "rows": rows}]
        data = {"original_path": "D:/kho/15.SQL.03.1996.C244537-C244537.pdf", "saved_view": True,
                "rename_only": rename_only, "tables": tables,
                "excel_path": None if rename_only else "D:/kho/15.SQL.03.1996.C244537-C244537.xlsx",
                "cover_meta": {"province_code": "15", "exam_date": "22-03-1996", "dossier_group": "SQL",
                               "book_type": "Sổ gốc", "box": "49", "box_number": "116", "license_class": "A1",
                               "course": "26", "total_licenses": 1, "license_sequence": "C244537",
                               "status_note": "Đủ"}}
        panel.load_data(data)
        return panel, action, data

    def test_a_saved_dossier_is_shown_read_only(self):
        panel, action, data = self.saved_panel()
        self.assertEqual(panel.txt_proposed_filename.get(), "15.SQL.03.1996.C244537-C244537")
        self.assertEqual((panel.txt_box.get(), panel.txt_total_gplx.get(), panel.opt_status_note.get()),
                         ("49", "1", "Đủ"))
        for widget in (panel.txt_proposed_filename, panel.txt_book_type, panel.txt_cover_date, panel.txt_hang,
                       panel.txt_khoa, panel.txt_box, panel.txt_box_number, panel.cmb_province, panel.cmb_group,
                       panel.opt_status_note, panel.txt_total_gplx):
            self.assertEqual(widget.cget("state"), "disabled", widget)
        self.assertEqual(panel.btn_confirm.winfo_manager(), "", "nothing to confirm")
        self.assertEqual([b.cget("text") for b in panel.saved_buttons],
                         ["📂 Mở file Excel", "🔄 Cập nhật sổ tổng hợp từ Excel", "✏ Sửa lại hồ sơ (đọc lại PDF)"])
        self.assertTrue(all(b.winfo_manager() == "pack" for b in panel.saved_buttons))
        self.assertEqual(panel.naming_notes_frame.winfo_children()[0].cget("text"),
                         "Hồ sơ đã lưu: chỉ xem. Sửa Excel rồi bấm Cập nhật, hoặc bấm Sửa lại để đọc lại PDF.")
        # The grid is not edited in place: the Excel is.
        panel.update_idletasks()
        row = panel.grid_tree.get_children()[0]
        x, y, _w, _h = panel.grid_tree.bbox(row, "#2") or (5, 5, 0, 0)
        panel._start_cell_edit(SimpleNamespace(x=x + 2, y=y + 2))
        self.assertIsNone(panel._cell_editor)
        panel.store_draft()
        self.assertNotIn("review_draft", data, "nothing typed to keep")
        for index, name in enumerate(("open_excel", "refresh", "reread")):
            panel.saved_buttons[index].invoke()
            action.assert_called_with(name)
        # A file read by OCR afterwards can be edited again.
        panel.load_data({"original_path": "b.pdf", "tables": [], "rename_only": True,
                         "cover_meta": {"province_code": "15", "exam_date": "15-09-2015"}})
        self.assertEqual((panel.txt_box.cget("state"), panel.cmb_province.cget("state"),
                          panel.opt_status_note.cget("state")), ("normal", "readonly", "normal"))
        self.assertEqual(panel.btn_confirm.winfo_manager(), "pack")
        self.assertTrue(all(b.winfo_manager() == "" for b in panel.saved_buttons))

    def test_a_saved_quick_rename_has_no_excel_buttons(self):
        panel, _action, _data = self.saved_panel(rename_only=True)
        self.assertEqual([b.cget("text") for b in panel.saved_buttons if b.winfo_manager()],
                         ["✏ Sửa lại hồ sơ (đọc lại PDF)"])

    def test_clicking_a_done_file_shows_what_was_saved_without_ocr(self):
        item = {"path": "a.pdf", "filename": "a.pdf", "status": "COMPLETED", "saved_pdf": "a.pdf", "data": None}
        app = SimpleNamespace(active_item=None, active_file_path=None, review=Mock(), viewer=Mock(),
                              sidebar=SimpleNamespace(show_active=Mock(), get_item=lambda path: item),
                              _process_single_file_async=Mock(), _load_saved_async=Mock())
        GPLXApp.on_file_selected(app, "a.pdf")
        app._load_saved_async.assert_called_once_with(item)
        app._process_single_file_async.assert_not_called()

        app._is_active = lambda it: GPLXApp._is_active(app, it)
        app._launch_worker = lambda work, **_kw: work()
        app._dispatch_to_ui = lambda callback, *args: callback(*args)
        for name in ("_on_saved_loaded", "_on_saved_error"):
            setattr(app, name, getattr(GPLXApp, name).__get__(app))
        app.active_item = item
        with patch("src.gui.app.load_saved_dossier", return_value={"saved_view": True}) as load, \
                patch("src.gui.app.process_dossier_pdf") as ocr:
            GPLXApp._load_saved_async(app, item)
        load.assert_called_once_with("a.pdf")
        ocr.assert_not_called()
        app.review.load_data.assert_called_once_with({"saved_view": True})
        # Data that cannot be read: the PDF may be read again on request.
        with patch("src.gui.app.load_saved_dossier", side_effect=ValueError("Không đọc được file Excel a.xlsx")), \
                patch("src.gui.app.messagebox.askyesno", return_value=True) as ask:
            GPLXApp._load_saved_async(app, item)
        self.assertIn("Không đọc được file Excel a.xlsx", ask.call_args.args[1])
        app._process_single_file_async.assert_called_once_with("a.pdf")

    def test_saved_view_buttons(self):
        item = {"path": "D:/kho/a.pdf", "filename": "a.pdf", "status": "COMPLETED", "saved_pdf": "D:/kho/a.pdf"}
        app = SimpleNamespace(active_item=item, active_file_path="D:/kho/a.pdf", review=Mock(),
                              _process_single_file_async=Mock(), _refresh_summaries=Mock())
        app.review.current_data = {"excel_path": "D:/kho/a.xlsx", "saved_view": True}
        with patch("src.gui.app.os.startfile") as start:
            GPLXApp.on_saved_action(app, "open_excel")
        start.assert_called_once_with("D:/kho/a.xlsx")
        GPLXApp.on_saved_action(app, "refresh")
        app._refresh_summaries.assert_called_once_with([item])
        GPLXApp.on_saved_action(app, "reread")
        app._process_single_file_async.assert_called_once_with("D:/kho/a.pdf")

    def test_summaries_are_refreshed_from_the_excels_and_reported(self):
        with TemporaryDirectory() as folder:
            a, b = os.path.join(folder, "a.pdf"), os.path.join(folder, "b.pdf")
            items = [{"path": a, "filename": "a.pdf", "status": "COMPLETED"},
                     {"path": b, "filename": "b.pdf", "status": "COMPLETED"}]
            app = SimpleNamespace(active_item=items[0], review=Mock(), search_screen=Mock(), lan_screen=Mock(),
                                  _load_saved_async=Mock())
            app._is_active = lambda it: it is app.active_item
            app.sidebar = SimpleNamespace(get_item=lambda path: next((i for i in items if i["path"] == path), None))
            app.review.current_data = {"saved_view": True}
            app._launch_worker = lambda work, **_kw: work()
            app._dispatch_to_ui = lambda callback, *args: callback(*args)
            app._finish_refresh = lambda results, errors: GPLXApp._finish_refresh(app, results, errors)
            app._excel_open_in_excel = GPLXApp._excel_open_in_excel

            # An Excel still open in Excel: only what was saved there counts.
            Path(folder, "~$a.xlsx").write_bytes(b"")
            with patch("src.gui.app.messagebox.askokcancel", return_value=False) as ask, \
                    patch("src.gui.app.refresh_summary_from_excel") as refresh:
                GPLXApp._refresh_summaries(app, items)
            self.assertIn("a.xlsx", ask.call_args.args[1])
            refresh.assert_not_called()

            def refresh_one(path):
                if path == b:
                    raise ValueError("Sổ tổng hợp đang mở")
                return {"total_licenses": 4, "license_sequence": "C1-C4", "status_note": "Đủ", "db_error": None}
            with patch("src.gui.app.messagebox.askokcancel", return_value=True), \
                    patch("src.gui.app.refresh_summary_from_excel", side_effect=refresh_one), \
                    patch("src.gui.app.messagebox.showwarning") as warning:
                GPLXApp._refresh_summaries(app, items)
            report = warning.call_args.args[1]
            self.assertIn("Đã cập nhật 1 / 2 hồ sơ", report)
            self.assertIn("b: Sổ tổng hợp đang mở", report)
            app._load_saved_async.assert_called_once_with(items[0])  # the open file shows the new values
            app.search_screen.refresh_results.assert_called_once()

    def test_every_box_must_be_filled_before_saving(self):
        confirm = Mock()
        panel, _data = self._quick_rename_panel(confirm)
        with patch("src.gui.review_panel.messagebox.showwarning") as warning:
            panel._handle_confirm()
        confirm.assert_not_called()
        self.assertIn("Hãy nhập: Khóa, Tổng số GPLX.", warning.call_args.args[1])
        self.assertNotIn("Dãy số", warning.call_args.args[1], "the sequence is computed, not typed")
        self.assertIn('"-"', warning.call_args.args[1])
        # "-" records that the paper does not show the value.
        for entry in (panel.txt_khoa, panel.txt_total_gplx):
            entry.insert(0, "-")
        with patch("src.gui.review_panel.messagebox.showwarning") as warning:
            panel._handle_confirm()
        warning.assert_not_called()
        cover = confirm.call_args.kwargs["cover_meta"]
        self.assertEqual((cover["course"], cover["total_licenses"], cover["license_sequence"]), ("-", "-", ""))
        from src.pipeline import _summary_record
        record = _summary_record("15.368.25.09.2015", cover, 0, folder_review=True)
        self.assertEqual(record["total_licenses"], "-")

    def test_the_sequence_is_computed_not_typed(self):
        confirm = Mock()
        panel = ReviewPanel(self.root, on_confirm_callback=confirm, on_page_jump_callback=Mock())
        self.addCleanup(panel.destroy)
        self.assertFalse(hasattr(panel, "txt_seq_summary"))
        texts = [w.cget("text") for w in panel.card_b.winfo_children() if isinstance(w, ctk.CTkLabel)]
        self.assertNotIn("Dãy số GPLX:", texts)
        columns = [{"label": "STT", "role": "stt"}, {"label": "Họ và tên", "role": "full_name"},
                   {"label": "Số GPLX", "role": "license_number"}]
        table = {"columns": columns, "rows": [
            {"cells": [str(i), f"Người {i}", code], "scores": [1.0] * 3, "bounds": [(0, 0, 1, 1)] * 3, "page_number": 2,
             "stt": i, "identity_confident": True, "license_number": code, "license_state": "valid"}
            for i, code in ((1, "C244537"), (2, "C244538"), (3, "C244540"))]}
        stats = summarize_license_tables([table])
        stats.pop("sequence_analysis")
        panel.load_data({"original_path": "x.pdf", "tables": [table], "rename_only": False,
                         "cover_meta": {"province_code": "15", "exam_date": "01-04-1996", "license_class": "A1",
                                        "course": "K1", "box": "49", "box_number": "116", **stats}})
        panel._handle_confirm()
        self.assertEqual(confirm.call_args.kwargs["cover_meta"]["license_sequence"], "C244537-C244538; C244540")

    def test_typed_values_are_kept_when_switching_to_another_file(self):
        panel, first = self._quick_rename_panel()
        panel.naming_fields["exam_date"].set("16/09/2015")
        panel.txt_khoa.insert(0, "P59")
        panel.txt_total_gplx.insert(0, "31")
        panel.store_draft()
        panel.clear_data()
        panel.load_data({**first, "original_path": "b.pdf", "review_draft": {}, "cover_meta": {"province_code": "15"}})
        panel.clear_data()
        panel.load_data(first)
        self.assertEqual(panel.naming_fields["exam_date"].get(), "16/09/2015")
        self.assertEqual((panel.txt_khoa.get(), panel.txt_total_gplx.get(), panel.txt_box.get()), ("P59", "31", "49"))
        self.assertEqual(first["cover_meta"]["exam_date"], "15/09/2015", "the reading itself is kept")
        # The desktop stores the draft whenever another file or a search result is shown.
        review = Mock()
        desktop = SimpleNamespace(active_file_path="a.pdf", active_item=object(), review=review, tabview=Mock(),
                                  viewer=Mock(), sidebar=SimpleNamespace(show_active=Mock(), queue_items=[]))
        GPLXApp.on_search_view_pdf(desktop, "other.pdf", 1)
        review.store_draft.assert_called_once()

    def test_box_folder_note_is_shown_until_the_box_is_typed(self):
        panel, data = self._quick_rename_panel()
        note = 'Tên thư mục "HOP 49 (2010)" có nhiều số, hãy đối chiếu và nhập Hộp.'
        data["cover_meta"].update(box="", metadata_review={"box": note})
        panel.load_data(data)
        # An empty required box is an error: red, under the heading, until the box is typed.
        notes = [(lbl.cget("text"), lbl.cget("text_color")) for lbl in panel.naming_notes_frame.winfo_children()]
        self.assertEqual(notes, [("Cần sửa trước khi lưu:", ("#D32F2F", "#EF5350")), (f"• {note}", ("#D32F2F", "#EF5350"))])
        panel.txt_box.insert(0, "49")
        panel._refresh_naming()
        self.assertEqual(panel.naming_notes_frame.winfo_children(), [])

    def test_the_empty_notes_box_takes_no_room(self):
        # Lỗi 33: with no error the empty notes frame kept its default height (400 px at Scale 200%).
        first = self.book_table((1, "Nguyễn Văn A", "C244537", 2, True), (2, "Lê Văn C", "C244538", 2, True))
        panel = self.book(first)
        panel.update_idletasks()
        self.assertEqual(panel.btn_confirm.cget("state"), "normal", "nothing to fix")
        self.assertEqual((panel.naming_notes_frame.winfo_children(), panel.naming_notes_frame.winfo_manager()), ([], ""))
        # An error shows the box again, under the file name.
        panel.cmb_province.set("Chọn mã tỉnh")
        panel._on_province_selected(None)
        self.assertEqual(panel.naming_notes_frame.winfo_manager(), "pack")
        self.assertEqual(panel.naming_notes_frame.pack_info()["in"], panel.banner_frame)
        self.assertEqual(panel.banner_frame.pack_slaves()[-1], panel.naming_notes_frame)
        # A message (no file open, saved dossier) is shown in it too.
        panel.clear_data("Chọn PDF để xem và rà soát.")
        self.assertEqual(panel.naming_notes_frame.winfo_manager(), "pack")

    def test_naming_notes_show_only_the_errors_in_red(self):
        panel, data = self._quick_rename_panel()
        data["cover_meta"].update(
            province_code="",
            exam_date="",
            document_type="decision",
            suggested_province_code="15",
            table_review="Có dòng chưa đọc rõ họ tên. Hãy đối chiếu số lượng GPLX.",
            metadata_review={"box": "Chưa đọc được số hộp."},
        )
        panel.load_data(data)
        red = ("#D32F2F", "#EF5350")
        notes = [(lbl.cget("text"), lbl.cget("text_color")) for lbl in panel.naming_notes_frame.winfo_children()]
        # Only why the confirm button is grey: no group, document type, OCR hint or list review in black.
        self.assertEqual(notes, [("Cần sửa trước khi lưu:", red),
                                 ("• Chưa chọn mã tỉnh lưu trữ (OCR gợi ý: 15 – Tỉnh Lào Cai).", red),
                                 ("• Nhập ngày thi/sát hạch hoặc xác nhận nhóm hồ sơ.", red)])

        data["cover_meta"].update(province_code="", suggested_province_code="")
        panel.load_data(data)
        texts = [lbl.cget("text") for lbl in panel.naming_notes_frame.winfo_children()]
        self.assertIn("• Chưa chọn mã tỉnh lưu trữ.", texts)
        self.assertFalse(any("gợi ý" in text for text in texts), "no hint when OCR read no province")

        panel.cmb_province.set(next(label for label in panel.province_options if label.startswith("15")))
        panel._on_province_selected(None)
        data["cover_meta"]["suggested_province_code"] = "15"
        panel._refresh_naming()
        texts = [lbl.cget("text") for lbl in panel.naming_notes_frame.winfo_children()]
        self.assertFalse(any("gợi ý" in text for text in texts), "the chosen province matches OCR: nothing to say")

        panel.naming_fields["exam_date"].set("15-09-2015")
        panel._refresh_naming()
        self.assertEqual(panel.naming_notes_frame.winfo_children(), [], "no errors: no notes")

    def test_clicking_the_open_file_again_keeps_typed_values(self):
        panel, data = self._quick_rename_panel()
        item = {"path": "a.pdf", "status": "READY", "data": data}
        desktop = SimpleNamespace(active_item=item, active_file_path="a.pdf", review=panel, viewer=Mock(),
                                  sidebar=SimpleNamespace(show_active=Mock(), get_item=lambda path: item),
                                  _process_single_file_async=Mock())
        panel.naming_fields["exam_date"].set("16/09/2015")
        GPLXApp.on_file_selected(desktop, "a.pdf")
        self.assertEqual(panel.naming_fields["exam_date"].get(), "16/09/2015")

    def test_confirmed_values_replace_an_older_draft(self):
        data = {"original_path": "a.pdf", "cover_meta": {"exam_date": "15/09/2015"},
                "review_draft": {"exam_date": "16/09/2015"}}
        item = {"path": "a.pdf", "status": "READY", "data": data, "rename_only": True}
        desktop = SimpleNamespace(viewer=Mock(current_page_idx=0), sidebar=Mock(), review=Mock(),
                                  _launch_worker=Mock())
        GPLXApp._save_item(desktop, item, "15.368.25.09.2015", {"exam_date": "17/09/2015"}, [])
        self.assertNotIn("review_draft", data)
        self.assertEqual(data["cover_meta"]["exam_date"], "17/09/2015")

    def book(self, *tables):
        panel = ReviewPanel(self.root, on_confirm_callback=Mock(), on_page_jump_callback=Mock())
        self.addCleanup(panel.destroy)
        stats = summarize_license_tables(tables)
        stats.pop("sequence_analysis")
        panel.load_data({"original_path": "x.pdf", "tables": list(tables), "rename_only": False,
                         "cover_meta": {"province_code": "15", "exam_date": "01/04/1996", **stats}})
        return panel

    @staticmethod
    def book_table(*rows, unresolved=None):
        columns = [{"label": "STT", "role": "stt"}, {"label": "Họ và tên", "role": "full_name"},
                   {"label": "Năm sinh", "role": "birth_year"}, {"label": "Số GPLX", "role": "license_number"}]
        table = {"columns": columns, "rows": [
            {"cells": [str(stt), name, "1980", code], "scores": [1.0] * 4, "bounds": [(0, 0, 1, 1)] * 4,
             "page_number": page, "stt": stt, "identity_confident": sure, "license_number": code,
             "license_state": "valid"} for stt, name, code, page, sure in rows]}
        if unresolved:
            table["unresolved_pages"] = unresolved
        return table

    def test_gplx_numbers_the_neighbours_point_to_are_suggested_and_accepted_together(self):
        table = self.book_table((1, "Nguyễn Văn A", "AG982435", 2, True), (2, "Lê Văn B", "", 2, True),
                                (3, "Hà Văn C", "AG982437", 3, True), (4, "Lò Văn D", "AG982413", 3, True),
                                (5, "Vi Văn E", "AG982439", 3, True), (6, "Lý Văn F", "AG982440", 3, True))
        unclear = table["rows"][1]
        unclear["cells"][3], unclear["license_state"] = "AG98240", "uncertain"
        panel = self.book(table)
        tree = panel.grid_tree
        shown = lambda row: tree.item(str(row), "values")[3]
        self.assertEqual((shown(1), shown(3)), ("AG98240 → AG982436?", "AG982413 → AG982438?"))
        self.assertIn("review", tree.item("3", "tags"), "a valid number the neighbours contradict is checked too")
        button = panel.btn_accept_suggestions
        self.assertEqual((button.winfo_manager(), button.cget("text")), ("grid", "✔ Nhận 2 số GPLX gợi ý"))
        button.invoke()
        self.assertEqual([r["cells"][3] for r in table["rows"]],
                         ["AG982435", "AG982436", "AG982437", "AG982438", "AG982439", "AG982440"])
        self.assertEqual([r["license_state"] for r in table["rows"]], ["valid"] * 6)
        self.assertEqual((shown(1), tree.item("1", "tags")), ("AG982436", ("edited",)))
        self.assertEqual(button.winfo_manager(), "", "nothing left to accept")
        self.assertEqual((panel.opt_status_note.get(), panel.txt_proposed_filename.get()),
                         ("Đủ", "15.SQL.04.1996.AG982435-AG982440"))

    def test_a_saved_dossier_has_no_suggestions_to_accept(self):
        panel, _action, data = self.saved_panel()
        self.assertEqual(panel.btn_accept_suggestions.winfo_manager(), "")

    def test_several_lists_are_named_and_summarized_as_one_book(self):
        import tkinter as tk
        first = self.book_table((1, "Nguyễn Văn A", "C244537", 2, True), (2, "Lê Văn C", "C244538", 2, True))
        second = self.book_table((1, "Hà Văn D", "C244539", 5, True), (2, "Tr~n V B", "C244540", 5, False))
        panel = self.book(first, second)
        self.assertEqual(panel.txt_proposed_filename.get(), "15.SQL.04.1996.C244537-C244540")
        self.assertEqual(panel.btn_confirm.cget("state"), "normal")
        notes = [lbl.cget("text") for lbl in panel.naming_notes_frame.winfo_children()]
        self.assertFalse(any("chọn danh sách" in text for text in notes), notes)
        # The total is the number of rows OCR read in every list, even while the status needs review.
        self.assertEqual((panel.txt_total_gplx.get(), panel.opt_status_note.get()), ("4", "Cần rà soát"))
        # Correcting the unclear name of list 2 completes the count of the whole book.
        panel._show_grid_table(second)
        editor = tk.Entry(panel.grid_tree)
        editor.insert(0, "Trần Văn B")
        panel._cell_editor = (editor, 1, 1)
        panel._finish_cell_edit()
        self.assertEqual((panel.txt_total_gplx.get(), panel.opt_status_note.get()), ("4", "Đủ"))
        # A corrected last GPLX number renames the book.
        panel._cell_editor = (tk.Entry(panel.grid_tree), 1, 3)
        panel._cell_editor[0].insert(0, "C244541")
        panel._finish_cell_edit()
        self.assertEqual(panel.txt_proposed_filename.get(), "15.SQL.04.1996.C244537-C244541")

    def test_every_unclear_page_of_the_book_has_a_button(self):
        first = self.book_table((1, "Nguyễn Văn A", "C244537", 10, True), unresolved=[11])
        second = self.book_table((1, "Hà Văn D", "C244539", 14, True), unresolved=[15])
        panel = self.book(first, second)
        buttons = [b for b in panel.table_pages_frame.winfo_children()]
        self.assertEqual([b.cget("text") for b in buttons], ["Đối chiếu trang 11", "Đối chiếu trang 15"])
        buttons[1].invoke()
        panel.on_page_jump_callback.assert_called_once_with(15)

        panel = self.book(self.book_table((1, "Nguyễn Văn A", "C244537", 3, True)))
        self.assertEqual([b.cget("text") for b in panel.table_pages_frame.winfo_children()],
                         ["Xem trang 3 (đầu danh sách)"])

    def test_an_exam_date_read_by_the_machine_is_shown_dd_mm_yyyy(self):
        panel, _ = self._quick_rename_panel()  # the cover says 15/09/2015
        self.assertEqual(panel.naming_fields["exam_date"].get(), "15-09-2015")
        self.assertEqual(panel.btn_confirm.cget("state"), "normal")

    def test_a_typed_exam_date_must_be_dd_mm_yyyy(self):
        panel, _ = self._quick_rename_panel()
        red = ("#D32F2F", "#EF5350")
        for typed in ("15/09/2015", "15-9-2015", "31-02-2015"):
            with self.subTest(typed=typed):
                panel.naming_fields["exam_date"].set(typed)
                notes = [(lbl.cget("text"), lbl.cget("text_color")) for lbl in panel.naming_notes_frame.winfo_children()]
                self.assertIn(("• Ngày thi/sát hạch phải là ngày có thật, nhập dạng dd-mm-yyyy (ví dụ 29-03-1996).", red),
                              notes)
                self.assertEqual((panel.btn_confirm.cget("state"), panel.txt_proposed_filename.get()), ("disabled", ""))
        panel.naming_fields["exam_date"].set("15-09-2015")
        self.assertEqual(panel.naming_notes_frame.winfo_children(), [])
        self.assertEqual(panel.txt_proposed_filename.get(), "15.368.25.09.2015")

    def test_typed_gplx_endpoints_must_be_upper_case(self):
        panel = self.book(self.book_table((1, "Nguyễn Văn A", "C244537", 2, True), (2, "Lê Văn C", "C244538", 2, True)))
        panel.naming_fields["first_license_no"].set("c244537")
        notes = [lbl.cget("text") for lbl in panel.naming_notes_frame.winfo_children()]
        self.assertIn("• Số GPLX đầu phải viết hoa, gồm 1–2 chữ cái và 6 chữ số liền nhau (ví dụ AM570000).", notes)
        self.assertEqual((panel.btn_confirm.cget("state"), panel.txt_proposed_filename.get()), ("disabled", ""))
        with patch("src.gui.review_panel.messagebox.showwarning") as warning:
            panel._handle_confirm()
        warning.assert_called_once()
        panel.on_confirm_callback.assert_not_called()
        panel.naming_fields["first_license_no"].set("C244537")
        self.assertEqual(panel.txt_proposed_filename.get(), "15.SQL.04.1996.C244537-C244538")

    def test_box_fields_have_their_own_rows(self):
        panel, _ = self._quick_rename_panel()
        box, box_number = panel.txt_box.grid_info(), panel.txt_box_number.grid_info()
        self.assertNotEqual(box["row"], box_number["row"])
        self.assertEqual((box["column"], box_number["column"]), (1, 1))
        total, status = panel.txt_total_gplx.grid_info(), panel.opt_status_note.grid_info()
        self.assertNotEqual(total["row"], status["row"])

    def test_page_buttons_wrap_three_to_a_row(self):
        tables = [self.book_table((1, "Nguyễn Văn A", "C2445%02d" % page, page, True), unresolved=[page + 1])
                  for page in (2, 4, 6, 8, 10)]
        panel = self.book(*tables)
        rows = {}
        for button in panel.table_pages_frame.winfo_children():
            rows.setdefault(button.grid_info()["row"], []).append(button.cget("text"))
        self.assertEqual(list(rows.values()), [["Đối chiếu trang 3", "Đối chiếu trang 5", "Đối chiếu trang 7"],
                                               ["Đối chiếu trang 9", "Đối chiếu trang 11"]])

    def test_correcting_an_unclear_name_updates_total_and_status(self):
        import tkinter as tk
        panel = ReviewPanel(self.root, on_confirm_callback=Mock(), on_page_jump_callback=Mock())
        self.addCleanup(panel.destroy)
        columns = [{"label": "STT", "role": "stt"}, {"label": "Họ và tên", "role": "full_name"},
                   {"label": "Năm sinh", "role": "birth_year"}, {"label": "Số GPLX", "role": "license_number"}]

        def person(stt, name, code, sure=True):
            return {"cells": [str(stt), name, "1980", code], "scores": [1.0] * 4, "bounds": [(0, 0, 1, 1)] * 4,
                    "page_number": 2, "stt": stt, "identity_confident": sure, "license_number": code,
                    "license_state": "valid"}

        table = {"columns": columns, "rows": [person(1, "Nguyễn Văn A", "AP014542"),
                                              person(2, "Tr~n V B", "AP014543", sure=False)]}
        stats = summarize_license_table(table)
        stats.pop("sequence_analysis")
        panel.load_data({"original_path": "x.pdf", "tables": [table], "rename_only": False,
                         "cover_meta": {"province_code": "15", "exam_date": "10/06/2010", **stats}})
        self.assertEqual((panel.txt_total_gplx.get(), panel.opt_status_note.get()), ("2", "Cần rà soát"))
        editor = tk.Entry(panel.grid_tree)
        editor.insert(0, "Trần Văn B")
        panel._cell_editor = (editor, 1, 1)
        panel._finish_cell_edit()
        self.assertEqual((panel.txt_total_gplx.get(), panel.opt_status_note.get()), ("2", "Đủ"))
        self.assertNotIn("chưa đọc rõ họ tên", panel.lbl_naming.cget("text"))

    def test_list_table_follows_the_display_scale_and_lists_are_a_drop_down(self):
        from tkinter import ttk
        panel = ReviewPanel(self.root, on_confirm_callback=Mock(), on_page_jump_callback=Mock())
        self.addCleanup(panel.destroy)
        columns = [{"label": "STT", "role": "stt"}, {"label": "Họ và tên", "role": "full_name"}]
        tables = [{"columns": columns, "rows": [{"cells": [str(i), f"Người {n}-{i}"], "page_number": n + 1}
                                                for i in range(n + 1)]} for n in range(10)]
        with patch.object(panel, "_get_widget_scaling", return_value=2.0):
            panel._populate_grid(tables)
        style = ttk.Style(panel)
        self.assertEqual(str(style.lookup("GPLX.Treeview", "font")), "{Segoe UI} -22")
        self.assertEqual(panel.grid_tree.column("c1", "width"), 340)
        self.assertTrue(panel.grid_tree.column("c1", "stretch"))
        # In a narrow panel the name keeps its width and the list scrolls sideways.
        self.assertEqual(panel.grid_tree.column("c1", "minwidth"), 340)
        # Ten lists no longer squeeze a row of buttons: one drop-down shows the whole label.
        self.assertEqual(len(panel.grid_chooser.cget("values")), 10)
        panel.grid_chooser._command("Danh sách 4 · 4 dòng")
        self.assertIs(panel._grid_table, tables[3])
        self.assertEqual(len(panel.grid_tree.get_children()), 4)

    def test_wheel_over_the_list_scrolls_the_list_not_the_form(self):
        tree = SimpleNamespace(yview=Mock(return_value=(0.2, 0.6)), yview_scroll=Mock())
        panel = SimpleNamespace(grid_tree=tree, _wheel_rest=0)
        self.assertEqual(ReviewPanel._on_grid_wheel(panel, SimpleNamespace(delta=-120)), "break")
        tree.yview_scroll.assert_called_once_with(3, "units")
        # Small touchpad steps add up instead of jumping three rows each.
        tree.yview_scroll.reset_mock()
        for _ in range(3):
            self.assertEqual(ReviewPanel._on_grid_wheel(panel, SimpleNamespace(delta=-20)), "break")
        tree.yview_scroll.assert_called_once_with(1, "units")
        # At the end of the list the form scrolls on.
        tree.yview.return_value = (0.4, 1.0)
        self.assertIsNone(ReviewPanel._on_grid_wheel(panel, SimpleNamespace(delta=-120)))
        tree.yview.return_value = (0.0, 0.4)
        self.assertIsNone(ReviewPanel._on_grid_wheel(panel, SimpleNamespace(delta=120)))

    def test_sync_from_excel_runs_in_the_background(self):
        jobs, results = [], []
        db = Mock()
        db.reindex_from_directory.return_value = 3
        db.get_inventory_stats.return_value = {"total_provinces": 0, "total_boxes": 0, "total_box_numbers": 0,
                                               "total_dossiers": 0, "total_citizens": 0}
        db.get_distinct_boxes.return_value = []
        db.get_all_dossiers.return_value = []
        with patch("src.gui.search_screen.DatabaseManager", return_value=db):
            screen = SearchScreenFrame(self.root, dispatch_to_ui=lambda callback, *args, **kw: results.append(
                (callback, args, kw)), run_in_background=jobs.append)
        self.addCleanup(screen.destroy)
        with patch("src.gui.search_screen.filedialog.askdirectory", return_value="D:/kho"):
            screen._sync_from_excel_folder()
        # Nothing is scanned on the UI thread; the button is locked until the scan reports back.
        db.reindex_from_directory.assert_not_called()
        self.assertEqual(screen.btn_sync.cget("state"), "disabled")
        jobs.pop()()
        db.reindex_from_directory.assert_called_once()
        callback, args, kw = results.pop()
        with patch("src.gui.search_screen.messagebox.showinfo") as info:
            callback(*args, **kw)
        info.assert_called_once()
        self.assertIn("3 hồ sơ", info.call_args.args[1])
        self.assertEqual(screen.btn_sync.cget("state"), "normal")

    def test_review_name_recomputes_when_date_or_code_changes(self):
        fields = dict(province_code="15", exam_date="15-09-2015", decision_number="368",
                      decision_date="25/09/2015", suggested_province_code="")
        panel = SimpleNamespace(
            current_data={"rename_only": True, "cover_meta": {}}, _saving=False, _naming_inputs=lambda: fields,
            chk_province=Mock(), cmb_group=Mock(), _needs_table_choice=Mock(return_value=False),
            txt_proposed_filename=Mock(), group_fields={}, lbl_naming=Mock(), btn_confirm=Mock(),
            txt_box=Mock(get=lambda: "49"), txt_box_number=Mock(get=lambda: "113"),
        )
        ReviewPanel._refresh_naming(panel)
        panel.txt_proposed_filename.insert.assert_called_with(0, "15.368.25.09.2015")
        fields.update(province_code="79", decision_date="26/09/2015")
        ReviewPanel._refresh_naming(panel)
        panel.txt_proposed_filename.insert.assert_called_with(0, "79.368.26.09.2015")


    def search_screen(self, db, opened=None):
        db.get_inventory_stats.return_value = {"total_provinces": 0, "total_boxes": 0, "total_box_numbers": 0,
                                               "total_dossiers": 0, "total_citizens": 0}
        db.get_distinct_boxes.return_value = []
        with patch("src.gui.search_screen.DatabaseManager", return_value=db):
            screen = SearchScreenFrame(self.root, on_open_pdf_callback=opened)
        self.addCleanup(screen.destroy)
        return screen

    def test_search_results_are_one_table_and_say_when_cut(self):
        db, opened = Mock(), Mock()
        db.search.return_value = [{"stt": i, "full_name": f"Nguyễn Văn {i}", "license_number": f"AP{i}",
                                   "page_number": 3, "pdf_path": f"D:/kho/{i}.pdf", "final_filename": "book"}
                                  for i in range(200)]
        db.count_search.return_value = 300
        screen = self.search_screen(db, opened)
        screen.txt_query.insert(0, "Nguyễn Văn")
        screen.perform_citizen_search()
        self.assertEqual(len(screen.results_tree.get_children()), 200)
        # A fixed set of widgets whatever the number of rows (a row of widgets each exhausted Windows handles).
        self.assertLessEqual(len(screen.results_frame.winfo_children()), 4)
        self.assertIn("200/300", screen.lbl_result_count.cget("text"))
        screen.results_tree.selection_set("5")
        screen._update_action_bar()
        with patch("src.gui.search_screen.os.path.exists", return_value=True):
            screen.btn_view_pdf.invoke()
        opened.assert_called_once_with("D:/kho/5.pdf", 3)

        db.count_search.return_value = 200
        screen.perform_citizen_search()
        self.assertEqual(screen.lbl_result_count.cget("text"), "Tìm thấy 200 kết quả công dân")

    def test_result_table_follows_the_windows_display_scale(self):
        from tkinter import ttk
        db = Mock()
        db.search.return_value = [{"stt": 1, "full_name": "Nguyễn Văn A", "page_number": 2, "pdf_path": "a.pdf"}]
        db.count_search.return_value = 1
        screen = self.search_screen(db)
        screen.txt_query.insert(0, "Nguyễn")
        screen.perform_citizen_search()
        # At 200% the old rows (CustomTkinter, size 11) drew 22-pixel text; the table must match.
        with patch.object(screen, "_get_widget_scaling", return_value=2.0):
            screen._apply_table_scaling()
        style = ttk.Style(screen)
        self.assertEqual(str(style.lookup("GPLXSearch.Treeview", "font")), "{Segoe UI} -22")
        self.assertEqual(int(style.lookup("GPLXSearch.Treeview", "rowheight")), 52)
        self.assertEqual(screen.results_tree.column("full_name", "width"), 380)
        self.assertEqual(screen.results_tree.column("full_name", "minwidth"), 380)

    def test_book_catalogue_says_when_cut_and_opens_a_book(self):
        db = Mock()
        db.get_all_dossiers.return_value = [{"id": 10 + i, "final_filename": f"15.SQL.{i}", "status_note": "Đủ"}
                                            for i in range(200)]
        db.count_dossiers.return_value = 950
        db.search.return_value = [{"stt": 1, "full_name": "A", "page_number": 2, "pdf_path": "a.pdf"}]
        screen = self.search_screen(db)
        mode = "📁 Danh Mục Sổ / File Excel Đã Import"
        screen.mode_toggle.set(mode)
        screen.on_mode_change(mode)
        self.assertEqual(len(screen.results_tree.get_children()), 200)
        self.assertIn("200/950", screen.lbl_result_count.cget("text"))
        screen.results_tree.selection_set("3")
        screen._update_action_bar()
        screen.btn_view_citizens.invoke()
        self.assertEqual(db.search.call_args.kwargs["dossier_id"], 13)
        self.assertEqual(screen.current_mode, "👤 Tra Cứu Công Dân")
        self.assertEqual(len(screen.results_tree.get_children()), 1)

    def test_enter_opens_the_selected_row_wherever_the_mouse_is(self):
        db, opened = Mock(), Mock()
        db.search.return_value = [{"stt": 1, "full_name": "A", "page_number": 4, "pdf_path": "D:/kho/a.pdf"}]
        db.count_search.return_value = 1
        screen = self.search_screen(db, opened)
        screen.txt_query.insert(0, "A")
        screen.perform_citizen_search()
        self.assertIn("_on_result_enter", screen.results_tree.bind("<Return>"))
        with patch("src.gui.search_screen.os.path.exists", return_value=True):
            screen._on_result_enter(SimpleNamespace(x=-40, y=-40))  # a key event carries the pointer position
        opened.assert_called_once_with("D:/kho/a.pdf", 4)

    def test_a_book_lists_all_its_citizens_and_says_why_it_is_empty(self):
        db = Mock()
        db.search.return_value = [{"stt": 1, "full_name": "A", "page_number": 2, "pdf_path": "a.pdf"}]
        screen = self.search_screen(db)
        screen.cmb_prov_filter.set("79 - TP. Hồ Chí Minh")  # chosen earlier for another search
        screen.drill_down_to_dossier_citizens(7, "15.SQL.05.2010.A1-A2")
        self.assertEqual(db.search.call_args.kwargs, {"query": "", "province_code": None, "dossier_id": 7,
                                                      "limit": 200})
        self.assertEqual(len(screen.results_tree.get_children()), 1)
        db.search.return_value = []
        db.get_dossier_files.return_value = {"pdf_path": "D:/kho/15.3081.04.03.2025.pdf", "excel_path": ""}
        screen.drill_down_to_dossier_citizens(8, "15.3081.04.03.2025")
        self.assertIn("mới được đổi tên nhanh", screen.lbl_placeholder.cget("text"))
        db.get_dossier_files.return_value = {"pdf_path": "D:/kho/b.pdf", "excel_path": "D:/kho/b.xlsx"}
        screen.drill_down_to_dossier_citizens(9, "15.SQL.06")
        self.assertIn("chưa có công dân nào", screen.lbl_placeholder.cget("text"))

    def test_rows_shown_are_read_again_after_a_rescan(self):
        db = Mock()
        db.reindex_from_directory.return_value = 1
        db.get_all_dossiers.return_value = [{"id": 1, "final_filename": "A"}, {"id": 2, "final_filename": "B"}]
        db.count_dossiers.return_value = 2
        screen = self.search_screen(db)
        mode = "📁 Danh Mục Sổ / File Excel Đã Import"
        screen.mode_toggle.set(mode)
        screen.on_mode_change(mode)
        self.assertEqual(len(screen.results_tree.get_children()), 2)
        db.get_all_dossiers.return_value, db.count_dossiers.return_value = [{"id": 1, "final_filename": "A"}], 1
        with patch("src.gui.search_screen.messagebox.showinfo"):
            screen._finish_sync(1, [], None, ["B"])
        self.assertEqual(len(screen.results_tree.get_children()), 1, "the dropped book is no longer listed")
        # The citizens of a book: shown again under the book's new id, or a note when it is gone.
        db.search.return_value = [{"stt": 1, "full_name": "A", "page_number": 2, "pdf_path": "a.pdf"}]
        screen.drill_down_to_dossier_citizens(1, "A")
        db.get_dossier_id.return_value = 11
        screen.refresh_results()
        self.assertEqual(db.search.call_args.kwargs["dossier_id"], 11)
        db.get_dossier_id.return_value = None
        with patch("src.gui.search_screen.messagebox.showinfo"):
            screen._finish_sync(0, [], None, ["A"])
        self.assertIn("không còn trong CSDL", screen.lbl_placeholder.cget("text"))
        # After a save the refresh never pops up an error.
        db.get_dossier_id.side_effect = OSError("database is locked")
        with patch("src.gui.search_screen.messagebox.showerror") as error:
            screen.refresh_results()
        error.assert_not_called()

    def test_status_change_updates_only_that_file(self):
        panel = self.sidebar()
        token = panel._folder_scan = object()
        panel._finish_folder_scan(token, [("a.pdf", None), ("b.pdf", None), ("c.pdf", None)], None, False)
        rows = panel.file_tree.get_children()
        tags = lambda row: tuple(panel.file_tree.tk.splitlist(panel.file_tree.item(row, "tags")))
        item = panel.queue_items[1]
        with patch.object(panel, "_rebuild_rows", side_effect=AssertionError("the list is not filled again")):
            panel.update_entry(item, "READY")
            self.assertEqual(panel.file_tree.item(rows[1], "values")[0], "👁 Duyệt")
            panel.update_entry(item, "SAVING")
        self.assertEqual(panel.file_tree.get_children(), rows)
        self.assertEqual(panel.file_tree.item(rows[1], "values")[0], "💾 Đang lưu")
        # The open file stays marked while the arrow keys move on.
        panel.show_active(item)
        self.assertEqual(tags(rows[1]), ("SAVING", "active"))
        panel.file_tree.selection_set(rows[2])
        self.assertIn("active", tags(rows[1]))
        # Saved: the file moves to the done list under its new name.
        item.update(path="15.SQL.05.2010.A1-A2.pdf", filename="15.SQL.05.2010.A1-A2.pdf", saved_pdf="x")
        panel.update_entry(item, "COMPLETED")
        self.assertEqual(panel.lbl_stats.cget("text"), "Đã duyệt: 1 / 3 file")
        self.assertEqual(panel.view_switch.get(), "Đã xong (1)", "the open file stays on screen")
        row, = panel.file_tree.get_children()
        self.assertEqual(tuple(panel.file_tree.item(row, "values")), ("✅ Xong", "15.SQL.05.2010.A1-A2"))
        self.assertEqual(tags(row), ("COMPLETED", "active"))
        panel._on_file_enter()
        panel.on_select_file_callback.assert_called_with("15.SQL.05.2010.A1-A2.pdf")
        panel.show_active(None)
        self.assertEqual(tags(row), ("COMPLETED",))
        self.assertEqual(panel.file_tree.selection(), ())

    def test_a_long_file_list_is_one_table(self):
        panel = self.sidebar()
        token = panel._folder_scan = object()
        started = time.perf_counter()
        panel._finish_folder_scan(token, [(f"D:/kho/HO SO {i}/15.SQL.03.1996.C{i:06}-C{i + 160:06}.pdf", None)
                                          for i in range(1300)], None, False)
        panel.update_idletasks()
        # 1,300 cards took 20 s and used up the 10,000 Windows handles a program may have.
        self.assertLess(time.perf_counter() - started, 3.0)
        self.assertEqual(len(panel.file_tree.get_children()), 1300)
        self.assertEqual(len(panel.list_holder.winfo_children()), 2, "a table and its scroll bar")

    def test_long_file_names_keep_their_start_and_end(self):
        panel = self.sidebar()
        name = "15.SQL.03.1996.C244337-C244498"
        panel._name_room = panel._name_font.measure(name) * 2 // 3
        panel._fitted = {}
        shown = panel._fit_name(name)
        self.assertIn("…", shown)
        self.assertTrue(shown.startswith("15.SQL"), shown)
        self.assertTrue(shown.endswith("C244498"), shown)
        self.assertLessEqual(panel._name_font.measure(shown), panel._name_room)
        panel._name_room = panel._name_font.measure(name)
        panel._fitted = {}
        self.assertEqual(panel._fit_name(name), name, "a name that fits is shown whole")

    def test_batch_ocr_can_be_stopped(self):
        panel = self.sidebar()
        token = panel._folder_scan = object()
        panel._finish_folder_scan(token, [("a.pdf", None), ("b.pdf", None), ("c.pdf", None)], None, False)
        workers = []
        app = SimpleNamespace(sidebar=panel, is_processing_batch=False, _batch_stop=None, _closing=False,
                              _launch_worker=lambda work, ocr=False: workers.append(work),
                              _dispatch_to_ui=lambda callback, *args, **kw: callback(*args, **kw),
                              _is_active=lambda item: item is panel.queue_items[2], review=Mock())
        app._finish_batch = lambda *a, **kw: GPLXApp._finish_batch(app, *a, **kw)
        app._on_single_file_processed = lambda *a: GPLXApp._on_single_file_processed(app, *a)
        panel.on_batch_stop_callback = lambda: GPLXApp.on_batch_stop_requested(app)
        GPLXApp.on_batch_run_requested(app, "15")
        self.assertEqual(panel.btn_run_batch.cget("state"), "normal", "the OCR button stops the batch")

        def read_first_then_stop(path, **kwargs):
            panel._stop_batch()
            return {"cover_meta": {}}

        with patch("src.gui.app.process_dossier_pdf", side_effect=read_first_then_stop) as read, \
                patch("src.gui.app.messagebox.showinfo") as info:
            workers.pop()()
        self.assertEqual(read.call_count, 1)
        self.assertEqual([item["status"] for item in panel.queue_items], ["READY", "PENDING", "PENDING"])
        self.assertEqual(info.call_args.args[0], "Đã dừng OCR")
        self.assertFalse(panel.is_loading)
        # The open file waited for its turn: its panel no longer says it is being read.
        app.review.clear_data.assert_called_once_with("Đã dừng OCR trước khi đọc file này. Bấm lại vào file để đọc.")

    def closing_app(self, workers, ocr, statuses=()):
        import threading
        return SimpleNamespace(
            _worker_lock=threading.Lock(), _active_workers=workers, _active_ocr=ocr, _ui_tasks=Mock(empty=lambda: True),
            sidebar=SimpleNamespace(show_active=Mock(), queue_items=[{"status": status} for status in statuses]),
            _batch_stop=None, _closing=False, _ocr=Mock(), viewer=Mock(), destroy=Mock())

    def test_app_can_close_while_only_ocr_runs(self):
        app = self.closing_app(workers=1, ocr=1, statuses=["PROCESSING"])
        with patch("src.gui.app.messagebox.askyesno", return_value=True) as ask:
            GPLXApp.on_close(app)
        ask.assert_called_once()
        app.destroy.assert_called_once()
        self.assertTrue(app.sidebar.queue_items[0]["cancelled"])
        self.assertTrue(app.exit_now, "OCR cannot stop inside a file: the process ends at once")
        app = self.closing_app(workers=0, ocr=0)
        GPLXApp.on_close(app)
        app.destroy.assert_called_once()
        self.assertFalse(getattr(app, "exit_now", False))

        for workers, ocr, statuses in ((1, 0, ()), (2, 1, ()), (1, 1, ["SAVING"])):
            app = self.closing_app(workers, ocr, statuses)
            with patch("src.gui.app.messagebox.showwarning") as warn:
                GPLXApp.on_close(app)
            warn.assert_called_once()
            app.destroy.assert_not_called()

    def test_closing_during_ocr_ends_the_process_at_once(self):
        for exit_now in (True, False):
            app = SimpleNamespace(mainloop=Mock(), exit_now=exit_now)
            with patch("src.gui.app.os._exit") as end, patch("src.gui.app.logging.shutdown") as flush:
                GPLXApp.run(app)
            app.mainloop.assert_called_once()
            self.assertEqual(end.call_args_list, [call(0)] if exit_now else [])
            self.assertEqual(flush.call_count, int(exit_now), "the log is written out first")

    def test_file_being_saved_is_not_opened_in_the_preview(self):
        item = {"path": "D:/kho/scan.pdf", "status": "SAVING", "data": {"cover_meta": {}}}
        app = SimpleNamespace(sidebar=SimpleNamespace(show_active=Mock(), get_item=lambda path: item, queue_items=[item]),
                              review=Mock(), viewer=Mock(), active_item=None, active_file_path=None, tabview=Mock())
        GPLXApp.on_file_selected(app, item["path"])
        app.viewer.load_pdf.assert_not_called()
        app.viewer.clear_preview.assert_called_once()
        app.review.set_saving.assert_called_with(True)

        with patch("src.gui.app.messagebox.showinfo") as info:
            GPLXApp.on_search_view_pdf(app, "D:\\kho\\scan.pdf", 2)
        info.assert_called_once()
        app.viewer.load_pdf.assert_not_called()


class PaneLayoutTest(unittest.TestCase):
    """The file list | PDF | review panes of the digitizing tab: sized for the display scale, and on each
    machine the side panes keep the widths the user last dragged them to."""

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        folder = TemporaryDirectory(prefix="gplx-layout-")
        self.addCleanup(folder.cleanup)
        self.folder = folder.name
        self.layout_file = os.path.join(folder.name, "GPLX", "giao_dien.json")
        moved = patch("src.gui.app.UI_SETTINGS_PATH", self.layout_file)
        moved.start()
        self.addCleanup(moved.stop)

    def start(self, scale=2.0):
        """The main window's pane code on a real tk.PanedWindow. A hidden test window has no geometry, so the
        panes report the widths a test puts in app.shown (screen pixels), and the PDF viewer starts at x=600."""
        paned = tk.PanedWindow(self.root)
        self.addCleanup(paned.destroy)
        app = SimpleNamespace(paned=paned, PANES=GPLXApp.PANES, shown={}, _dragged=None)
        for name in ("sidebar", "viewer", "review"):
            pane = tk.Frame(paned)
            pane.winfo_width = lambda name=name: app.shown[name]
            pane._get_widget_scaling = lambda: scale
            paned.add(pane)
            setattr(app, name, pane)
        app.viewer.winfo_x = lambda: 600
        for method in ("_load_pane_widths", "_save_pane_widths", "_apply_pane_scaling", "_pane_width",
                       "_on_sash_pressed", "_on_sash_released", "_remember_dragged_pane"):
            setattr(app, method, getattr(GPLXApp, method).__get__(app))
        app.pane_widths = app._load_pane_widths()
        app._apply_pane_scaling()
        return app

    def sizes(self, app, option="width"):
        return [int(str(app.paned.panecget(getattr(app, name), option))) for name in ("sidebar", "viewer", "review")]

    def drag(self, app, divider, shown, dragged_to):
        """Press on divider 0 (file list | PDF) or 1 (PDF | review), move it, let go."""
        app.shown.update(shown)
        app._on_sash_pressed(SimpleNamespace(x=300 if divider == 0 else 1800, y=10))
        app.shown.update(dragged_to)
        app._remember_dragged_pane()

    def write_layout(self, text):
        os.makedirs(os.path.dirname(self.layout_file), exist_ok=True)
        with open(self.layout_file, "w", encoding="utf-8") as f:
            f.write(text)

    def saved(self):
        with open(self.layout_file, encoding="utf-8") as f:
            return json.load(f)

    def test_first_start_uses_the_default_widths_for_the_display_scale(self):
        app = self.start(scale=2.0)
        # tk.PanedWindow counts screen pixels: at 200% the old sizes gave the file list half its width.
        self.assertEqual(self.sizes(app), [492, 1260, 1020])
        self.assertEqual(self.sizes(app, "minsize"), [360, 760, 940])
        self.assertEqual(int(str(app.paned.cget("sashwidth"))), 12)
        self.assertFalse(os.path.exists(self.layout_file), "nothing is written before a divider is dragged")

    def test_a_dragged_divider_is_kept_for_the_next_start(self):
        app = self.start(scale=2.0)
        self.drag(app, 1, shown={"sidebar": 492, "review": 1020}, dragged_to={"review": 1300})
        self.assertEqual(self.saved(), {"panes": {"sidebar": 246, "review": 650}})  # 100% units

        app._apply_pane_scaling(1.5)  # the window moved to a 150% screen
        self.assertEqual(self.sizes(app), [369, 945, 975])
        later = self.start(scale=1.0)  # next start
        self.assertEqual(self.sizes(later), [246, 630, 650])

    def test_each_divider_keeps_only_its_own_pane(self):
        # A narrow window squeezes the panes for a while (here the file list to 230 of 300): dragging the
        # other divider must not store a squeezed width.
        self.write_layout('{"panes": {"sidebar": 300, "review": 510}}')
        app = self.start(scale=2.0)
        self.drag(app, 1, shown={"sidebar": 492, "review": 1020}, dragged_to={"review": 1200})
        self.assertEqual(self.saved(), {"panes": {"sidebar": 300, "review": 600}})
        self.drag(app, 0, shown={"sidebar": 492, "review": 1200}, dragged_to={"sidebar": 520, "review": 1140})
        self.assertEqual(self.saved(), {"panes": {"sidebar": 260, "review": 600}})

    def test_a_click_on_a_divider_writes_nothing(self):
        app = self.start()
        self.drag(app, 1, shown={"sidebar": 492, "review": 1020}, dragged_to={})
        self.assertFalse(os.path.exists(self.layout_file))

    def test_the_width_is_read_after_tk_has_moved_the_panes(self):
        app = self.start(scale=2.0)
        # Timers are run by hand: updating the hidden root would also run the leftover timers of windows
        # other tests destroyed (Tcl prints "invalid command name").
        waiting = []
        app.after = lambda delay, callback: waiting.append(callback)
        app.shown.update(sidebar=492, review=1020)
        app._on_sash_pressed(SimpleNamespace(x=300, y=10))
        app._on_sash_released(SimpleNamespace(x=420, y=10))
        app.shown["sidebar"] = 700  # Tk lays the panes out after the button is let go
        for callback in waiting:
            callback()
        self.assertEqual(self.saved(), {"panes": {"sidebar": 350, "review": 510}})

    def test_a_damaged_layout_file_is_ignored(self):
        for text, widths, unreadable in (('{"panes": {"sidebar": 300', [492, 1260, 1020], True),
                                         ('[300, 650]', [492, 1260, 1020], True),
                                         ('{"panes": {"sidebar": "rộng", "review": 650}}', [492, 1260, 1300], False),
                                         ('{"panes": {"sidebar": 100, "review": true}}', [492, 1260, 1020], False),
                                         ('{"panes": {"sidebar": 300, "review": 99999}}', [600, 1260, 1020], False)):
            with self.subTest(text=text):
                self.write_layout(text)
                logs = self.assertLogs if unreadable else self.assertNoLogs
                with logs("gplx.src.gui.app", level="WARNING"):
                    app = self.start(scale=2.0)
                self.assertEqual(self.sizes(app), widths)

    def test_a_layout_that_cannot_be_written_is_only_logged(self):
        with open(os.path.join(self.folder, "GPLX"), "w"):
            pass  # a file where the GPLX folder should be
        app = self.start(scale=2.0)
        with self.assertLogs("gplx.src.gui.app", level="WARNING"):
            self.drag(app, 1, shown={"sidebar": 492, "review": 1020}, dragged_to={"review": 1300})
        self.assertEqual(app.pane_widths["review"], 650, "the drag still holds while the app runs")


class BoxFolderNamesTest(unittest.TestCase):
    def locate(self, relative):
        temporary = TemporaryDirectory(prefix="gplx-box-")
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name, "Tinh Yen Bai", *relative.split("/"))
        folder.mkdir(parents=True)
        (folder / "a.pdf").write_bytes(b"")
        result = folder_review_location(str(folder / "a.pdf"))
        return result["box"], result["box_number"], result["province_folder"], result.get("box_review", {})

    def test_box_numbers_with_a_letter_are_kept_and_the_province_stays_above(self):
        self.assertEqual(self.locate("HOP 49/HO SO 116")[:3], ("49", "116", "Tinh Yen Bai"))
        self.assertEqual(self.locate("Hop 49A/Ho so 116")[:3], ("49A", "116", "Tinh Yen Bai"))
        self.assertEqual(self.locate("HOP 49/HO SO 116b")[:3], ("49", "116B", "Tinh Yen Bai"))
        self.assertEqual(self.locate("Hộp49a/Hộp số 116")[:3], ("49A", "116", "Tinh Yen Bai"))
        self.assertEqual(self.locate("Tủ 3/HO SO 116/Scan lan 2")[:3], ("3", "116", "Tinh Yen Bai"))
        # Any punctuation may stand between the word and the number, as before.
        for box in ("HOP (49)", "HOP#49", "HOP [49]", "TU-49", "HOP.49"):
            self.assertEqual(self.locate(f"{box}/HO SO 116")[:3], ("49", "116", "Tinh Yen Bai"), box)
        self.assertEqual(self.locate("HOP 49/HO SO (116)")[:3], ("49", "116", "Tinh Yen Bai"))
        self.assertEqual(self.locate("HOP_49/HOP_SO_115")[:3], ("49", "115", "Tinh Yen Bai"))
        # A letter written apart from the number belongs to it.
        self.assertEqual(self.locate("HOP 49 A/HO SO 116 - b")[:3], ("49A", "116B", "Tinh Yen Bai"))
        self.assertEqual(self.locate("HOP 49/HO SO 116 lan")[:2], ("49", "116"))
        # "Từ" (from) is not "Tủ" (cabinet), although both fold to "tu".
        self.assertEqual(self.locate("Từ 1990 đến 1995/HOP 49/HO SO 116")[:3], ("49", "116", "Từ 1990 đến 1995"))

    def test_box_filter_lists_boxes_in_number_order(self):
        from src.database import sort_box_labels
        self.assertEqual(sort_box_labels(["100", "49A", "2", "10", "49", "1", "Kho A", "49B"]),
                         ["1", "2", "10", "49", "49A", "49B", "100", "Kho A"])

    def test_other_numbers_in_a_box_folder_name_leave_the_box_for_review(self):
        box, box_number, province, review = self.locate("HOP 49 (2010)/HO SO 116")
        self.assertEqual((box, box_number, province), ("", "116", "Tinh Yen Bai"))
        self.assertIn("HOP 49 (2010)", review["box"])
        box, box_number, province, review = self.locate("HOP 49/HO SO 116 - 2015")
        self.assertEqual((box, box_number, province), ("49", "", "Tinh Yen Bai"))
        self.assertIn("box_number", review)


if __name__ == "__main__":
    unittest.main()
