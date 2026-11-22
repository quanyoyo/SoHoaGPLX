import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from src.pipeline import fast_extract_rename_metadata, summarize_license_table
from src.table_extractor import (
    Box, LicenseTableExtractor, _joined_rules, _name_anchors, _split_merged, apply_cell_edit, measure_page_grid, table_citizens,
)


SIZE = (900, 730)
EDGES = (25, 90, 255, 375, 550, 720, 875)
HEADERS = ("STT", "Họ và tên", "Năm sinh", "Nơi cư trú", "Số GPLX", "Ngày cấp")


def make_page(*sections, edges=EDGES):
    image = Image.new("L", SIZE, 255)
    draw = ImageDraw.Draw(image)
    result = []
    for start, headers, records in sections:
        values = ([headers] if headers else []) + records
        end = start + 38 * len(values)
        for x in edges:
            draw.line((x, start, x, end), fill=0, width=1)
        for i in range(len(values) + 1):
            y = start + i * 38
            draw.line((edges[0], y, edges[-1], y), fill=0, width=1)
        for i, row in enumerate(values):
            y = start + i * 38 + 9
            for column, value in enumerate(row):
                if value is None:
                    continue
                x = edges[column] + 8
                score = .95
                if isinstance(value, tuple):
                    value, score = value
                if score is None:
                    # A real ink mark that was missed entirely by OCR.
                    draw.rectangle((x, y, x + 5, y + 12), fill=0)
                    continue
                width = min(len(value) * 7, edges[column+1] - x - 5)
                result.append(([(x, y), (x + width, y), (x + width, y + 16), (x, y + 16)], value, score))
    return result, measure_page_grid(image)


def row(stt, code):
    return (str(stt), "Nguyễn Văn A", "1982", "Tỉnh Yên Bái", code, "01/06/2010")


