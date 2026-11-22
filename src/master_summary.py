"""
Module for managing and updating the Province Master Summary Excel file:
'SỔ THEO DÕI, RÀ SOÁT DÃY SỐ GPLX TRONG SỔ GỐC'
"""
import os
import re
import socket
import time
from contextlib import contextmanager
from datetime import date, datetime
from tempfile import mkstemp
from threading import RLock
from typing import Dict, Any
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

# Layout of the reference workbook "File tổng soát số hóa GPLX.xlsx".
TITLE = "SỔ THEO DÕI, RÀ SOÁT DÃY SỐ GPLX TRONG SỔ GỐC"
SHEET_NAME = "DANH SACH SO GOC"
LEGACY_SHEET_NAME = "Theo dõi dãy số GPLX"
TABLE_NAME = "SoGocTongHop"
HEADER_ROW = 2
FIRST_DATA_ROW = 3
HEADERS = [
    ("STT", 5.75),
    ("Loại sổ", 21.5),
    ("Ngày tại bìa sổ", 12.83),
    ("Tên file PDF", 21.5),
    ("HỘP", 8.91),
    ("HỘP SỐ", 9.83),
    ("Hạng", 9),
    ("Tổng số lượng GPLX", 11),
    ("Số GPLX trong file", 56),
    ("Tổng số trang PDF", 10.58),
    ("Ghi chú / nhận định", 20.83),
    ("Ngày cập nhật", 15),
]
_LAST_COLUMN = get_column_letter(len(HEADERS))
_DATE_FORMAT = "dd/mm/yyyy"
_DATETIME_FORMAT = "dd/mm/yyyy hh:mm"
_FONT = "Times New Roman"
_THIN = Side(style="thin", color="000000")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)

_SUMMARY_LOCK = RLock()
_RENAME_SHEET = "_GPLX_Rename"
# Several machines save into the same summary on the host's share.
LOCK_WAIT_SECONDS = 15
LOCK_STALE_SECONDS = 120


class SummaryBusyError(OSError):
    pass


def _new_summary_workbook():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET_NAME

    ws.merge_cells(f"A1:{_LAST_COLUMN}1")
    title_cell = ws["A1"]
    title_cell.value = TITLE
    title_cell.font = Font(name=_FONT, size=17, bold=True, color="FFFFFF")
    title_cell.fill = PatternFill("solid", fgColor="17324F")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 36

    ws.row_dimensions[HEADER_ROW].height = 44
    for col_idx, (col_name, col_width) in enumerate(HEADERS, start=1):
        cell = ws.cell(row=HEADER_ROW, column=col_idx, value=col_name)
        cell.font = Font(name=_FONT, size=11, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="0D766E")
        cell.alignment = _CENTER
        cell.border = _BORDER
        ws.column_dimensions[get_column_letter(col_idx)].width = col_width

    ws.freeze_panes = f"B{FIRST_DATA_ROW}"
    _sync_table(ws, FIRST_DATA_ROW)
    return wb


def _file_stamp(path):
    try:
        stat = os.stat(path)
        return stat.st_size, stat.st_mtime_ns
    except FileNotFoundError:
        return None


def lock_path(path):
    directory, name = os.path.split(os.path.abspath(path))
    return os.path.join(directory, f".{name}.lock")


@contextmanager
def _machine_lock(path, wait=None):
    """Exclusive lock file next to the summary, shared by every machine using the folder."""
    lock = lock_path(path)
    os.makedirs(os.path.dirname(lock), exist_ok=True)
    deadline = time.monotonic() + (LOCK_WAIT_SECONDS if wait is None else wait)
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - os.stat(lock).st_mtime > LOCK_STALE_SECONDS:
                    os.unlink(lock)  # left by a machine that stopped while saving
                    continue
            except FileNotFoundError:
                continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                owner = ""
                try:
                    with open(lock, encoding="utf-8", errors="replace") as handle:
                        owner = handle.read(200).strip()
                except OSError:
                    pass
                raise SummaryBusyError(
                    f"Máy khác đang ghi sổ {os.path.basename(path)}{f' ({owner})' if owner else ''}. "
                    "Hãy đợi vài giây rồi xác nhận lại."
                )
            time.sleep(0.3)
    try:
        os.write(fd, f"{socket.gethostname()} {time.strftime('%d/%m/%Y %H:%M:%S')}".encode("utf-8"))
    finally:
        os.close(fd)
    try:
        yield
    finally:
        try:
            os.unlink(lock)
        except OSError:
            pass


