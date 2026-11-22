import unittest
from unittest.mock import patch

from src.cover_parser import parse_cover_ocr, parse_cover_page_text
from src.pipeline import _read_opening_page


DECISION = """UBND TỈNH YÊN BÁI
Số: 368/QĐ-SGTVT
Yên Bái, ngày 25 tháng 9 năm 2015
QUYẾT ĐỊNH
Căn cứ Quyết định số 1422/QĐ-UBND ngày 22/09/2009
Căn cứ biên bản và kết quả sát hạch ngày 15/09/2015
Điều 1. Công nhận trúng tuyển hạng A1 khóa P59
"""


class DocumentMetadataV3Test(unittest.TestCase):
    def test_cover_and_field_provenance(self):
        result = parse_cover_page_text(
            "SỞ GIAO THÔNG VẬN TẢI YÊN BÁI\nSỔ GỐC\nHẠNG: A1  KHÓA: 26\nNGÀY THI: 29 - 03 - 1996",
            page_number=2,
        )
        self.assertEqual(result["document_type"], "cover")
        self.assertEqual(result["exam_date"], "29-03-1996")
        self.assertEqual(result["license_class"], "A1")
        self.assertEqual(result["course"], "26")
        self.assertEqual(result["metadata_pages"]["exam_date"], 2)

    def test_decision_keeps_exam_and_signed_dates_separate(self):
        result = parse_cover_page_text(DECISION)
        self.assertEqual(result["document_type"], "decision")
        self.assertEqual(result["exam_date"], "15-09-2015")
        self.assertEqual(result["decision_date"], "25-09-2015")
        self.assertEqual(result["decision_number"], "368/QĐ-SGTVT")
        self.assertEqual(result["province_code"], "15")
        self.assertEqual(result["metadata_review"], {})

    def test_citation_does_not_supply_missing_signed_date(self):
        result = parse_cover_page_text(DECISION.replace("Yên Bái, ngày 25 tháng 9 năm 2015\n", ""))
        self.assertEqual(result["decision_date"], "")
        self.assertIn("decision_date", result["metadata_review"])
        self.assertEqual(result["exam_date"], "15-09-2015")

    def test_attached_list_with_incomplete_year(self):
        result = parse_cover_page_text(
            "DANH SÁCH THÍ SINH TRÚNG TUYỂN ĐƯỢC CẤP GIẤY PHÉP LÁI XE\n"
            "Hạng A1 Ngày thi: 10/06/2010\n"
            "Kèm theo QĐ số: 71/QĐ-SGTVT, ngày 16 tháng 6 năm 200 của Sở GTVT Yên Bái\n"
        )
        self.assertEqual(result["document_type"], "decision_with_list")
        self.assertEqual(result["decision_number"], "71/QĐ-SGTVT")
        self.assertEqual(result["exam_date"], "10-06-2010")
        self.assertEqual(result["decision_date"], "")
        self.assertIn("decision_date", result["metadata_review"])

    def test_low_confidence_decision_number_goes_to_review(self):
        def box(x, y, text, score=0.94):
            return ([(x, y), (x + 20, y), (x + 20, y + 8), (x, y + 8)], text, score)

        boxes = [
            box(100, 55, "UBND TỈNH YÊN BÁI"),
            box(100, 130, "S6: 11 /QD- SGTVT", 0.78),
            box(450, 131, "Yên Bái, ngày 16 tháng 6 năm 2010"),
            box(300, 160, "QUYET DINH"),
            box(110, 400, "Xét biên bản và kết quả sát hạch ngày 10 tháng 6 năm 2010"),
        ]
        result = parse_cover_ocr(boxes[::-1], 1000)
        self.assertEqual(result["document_type"], "decision")
        self.assertEqual(result["decision_number"], "")
        self.assertIn("decision_number", result["metadata_review"])
        self.assertEqual(result["decision_date"], "16-06-2010")
        self.assertEqual(result["exam_date"], "10-06-2010")

    def test_implausible_dates_are_left_blank_for_review(self):
        future = parse_cover_page_text("SỔ GỐC\nHẠNG: A1\nNGÀY THI: 29 - 03 - 2096")
        self.assertEqual(future["exam_date"], "")
        self.assertIn("không hợp lý", future["metadata_review"]["exam_date"])
        early = parse_cover_page_text("SỔ GỐC\nHẠNG: A1\nNGÀY THI: 29 - 03 - 1906")
        self.assertEqual((early["exam_date"], early["year"]), ("", ""))
        self.assertIn("29-03-1906", early["metadata_review"]["exam_date"])

    def test_signed_before_exam_leaves_both_dates_blank(self):
        # "2015" read as "2014" in the signing date: the decision would predate the exam.
        result = parse_cover_page_text(DECISION.replace("năm 2015", "năm 2014"))
        self.assertEqual((result["exam_date"], result["decision_date"]), ("", ""))
        self.assertIn("trước ngày thi", result["metadata_review"]["exam_date"])
        self.assertIn("trước ngày thi", result["metadata_review"]["decision_date"])
        self.assertEqual(result["decision_number"], "368/QĐ-SGTVT")

    def test_date_read_with_very_low_confidence_is_left_blank(self):
        def box(x, y, text, score=0.94):
            return ([(x, y), (x + 20, y), (x + 20, y + 8), (x, y + 8)], text, score)

        boxes = [
            box(100, 55, "UBND TỈNH YÊN BÁI"),
            box(100, 130, "Số: 11/QĐ-SGTVT"),
            box(450, 131, "Yên Bái, ngày 16 tháng 6 năm 2010", 0.42),
            box(300, 160, "QUYET DINH"),
            box(110, 400, "Xét biên bản và kết quả sát hạch ngày 10 tháng 6 năm 2010"),
        ]
        result = parse_cover_ocr(boxes, 1000)
        self.assertEqual(result["decision_date"], "")
        self.assertIn("đọc mờ", result["metadata_review"]["decision_date"])
        self.assertEqual(result["exam_date"], "10-06-2010")  # clear text on its own line is kept

    def test_1996_cover_with_joined_label_and_overlapping_day_box(self):
        # OCR of HO SO 116 (1996): "NGAYTHI:" without a space; the handwritten "29" box overlaps
        # "9.-.03-.1996", which repeats its last digit.
        def box(x0, x1, y, text, score=0.80):
            return ([(x0, y), (x1, y), (x1, y + 20), (x0, y + 20)], text, score)

        boxes = [
            box(380, 870, 120, "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"),
            box(460, 870, 240, "SỞ GIAO THÔNG VẬN TẢI YÊN BÁI"),
            box(500, 760, 370, "SỔ GỐC"),
            box(380, 880, 450, "CẤP BẰNG LÁI XE CƠ GIỚI ĐB"),
            box(300, 380, 600, "HANG:"),
            box(470, 520, 595, "A1"),
            box(660, 745, 598, "KHOA:."),
            box(780, 820, 592, "26"),
            box(300, 413, 631, "NGAYTHI:"),
            box(566, 707, 631, "9.-.03-.1996", .63),
            box(544, 577, 633, "29", .59),
            box(297, 793, 662, "DIA Diem THI....m...THUY...DEen...ThHA...BA", .55),
        ]
        result = parse_cover_ocr(boxes, 820)
        self.assertEqual(result["document_type"], "cover")
        self.assertEqual(result["exam_date"], "29-03-1996")
        self.assertEqual((result["license_class"], result["course"]), ("A1", "26"))
        # Separate boxes that only touch are not merged.
        boxes[-3:-1] = [box(566, 707, 631, "03-1996", .63), box(520, 560, 633, "29", .59)]
        self.assertEqual(parse_cover_ocr(boxes, 820)["exam_date"], "")

    def test_usable_text_layer_needs_no_ocr_for_metadata(self):
        with patch("src.pipeline.read_pdf_page_text", return_value=DECISION), patch("src.pipeline._read_page_ocr") as ocr:
            result, opening_ocr = _read_opening_page(object())
        self.assertEqual(result["decision_number"], "368/QĐ-SGTVT")
        self.assertIsNone(opening_ocr)
        ocr.assert_not_called()


if __name__ == "__main__":
    unittest.main()
