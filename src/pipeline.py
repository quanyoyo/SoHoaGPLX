"""
End-to-End Processing Pipeline for GPLX PDF dossiers.
Coordinates PDF rendering, OCR, parsing, naming, and Excel export.
"""
import io
import os
import shutil
from copy import deepcopy
from filecmp import cmp
from functools import lru_cache
from pathlib import Path
from tempfile import mkstemp
from typing import Dict, Any, List, Optional

import openpyxl
from src.pdf_processor import open_pdf, page_count, read_pdf_page_text, render_pdf_page
from src.ocr_engine import run_ocr
from src.cover_parser import parse_cover_ocr, parse_cover_page_text
from src.table_extractor import LicenseTableExtractor, measure_page_grid, merge_tables, table_citizens
from src.naming_rules import STANDARD_DOSSIER_PDF, is_valid_windows_filename_stem, propose_dossier_filename
from src.excel_generator import generate_excel_companion
from src.folder_parser import folder_review_location
from src.sequence_analyzer import analyze_license_sequences
from src.master_summary import (
    edit_master_summary, read_rename_records, register_dossier_name, summary_rows_by_name, update_summary_counts,
    write_summary_entry,
)
from src.database import DatabaseManager, read_dossier_workbook, read_saved_tables
from src.config import PROVINCE_CODES
from src.logger import get_logger

logger = get_logger(__name__)


def _read_page_ocr(pdf, index):
    with render_pdf_page(pdf, index) as image:
        result, _ = run_ocr(image)
        return result, image.size


def _read_opening_page(pdf):
    from pypdfium2 import PdfiumError

    # A damaged or partial text layer is common in scanned decisions.
    try:
        text = read_pdf_page_text(pdf, 0)
    except PdfiumError:
        logger.warning("Could not read opening page text layer", exc_info=True)
        text = ""
    native = parse_cover_page_text(text)
    if native["document_type"] != "unknown" and not native["metadata_review"]:
        return native, None

    raw_ocr = _read_page_ocr(pdf, 0)
    scan = parse_cover_ocr(raw_ocr[0], raw_ocr[1][1])
    if native["document_type"] == "unknown":
        return scan, raw_ocr
    if native["document_type"] == scan["document_type"]:
        for field in ("province_code", "province_name", "exam_date", "decision_date", "decision_number",
                      "license_class", "course", "exam_location", "day", "month", "year"):
            if not native[field] and scan[field]:
                native[field] = scan[field]
                native["metadata_review"].pop(field, None)
                if field in scan["metadata_pages"]:
                    native["metadata_pages"][field] = scan["metadata_pages"][field]
    return native, raw_ocr


class StalePdfError(ValueError):
    """The PDF on disk is not the one that was read; its review data must be read again."""


def _pdf_cache_key(pdf_path):
    path = os.path.realpath(pdf_path)
    stat = os.stat(path)
    return path, stat.st_size, stat.st_mtime_ns


@lru_cache(maxsize=8)
def _cached_opening(key):
    with open_pdf(key[0]) as pdf:
        total = page_count(pdf)
        if not total:
            raise ValueError("File PDF rỗng không có trang nào.")
        cover, opening_ocr = _read_opening_page(pdf)
        return cover, total, opening_ocr


@lru_cache(maxsize=4)
def _cached_tables(key):
    _, total, opening_ocr = _cached_opening(key)
    extractor = LicenseTableExtractor()
    with open_pdf(key[0]) as pdf:
        for index in range(total):
            logger.info("Reading GPLX table candidates on page %d/%d: %s", index + 1, total, key[0])
            with render_pdf_page(pdf, index) as image:
                result = opening_ocr[0] if index == 0 and opening_ocr is not None else run_ocr(image)[0]
                extractor.read_page(result, image.size, measure_page_grid(image), index + 1)
    return extractor.tables