@contextmanager
def edit_master_summary(path):
    """Publish a complete workbook in one replacement so a locked file stays intact."""
    directory = os.path.dirname(os.path.abspath(path))
    with _SUMMARY_LOCK, _machine_lock(path):
        stamp = _file_stamp(path)
        workbook = openpyxl.load_workbook(path) if stamp is not None else _new_summary_workbook()
        try:
            yield workbook
            os.makedirs(directory, exist_ok=True)
            fd, temporary = mkstemp(prefix=".gplx-", suffix=".xlsx", dir=directory)
            os.close(fd)
            try:
                workbook.save(temporary)
                if _file_stamp(path) != stamp:
                    raise OSError(f"Sổ tổng hợp đã thay đổi khi đang lưu: {os.path.basename(path)}. Hãy thử lại.")
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        finally:
            workbook.close()


def init_master_summary_file(file_path: str, province_name: str = "Tỉnh"):
    """Creates a new formatted Master Summary Excel file."""
    workbook = _new_summary_workbook()
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    workbook.save(file_path)
    return workbook


def _filename_key(name):
    return str(name or "").strip().casefold().removesuffix(".pdf")


def _summary_sheet(workbook):
    for name in (SHEET_NAME, LEGACY_SHEET_NAME):
        if name in workbook.sheetnames:
            return workbook[name]
    return next(sheet for sheet in workbook.worksheets if sheet.sheet_state == "visible")


def _is_data_row(ws, row):
    # Column A alone does not make a record; blank separator rows may keep their borders or STT.
    return any(ws.cell(row, col).value not in (None, "") for col in range(2, len(HEADERS) + 1))


def _last_data_row(ws):
    """Rows below the table can carry formatting only, so max_row is not the end of the data."""
    for row in range(ws.max_row, FIRST_DATA_ROW - 1, -1):
        if _is_data_row(ws, row):
            return row
    return FIRST_DATA_ROW - 1


def _renumber(ws):
    """STT follows the records from top to bottom, skipping separator rows."""
    number = 0
    for row in range(FIRST_DATA_ROW, _last_data_row(ws) + 1):
        if _is_data_row(ws, row):
            number += 1
            ws.cell(row, 1).value = number


def _headers_match(ws):
    return all(
        str(ws.cell(HEADER_ROW, col).value or "").strip() == name
        for col, (name, _) in enumerate(HEADERS, start=1)
    )


def _sync_table(ws, last_row):
    """Extend the summary's Excel table to the last record, creating it when the layout matches."""
    ref = f"A{HEADER_ROW}:{_LAST_COLUMN}{max(last_row, FIRST_DATA_ROW)}"
    for table in ws.tables.values():
        if table.ref.split(":")[0] == f"A{HEADER_ROW}":
            table.ref = ref
            if table.autoFilter is not None:
                table.autoFilter.ref = ref
            return
    if ws.tables or not _headers_match(ws):
        return
    workbook = ws.parent
    used = {name for sheet in workbook.worksheets for name in sheet.tables}
    name = TABLE_NAME
    suffix = 1
    while name in used:
        suffix += 1
        name = f"{TABLE_NAME}{suffix}"
    # Excel table column names must equal the header cells exactly, including stray spaces.
    for col in range(1, len(HEADERS) + 1):
        cell = ws.cell(HEADER_ROW, col)
        cell.value = str(cell.value)
    table = Table(displayName=name, ref=ref)
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(table)


def _as_date(value):
    if isinstance(value, (date, datetime)):
        return value
    match = re.fullmatch(r"\s*([0-9]{1,2})\s*[-/.]\s*([0-9]{1,2})\s*[-/.]\s*([0-9]{4})\s*", str(value or ""))
    if match:
        day, month, year = map(int, match.groups())
        try:
            return datetime(year, month, day)
        except ValueError:
            pass
    return value


def _as_number(value):
    """Store plain box numbers as numbers like the reference workbook; keep codes such as '01' as text."""
    if isinstance(value, str):
        text = value.strip()
        if text.isascii() and text.isdigit() and (len(text) == 1 or not text.startswith("0")):
            return int(text)
        return text
    return value


def summary_rows_by_name(workbook):
    worksheet = _summary_sheet(workbook)
    rows = {}
    if worksheet.max_row >= 3:
        for row, (value,) in enumerate(worksheet.iter_rows(min_row=3, min_col=4, max_col=4, values_only=True), 3):
            if key := _filename_key(value):
                rows.setdefault(key, []).append(row)
    return rows