class LicenseTablesV3Test(unittest.TestCase):
    def setUp(self):
        self.extractor = LicenseTableExtractor()

    def read(self, page_number, *sections):
        ocr, grid = make_page(*sections)
        self.extractor.read_page(ocr, SIZE, grid, page_number)

    def test_wrapped_name_heading_and_broken_rule_are_recognized(self):
        # QD_000493: "Họ" above "và tên" are two OCR boxes; the rule under the heading is broken.
        boxes = [Box("Ho", .66, .173, .099, .201, .116), Box("va ten", .75, .158, .118, .213, .132),
                 Box("Nam", .54, .244, .100, .287, .115)]
        anchor, = _name_anchors(boxes)
        self.assertEqual((anchor.text, anchor.x0, anchor.y0, anchor.x1, anchor.y1), ("Ho va ten", .158, .099, .213, .132))
        self.assertEqual(_joined_rules([(.1346, .027, .25), (.135, .279, .961), (.20, .5, .6)]),
                         [(.1346, .027, .961), (.20, .5, .6)])

    def test_name_ending_in_cong_does_not_end_the_list(self):
        # Accents are lost in OCR: a wrapped "Hoàng Văn / Công" reads like the "Cộng" total.
        self.read(1, (60, HEADERS, [row(1, "AP014542"), ("", "Cong", "", "", "", ""), row(2, "AP014543"),
                                    row(3, "AP014544")]))
        table, = self.extractor.tables
        self.assertEqual([r["license_number"] for r in table["rows"]], ["AP014542", "AP014543", "AP014544"])

    def test_repeated_heading_with_missed_column_label_joins_previous_list(self):
        self.read(1, (60, HEADERS, [row(1, "AP014542"), row(2, "AP014543")]))
        missed = ("STT", "Họ và tên", "Năm sinh", None, "Số GPLX", "Ngày cấp")
        self.read(2, (60, missed, [row(3, "AP014544"), row(4, "AP014545")]))
        table, = self.extractor.tables
        self.assertEqual([r["license_number"] for r in table["rows"]], ["AP014542", "AP014543", "AP014544", "AP014545"])
        self.assertTrue(all(len(r["cells"]) == len(table["columns"]) == 6 for r in table["rows"]))
        self.assertEqual(table["rows"][3]["cells"][3], "Tỉnh Yên Bái", "cells follow the list's own columns")

    def test_wrapped_name_line_stays_in_its_row(self):
        ocr, grid = make_page((60, HEADERS, [row(1, "AP014542"), row(2, "AP014543")]))
        # Second line of row 1's name and address, inside the same ruled row.
        for x, text in ((98, "Trường Giang"), (383, "Huyện Văn Chấn")):
            y = 60 + 38 + 22
            ocr.append(([(x, y), (x + 80, y), (x + 80, y + 14), (x, y + 14)], text, .9))
        self.extractor.read_page(ocr, SIZE, grid, 1)
        table, = self.extractor.tables
        self.assertEqual([r["license_number"] for r in table["rows"]], ["AP014542", "AP014543"])
        self.assertEqual(table["rows"][0]["cells"][1], "Nguyễn Văn A Trường Giang")

    def test_full_width_punctuation_and_rule_through_last_row(self):
        ocr, grid = make_page((60, HEADERS, [row(1, "AP014542"), row(2, "：AP014543")]))
        # A scan streak through the last row's text must not cut that row short. As on
        # QD_000493 page 7, the licence box sits slightly lower than the name box.
        box, text, score = ocr[-2]
        ocr[-2] = ([(x, y + 3) for x, y in box], text, score)
        name_y = 60 + 38 * 2 + 9 + 8
        grid.horizontal.append(((name_y + 1) / SIZE[1], 90 / SIZE[0], 470 / SIZE[0]))
        self.extractor.read_page(ocr, SIZE, grid, 1)
        table, = self.extractor.tables
        self.assertEqual([(r["license_number"], r["license_state"]) for r in table["rows"]],
                         [("AP014542", "valid"), ("AP014543", "valid")])

    def test_merged_birth_and_nationality_heading_is_split(self):
        # 1996 books: OCR reads the "Năm sinh | Quốc tịch" border as a letter.
        for text in ("NAM SINHIQUOCTICH", "NAM SINH I QUOC TICH", "NĂM SINH|QUỐC TỊCH"):
            parts = _split_merged(Box(text, .9, .30, .1, .50, .12))
            self.assertEqual([p.text for p in parts], ["Năm sinh", "Quốc tịch"], text)
            self.assertLess(parts[0].x1, parts[1].x1)

    def test_reads_only_lists_with_name_and_birth_columns(self):
        no_birth = ("STT", "Họ và tên", "Quốc tịch", "Nơi cư trú", "Số GPLX", "Ngày cấp")
        with_birth_date = ("STT", "Họ tên", "Ngày tháng năm sinh", "Nơi cư trú", "Số GPLX", "Ngày cấp")
        self.read(1, (60, no_birth, [row(1, "AP014542"), row(2, "AP014543")]))
        # The unlabeled next page belongs to the skipped table and must not start or join a list.
        self.read(2, (60, None, [row(3, "AP014544"), row(4, "AP014545")]))
        self.assertEqual(self.extractor.tables, [])
        self.read(3, (60, with_birth_date, [row(1, "AP014600"), row(2, "AP014601")]))
        table, = self.extractor.tables
        self.assertEqual([r["license_number"] for r in table["rows"]], ["AP014600", "AP014601"])
        self.read(4, (60, None, [row(3, "AP014602")]))
        self.assertEqual(len(table["rows"]), 3)

    def test_cell_edit_updates_lookup_fields(self):
        self.read(1, (60, HEADERS, [row(1, "AP014542"), row(2, ("AP0l4543", .40))]))
        table, = self.extractor.tables
        second = table["rows"][1]
        self.assertNotEqual(second["license_state"], "valid")
        apply_cell_edit(table, second, 4, "AP014543")
        self.assertEqual((second["license_number"], second["license_state"]), ("AP014543", "valid"))
        apply_cell_edit(table, second, 1, "TRẦN THỊ BÍCH")  # capital accented letters are kept
        citizens = table_citizens(table)
        self.assertEqual([c["license_number"] for c in citizens], ["AP014542", "AP014543"])
        self.assertEqual(citizens[1]["full_name"], "Trần Thị Bích")
        apply_cell_edit(table, second, 4, "")
        self.assertEqual((second["license_number"], second["license_state"]), ("", "blank"))

    def test_ignores_fees_and_keeps_first_page_list(self):
        self.read(1, (60, HEADERS, [row(1, "AP014542"), row(3, "AP014544")]),
                  (300, ("Số TT", "Nội dung", "Số lượng", "Phí sát hạch", "Thành tiền", ""),
                   [("1", "Lệ phí cấp GPLX", "29", "50.000", "1.450.000", None)]))
        table, = self.extractor.tables
        self.assertEqual([c["label"] for c in table["columns"]], list(HEADERS))
        self.assertEqual([r["stt"] for r in table["rows"]], [1, 3])
        self.assertEqual([r["page_number"] for r in table["rows"]], [1, 1])

    def test_joins_headerless_and_repeated_header_pages_using_row_order(self):
        self.read(2, (60, HEADERS, [row(1, "C244344"), row(2, "C244355")]))
        self.read(3, (90, None, [row(4, "C244340"), row(6, "C244337")]))
        self.read(4, (80, HEADERS, [row(7, "C244341")]))
        table, = self.extractor.tables
        self.assertEqual([r["page_number"] for r in table["rows"]], [2, 2, 3, 3, 4])
        summary = summarize_license_table(table)
        self.assertEqual((summary["first_license_no"], summary["last_license_no"]), ("C244344", "C244341"))
        self.assertEqual(summary["total_licenses"], 5)

    def test_independent_lists_stay_separate_on_one_page_and_across_pages(self):
        self.read(1, (50, HEADERS, [row(1, "A465211"), row(2, "A465212")]),
                  (350, HEADERS, [row(1, "B295726"), row(2, "B295727")]))
        self.read(2, (50, HEADERS, [row(1, "C244337")]))
        self.assertEqual([t["rows"][0]["license_number"] for t in self.extractor.tables],
                         ["A465211", "B295726", "C244337"])

    def test_side_by_side_lists_stay_separate(self):
        left = (12, 43, 115, 172, 252, 334, 418)
        right = tuple(x + 452 for x in left)
        left_ocr, left_grid = make_page((60, HEADERS, [row(1, "A465211")]), edges=left)
        right_ocr, right_grid = make_page((60, HEADERS, [row(1, "B295726")]), edges=right)
        left_grid.vertical.extend(right_grid.vertical)
        left_grid.horizontal.extend(right_grid.horizontal)
        self.extractor.read_page(left_ocr + right_ocr, SIZE, left_grid, 1)
        self.assertEqual([t["rows"][0]["license_number"] for t in self.extractor.tables],
                         ["A465211", "B295726"])

    def test_follows_matching_license_codes_when_stt_was_not_read(self):
        self.read(1, (60, HEADERS, [row(1, "AP014542"), (None, *row(2, "AP014543")[1:])]))
        self.read(2, (90, None, [(None, *row(3, "AP014544")[1:])]))
        table, = self.extractor.tables
        self.assertEqual([r["license_number"] for r in table["rows"]], ["AP014542", "AP014543", "AP014544"])
        self.assertEqual(table["rows"][-1]["page_number"], 2)

    def test_unresolved_continuation_does_not_use_previous_endpoint(self):
        self.read(1, (60, HEADERS, [row(1, "AP014542"), row(2, "AP014543")]))
        self.read(2, (90, None, [(None, *row(3, "APO14544")[1:])]))
        table, = self.extractor.tables
        summary = summarize_license_table(table)
        self.assertEqual(table["unresolved_pages"], [2])
        self.assertEqual(summary["total_licenses"], 2, "rows of the list; page 2 is left to check")
        self.assertEqual(summary["last_license_no"], "")

    def test_verified_blank_ignores_register_number(self):
        headers = ("STT", "Họ và tên", "Năm sinh", "Số TT bảng kê", "Số giấy phép", "Ngày cấp")
        self.read(1, (60, headers, [
            ("1", "Nguyễn Văn A", "1982", "AP014542", None, "01/06/2010"),
            ("2", "Nguyễn Văn B", "1985", "AP014543", None, "01/06/2010"),
        ]))
        table, = self.extractor.tables
        self.assertEqual([r["license_state"] for r in table["rows"]], ["blank", "blank"])
        self.assertTrue(summarize_license_table(table)["license_column_empty"])
        self.assertEqual(table["rows"][0]["cells"][3:5], ["AP014542", ""])

    def test_register_number_preserves_row_when_ocr_joins_name_and_misses_stt(self):
        headers = ("STT", "Họ và tên", "Năm sinh", "Số TT bảng kê", "Số giấy phép", "Ngày cấp")
        self.read(1, (60, headers, [
            ("1", "Nguyễn Văn A", "1982", "170656", None, "01/06/2010"),
            (None, "HàVũ", "1989", "170657", None, "01/06/2010"),
            ("3", "Nguyễn Văn B", "1985", "170658", None, "01/06/2010"),
        ]))
        table, = self.extractor.tables
        self.assertEqual([r["cells"][3] for r in table["rows"]], ["170656", "170657", "170658"])
        middle = table["rows"][1]
        self.assertIsNone(middle["stt"])
        self.assertFalse(middle["identity_confident"])
        self.assertEqual(middle["cells"][1], "HàVũ")
        self.assertEqual(middle["license_state"], "blank")

    def test_known_license_column_and_birth_year_preserve_row_without_recognized_name(self):
        self.read(1, (60, HEADERS, [
            row(1, "AP014542"),
            (None, "HàVũ", "1989", "Tỉnh Yên Bái", "AP014543", "01/06/2010"),
            row(3, "AP014544"),
            (None, None, None, None, "AP014545", None),
        ]))
        table, = self.extractor.tables
        self.assertEqual([r["license_number"] for r in table["rows"]], ["AP014542", "AP014543", "AP014544"])
        self.assertFalse(table["rows"][1]["identity_confident"])

    def test_ink_and_low_confidence_are_not_verified_blank(self):
        self.read(1, (60, HEADERS, [
            row(1, ("AP014542", .45)), row(2, ("OCR missed", None)), row(3, "AP014544"),
        ]))
        table, = self.extractor.tables
        self.assertEqual([r["license_state"] for r in table["rows"]], ["uncertain", "uncertain", "valid"])
        stats = summarize_license_table(table)
        self.assertEqual((stats["first_license_no"], stats["last_license_no"]), ("", "AP014544"))
        self.assertEqual(stats["license_sequence"], "")
        self.assertFalse(stats["license_column_empty"])

    def test_unknown_header_uses_repeated_pattern_in_one_column(self):
        headers = (*HEADERS[:4], "Ký hiệu", HEADERS[5])
        self.read(1, (60, headers, [row(1, "AH515361"), row(2, "AH515362")]))
        table, = self.extractor.tables
        self.assertTrue(table["columns"][4]["inferred"])
        self.assertEqual([r["license_number"] for r in table["rows"]], ["AH515361", "AH515362"])

    def test_single_match_under_unknown_header_does_not_assign_license_column(self):
        headers = (*HEADERS[:4], "Ký hiệu", HEADERS[5])
        self.read(1, (60, headers, [row(1, "AH515361"), row(2, "163913")]))
        table, = self.extractor.tables
        self.assertEqual([r["license_state"] for r in table["rows"]], ["unknown_column", "unknown_column"])

    def test_folder_naming_of_several_sql_lists_spans_the_book(self):
        self.read(1, (50, HEADERS, [row(1, "A465211")]), (350, HEADERS, [row(1, "B295726")]))
        self.assertEqual(len(self.extractor.tables), 2)
        cover = dict(document_type="cover", exam_date="01/06/2010", province_code="15", decision_date="",
                     decision_number="", metadata_review={})
        with (patch("src.pipeline._pdf_cache_key", return_value=("example.pdf", 5, 5)),
              patch("src.pipeline._cached_opening", return_value=(cover, 1, None)),
              patch("src.pipeline._cached_tables", return_value=self.extractor.tables)):
            self.assertEqual(fast_extract_rename_metadata("example.pdf", "15"), "15.SQL.06.2010.A465211-B295726")


