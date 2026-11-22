"""
Module for generating standardized Excel companion files for digitized driving license registers.
"""
import os
import json
from contextlib import contextmanager, nullcontext
from io import BytesIO
from tempfile import mkstemp
from typing import List, Dict, Any

import cv2
import numpy as np
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.comments import Comment
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from src.logger import get_logger
from src.pdf_processor import open_pdf, page_count, render_pdf_page
from src.table_extractor import table_citizens

WORKBOOK_METADATA = "_GPLX"
WORKBOOK_VERSION = "GPLX/3"
ROLE_ROW = 4
HEADER_ROW = 5
PAGE_ROLE = "_page_number"
REVIEW_ROLE = "_review"
LOOKUP_FIELDS = ("stt", "full_name", "birth_year", "nationality", "address", "license_number")
METADATA_FIELDS = (
    "province_code", "province_name", "book_type", "document_type", "dossier_group",
    "exam_date", "decision_date", "decision_number", "license_class", "course",
    "box", "box_number", "total_pages", "license_sequence", "status_note",
)
logger = get_logger(__name__)


def _generate_legacy_companion(
    dossier_meta: Dict[str, Any],
    citizens: List[Dict[str, Any]],
    output_path: str
) -> str:
    """
    Creates an Excel spreadsheet (.xlsx) mirroring the digitized PDF dossier.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Danh sách cấp GPLX"
    ws.views.sheetView[0].showGridLines = True

    # Styling definitions
    font_title = Font(name="Times New Roman", size=14, bold=True, color="002060")
    font_subtitle = Font(name="Times New Roman", size=11, italic=True)
    font_header = Font(name="Times New Roman", size=11, bold=True, color="FFFFFF")
    font_body = Font(name="Times New Roman", size=11)
    font_bold = Font(name="Times New Roman", size=11, bold=True)

    fill_header = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    fill_alt = PatternFill(start_color="F2F5F8", end_color="F2F5F8", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='BFBFBF'),
        right=Side(style='thin', color='BFBFBF'),
        top=Side(style='thin', color='BFBFBF'),
        bottom=Side(style='thin', color='BFBFBF')
    )

    # 1. Document Title
    ws.merge_cells("A1:G1")
    title_cell = ws["A1"]
    title_cell.value = "SỔ GỐC CẤP GIẤY PHÉP LÁI XE CƠ GIỚI ĐƯỜNG BỘ"
    title_cell.font = font_title
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    # 2. Metadata info rows
    p_name = dossier_meta.get("province_name", "Yên Bái")
    p_code = dossier_meta.get("province_code", "")
    hang = dossier_meta.get("license_class", "")
    khoa = dossier_meta.get("course", "")
    ngay_thi = dossier_meta.get("exam_date", "")
    dia_diem = dossier_meta.get("exam_location", "")
    so_dau = dossier_meta.get("first_license_no", "")
    so_cuoi = dossier_meta.get("last_license_no", "")

    ws.merge_cells("A2:G2")
    ws["A2"].value = f"Đơn vị: SỞ GIAO THÔNG VẬN TẢI {p_name.upper()} (Mã tỉnh: {p_code}) | Hạng: {hang} | Khóa: {khoa}"
    ws["A2"].font = font_subtitle
    ws["A2"].alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells("A3:G3")
    ws["A3"].value = f"Ngày thi: {ngay_thi} | Địa điểm: {dia_diem} | Dải số bằng: {so_dau} đến {so_cuoi}"
    ws["A3"].font = font_subtitle
    ws["A3"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[3].height = 20

    # 3. Table Column Headers
    headers = [
        ("STT", 6, "center"),
        ("Họ và tên", 26, "left"),
        ("Năm sinh", 12, "center"),
        ("Quốc tịch", 12, "center"),
        ("Nơi cư trú", 32, "left"),
        ("Số bằng", 16, "center"),
        ("Trang PDF", 12, "center")
    ]

    header_row = 5
    ws.row_dimensions[header_row].height = 24

    for col_idx, (col_name, col_width, col_align) in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_idx)
        cell.value = col_name
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = col_width

    # 4. Populate Citizen Data
    current_row = header_row + 1
    for idx, item in enumerate(citizens, start=1):
        ws.row_dimensions[current_row].height = 20
        is_alt = (current_row % 2 == 1)

        # STT luôn được render theo thứ tự lần lượt 1..n
        stt_val = item.get("stt")
        if not stt_val or not str(stt_val).isdigit() or int(stt_val) <= 0:
            stt_val = idx
        else:
            stt_val = int(stt_val)

        row_data = [
            (stt_val, "center", font_body),
            (item.get("full_name", "").strip(), "left", font_bold),
            (item.get("birth_year", "").strip(), "center", font_body),
            (item.get("nationality", "Việt Nam").strip(), "center", font_body),
            (item.get("address", "").strip(), "left", font_body),
            (item.get("license_number", "").strip(), "center", font_bold),
            (item.get("page_number", 1), "center", font_body)
        ]

        for col_idx, (val, align, font_style) in enumerate(row_data, start=1):
            cell = ws.cell(row=current_row, column=col_idx)
            _write_text(cell, val)
            cell.font = font_style
            cell.alignment = Alignment(horizontal=align, vertical="center")
            cell.border = thin_border
            if is_alt:
                cell.fill = fill_alt

        current_row += 1

    return _save_workbook(wb, output_path)


def _save_workbook(workbook, path):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temporary = mkstemp(prefix=".gplx-", suffix=".xlsx", dir=directory)
    os.close(fd)
    try:
        workbook.save(temporary)
        os.replace(temporary, path)
    finally:
        workbook.close()
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def _write_text(cell, value):
    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub("", value)
        if value:
            cell.value = value
            cell.data_type = "s"
            cell.number_format = "@"
    elif value is not None:
        cell.value = value


def _attach_note(cell, message):
    text = f"{cell.comment.text}\n{message}" if cell.comment else message
    cell.comment = Comment(text, "GPLX")


@contextmanager
def _render_cell_pages(pdf_path):
    """Keep at most one rendered source page open while exporting images."""
    image = None
    image_page = None
    with open_pdf(pdf_path) as pdf:
        total_pages = page_count(pdf)

        def get_page(number):
            nonlocal image, image_page
            if not 1 <= number <= total_pages:
                return None
            if image_page != number:
                if image is not None:
                    image.close()
                image, image_page = None, None
                image = render_pdf_page(pdf, number - 1)
                image_page = number
            return image

        try:
            yield get_page
        finally:
            if image is not None:
                image.close()


def _crop_media(image, bounds, role):
    """Return a contained image region, a verified blank, or a review state."""
    if image is None or not bounds or not all(0 <= value <= 1 for value in bounds):
        return "review", None
    x0, y0, x1, y1 = bounds
    left, top, right, bottom = (round(x0 * image.width), round(y0 * image.height),
                                 round(x1 * image.width), round(y1 * image.height))
    width, height = right - left, bottom - top
    if width < 20 or height < 24:
        return "review", None

    # Cut out the estimated printed border, then require a clean margin around the content.
    dx, dy = max(2, round(width * 0.025)), max(2, round(height * 0.025))
    with image.crop((left + dx, top + dy, right - dx, bottom - dy)) as box:
        with box.convert("RGB") as rgb:
            pixels = np.asarray(rgb)
            gray = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
            mask = gray < min(185, float(np.median(gray)) - 28)
            if role == "photo":
                mask |= pixels.max(axis=2) - pixels.min(axis=2) >= 36
            plane = mask.astype(np.uint8)
            rows, cols = plane.shape
            margin = max(2, round(min(rows, cols) * .03))
            # Remove isolated rules before closing can join them to a neighbouring photo.
            _, labels, stats, _ = cv2.connectedComponentsWithStats(plane, connectivity=8)
            for label, (x, y, w, h, _) in enumerate(stats[1:], 1):
                if ((w >= cols * .65 and h <= margin * 2 and (y < margin or y + h > rows - margin))
                        or (h >= rows * .65 and w <= margin * 2 and (x < margin or x + w > cols - margin))):
                    region = (slice(y, y + h), slice(x, x + w))
                    plane[region][labels[region] == label] = 0
            if role == "photo":
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, width // 18), max(3, height // 22)))
                plane = cv2.morphologyEx(plane, cv2.MORPH_CLOSE, kernel)
            stats = cv2.connectedComponentsWithStats(plane, connectivity=8)[2]
            marks = [tuple(map(int, mark)) for mark in stats[1:] if mark[4] >= max(5, plane.size * .0006)]
            if not marks:
                return "blank", None
            if any(x < margin or y < margin or x + w > cols - margin or y + h > rows - margin for x, y, w, h, _ in marks):
                return "review", None
            if role == "photo":
                x, y, w, h, area = max(marks, key=lambda item: item[4])
                if w < width * .30 or h < height * .35 or area < w * h * .32:
                    return "review", None
                if any(size > area * .35 for a, b, _, _, size in marks if not (x <= a < x + w and y <= b < y + h)):
                    return "review", None
                region = (x, y, x + w, y + h)
            else:
                region = (min(m[0] for m in marks), min(m[1] for m in marks),
                          max(m[0] + m[2] for m in marks), max(m[1] + m[3] for m in marks))
                if region[2] - region[0] < width * .12 or region[3] - region[1] < height * .12:
                    return "review", None
            x, y, x_end, y_end = region
            return "embedded", rgb.crop((x - 1, y - 1, x_end + 1, y_end + 1))


def _add_media(ws, cell, role, source_row, bounds, get_page):
    page = source_row["page_number"]
    result, crop = "review", None
    if get_page and source_row.get("identity_confident"):
        try:
            result, crop = _crop_media(get_page(page), bounds, role)
        except Exception:
            logger.warning("Could not verify %s crop at PDF page %s", role, page, exc_info=True)
    if result == "embedded":
        with crop:
            crop.thumbnail((140, 100))
            buffer = BytesIO()
            crop.save(buffer, "PNG")
        buffer.seek(0)
        graphic = ExcelImage(buffer)
        ws.add_image(graphic, cell.coordinate)
        ws.row_dimensions[cell.row].height = max(ws.row_dimensions[cell.row].height or 20, graphic.height * .75 + 3)
    elif result == "review" or cell.value:
        _attach_note(cell, f"Cần đối chiếu {'ảnh' if role == 'photo' else 'chữ ký'} ở trang PDF {page}.")


def _row_values(row, roles, baseline, reviewed):
    values = list(row["cells"])
    extra = {}
    for field in LOOKUP_FIELDS:
        positions = [i for i, role in enumerate(roles) if role == field]
        value = reviewed.get(field, baseline.get(field))
        if value != baseline.get(field):
            if len(positions) == 1:
                values[positions[0]] = str(value) if value is not None else ""
            else:
                extra[field] = value
    if (row.get("license_state") == "uncertain"
            and reviewed.get("license_number", baseline.get("license_number")) == baseline.get("license_number")
            and roles.count("license_number") == 1):
        index = roles.index("license_number")
        extra["_blocked_license"] = values[index]
    return values, extra


def _write_source_list(ws, table, reviewed, dossier_meta, get_page):
    roles = [column["role"] for column in table["columns"]]
    labels = [column["label"] for column in table["columns"]]
    page_col, review_col = len(labels) + 1, len(labels) + 2
    for row, text in enumerate((
        dossier_meta.get("book_type") or "DANH SÁCH CẤP GIẤY PHÉP LÁI XE",
        f"Mã tỉnh: {dossier_meta.get('province_code', '')}  |  Hạng: {dossier_meta.get('license_class', '')}  |  Khóa: {dossier_meta.get('course', '')}",
        f"Ngày thi/sát hạch: {dossier_meta.get('exam_date', '')}  |  Quyết định: {dossier_meta.get('decision_number', '')}"
        f"  |  Ngày ký: {dossier_meta.get('decision_date', '')}",
    ), 1):
        if page_col > 1:
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=page_col)
        cell = ws.cell(row, 1)
        _write_text(cell, text)
        cell.font = Font(bold=row == 1, size=14 if row == 1 else 11)
    if table.get("unresolved_pages"):
        _attach_note(ws["A3"], "Cần rà soát trang PDF: " + ", ".join(map(str, table["unresolved_pages"])))

    ws.freeze_panes = "A6"
    ws.row_dimensions[ROLE_ROW].hidden = True
    ws.column_dimensions[get_column_letter(review_col)].hidden = True
    ws.auto_filter.ref = f"A{HEADER_ROW}:{get_column_letter(review_col)}{HEADER_ROW + len(table['rows'])}"
    for index, (label, role) in enumerate(zip([*labels, "Trang PDF", "_GPLX"], [*roles, PAGE_ROLE, REVIEW_ROLE]), 1):
        _write_text(ws.cell(ROLE_ROW, index), role)
        heading = ws.cell(HEADER_ROW, index)
        _write_text(heading, label)
        heading.font = Font(bold=True, color="FFFFFF")
        heading.fill = PatternFill("solid", fgColor="1F497D")
        heading.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(index)].width = {
            "address": 38, "full_name": 28, "photo": 22, "signature": 22,
        }.get(role, max(12, min(28, len(label) + 2)))
    ws.row_dimensions[HEADER_ROW].height = 28

    for index, (row, baseline, citizen) in enumerate(zip(table["rows"], table_citizens(table), reviewed), HEADER_ROW + 1):
        values, extra = _row_values(row, roles, baseline, citizen)
        ws.row_dimensions[index].height = 20
        for col, (value, role) in enumerate(zip(values, roles), 1):
            cell = ws.cell(index, col)
            _write_text(cell, value)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if role in ("photo", "signature"):
                bounds = row.get("bounds", [])
                _add_media(ws, cell, role, row, bounds[col - 1] if col <= len(bounds) else None, get_page)
            elif ((role == "license_number" and "_blocked_license" in extra)
                  or (role == "full_name" and not row.get("identity_confident") and value == row["cells"][col - 1])
                  or (value and role != "license_number" and col <= len(row.get("scores", []))
                      and row["scores"][col - 1] < .65 and value == row["cells"][col - 1])):
                _attach_note(cell, f"Cần đối chiếu nội dung ở trang PDF {row['page_number']}.")
        page = ws.cell(index, page_col, row["page_number"])
        if row.get("license_state") == "unknown_column" and not citizen.get("license_number"):
            _attach_note(page, "Chưa xác định được cột số GPLX trong danh sách này.")
        if extra:
            _write_text(ws.cell(index, review_col), json.dumps(extra, ensure_ascii=False))


def generate_excel_companion(dossier_meta, citizens, output_path, *, source_tables=None, pdf_path=None):
    """Export the original columns, with explicitly reviewed corrections and page provenance."""
    if source_tables is None:
        return _generate_legacy_companion(dossier_meta, citizens, output_path)
    tables = source_tables or [{"columns": [], "rows": []}]
    if sum(len(table["rows"]) for table in tables) != len(citizens):
        raise ValueError("Số dòng đã duyệt không khớp bảng nguồn. Hãy đọc lại hồ sơ trước khi xuất Excel.")
    workbook = Workbook()
    use_images = pdf_path and any(c["role"] in ("photo", "signature") for table in tables for c in table["columns"])
    with (_render_cell_pages(pdf_path) if use_images else nullcontext(None)) as get_page:
        start = 0
        for index, table in enumerate(tables, 1):
            ws = workbook.active if index == 1 else workbook.create_sheet()
            ws.title = f"Danh sách GPLX {index}"
            end = start + len(table["rows"])
            _write_source_list(ws, table, citizens[start:end], dossier_meta, get_page)
            start = end
    metadata = workbook.create_sheet(WORKBOOK_METADATA)
    _write_text(metadata["A1"], WORKBOOK_VERSION)
    for index, field in enumerate(METADATA_FIELDS, 2):
        _write_text(metadata.cell(index, 1), field)
        _write_text(metadata.cell(index, 2), dossier_meta.get(field))
    metadata.sheet_state = "hidden"
    return _save_workbook(workbook, output_path)