def _date_text(value):
    if isinstance(value, (datetime, date)):
        return value.strftime("%d/%m/%Y")
    return str(value or "").strip()


def read_summary_entries(workbook):
    """Summary rows as {field: value}, one per dossier name; names listed twice are left out."""
    worksheet = _summary_sheet(workbook)
    entries, seen = {}, set()
    for values in worksheet.iter_rows(min_row=FIRST_DATA_ROW, max_col=len(HEADERS), values_only=True):
        values = (*values, *[None] * (len(HEADERS) - len(values)))
        key = _filename_key(values[3])
        if not key:
            continue
        if key in seen:
            entries.pop(key, None)
            continue
        seen.add(key)
        total = values[7]
        entries[key] = {
            "pdf_filename": str(values[3]).strip().removesuffix(".pdf").removesuffix(".PDF"),
            "book_type": str(values[1] or "").strip(),
            "cover_date": _date_text(values[2]),
            "box": str(values[4] if values[4] is not None else "").strip(),
            "box_number": str(values[5] if values[5] is not None else "").strip(),
            "license_class": str(values[6] or "").strip(),
            "total_licenses": total if isinstance(total, int) else
            int(total) if isinstance(total, str) and total.strip().isdigit() else None,
            "license_sequence": str(values[8] or "").strip(),
            "total_pages": values[9] if isinstance(values[9], int) and values[9] > 0 else 1,
            "status_note": str(values[10] or "").strip(),
        }
    return list(entries.values())


def read_rename_records(workbook):
    if _RENAME_SHEET not in workbook.sheetnames:
        return []
    return [
        (filename, source, target)
        for filename, source, target in workbook[_RENAME_SHEET].iter_rows(min_row=2, max_col=3, values_only=True)
        if all(isinstance(value, str) and value for value in (filename, source, target))
    ]


def _norm(path):
    return os.path.normcase(os.path.normpath(path))


_RENAME_HEADERS = ("Tên file", "PDF nguồn", "PDF đích", "Nhóm hồ sơ", "Ngày thi")


def _rename_sheet(workbook):
    if _RENAME_SHEET not in workbook.sheetnames:
        links = workbook.create_sheet(_RENAME_SHEET)
        links.sheet_state = "hidden"
        links.append(_RENAME_HEADERS)
    links = workbook[_RENAME_SHEET]
    for column, header in enumerate(_RENAME_HEADERS, 1):
        if links.cell(1, column).value in (None, ""):
            links.cell(1, column, header)  # sheets written by older versions have 3 columns
    return links


def read_rename_details(workbook):
    """{dossier name key: (group, exam date)}; empty strings for records of older versions.

    A QĐTT summary row shows the signing date, so its exam date is kept here.
    """
    if _RENAME_SHEET not in workbook.sheetnames:
        return {}
    details = {}
    for name, _source, _target, group, exam in workbook[_RENAME_SHEET].iter_rows(min_row=2, max_col=5, values_only=True):
        if isinstance(name, str) and name.strip():
            details[_filename_key(name)] = (str(group or "").strip(), str(exam or "").strip())
    return details


def register_dossier_name(workbook, filename, current, target, *, same_file=None, group="", exam_date=""):
    """Claim filename for the PDF at current (relative to the province folder), renamed to target.

    The rename sheet keeps one record per dossier: its name, the original scan file and the
    current PDF. A PDF saved before keeps its record, so saving it again under another name
    renames the record instead of claiming a second one. Returns the name the dossier had
    before (None for a new dossier), so its summary row can be updated in place.

    same_file(saved target) tells whether the PDF at current is a copy of a PDF saved from the
    same scan name (left by older versions, which copied instead of renaming). Without it any
    PDF at a saved scan's path is refused; with it a new scan reusing that name is a new dossier.
    """
    wanted = _filename_key(filename)
    rows = summary_rows_by_name(workbook)
    current_key, target_key = _norm(current), _norm(target)
    links = _rename_sheet(workbook)
    records = [
        (row, name, source, dest)
        for row, (name, source, dest) in enumerate(links.iter_rows(min_row=2, max_col=3, values_only=True), 2)
        if all(isinstance(value, str) and value for value in (name, source, dest))
    ]
    own = next((record for record in records if _norm(record[3]) == current_key), None)
    previous = own[1] if own else None
    if own is None:
        # Saved by an older version (no record yet): the PDF already carries its summary name.
        stem = _filename_key(os.path.splitext(os.path.basename(current))[0])
        if len(rows.get(stem, [])) == 1 and not any(_filename_key(r[1]) == stem for r in records):
            previous = os.path.splitext(os.path.basename(current))[0]
        moved = next((r for r in records if _norm(r[2]) == current_key and _norm(r[3]) != current_key
                      and (same_file is None or same_file(r[3]))), None)
        if moved is not None:
            raise FileExistsError(f"PDF này đã được lưu thành {os.path.basename(moved[3])} trước đây.")
    if any(_filename_key(r[1]) == wanted for r in records if r is not own):
        raise FileExistsError(f"Sổ tổng hợp đã có tên {filename}.pdf cho hồ sơ khác. Hãy chọn tên khác.")
    claimed = rows.get(wanted, [])
    if len(claimed) > 1 or (claimed and _filename_key(previous) != wanted):
        raise FileExistsError(f"Sổ tổng hợp đã có tên {filename}.pdf cho hồ sơ khác hoặc chưa rõ nguồn. Hãy chọn tên khác.")
    if own is not None:
        row = own[0]
        values = (filename, own[2], target, group, exam_date)
    else:
        row = links.max_row + 1
        values = (filename, current, target, group, exam_date)
    for index, value in enumerate(values, 1):
        links.cell(row, index, value).data_type = "s"
    return previous