def plain_list(columns, rows, page, unresolved=None):
    table = {"columns": [{"label": label, "role": role} for label, role in columns], "rows": [
        {"cells": list(cells), "scores": [.9] * len(cells), "bounds": [(0, 0, 1, 1)] * len(cells), "page_number": page,
         "stt": None, "identity_confident": True, "license_number": cells[-1] if cells[-1].startswith("C") else "",
         "license_state": "valid"} for cells in rows]}
    if unresolved:
        table["unresolved_pages"] = unresolved
    return table


class MergeListsTest(unittest.TestCase):
    """The lists of one PDF are one dossier: shown, summarized and saved as one list (one Excel sheet)."""

    def test_lists_become_one_list_with_every_column(self):
        from src.table_extractor import merge_tables
        first = plain_list([("STT", "stt"), ("Họ và tên", "full_name"), ("Năm sinh", "birth_year"), ("Số GPLX", "license_number")],
                           [("1", "Nguyễn Văn A", "1980", "C244537"), ("2", "Lê Văn B", "1981", "C244538")], 2, unresolved=[3])
        second = plain_list([("STT", "stt"), ("HO VA TEN", "full_name"), ("ANH 3 X 4", "photo"), ("Năm sinh", "birth_year"),
                             ("Số GPLX", "license_number"), ("Ký nhận", "signature")],
                            [("1", "Hà Văn C", "ảnh", "1982", "C244539", "ký")], 5)
        merged, = merge_tables([first, {"columns": [], "rows": []}, second])
        self.assertEqual([(c["label"], c["role"]) for c in merged["columns"]], [
            ("STT", "stt"), ("Họ và tên", "full_name"), ("ANH 3 X 4", "photo"), ("Năm sinh", "birth_year"),
            ("Số GPLX", "license_number"), ("Ký nhận", "signature")])
        self.assertEqual([r["cells"] for r in merged["rows"]], [
            ["1", "Nguyễn Văn A", "", "1980", "C244537", ""], ["2", "Lê Văn B", "", "1981", "C244538", ""],
            ["1", "Hà Văn C", "ảnh", "1982", "C244539", "ký"]])
        self.assertEqual([len(r["scores"]) for r in merged["rows"]], [6, 6, 6])
        self.assertEqual(merged["rows"][0]["bounds"][2], None, "no photo cell in that list")
        self.assertEqual([r.get("absent_columns", []) for r in merged["rows"]], [[2, 5], [2, 5], []])
        self.assertEqual([r["page_number"] for r in merged["rows"]], [2, 2, 5])
        self.assertEqual(merged["unresolved_pages"], [3])
        self.assertEqual(len(first["rows"][0]["cells"]), 4, "the lists read are not changed")
        self.assertEqual(merge_tables([first])[0]["columns"], first["columns"])
        self.assertEqual(merge_tables([]), [])

    def test_the_same_printed_column_is_one_column_whatever_its_heading_was_read_as(self):
        from src.table_extractor import merge_tables

        def placed(columns, rows, page):
            table = plain_list([(label, role) for label, role, _, _ in columns], rows, page)
            for column, (_, _, left, right) in zip(table["columns"], columns):
                column.update(left=left, right=right)
            return table
        # The headings of one book as OCR read them on two pages (sample 4_SG_000116_..._000006).
        first = placed([("STT", "stt", .05, .09), ("HO VA TEN", "full_name", .09, .30), ("ANH 3 X 4", "photo", .30, .42),
                        ("Quốc tịch", "nationality", .42, .52), ("Số bằng", "license_number", .52, .70),
                        ("Ký nhận", "signature", .70, .95)],
                       [("1", "Nguyễn Văn A", "", "Viet Nam", "C244537", "")], 2)
        second = placed([("STT", "stt", .06, .10), ("HO VA TEN", "full_name", .10, .31), ("ANH 3", "other", .31, .37),
                         ("X4", "other", .37, .43), ("QUOC", "other", .43, .47), ("TICH", "other", .47, .53),
                         ("BANG", "license_number", .53, .71), ("KY", "other", .71, .82), ("NHAN", "other", .82, .96)],
                        [("1", "Lê Văn B", "", "", "Viet", "Nam", "C244538", "", "")], 3)
        merged, = merge_tables([first, second])
        self.assertEqual([(c["label"], c["role"]) for c in merged["columns"]], [
            ("STT", "stt"), ("HO VA TEN", "full_name"), ("ANH 3 X 4", "photo"), ("Quốc tịch", "nationality"),
            ("Số bằng", "license_number"), ("Ký nhận", "signature")])
        self.assertEqual(merged["rows"][1]["cells"], ["1", "Lê Văn B", "", "Viet Nam", "C244538", ""])
        self.assertNotIn("absent_columns", merged["rows"][1])
        # A heading read only as text on the first page takes the role read on another page.
        first["columns"][3].update(label="QUOC TICH!", role="other")
        merged, = merge_tables([first, second])
        self.assertEqual([c["role"] for c in merged["columns"]][3], "other")
        merged, = merge_tables([second, first])
        self.assertEqual((merged["columns"][3]["label"], merged["columns"][3]["role"]), ("QUOC TICH!", "other"))
        # A column wider than the frame's (its heading split differently) joins it; so does the one GPLX column
        # wherever it was read (sample 4_SG_000116_..._000007: numbers under the "NHAN" heading).
        fourth = placed([("STT", "stt", .05, .09), ("HO VA TEN", "full_name", .09, .30), ("ANH", "photo", .28, .48),
                         ("NHAN", "license_number", .72, .95)], [("1", "Đỗ Văn D", "", "C244540")], 5)
        merged, = merge_tables([first, fourth])
        self.assertEqual(len(merged["columns"]), 6)
        self.assertEqual(merged["rows"][1]["cells"], ["1", "Đỗ Văn D", "", "", "C244540", ""])
        # A heading split in two on the frame page: the photo column of another page joins the photo half.
        split = placed([("STT", "stt", .05, .09), ("HO VA TEN", "full_name", .09, .30), ("ANH", "photo", .30, .36),
                        ("X4", "other", .36, .42), ("Quốc tịch", "nationality", .42, .52), ("Số bằng", "license_number", .52, .70),
                        ("Ký nhận", "signature", .70, .95)], [("1", "Ngô Văn E", "", "", "Viet Nam", "C244541", "")], 6)
        merged, = merge_tables([split, fourth])
        self.assertEqual([c["role"] for c in merged["columns"]].count("photo"), 1)
        self.assertEqual([c["label"] for c in merged["columns"]][2:4], ["ANH", "X4"])
        # A column at a different place is its own column, in page order.
        third = placed([("STT", "stt", .05, .09), ("HO VA TEN", "full_name", .09, .30), ("Năm sinh", "birth_year", .30, .40),
                        ("Số bằng", "license_number", .52, .70)], [("1", "Hà Văn C", "1982", "C244539")], 4)
        merged, = merge_tables([first, third])
        self.assertEqual([c["role"] for c in merged["columns"]],
                         ["stt", "full_name", "photo", "birth_year", "other", "license_number", "signature"])

    def test_a_page_to_check_inside_the_book_keeps_the_last_number(self):
        from src.table_extractor import merge_tables
        columns = [("STT", "stt"), ("Họ và tên", "full_name"), ("Số GPLX", "license_number")]
        merged = merge_tables([plain_list(columns, [("1", "A", "C244537")], 2, unresolved=[3]),
                               plain_list(columns, [("1", "B", "C244538")], 4)])
        stats = summarize_license_table(merged[0])
        self.assertEqual((stats["first_license_no"], stats["last_license_no"], stats["status_note"]),
                         ("C244537", "C244538", "Cần rà soát"))
        # A page to check after the last row: the list may go on there, so its end is not known.
        stats = summarize_license_table(plain_list(columns, [("1", "A", "C244537")], 2, unresolved=[3]))
        self.assertEqual(stats["last_license_no"], "")

    def test_the_review_gets_the_lists_of_a_pdf_as_one(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path as P
        from src.pipeline import process_dossier_pdf
        extractor = LicenseTableExtractor()
        ocr, grid = make_page((50, HEADERS, [row(1, "A465211")]), (350, HEADERS, [row(1, "A465212")]))
        extractor.read_page(ocr, SIZE, grid, 1)
        self.assertEqual(len(extractor.tables), 2)
        cover = dict(document_type="cover", exam_date="01/06/2010", province_code="15", decision_date="",
                     decision_number="", metadata_review={})
        with TemporaryDirectory() as folder:
            pdf = P(folder, "scan.pdf")
            pdf.write_bytes(b"%PDF")
            with (patch("src.pipeline._pdf_cache_key", return_value=(str(pdf), 5, 5)),
                  patch("src.pipeline._cached_opening", return_value=(cover, 1, None)),
                  patch("src.pipeline._cached_tables", return_value=extractor.tables)):
                data = process_dossier_pdf(str(pdf), "15")
        table, = data["tables"]
        self.assertEqual([r["license_number"] for r in table["rows"]], ["A465211", "A465212"])
        self.assertEqual(data["proposed_filename"], "15.SQL.06.2010.A465211-A465212")


class LookupFieldsTest(unittest.TestCase):
    def test_names_are_stored_as_read_without_guessing_accents(self):
        from src.vietnamese_utils import clean_vietnamese_name
        cases = {
            "Nguyén Van Thanh": "Nguyén Van Thanh",   # not "Thành"
            "Me Van Nguyen": "Me Van Nguyen",         # not "Nguyễn"
            "  Lo   Van  Hoa ": "Lo Van Hoa",
            "(Ha Van Thuat": "Ha Van Thuat",
            "TRẦN THỊ BÍCH": "Trần Thị Bích",          # all capitals: only the letter case changes
            "Nguyễn Văn An": "Nguyễn Văn An",
            "": "",
        }
        self.assertEqual({raw: clean_vietnamese_name(raw) for raw in cases}, cases)

    def test_address_keeps_its_own_separator_before_the_province(self):
        from src.vietnamese_utils import normalize_vietnamese_address
        self.assertEqual(normalize_vietnamese_address("TTr Yen Binh - Huyen Yen Binh - Tinh Yen Bai"),
                         "TTr Yen Binh - Huyện Yen Binh - Tỉnh Yên Bái")
        self.assertEqual(normalize_vietnamese_address("H.Luc yen tinh Yen bai"), "H. Lục Yên, Tỉnh Yên Bái")
        self.assertEqual(normalize_vietnamese_address("X. La Pan Tan, Tinh Yen Bai"), "X. La Pan Tan, Tỉnh Yên Bái")

    def test_list_with_one_license_is_complete(self):
        from src.sequence_analyzer import analyze_license_sequences
        result = analyze_license_sequences(["AP014542"])
        self.assertEqual((result["sequence_summary"], result["status"]), ("AP014542", "Đủ"))
        self.assertEqual(analyze_license_sequences(["AP014543", "AP014542"])["status"], "Ngắt, không theo thứ tự")

    def test_missing_stt_column_reconstructed_from_sequential_codes_and_names(self):
        from src.table_extractor import _recover_missing_columns, table_citizens
        columns = [
            {"label": "TT B.Kê", "role": "register_index", "left": 0.05, "right": 0.25},
            {"label": "Họ và tên", "role": "full_name", "left": 0.25, "right": 0.65},
            {"label": "Năm sinh", "role": "birth_year", "left": 0.65, "right": 0.85},
        ]
        rows = [
            {"cells": ["69", "201117 Vu Thi Thanh", "1962"], "scores": [0.95, 0.95, 0.95],
             "bounds": [(0.05, 0.1, 0.25, 0.15), (0.25, 0.1, 0.65, 0.15), (0.65, 0.1, 0.85, 0.15)],
             "page_number": 7, "stt": None, "identity_confident": True},
            {"cells": ["70", "201118 Nguyen Htru Hai", "1978"], "scores": [0.95, 0.95, 0.95],
             "bounds": [(0.05, 0.15, 0.25, 0.2), (0.25, 0.15, 0.65, 0.2), (0.65, 0.15, 0.85, 0.2)],
             "page_number": 7, "stt": None, "identity_confident": True},
            {"cells": ["74", ":201122HaVanHai", "1980"], "scores": [0.95, 0.95, 0.95],
             "bounds": [(0.05, 0.2, 0.25, 0.25), (0.25, 0.2, 0.65, 0.25), (0.65, 0.2, 0.85, 0.25)],
             "page_number": 7, "stt": None, "identity_confident": True},
            {"cells": ["76 201124", "Ha Van Huan", "1987"], "scores": [0.95, 0.95, 0.95],
             "bounds": [(0.05, 0.25, 0.25, 0.3), (0.25, 0.25, 0.65, 0.3), (0.65, 0.25, 0.85, 0.3)],
             "page_number": 7, "stt": None, "identity_confident": True},
            {"cells": ["79", "201127TranMinh Quang", "1982"], "scores": [0.95, 0.95, 0.95],
             "bounds": [(0.05, 0.3, 0.25, 0.35), (0.25, 0.3, 0.65, 0.35), (0.65, 0.3, 0.85, 0.35)],
             "page_number": 7, "stt": None, "identity_confident": True},
            {"cells": ["80", "201128 Bui DuyTien", "1964"], "scores": [0.95, 0.95, 0.95],
             "bounds": [(0.05, 0.35, 0.25, 0.4), (0.25, 0.35, 0.65, 0.4), (0.65, 0.35, 0.85, 0.4)],
             "page_number": 7, "stt": None, "identity_confident": True},
        ]
        _recover_missing_columns(rows, columns)

        # 4 columns reconstructed
        self.assertEqual([c["role"] for c in columns], ["stt", "register_index", "full_name", "birth_year"])
        self.assertEqual([c["label"] for c in columns], ["STT", "TT B.Kê", "Họ và tên", "Năm sinh"])

        # STT numbers and register numbers extracted properly
        self.assertEqual([r["stt"] for r in rows], [69, 70, 74, 76, 79, 80])
        self.assertEqual([r["cells"][0] for r in rows], ["69", "70", "74", "76", "79", "80"])
        self.assertEqual([r["cells"][1] for r in rows], ["201117", "201118", "201122", "201124", "201127", "201128"])

        # Citizen names cleaned with CamelCase separated
        self.assertEqual([r["cells"][2] for r in rows], [
            "Vu Thi Thanh", "Nguyen Htru Hai", "Ha Van Hai", "Ha Van Huan", "Tran Minh Quang", "Bui Duy Tien"
        ])

        # Citizens projection works as expected
        table = {"columns": columns, "rows": rows}
        for r in rows:
            r["license_state"] = "unknown_column"
            r["license_number"] = ""
        citizens = table_citizens(table)
        self.assertEqual([c["stt"] for c in citizens], [69, 70, 74, 76, 79, 80])
        self.assertEqual([c["full_name"] for c in citizens], [
            "Vu Thi Thanh", "Nguyen Htru Hai", "Ha Van Hai", "Ha Van Huan", "Tran Minh Quang", "Bui Duy Tien"
        ])

    def test_missing_register_index_header_reconstructed(self):
        from src.table_extractor import _recover_missing_columns
        columns = [
            {"label": "STT", "role": "stt", "left": 0.05, "right": 0.15},
            {"label": "Họ và tên", "role": "full_name", "left": 0.15, "right": 0.65},
            {"label": "Năm sinh", "role": "birth_year", "left": 0.65, "right": 0.85},
        ]
        rows = [
            {"cells": ["1", "201117 Vu Thi Thanh", "1962"], "scores": [0.95, 0.95, 0.95],
             "bounds": [(0.05, 0.1, 0.15, 0.15), (0.15, 0.1, 0.65, 0.15), (0.65, 0.1, 0.85, 0.15)],
             "page_number": 1, "stt": 1, "identity_confident": True},
            {"cells": ["2", "201118 Nguyen Htru Hai", "1978"], "scores": [0.95, 0.95, 0.95],
             "bounds": [(0.05, 0.15, 0.15, 0.2), (0.15, 0.15, 0.65, 0.2), (0.65, 0.15, 0.85, 0.2)],
             "page_number": 1, "stt": 2, "identity_confident": True},
        ]
        _recover_missing_columns(rows, columns)
        self.assertEqual([c["role"] for c in columns], ["stt", "register_index", "full_name", "birth_year"])
        self.assertEqual([r["cells"][1] for r in rows], ["201117", "201118"])
        self.assertEqual([r["cells"][2] for r in rows], ["Vu Thi Thanh", "Nguyen Htru Hai"])


def ocr_row(cells, sure=True, page=5):
    width = len(cells)
    return {"cells": list(cells), "scores": [0.9] * width, "bounds": [(0, 0, 1, 1)] * width, "page_number": page,
            "stt": None, "identity_confident": sure}


class ColumnRecoveryReviewTest(unittest.TestCase):
    """Rows rebuilt from a list whose STT or TT B.Kê heading OCR missed (QD_000493, pages 4-7)."""

    NO_STT = [{"label": "TT B.Ke", "role": "register_index", "left": 0.0, "right": 0.14},
              {"label": "Ho va ten", "role": "full_name", "left": 0.14, "right": 0.24},
              {"label": "Nam sinh", "role": "birth_year", "left": 0.24, "right": 0.3}]
    BOTH = [{"label": "STT", "role": "stt", "left": 0.0, "right": 0.06},
            {"label": "TT B.Ke", "role": "register_index", "left": 0.06, "right": 0.14},
            {"label": "Ho va ten", "role": "full_name", "left": 0.14, "right": 0.24},
            {"label": "Nam sinh", "role": "birth_year", "left": 0.24, "right": 0.3}]

    def recover(self, columns, rows):
        from src.table_extractor import _recover_missing_columns
        columns = [dict(c) for c in columns]
        _recover_missing_columns(rows, columns)
        return [r["cells"][:3] for r in rows], [r["identity_confident"] for r in rows]

    def test_a_name_ocr_read_poorly_still_needs_review_after_the_split(self):
        rows = [ocr_row(["24", "201072 Nguyen Van Thang", "1980"]),
                ocr_row(["26", "201074 Ta Hong Cam", "1981"], sure=False),
                ocr_row(["27", "201075 Le Nhur Thong", "1982"])]
        cells, sure = self.recover(self.NO_STT, rows)
        self.assertEqual(cells[1], ["26", "201074", "Ta Hong Cam"])
        self.assertEqual(sure, [True, False, True])

        rows = [ocr_row(["1", "", "201117 Vu Thi Thanh", "1962"], sure=False),
                ocr_row(["2", "201118", "Nguyen Htru Hai", "1978"])]
        cells, sure = self.recover(self.BOTH, rows)
        self.assertEqual(cells[0], ["1", "201117", "Vu Thi Thanh"])
        self.assertEqual(sure, [False, True])

    def test_codes_after_a_stray_mark_or_before_a_slash_are_split(self):
        rows = [ocr_row(["12", "201060 Nguyén Ngoc Bich", "1975"]),
                ocr_row(["13", "I 201061 Nguyen Dang Khoa", "1976"]),
                ocr_row(["14", "201062/Vu Durc Cong", "1977"]),
                ocr_row(["15", "|201063 Phan Viet Khoa", "1978"])]
        cells, sure = self.recover(self.NO_STT, rows)
        self.assertEqual(cells[1:], [["13", "201061", "Nguyen Dang Khoa"], ["14", "201062", "Vu Durc Cong"],
                                     ["15", "201063", "Phan Viet Khoa"]])
        self.assertEqual(sure, [True] * 4)

    def test_a_family_name_caught_in_the_first_column_goes_back_to_the_name(self):
        rows = [ocr_row(["27", "201075 Le Nhur Thong", "1982"]),
                ocr_row(["28 201076 Tran Quy", "Quan", "1983"]),
                ocr_row(["201052 Nguyén", "Trurong Giang", "1981"]),
                ocr_row(["23 201071 /Vu Tien", "Thanh", "1979"]),
                ocr_row(["31", "201079 Hoang Van Phong", "1984"])]
        cells, sure = self.recover(self.NO_STT, rows)
        self.assertEqual(cells, [["27", "201075", "Le Nhur Thong"], ["28", "201076", "Tran Quy Quan"],
                                 ["", "201052", "Nguyén Trurong Giang"], ["23", "201071", "Vu Tien Thanh"],
                                 ["31", "201079", "Hoang Van Phong"]])
        # The machine guessed where these names start: they are shown for review.
        self.assertEqual(sure, [True, False, False, False, True])

        rows = [ocr_row(["61", "201109 Nguyén", "Manh Hung", "1970"]),
                ocr_row(["62", "201110", "Hoang Van Thuy", "1971"])]
        cells, sure = self.recover(self.BOTH, rows)
        self.assertEqual(cells, [["61", "201109", "Nguyén Manh Hung"], ["62", "201110", "Hoang Van Thuy"]])
        self.assertEqual(sure, [False, True])


def listed(stt, license_number, sure=True, page=2):
    return {"cells": [str(stt), f"Người {stt}", "1980", license_number], "page_number": page, "stt": stt,
            "identity_confident": sure, "license_number": license_number,
            "license_state": "valid" if license_number else "uncertain"}


def book_list(*rows, unresolved=None):
    columns = [{"label": "STT", "role": "stt"}, {"label": "Họ và tên", "role": "full_name"},
               {"label": "Năm sinh", "role": "birth_year"}, {"label": "Số GPLX", "role": "license_number"}]
    table = {"columns": columns, "rows": list(rows)}
    if unresolved:
        table["unresolved_pages"] = unresolved
    return table


class WholeBookSummaryTest(unittest.TestCase):
    """A PDF with several lists is one dossier: one name, one summary row, one Excel (a sheet per list)."""

    def test_name_range_and_count_span_every_list(self):
        from src.pipeline import summarize_license_tables
        stats = summarize_license_tables([book_list(listed(1, "C244537"), listed(2, "C244538")),
                                          book_list(listed(1, "C244539", page=5), listed(2, "C244540", page=5))])
        self.assertEqual((stats["first_license_no"], stats["last_license_no"], stats["total_licenses"]),
                         ("C244537", "C244540", 4))
        self.assertEqual((stats["status_note"], stats["table_review"]), ("Đủ", ""))

    def test_an_unclear_list_is_named_in_the_review_note(self):
        from src.pipeline import summarize_license_tables
        stats = summarize_license_tables([book_list(listed(1, "C244537")),
                                          book_list(listed(1, "C244538", page=10), unresolved=[11]),
                                          book_list(listed(1, "C244600", page=12), listed(2, "C244601", sure=False, page=12))])
        self.assertEqual((stats["first_license_no"], stats["last_license_no"]), ("C244537", "C244601"))
        self.assertEqual((stats["total_licenses"], stats["status_note"]), (4, "Cần rà soát"))
        self.assertEqual(stats["table_review"].splitlines(), [
            "Danh sách 2: Cần đối chiếu trang 11 để xác định danh sách có tiếp tục hay không.",
            "Danh sách 3: Có dòng chưa đọc rõ họ tên. Hãy đối chiếu số lượng GPLX."])

        stats = summarize_license_tables([book_list(listed(1, "C244537")),
                                          book_list(listed(1, "C244538", page=10), unresolved=[11])])
        self.assertEqual(stats["last_license_no"], "", "the last list may go on after page 10")

    def test_one_list_is_summarized_as_before(self):
        from src.pipeline import summarize_license_tables
        table = book_list(listed(1, "C244537"), listed(2, "C244538", sure=False))
        whole, single = summarize_license_tables([table]), summarize_license_table(table)
        self.assertEqual(whole, single)
        self.assertEqual(whole["table_review"], "Có dòng chưa đọc rõ họ tên. Hãy đối chiếu số lượng GPLX.")


WIDE = ("STT", "Họ và tên", "Năm sinh", "Nơi đăng ký hộ khẩu", "Quốc tịch", "Số giấy phép", "Hạng GPLX")
WIDE_EDGES = (25, 70, 230, 300, 520, 620, 780, 875)


def wide_page(records):
    """A typed list: each record is a list of OCR boxes (text, [(x0, x1) of each piece of ink]).

    One box may cover ink on both sides of a printed rule, as OCR reads a line across a cell border.
    """
    image = Image.new("L", SIZE, 255)
    draw = ImageDraw.Draw(image)
    start, step = 60, 38
    end = start + step * (len(records) + 1)
    for x in WIDE_EDGES:
        draw.line((x, start, x, end), fill=0, width=1)
    for i in range(len(records) + 2):
        draw.line((WIDE_EDGES[0], start + i * step, WIDE_EDGES[-1], start + i * step), fill=0, width=1)
    result = []
    lines = [[(label, [(WIDE_EDGES[c] + 6, WIDE_EDGES[c] + 6 + min(len(label) * 7, WIDE_EDGES[c + 1] - WIDE_EDGES[c] - 10))])
              for c, label in enumerate(WIDE)]] + records
    for i, boxes in enumerate(lines):
        y = start + i * step + 11
        for text, pieces in boxes:
            for x0, x1 in pieces:
                draw.rectangle((x0, y + 2, x1, y + 13), fill=0)  # the printed words
            x0, x1 = pieces[0][0], pieces[-1][1]
            result.append(([(x0, y), (x1, y), (x1, y + 16), (x0, y + 16)], text, .95))
    return result, measure_page_grid(image)


def cell(column, text):
    """A box inside one column."""
    x0 = WIDE_EDGES[column] + 6
    return text, [(x0, x0 + min(len(text) * 7, WIDE_EDGES[column + 1] - x0 - 4))]


class ShiftedCellsTest(unittest.TestCase):
    """Typed lists where OCR read one line across several cells (Năm sinh | Nơi ĐKHK, Quốc tịch | Số giấy phép | Hạng)."""

    def test_a_box_across_printed_rules_is_cut_at_the_rules(self):
        ocr, grid = wide_page([
            [cell(0, "1"), cell(1, "Hoàng Văn An"),
             ("1974 Xa Thinh Hung - Yen Binh", [(240, 270), (306, 330), (336, 440)]),
             ("Lao Cai ZZ", [(450, 500), (528, 548)])],
            [cell(0, "2"), cell(1, "Lê Thị Bình"), cell(2, "1980"), cell(3, "Xa Tan Nguyen"),
             ("Viet Nam AG982436 A1", [(528, 590), (628, 690), (788, 802)])],
        ])
        extractor = LicenseTableExtractor()
        extractor.read_page(ocr, SIZE, grid, 1)
        table, = extractor.tables
        self.assertEqual([c["role"] for c in table["columns"]],
                         ["stt", "full_name", "birth_year", "address", "nationality", "license_number", "license_class"])
        first, second = (r["cells"] for r in table["rows"])
        self.assertEqual(first[2:5], ["1974", "Xa Thinh Hung - Yen Binh Lao Cai", "ZZ"])
        self.assertEqual(second[4:], ["Viet Nam", "AG982436", "A1"])
        self.assertEqual((table["rows"][1]["license_number"], table["rows"][1]["license_state"]), ("AG982436", "valid"))

    def test_a_box_reaching_over_a_rule_without_ink_there_is_kept_whole(self):
        # The OCR box is wider than the words; only ink decides where the text is.
        ocr, grid = wide_page([[cell(0, "1"), ("Nguyễn Văn Thành Long", [(76, 226)]), cell(2, "1980"),
                                cell(3, "Xa Tan Nguyen"), cell(5, "AG982436")],
                               [cell(0, "2"), cell(1, "Lê Văn Bình"), cell(2, "1981"), cell(3, "Xa Tan Nguyen"),
                                cell(5, "AG982437")]])
        ocr[-9] = ([(76, 109), (300, 109), (300, 125), (76, 125)], "Nguyễn Văn Thành Long", .95)
        extractor = LicenseTableExtractor()
        extractor.read_page(ocr, SIZE, grid, 1)
        self.assertEqual(extractor.tables[0]["rows"][0]["cells"][1:3], ["Nguyễn Văn Thành Long", "1980"])

    COLUMNS = [{"label": label, "role": role, "left": i / 7, "right": (i + 1) / 7} for i, (label, role) in enumerate((
        ("STT", "stt"), ("Họ và tên", "full_name"), ("Năm sinh", "birth_year"), ("Nơi ĐKHK", "address"),
        ("Quốc tịch", "nationality"), ("Số giấy phép", "license_number"), ("Hạng GPLX", "license_class")))]

    def repair(self, *cells):
        from types import SimpleNamespace
        from src.table_extractor import _finish_rows
        rows = [ocr_row(c) for c in cells]
        _finish_rows(rows, [dict(c) for c in self.COLUMNS], SimpleNamespace(is_blank=lambda bounds: False))
        return rows

    def test_cells_shifted_into_the_next_column_go_back_by_what_they_hold(self):
        # Rows of the screenshot of 22/11/2026: the edges between columns did not match the printed cells.
        rows = self.repair(
            ["1", "Hoàng Văn A", "Bai", "1974 Xa ThinhHung -Huyen Yen Binh -Tinh Yen", "", "Viet Nam AG982435 Al", ""],
            ["2", "Lê Văn B", "Bai", "1985XaTanNguyen-Huyen Yen Binh -Tinh", "Viet Nam", "AG982436 A1", ""],
            ["5", "Hà Văn E", "1988 Bai", "Xa Yen Binh-Huyen Yen Binh -Tinh Yen", "", "Viet Nam AG982439 A1", ""],
            ["9", "Lò Văn I", "", "1985XaDeXuPhinh- Huyen Mu Cang Cha", "Viet Nam :", "AG983278A1", ""],
        )
        self.assertEqual([r["cells"][2:] for r in rows], [
            ["1974", "Xa ThinhHung -Huyen Yen Binh -Tinh Yen Bai", "Viet Nam", "AG982435", "A1"],
            ["1985", "XaTanNguyen-Huyen Yen Binh -Tinh Bai", "Viet Nam", "AG982436", "A1"],
            ["1988", "Xa Yen Binh-Huyen Yen Binh -Tinh Yen Bai", "Viet Nam", "AG982439", "A1"],
            ["1985", "XaDeXuPhinh- Huyen Mu Cang Cha", "Viet Nam", "AG983278", "A1"],
        ])
        self.assertEqual([r["license_state"] for r in rows], ["valid"] * 4)

    def test_cells_already_in_place_are_not_moved(self):
        rows = self.repair(
            ["1", "Hoàng Văn A", "1974", "1975 Hoang Hoa Tham - TP Yen Bai", "Viet Nam", "AB123456", "B2"],
            ["2", "Lê Văn B", "12/03/1980", "Xa Tan Nguyen", "Lào", "AG982436", ""],
            ["3", "Hà Văn C", "1981", "Xa Tan Nguyen", "", "A&9826", ""],
        )
        self.assertEqual([r["cells"][2:] for r in rows], [
            ["1974", "1975 Hoang Hoa Tham - TP Yen Bai", "Viet Nam", "AB123456", "B2"],
            ["12/03/1980", "Xa Tan Nguyen", "Lào", "AG982436", ""],
            ["1981", "Xa Tan Nguyen", "", "A&9826", ""],
        ])


def numbered(*cells):
    """A list of rows with only a GPLX column, as read: valid numbers and unclear ones."""
    from src.table_extractor import _license
    rows = []
    for text in cells:
        state, text = (text, "") if text in ("blank",) else ("valid" if _license(text) else "uncertain", text)
        rows.append({"cells": [text], "license_number": _license(text) if state == "valid" else "",
                     "license_state": state, "page_number": 1, "stt": None, "identity_confident": True})
    return {"columns": [{"label": "Số GPLX", "role": "license_number"}], "rows": rows}


class LicenseSuggestionTest(unittest.TestCase):
    """GPLX numbers of one list are usually consecutive: a number the neighbours fix is suggested."""

    def suggest(self, *cells, edited=()):
        from src.table_extractor import suggest_license_numbers
        table = numbered(*cells)
        for index in edited:
            table["rows"][index]["_edited"] = True
        return suggest_license_numbers(table)

    def test_numbers_read_wrong_between_consecutive_neighbours(self):
        self.assertEqual(self.suggest("AG982435", "AG98240", "AG982437", "4G982438", "AG982439", "AG982413",
                                      "AG982441", "AG982442", "A98244y"),
                         {1: "AG982436", 3: "AG982438", 5: "AG982440", 8: "AG982443"})

    def test_two_unclear_numbers_in_a_row_and_a_gap_that_does_not_fit(self):
        self.assertEqual(self.suggest("C244537", "C2445??", "C24453?", "C244540"), {1: "C244538", 2: "C244539"})
        self.assertEqual(self.suggest("C244537", "C2445??", "C24453?", "C244545"), {}, "the count does not fit")

    def test_numbers_next_to_a_break_follow_their_own_side(self):
        # Two lists of one PDF shown as one (sample 15.SQL.03.1996.C244337-C244498, pages 26 and 28).
        self.assertEqual(self.suggest("C244433", "C244434", "C244435 --", "C244436 --", "C244441", "C244442"),
                         {2: "C244435", 3: "C244436"})
        # Both sides fit as well: nothing is guessed. Else the closer one is suggested.
        self.assertEqual(self.suggest("C244433", "C244434", "C24443?", "C244437", "C244438"), {})
        self.assertEqual(self.suggest("C244433", "C244434", "C24443?", "C244445", "C244446"), {2: "C244435"})

    def test_a_number_read_clearly_is_not_replaced_from_one_side(self):
        from src.table_extractor import suggest_license_numbers
        # Sample 15.SQL.03.1996.C244337-C244498 p37-39: a list whose GPLX column was not found, and one
        # row holding two people's numbers, so counting rows is one off. The numbers read stay.
        table = numbered("C244476", "C244477", "C244335", "C244481", "C244482 C244483", "C244484", "C244485", "C244486")
        for row in table["rows"][3:6]:
            row.update(license_state="unknown_column", license_number="")
        self.assertEqual(suggest_license_numbers(table), {5: "C244484"})

    def test_real_breaks_blanks_and_checked_cells_are_left(self):
        self.assertEqual(self.suggest("C244537", "C244538", "C244600", "C244601"), {})
        self.assertEqual(self.suggest("C244537", "blank", "C244539"), {})
        self.assertEqual(self.suggest("C244537", "C24453B", "C244539", edited=(1,)), {})
        # One known number is not a sequence to follow.
        self.assertEqual(self.suggest("C244537", "C24453B"), {})
        # A number unlike the expected one at the end of a list is not guessed.
        self.assertEqual(self.suggest("C244537", "C244538", "Z1"), {})


if __name__ == "__main__":
    unittest.main()