def _list_state(table):
    """What one list allows to conclude: its rows, unclear pages and the review warning."""
    rows = table["rows"] if table else []
    unresolved = table.get("unresolved_pages", []) if table else []
    known_count = bool(rows) and not unresolved and all(row["identity_confident"] for row in rows)
    blank = bool(rows) and all(row["license_state"] == "blank" for row in rows)
    complete = known_count and all(row["license_state"] == "valid" for row in rows)
    if not rows:
        warning = "Chưa xác định được danh sách GPLX."
    elif unresolved:
        warning = f"Cần đối chiếu trang {', '.join(map(str, unresolved))} để xác định danh sách có tiếp tục hay không."
    elif not known_count:
        warning = "Có dòng chưa đọc rõ họ tên. Hãy đối chiếu số lượng GPLX."
    elif blank:
        warning = "Cột số GPLX của danh sách đang trống."
    elif any(row["license_state"] == "unknown_column" for row in rows):
        warning = "Chưa xác định được cột số GPLX."
    elif not complete:
        warning = "Có ô số GPLX trống hoặc đọc chưa rõ. Hãy đối chiếu danh sách."
    else:
        warning = ""
    return {"rows": rows, "unresolved": unresolved, "known_count": known_count, "blank": blank,
            "complete": complete, "warning": warning}


def summarize_license_table(table):
    """Use the physical endpoints. Unknown cells and verified blanks have different results."""
    return summarize_license_tables([table] if table else [])


def summarize_license_tables(tables):
    """One summary for the whole PDF: every list it holds belongs to the same dossier.

    The SQL name runs from the first GPLX of the first list to the last GPLX of the last list
    (page order); the count, sequence and status cover all lists. A warning names its list when
    the PDF holds more than one.
    """
    states = [_list_state(table) for table in tables] or [_list_state(None)]
    rows = [row for state in states for row in state["rows"]]
    known_count = all(state["known_count"] for state in states)
    blank = all(state["blank"] for state in states)
    complete = all(state["complete"] for state in states)
    sequence = analyze_license_sequences([row["license_number"] for row in rows] if complete else [])
    if len(states) == 1:
        warning = states[0]["warning"]
    else:
        warning = "\n".join(f"Danh sách {i}: {state['warning']}" for i, state in enumerate(states, 1) if state["warning"])
    last = states[-1]
    return {
        "first_license_no": rows[0]["license_number"] if rows else "",
        # A page to check after the last row may continue the list; one inside the book does not move its end.
        "last_license_no": last["rows"][-1]["license_number"] if last["rows"] and not any(
            page > last["rows"][-1]["page_number"] for page in last["unresolved"]) else "",
        "license_column_empty": blank and known_count,
        "license_sequence": sequence["sequence_summary"],
        "status_note": "Cần rà soát" if warning and not blank else sequence["status"],
        "total_licenses": len(rows) if rows else None,  # the rows OCR read; the status says if they are sure
        "table_review": warning,
        "sequence_analysis": sequence,
    }