def record_folder_rename(workbook, filename, source, target):
    """Backward-compatible wrapper: True when the PDF was already saved under filename."""
    return _filename_key(register_dossier_name(workbook, filename, source, target)) == _filename_key(filename)


def write_summary_entry(workbook, record: Dict[str, Any], previous_filename=None) -> None:
    ws = _summary_sheet(workbook)

    pdf_filename = record.get("pdf_filename", "")

    names = summary_rows_by_name(workbook)
    rows = names.get(_filename_key(pdf_filename), [])
    if not rows and previous_filename:
        rows = names.get(_filename_key(previous_filename), [])
    target_row = rows[0] if rows else None

    is_new = (target_row is None)
    if is_new:
        # Append right after the last record; formatted empty rows below the table do not count.
        target_row = _last_data_row(ws) + 1

    row_values = [
        None,  # STT is renumbered below.
        record.get("book_type", "Sổ gốc cấp bằng lái xe cơ giới đường bộ"),
        _as_date(record.get("cover_date", "")),
        pdf_filename,
        _as_number(record.get("box", "")),
        _as_number(record.get("box_number", "")),
        record.get("license_class", ""),
        record.get("total_licenses", 0),
        record.get("license_sequence", ""),
        record.get("total_pages", 1),
        record.get("status_note", ""),
        datetime.now().replace(second=0, microsecond=0),
    ]

    if is_new:
        ws.row_dimensions[target_row].height = 28
    for col_idx, val in enumerate(row_values, start=1):
        cell = ws.cell(row=target_row, column=col_idx)
        if col_idx > 1:
            cell.value = val
            if isinstance(val, str):
                cell.data_type = "s"
        if isinstance(val, datetime):
            cell.number_format = _DATETIME_FORMAT if col_idx == len(HEADERS) else _DATE_FORMAT
        if is_new:
            cell.font = Font(name=_FONT, size=11)
            cell.alignment = _CENTER
            cell.border = _BORDER

    _renumber(ws)
    _sync_table(ws, _last_data_row(ws))


def update_summary_counts(summary_file_path: str, pdf_filename: str, *, total_licenses, license_sequence,
                          status_note) -> None:
    """Columns 8 (total), 9 (GPLX numbers) and 11 (status) of one dossier, from its edited Excel.

    The other columns keep what is there, also values typed in the summary by hand.
    """
    with edit_master_summary(summary_file_path) as workbook:
        ws = _summary_sheet(workbook)
        rows = summary_rows_by_name(workbook).get(_filename_key(pdf_filename), [])
        if len(rows) != 1:
            raise ValueError(f"Sổ tổng hợp {'không có' if not rows else 'có nhiều'} dòng {pdf_filename}.")
        row = rows[0]
        for column, value in ((8, total_licenses), (9, license_sequence), (11, status_note)):
            cell = ws.cell(row, column)
            cell.value = value
            if isinstance(value, str):
                cell.data_type = "s"
        stamp = ws.cell(row, len(HEADERS))
        stamp.value = datetime.now().replace(second=0, microsecond=0)
        stamp.number_format = _DATETIME_FORMAT


def update_or_append_summary_entry(summary_file_path: str, record: Dict[str, Any]) -> str:
    with edit_master_summary(summary_file_path) as workbook:
        write_summary_entry(workbook, record)
    return summary_file_path