def process_dossier_pdf(pdf_path: str, default_province: str = "", *, rename_only: bool = False) -> Dict[str, Any]:
    """
    Processes a raw digitized PDF:
    1. Reads document metadata on the opening page
    2. Reads OCR and table data one page at a time
    4. Analyzes license sequences and continuity
    5. Extracts folder metadata (Hộp, Hộp số)
    6. Generates proposed standard filename
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File not found: {pdf_path}")

    # 0. Extract folder hierarchy (same rules for both flows; missing values stay empty)
    folder_info = folder_review_location(pdf_path)

    key = _pdf_cache_key(pdf_path)
    cached_cover, total_pages, _ = _cached_opening(key)
    cover_meta = deepcopy(cached_cover)
    # Quick rename reads the opening page only; the GPLX range and counts are typed by the user.
    # Every list of the PDF is one dossier: reviewed and saved as one list.
    tables = [] if rename_only else merge_tables(deepcopy(_cached_tables(key)))
    all_citizens = [row for table in tables for row in table_citizens(table)]
    
    cover_meta["suggested_province_code"] = cover_meta["province_code"]
    cover_meta["province_code"] = default_province if default_province != "auto" else ""
    cover_meta["province_name"] = next(
        (p["name"] for p in PROVINCE_CODES if p["code"] == cover_meta["province_code"]), ""
    )

    # Attach folder metadata
    cover_meta["box"] = folder_info.get("box", "")
    cover_meta["box_number"] = folder_info.get("box_number", "")
    # A new dict: the cached reading of the opening page is not changed.
    cover_meta["metadata_review"] = {**cover_meta.get("metadata_review", {}), **folder_info.get("box_review", {})}

    stats = summarize_license_tables(tables)
    seq_analysis = stats.pop("sequence_analysis")
    if rename_only:
        stats.update(first_license_no="", last_license_no="", license_sequence="", status_note="",
                     total_licenses=None, table_review="", license_column_empty=False)
    cover_meta.update(stats)
    cover_meta["total_pages"] = total_pages

    # 5. Generate Standardized Filename
    proposal = propose_dossier_filename(
        province_code=cover_meta["province_code"],
        suggested_province_code=cover_meta["suggested_province_code"],
        exam_date=cover_meta["exam_date"],
        decision_number=cover_meta.get("decision_number", ""),
        decision_date=cover_meta.get("decision_date", ""),
        first_license_no=cover_meta["first_license_no"],
        last_license_no=cover_meta["last_license_no"],
        license_column_empty=cover_meta["license_column_empty"],
    )

    return {
        "original_path": pdf_path,
        "original_filename": os.path.basename(pdf_path),
        "proposed_filename": proposal.filename or "",
        "cover_meta": cover_meta,
        "citizens": all_citizens,
        "tables": tables,
        "total_citizens": len(all_citizens),
        "total_pages": total_pages,
        "sequence_analysis": seq_analysis,
        "folder_info": folder_info,
        "rename_only": rename_only,
        "source_stamp": key[1:],
        "status": "READY_FOR_REVIEW"
    }


def _copy_named_pdf(source, target, *, allow_existing=True):
    if os.path.normcase(os.path.abspath(source)) == os.path.normcase(os.path.abspath(target)):
        return False
    created = False
    try:
        with open(source, "rb") as original, open(target, "xb") as renamed:
            created = True
            shutil.copyfileobj(original, renamed)
        shutil.copystat(source, target)
        return True
    except FileExistsError:
        if not allow_existing or not cmp(source, target, shallow=False):
            raise FileExistsError(f"Đã có PDF mang tên {os.path.basename(target)}. Hãy kiểm tra hoặc chọn tên khác.")
        return False
    except OSError:
        if created:
            os.unlink(target)
        raise


_SUMMARY_PREFIX = "So_Theo_Doi_Day_So_GPLX_"


def _summary_record(final_filename, cover_meta, total_citizens, *, folder_review=False):
    exam_date = cover_meta.get("exam_date", "")
    if cover_meta.get("dossier_group") == "QĐTT":
        # QĐTT dossiers are named by the signing date, which is also the summary's cover date.
        exam_date = cover_meta.get("decision_date", "")
    sequence = cover_meta.get("license_sequence", "")
    first = cover_meta.get("first_license_no")
    last = cover_meta.get("last_license_no")
    if not sequence and first and last and (folder_review or "license_sequence" not in cover_meta):
        sequence = f"Đầu {first} · Cuối {last}" if folder_review else f"{first}-{last}"
    total = cover_meta.get("total_licenses", total_citizens)
    return {
        "book_type": cover_meta.get("book_type", "Sổ gốc cấp bằng lái xe cơ giới đường bộ"),
        "cover_date": exam_date,
        "pdf_filename": final_filename,
        "box": cover_meta.get("box", ""),
        "box_number": cover_meta.get("box_number", ""),
        "license_class": cover_meta.get("license_class", ""),
        "total_licenses": total if total is not None else "",
        "license_sequence": sequence,
        "total_pages": cover_meta.get("total_pages", 1),
        "status_note": cover_meta.get("status_note", ""),
    }


class _FileMoves:
    """Renames done while saving, undone in reverse order when a later step fails."""

    def __init__(self):
        self._done = []
        self._discard = []

    def rename(self, source, target):
        if os.path.normcase(os.path.abspath(source)) == os.path.normcase(os.path.abspath(target)):
            return
        if os.path.exists(target):
            raise FileExistsError(f"Đã có file mang tên {os.path.basename(target)}. Hãy kiểm tra hoặc chọn tên khác.")
        try:
            os.rename(source, target)
        except PermissionError as exc:
            raise PermissionError(
                f"Không đổi tên được {os.path.basename(source)}: file đang được mở (trên máy này hoặc máy khác). "
                "Hãy đóng file rồi xác nhận lại."
            ) from exc
        self._done.append((source, target))

    def replace(self, source, target):
        """Put source at target. An existing target is kept aside until the save succeeds."""
        if os.path.exists(target):
            backup = f"{target}.{os.getpid()}.gplx-old"
            self.rename(target, backup)
            self._discard.append(backup)
        self.rename(source, target)

    def remove_later(self, path):
        """Delete path once the save succeeded (kept aside until then)."""
        if os.path.exists(path):
            backup = f"{path}.{os.getpid()}.gplx-old"
            self.rename(path, backup)
            self._discard.append(backup)

    def rollback(self):
        for source, target in reversed(self._done):
            try:
                os.rename(target, source)
            except OSError:
                logger.exception("Could not restore %s to %s", target, source)
                raise OSError(
                    f"Lưu thất bại và không trả lại được tên file {os.path.basename(source)} "
                    f"(hiện là {os.path.basename(target)}). Hãy đổi tên thủ công."
                )
        self._done.clear()
        self._discard.clear()

    def commit(self):
        for path in self._discard:
            try:
                os.unlink(path)
            except OSError:
                logger.warning("Could not remove replaced file %s", path, exc_info=True)


def save_dossier(
    original_pdf_path: str,
    final_filename: str,
    cover_meta: Dict[str, Any],
    *,
    citizens: Optional[List[Dict[str, Any]]] = None,
    source_tables=None,
    source_stamp=None,
    with_excel: bool,
) -> Dict[str, Any]:
    """Rename the PDF for real, update the province summary and, for digitization, its Excel.

    Both flows share this function. Steps that change files run inside the summary edit, so a
    failed summary save renames everything back. The database is written last.
    """
    if not is_valid_windows_filename_stem(final_filename):
        raise ValueError("Tên file không hợp lệ cho Windows. Nhập tên và bỏ phần đuôi .pdf.")
    province = cover_meta.get("province_code")
    if province not in {p["code"] for p in PROVINCE_CODES}:
        raise ValueError("Hãy chọn mã tỉnh lưu trữ hợp lệ.")
    source, *current_stamp = _pdf_cache_key(original_pdf_path)
    if source_stamp is not None and tuple(current_stamp) != tuple(source_stamp):
        raise StalePdfError("PDF đã thay đổi sau khi đọc.")
    citizens = citizens or []

    folder = os.path.dirname(source)
    province_root = folder_review_location(source)["province_root"]
    target_pdf = os.path.join(folder, f"{final_filename}.pdf")
    target_xlsx = os.path.join(folder, f"{final_filename}.xlsx")
    summary_path = os.path.join(province_root, f"{_SUMMARY_PREFIX}{province}.xlsx")

    temp_xlsx = None
    if with_excel:
        fd, temp_xlsx = mkstemp(prefix=".gplx-", suffix=".xlsx", dir=folder)
        os.close(fd)
    moves = _FileMoves()
    previous = None
    try:
        if with_excel:
            generate_excel_companion(cover_meta, citizens, temp_xlsx, source_tables=source_tables, pdf_path=source)
        logger.info("Saving dossier %s -> %s (excel=%s)", source, target_pdf, with_excel)
        with edit_master_summary(summary_path) as workbook:
            def same_file(saved):
                saved = os.path.join(province_root, saved)
                return os.path.isfile(saved) and cmp(source, saved, shallow=False)

            previous = register_dossier_name(
                workbook, final_filename,
                os.path.relpath(source, province_root), os.path.relpath(target_pdf, province_root),
                same_file=same_file, group=cover_meta.get("dossier_group") or "",
                exam_date=cover_meta.get("exam_date") or "",
            )
            write_summary_entry(
                workbook, _summary_record(final_filename, cover_meta, len(citizens), folder_review=not with_excel),
                previous_filename=previous,
            )
            old_xlsx = os.path.join(folder, f"{os.path.splitext(os.path.basename(source))[0]}.xlsx")
            # Only the Excel named like the PDF being saved is its own and may be replaced.
            if (with_excel and os.path.exists(target_xlsx)
                    and os.path.normcase(target_xlsx) != os.path.normcase(old_xlsx)):
                raise FileExistsError(
                    f"Đã có file Excel mang tên {os.path.basename(target_xlsx)} của file khác. "
                    "Hãy kiểm tra hoặc chọn tên khác."
                )
            moves.rename(source, target_pdf)
            if with_excel:
                moves.replace(temp_xlsx, target_xlsx)
                temp_xlsx = None
                if previous and os.path.normcase(old_xlsx) != os.path.normcase(target_xlsx):
                    moves.remove_later(old_xlsx)
            elif previous and os.path.isfile(old_xlsx):
                # The Excel of an earlier digitization follows its PDF.
                moves.rename(old_xlsx, target_xlsx)
    except Exception as exc:
        moves.rollback()
        if isinstance(exc, PermissionError) and not str(exc).startswith("Không đổi tên"):
            raise PermissionError(f"Không ghi được PDF hoặc sổ {os.path.basename(summary_path)}. "
                                  "Hãy đóng sổ trong Excel và kiểm tra quyền ghi rồi thử lại.") from exc
        raise
    finally:
        if temp_xlsx and os.path.exists(temp_xlsx):
            os.unlink(temp_xlsx)
    moves.commit()
    _cached_opening.cache_clear()
    _cached_tables.cache_clear()

    excel_path = target_xlsx if os.path.isfile(target_xlsx) else ""
    db_error = None
    try:
        db = DatabaseManager()
        if with_excel:
            db.insert_or_update_dossier(
                final_filename=final_filename, cover_meta=cover_meta, citizens=citizens,
                pdf_path=target_pdf, excel_path=target_xlsx, previous_filename=previous,
            )
        else:
            db.upsert_dossier_info(final_filename, cover_meta, target_pdf, previous_filename=previous,
                                   excel_path=excel_path or None)
    except Exception as exc:
        logger.exception("SQLite sync failed for %s", final_filename)
        db_error = str(exc)
    logger.info("Saved dossier %s (previous name: %s)", target_pdf, previous)
    return {
        "success": True,
        "pdf_path": target_pdf,
        "excel_path": excel_path,
        "master_summary_path": summary_path,
        "original_path": source,
        "previous_filename": previous,
        "total_citizens": len(citizens),
        "db_error": db_error,
        "final_filename": final_filename,
    }


def commit_folder_dossier(original_pdf_path, final_filename, cover_meta, *, source_stamp=None):
    """Quick rename: rename the PDF and update its province summary and database record."""
    return save_dossier(original_pdf_path, final_filename, cover_meta, source_stamp=source_stamp, with_excel=False)


def commit_dossier(
    original_pdf_path: str,
    final_filename: str,
    cover_meta: Dict[str, Any],
    citizens: List[Dict[str, Any]],
    output_dir: Optional[str] = None,
    *,
    source_tables=None,
    source_stamp=None,
) -> Dict[str, Any]:
    """Digitization: rename the PDF, export its Excel, update the summary and the database.

    output_dir is accepted for compatibility; files are always saved next to the PDF.
    """
    if output_dir and os.path.normcase(os.path.abspath(output_dir)) != os.path.normcase(
            os.path.dirname(os.path.abspath(original_pdf_path))):
        raise ValueError("Hồ sơ được lưu tại thư mục của PDF.")
    return save_dossier(original_pdf_path, final_filename, cover_meta, citizens=citizens,
                        source_tables=source_tables, source_stamp=source_stamp, with_excel=True)


def _registered_names(province_root):
    """{current PDF (normcase abs path): dossier name} from the province summaries."""
    registered = {}
    root_path = Path(province_root)
    for summary in root_path.glob(f"{_SUMMARY_PREFIX}[0-9][0-9].xlsx"):
        try:
            # Read a copy: an open handle would stop another machine's save from replacing the summary.
            workbook = openpyxl.load_workbook(io.BytesIO(summary.read_bytes()), read_only=True)
            try:
                names = summary_rows_by_name(workbook)
                linked = set()
                for filename, _source, target in read_rename_records(workbook):
                    key = filename.strip().casefold().removesuffix(".pdf")
                    if len(names.get(key, [])) == 1:
                        registered[os.path.normcase(str((root_path / target).resolve()))] = filename
                        linked.add(key)
                for key in names.keys() - linked:
                    registered.setdefault(("name", key), key)
            finally:
                workbook.close()
        except Exception:
            logger.warning("Could not read registered PDFs from %s", summary, exc_info=True)
    return registered


def list_folder_review_pdfs(folder_path, *, require_excel=False):
    """PDFs under folder_path with the dossier name they were saved under (None if not saved).

    A PDF counts as saved when the summary links it to a name, or (older versions) when its own
    name is in the summary. Digitization also needs the Excel next to it.
    """
    paths = sorted(
        (str(path.resolve()) for path in Path(folder_path).rglob("*") if path.suffix.lower() == ".pdf" and path.is_file()),
        key=str.casefold,
    )
    registered = {}
    for root in {folder_review_location(path)["province_root"] for path in paths}:
        registered.update(_registered_names(root))
    entries = []
    for path in paths:
        stem = os.path.splitext(os.path.basename(path))[0]
        name = registered.get(os.path.normcase(path)) or registered.get(("name", stem.casefold()))
        if name and require_excel and not os.path.isfile(os.path.join(os.path.dirname(path), f"{stem}.xlsx")):
            name = None
        entries.append((path, path if name else None))
    return entries

def _saved_summary_row(pdf_path):
    """(summary path, summary row, (group, exam date) of the rename sheet) of a saved PDF, or Nones."""
    from src.master_summary import read_rename_details, read_summary_entries

    key = Path(pdf_path).stem.casefold()
    root = Path(folder_review_location(pdf_path)["province_root"])
    for summary in sorted(root.glob(f"{_SUMMARY_PREFIX}[0-9][0-9].xlsx")):
        # Read a copy: an open handle would stop another machine's save from replacing the summary.
        workbook = openpyxl.load_workbook(io.BytesIO(summary.read_bytes()), read_only=True)
        try:
            entry = next((e for e in read_summary_entries(workbook) if e["pdf_filename"].casefold() == key), None)
            if entry:
                return str(summary), entry, read_rename_details(workbook).get(key, ("", ""))
        finally:
            workbook.close()
    return None, None, None


def load_saved_dossier(pdf_path: str) -> Dict[str, Any]:
    """A saved dossier for the review panel, read from its Excel and province summary. No OCR.

    Digitized dossiers have an Excel next to the PDF (cover fields in its hidden sheet, every list
    with its own columns); quick renames only have their summary row. The summary row gives the
    count, GPLX numbers and status, as last written by a save or by refresh_summary_from_excel.
    """
    excel = os.path.splitext(pdf_path)[0] + ".xlsx"
    summary_path, entry, details = _saved_summary_row(pdf_path)
    has_excel = os.path.isfile(excel)
    if entry is None and not has_excel:
        raise ValueError(f"Không tìm thấy dữ liệu đã lưu của {os.path.basename(pdf_path)} (sổ tổng hợp, file Excel).")
    cover, tables = {}, []
    if has_excel:
        try:
            cover, _citizens = read_dossier_workbook(excel, pdf_path)
            workbook = openpyxl.load_workbook(io.BytesIO(Path(excel).read_bytes()), read_only=True, data_only=True)
            try:
                tables = merge_tables(read_saved_tables(workbook))  # Excel saved before 22/11/2026: a sheet per list
            finally:
                workbook.close()
        except Exception as exc:
            logger.warning("Could not read saved Excel %s", excel, exc_info=True)
            raise ValueError(f"Không đọc được file Excel {os.path.basename(excel)}: {exc}") from exc
    if entry is not None:
        group, exam_date = details
        cover.setdefault("province_code", Path(summary_path).stem.removeprefix(_SUMMARY_PREFIX))
        cover.setdefault("dossier_group", group)
        cover.setdefault("exam_date", exam_date or (entry["cover_date"] if group != "QĐTT" else ""))
        cover.update({field: entry[field] for field in (
            "book_type", "box", "box_number", "license_class", "total_licenses", "license_sequence", "status_note",
        ) if entry[field] not in ("", None)})
    return {
        "original_path": pdf_path, "tables": tables, "cover_meta": cover, "rename_only": not has_excel,
        "saved_view": True, "excel_path": excel if has_excel else None, "summary_path": summary_path,
    }


def refresh_summary_from_excel(pdf_path: str) -> Dict[str, Any]:
    """After the Excel was edited by hand: count, GPLX numbers and status of its rows go to the
    province summary (that dossier's row only) and the lookup database. The Excel is not changed.
    """
    excel = os.path.splitext(pdf_path)[0] + ".xlsx"
    name = Path(pdf_path).stem
    if not os.path.isfile(excel):
        raise ValueError(f"Hồ sơ {name} không có file Excel (đổi tên nhanh), nên không cập nhật từ Excel được.")
    summary_path, entry, _details = _saved_summary_row(pdf_path)
    if entry is None:
        raise ValueError(f"Sổ tổng hợp chưa có dòng {name}. Hãy lưu hồ sơ trước.")
    cover, citizens = read_dossier_workbook(excel, pdf_path)
    counts = {"total_licenses": len(citizens), "license_sequence": cover["license_sequence"],
              "status_note": cover["status_note"]}
    update_summary_counts(summary_path, name, **counts)
    db_error = None
    try:
        DatabaseManager().insert_or_update_dossier(
            final_filename=name, cover_meta=cover, citizens=citizens, pdf_path=pdf_path, excel_path=excel)
    except Exception as exc:
        logger.exception("Could not update the database from %s", excel)
        db_error = str(exc)
    return {**counts, "summary_path": summary_path, "excel_path": excel, "db_error": db_error}


def fast_extract_rename_metadata(pdf_path: str, default_province: str = "") -> str:
    """Read the header first. SQL names also need the endpoints of a unique GPLX list."""
    logger.info("Folder rename: opening PDF %s", pdf_path)
    key = _pdf_cache_key(pdf_path)
    cover_meta, total_pages, _ = _cached_opening(key)
    logger.info("Folder rename: PDF has %d pages, type=%s, review_fields=%s: %s",
                total_pages, cover_meta["document_type"], list(cover_meta["metadata_review"]), pdf_path)
    fields = {
        "province_code": default_province,
        "suggested_province_code": cover_meta["province_code"],
        "exam_date": cover_meta["exam_date"],
        "decision_number": cover_meta["decision_number"],
        "decision_date": cover_meta["decision_date"],
    }
    proposal = propose_dossier_filename(**fields)
    if proposal.filename:
        return proposal.filename
    if proposal.group != "SQL" or proposal.errors.keys() - {"first_license_no", "last_license_no"}:
        raise ValueError("Cần rà soát: " + " ".join(proposal.errors.values()))

    tables = _cached_tables(key)
    if not tables:
        raise ValueError("Cần rà soát: Chưa tìm thấy danh sách GPLX.")
    stats = summarize_license_tables(tables)
    proposal = propose_dossier_filename(
        **fields,
        first_license_no=stats["first_license_no"],
        last_license_no=stats["last_license_no"],
        license_column_empty=stats["license_column_empty"],
    )
    if proposal.filename is None:
        raise ValueError("Cần rà soát: " + " ".join(proposal.errors.values()))
    return proposal.filename

def batch_copy_and_rename_folder_pdfs(
    folder_path: str,
    default_province: str = "",
    progress_callback = None
) -> Dict[str, Any]:
    """
    Scans a folder for raw PDFs and renames files with sufficient OCR data to their proposed names.
    Does not generate companion Excel files or update the summary.
    """
    import time

    logger.info("Folder rename started: folder=%s province=%s", folder_path, default_province)

    found_pdfs = []
    for root, _, files in os.walk(folder_path):
        for f in files:
            if f.lower().endswith(".pdf") and not STANDARD_DOSSIER_PDF.fullmatch(f):
                found_pdfs.append(os.path.join(root, f))
    found_pdfs.sort()

    total_files = len(found_pdfs)
    results = []
    logger.info("Folder rename found %d unrenamed PDF files in %s", total_files, folder_path)

    for idx, pdf_path in enumerate(found_pdfs, start=1):
        started_at = time.monotonic()
        try:
            logger.info(
                "Folder rename file %d/%d started: path=%s size_bytes=%d",
                idx, total_files, pdf_path, os.path.getsize(pdf_path),
            )
            if progress_callback:
                progress_callback(idx, total_files, os.path.basename(pdf_path))

            # Thuật toán đọc nhanh siêu tốc: Chỉ đọc Trang 1, Trang 2 và Trang cuối
            new_filename = fast_extract_rename_metadata(pdf_path, default_province=default_province)

            parent_dir = os.path.dirname(os.path.abspath(pdf_path))
            new_pdf_path = os.path.join(parent_dir, f"{new_filename}.pdf")

            # Rename for real: the original scan name is not kept.
            if os.path.exists(new_pdf_path):
                raise FileExistsError(f"Đã có PDF mang tên {os.path.basename(new_pdf_path)}.")
            os.rename(pdf_path, new_pdf_path)

            results.append({
                "original_path": pdf_path,
                "new_path": new_pdf_path,
                "new_filename": new_filename,
                "success": True,
                "error": None
            })
            logger.info(
                "Folder rename file %d/%d completed: output=%s elapsed_seconds=%.1f",
                idx, total_files, new_pdf_path, time.monotonic() - started_at,
            )
        except Exception as e:
            logger.exception(
                "Folder rename file %d/%d failed after %.1f seconds: %s",
                idx, total_files, time.monotonic() - started_at, pdf_path,
            )
            results.append({
                "original_path": pdf_path,
                "new_path": None,
                "new_filename": None,
                "success": False,
                "error": str(e)
            })

    result = {
        "total_scanned": total_files,
        "success_count": sum(1 for r in results if r["success"]),
        "failed_count": sum(1 for r in results if not r["success"]),
        "results": results
    }
    logger.info(
        "Folder rename finished: folder=%s total=%d success=%d failed=%d",
        folder_path, result["total_scanned"], result["success_count"], result["failed_count"],
    )
    return result
