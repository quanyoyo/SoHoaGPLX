"""
Zero-Config Embedded Database Module for GPLX Management.
Uses SQLite 3. Search matches substrings with LIKE; the citizens_fts table is kept in sync but not queried.
No external database server or connection string required.
"""
import io
import os
import json
import sqlite3
import shutil
import unicodedata
import re
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
import openpyxl

from datetime import date
from src.config import DATABASE_BACKUP_DIR, DATABASE_PATH, LEGACY_DATABASE_PATHS, get_handover_root_dir
from src.excel_generator import METADATA_FIELDS, PAGE_ROLE, REVIEW_ROLE, ROLE_ROW, WORKBOOK_METADATA, WORKBOOK_VERSION
from src.logger import get_logger
from src.naming_rules import LICENSE_NUMBER
from src.pdf_processor import get_pdf_page_count
from src.table_extractor import project_citizen, source_column_role

logger = get_logger(__name__)

# Province summaries written by the app: So_Theo_Doi_Day_So_GPLX_<province code>.xlsx
_SUMMARY_FILE = re.compile(r"So_Theo_Doi_Day_So_GPLX_([0-9]{2})\.xlsx", re.IGNORECASE)


def _excel_text(value):
    return "" if value is None else str(value).strip()


def _excel_positive_int(value, default=None):
    text = _excel_text(value)
    if re.fullmatch(r"[0-9]{1,9}", text) and int(text) > 0:
        return int(text)
    return default


def _lookup_license(value):
    text = _excel_text(value).upper()
    compact = re.sub(r"\s+", "", text).strip(".,:;")
    return compact if LICENSE_NUMBER.fullmatch(compact) else text


def _excel_rows(rows, roles, total_pages, *, legacy=False):
    positions = {role: roles.index(role) for role in (
        "stt", "full_name", "birth_year", "nationality", "address", "license_number", PAGE_ROLE, REVIEW_ROLE,
    ) if roles.count(role) == 1}
    for position, row in enumerate(rows, 1):
        values = {role: _excel_text(row[index]) for role, index in positions.items() if index < len(row)}
        extra = json.loads(values.pop(REVIEW_ROLE, "") or "{}")
        if not isinstance(extra, dict):
            raise ValueError("Dữ liệu đối chiếu trong Excel không hợp lệ.")
        license_number = values.get("license_number", "")
        if "_blocked_license" in extra and license_number == _excel_text(extra["_blocked_license"]):
            license_number = ""
        if "license_number" in extra:
            license_number = _excel_text(extra["license_number"])
        for key in ("full_name", "birth_year", "nationality", "address", "stt"):
            if key in extra:
                values[key] = _excel_text(extra[key])
        if not any((values.get("full_name"), license_number, values.get("stt"))):
            continue
        raw_page = values.get(PAGE_ROLE, "")
        page = _excel_positive_int(raw_page, default=1 if legacy and not raw_page else None)
        if page is None or page > total_pages:
            raise ValueError(f"Số trang PDF không hợp lệ tại dòng dữ liệu {position}: {raw_page[:50] or '(trống)'}.")
        normalized_license = _lookup_license(license_number)
        stt = _excel_positive_int(values.get("stt"), position)
        if legacy:
            yield {
                "stt": stt, "page_number": page, "license_number": normalized_license,
                **{key: values.get(key, "") for key in ("full_name", "birth_year", "address", "nationality")},
            }
        else:
            yield project_citizen(values, stt=stt, page_number=page, license_number=normalized_license)


def _read_source_workbook(workbook, total_pages):
    meta = workbook[WORKBOOK_METADATA]
    if meta["A1"].value != WORKBOOK_VERSION:
        raise ValueError("Phiên bản Excel GPLX chưa được hỗ trợ.")
    cover = {key: _excel_text(value) for key, value in meta.iter_rows(min_row=2, max_col=2, values_only=True)
             if key in METADATA_FIELDS}
    citizens = []
    found_table = False
    for sheet in workbook.worksheets:
        if sheet.sheet_state != "visible":
            continue
        rows = iter(sheet.iter_rows(min_row=ROLE_ROW, values_only=True))
        roles = next(rows, ())
        if PAGE_ROLE not in roles or REVIEW_ROLE not in roles:
            continue
        found_table = True
        next(rows, None)
        citizens.extend(_excel_rows(rows, roles, total_pages))
    if not found_table:
        raise ValueError("Không tìm thấy sheet danh sách GPLX có thông tin trang PDF.")
    return cover, citizens


def _read_legacy_workbook(workbook, total_pages):
    sheet = workbook.active
    title = _excel_text(sheet["A2"].value)
    dates = _excel_text(sheet["A3"].value)

    def metadata(pattern, text, default=""):
        match = re.search(pattern, text)
        return match[1] if match else default

    cover = {
        "province_code": metadata(r"Mã tỉnh:\s*([0-9]+)", title),
        "book_type": _excel_text(sheet["A1"].value) or "Sổ gốc cấp bằng lái xe cơ giới đường bộ",
        "license_class": metadata(r"Hạng:\s*([A-Za-z0-9]+)", title),
        "course": metadata(r"Khóa:\s*([A-Za-z0-9]+)", title),
        "exam_date": metadata(r"Ngày thi:\s*([0-9\-/.]+)", dates),
    }
    rows = iter(sheet.values)
    for row in rows:
        roles = tuple(PAGE_ROLE if _excel_text(value).casefold() in {"trang pdf", "trang", "số trang pdf"}
                      else source_column_role(value) for value in row)
        if "full_name" in roles and {"stt", "license_number", PAGE_ROLE}.intersection(roles):
            return cover, list(_excel_rows(rows, roles, total_pages, legacy=True))
    raise ValueError("Không tìm thấy tiêu đề danh sách GPLX trong Excel dạng cũ.")

def remove_vietnamese_accents(text: str) -> str:
    """
    Normalizes and removes accents from Vietnamese text.
    E.g. 'Trần Văn Yên' -> 'tran van yen'
         'Đỗ Vi Thượng' -> 'do vi thuong'
    """
    if not text:
        return ""
    # Replace special characters đ/Đ
    s = text.replace("đ", "d").replace("Đ", "d")
    # Decompose unicode characters into base char + combining mark
    nfkd_form = unicodedata.normalize('NFKD', s)
    # Filter out combining marks
    res = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    return res.lower().strip()

def sort_box_labels(labels):
    """Box labels in number order (2 before 10, 49 before 49A); labels without a number come last."""
    def key(label):
        match = re.match(r"\s*([0-9]+)(.*)", label)
        return (0, int(match[1]), match[2].casefold()) if match else (1, 0, label.casefold())
    return sorted(labels, key=key)


def _named_group(name):
    """Group read from a dossier name, for summary records saved before the group was recorded.

    'MM.Số.DD.MM.YYYY' before 01/03/2025 is QĐTT (named by its signing date); later dates are QĐSH.
    """
    if ".sql." in name.casefold():
        return "SQL"
    match = re.fullmatch(r"[0-9]{2}\.[0-9]+\.([0-9]{2})\.([0-9]{2})\.([0-9]{4})", name.strip())
    if not match:
        return ""
    day, month, year = map(int, match.groups())
    try:
        return "QĐTT" if date(year, month, day) < date(2025, 3, 1) else "QĐSH"
    except ValueError:
        return ""


class DatabaseManager:
    def __init__(self, db_path: str = DATABASE_PATH, files_root: Optional[str] = None):
        self.db_path = db_path
        # Paths inside the shared "So Hoa GPLX" folder are stored relative to it, because each
        # machine reaches the share through its own path (D:\..., Z:\..., \\server\...).
        self.files_root = os.path.abspath(files_root or get_handover_root_dir())
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        # Older builds kept a private database per machine. Seed the shared one once.
        if db_path == DATABASE_PATH and not os.path.exists(db_path):
            for legacy in LEGACY_DATABASE_PATHS:
                if os.path.isfile(legacy):
                    shutil.copy2(legacy, db_path)
                    logger.info("Seeded shared database %s from %s", db_path, legacy)
                    break
        self.init_db()

    def _stored_path(self, path: str) -> str:
        if not path:
            return ""
        path = os.path.abspath(path)
        try:
            relative = os.path.relpath(path, self.files_root)
        except ValueError:  # another drive
            return path
        if relative == os.pardir or relative.startswith(os.pardir + os.sep):
            return path
        return relative

    def resolve_path(self, stored: str) -> str:
        if not stored:
            return ""
        return stored if os.path.isabs(stored) else os.path.join(self.files_root, stored)

    def _resolve_row(self, row) -> Dict[str, Any]:
        data = dict(row)
        for key in ("pdf_path", "excel_path"):
            if key in data:
                data[key] = self.resolve_path(data[key])
        return data

    @staticmethod
    def _find_dossier(cursor, final_filename: str, previous_filename: Optional[str]):
        """Rows saved under the new name and, after a rename, under the old one."""
        names = [final_filename] + ([previous_filename] if previous_filename and previous_filename != final_filename else [])
        cursor.execute(
            f"SELECT id, final_filename, pdf_path, excel_path FROM dossiers "
            f"WHERE final_filename IN ({','.join('?' * len(names))})", names,
        )
        return {row["final_filename"]: row for row in cursor.fetchall()}

    def _check_not_other_dossier(self, row, pdf_path: str, final_filename: str):
        existing = self.resolve_path(row["pdf_path"])
        if (os.path.isfile(existing) and os.path.isfile(pdf_path)
                and os.path.normcase(os.path.realpath(existing)) != os.path.normcase(os.path.realpath(pdf_path))):
            raise FileExistsError(f"CSDL đã có hồ sơ cùng tên tại thư mục khác: {final_filename}.pdf")

    @staticmethod
    def _delete_dossier(cursor, dossier_id: int):
        cursor.execute("DELETE FROM citizens_fts WHERE rowid IN (SELECT id FROM citizens WHERE dossier_id = ?)", (dossier_id,))
        cursor.execute("DELETE FROM citizens WHERE dossier_id = ?", (dossier_id,))
        cursor.execute("DELETE FROM dossiers WHERE id = ?", (dossier_id,))

    @staticmethod
    def _dossier_values(cover_meta: Dict[str, Any]):
        return (
            cover_meta.get("province_code") or "",
            cover_meta.get("book_type", "Sổ gốc cấp bằng lái xe cơ giới đường bộ"),
            cover_meta.get("exam_date", ""),
            cover_meta.get("license_class", ""),
            cover_meta.get("course", ""),
            cover_meta.get("box", ""),
            cover_meta.get("box_number", ""),
        )

    def upsert_dossier_info(
        self,
        final_filename: str,
        cover_meta: Dict[str, Any],
        pdf_path: str,
        *,
        previous_filename: Optional[str] = None,
        excel_path: Optional[str] = None,
    ) -> int:
        """Record a dossier saved without a citizen list (quick rename).

        A citizen list imported earlier for the same dossier is kept. excel_path=None keeps
        the stored Excel path.
        """
        pdf_path = os.path.abspath(pdf_path)
        total = cover_meta.get("total_licenses")
        total = total if isinstance(total, int) else 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            rows = self._find_dossier(cursor, final_filename, previous_filename)
            current = rows.get(final_filename)
            if current is not None:
                self._check_not_other_dossier(current, pdf_path, final_filename)
            previous = rows.get(previous_filename) if previous_filename else None
            keep = previous if previous is not None else current
            if current is not None and keep is not current:
                self._delete_dossier(cursor, current["id"])
            values = (
                final_filename, self._stored_path(pdf_path),
                self._stored_path(excel_path) if excel_path is not None else None,
                *self._dossier_values(cover_meta),
                cover_meta.get("total_pages", 1), cover_meta.get("license_sequence", ""),
                cover_meta.get("status_note", ""),
            )
            if keep is None:
                cursor.execute("""
                INSERT INTO dossiers (
                    final_filename, pdf_path, excel_path, province_code, book_type, exam_date,
                    license_class, course, box, box_number, total_pages, license_sequence, status_note,
                    total_citizens
                ) VALUES (?, ?, COALESCE(?, ''), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (*values, total))
                return cursor.lastrowid
            cursor.execute("SELECT COUNT(*) FROM citizens WHERE dossier_id = ?", (keep["id"],))
            has_citizens = cursor.fetchone()[0] > 0
            cursor.execute("""
            UPDATE dossiers SET
                final_filename = ?, pdf_path = ?, excel_path = COALESCE(?, excel_path), province_code = ?,
                book_type = ?, exam_date = ?, license_class = ?, course = ?, box = ?, box_number = ?,
                total_pages = ?, license_sequence = ?, status_note = ?,
                total_citizens = CASE WHEN ? THEN total_citizens ELSE ? END
            WHERE id = ?
            """, (*values, has_citizens, total, keep["id"]))
            return keep["id"]

    def backup_daily(self, keep: int = 7, backup_dir: str = DATABASE_BACKUP_DIR) -> Optional[str]:
        """Copy the database once per day with SQLite's online backup, keeping the newest copies."""
        if not os.path.isfile(self.db_path):
            return None
        os.makedirs(backup_dir, exist_ok=True)
        target = os.path.join(backup_dir, f"gplx_index_{date.today():%Y%m%d}.db")
        if os.path.exists(target):
            return None
        temporary = f"{target}.{os.getpid()}.tmp"
        source = sqlite3.connect(self.db_path, timeout=30)
        try:
            copy = sqlite3.connect(temporary)
            try:
                source.backup(copy)
            finally:
                copy.close()
        finally:
            source.close()
        try:
            os.rename(temporary, target)
        except FileExistsError:  # another machine finished today's copy first
            os.unlink(temporary)
            return None
        backups = sorted(name for name in os.listdir(backup_dir)
                         if re.fullmatch(r"gplx_index_[0-9]{8}\.db", name))
        for name in backups[:-keep] if keep > 0 else []:
            try:
                os.unlink(os.path.join(backup_dir, name))
            except OSError:
                logger.warning("Could not remove old database backup %s", name, exc_info=True)
        return target

    @contextmanager
    def get_connection(self):
        # The database lives on a network share used by several machines: wait for a
        # writer instead of failing at once. Rollback journal mode (the default) is kept,
        # because WAL needs shared memory that network file systems do not provide.
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self):
        """Initializes tables and FTS5 full-text search index."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Dossiers Table (Sổ quản lý)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS dossiers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                final_filename TEXT NOT NULL UNIQUE,
                pdf_path TEXT NOT NULL,
                excel_path TEXT NOT NULL,
                province_code TEXT NOT NULL,
                book_type TEXT,
                exam_date TEXT,
                license_class TEXT,
                course TEXT,
                box TEXT,
                box_number TEXT,
                total_citizens INTEGER DEFAULT 0,
                total_pages INTEGER DEFAULT 1,
                license_sequence TEXT,
                status_note TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # 2. Citizens Table (Danh sách công dân)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS citizens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dossier_id INTEGER NOT NULL,
                stt INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                full_name_unaccented TEXT NOT NULL,
                birth_year TEXT,
                nationality TEXT DEFAULT 'Việt Nam',
                address TEXT,
                license_number TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                FOREIGN KEY(dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
            )
            """)

            # 3. Fast Indices
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_citizens_license ON citizens(license_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_citizens_name_unaccented ON citizens(full_name_unaccented)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_citizens_birth_year ON citizens(birth_year)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dossiers_filename ON dossiers(final_filename)")

            # 4. FTS5 Virtual Table for Instant Search
            cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS citizens_fts USING fts5(
                full_name,
                full_name_unaccented,
                license_number,
                address,
                content='citizens',
                content_rowid='id'
            )
            """)

            conn.commit()

    def insert_or_update_dossier(
        self,
        final_filename: str,
        cover_meta: Dict[str, Any],
        citizens: List[Dict[str, Any]],
        pdf_path: str,
        excel_path: str,
        *,
        previous_filename: Optional[str] = None,
    ) -> int:
        """
        Inserts or updates a dossier and its citizen records into SQLite.
        previous_filename drops the record of the same dossier saved under its old name.
        """
        pdf_path, excel_path = os.path.abspath(pdf_path), os.path.abspath(excel_path)
        with self.get_connection() as conn:
            cursor = conn.cursor()

            rows = self._find_dossier(cursor, final_filename, previous_filename)
            if final_filename in rows:
                self._check_not_other_dossier(rows[final_filename], pdf_path, final_filename)
            for row in rows.values():
                self._delete_dossier(cursor, row["id"])

            # Insert dossier
            cursor.execute("""
            INSERT INTO dossiers (
                final_filename, pdf_path, excel_path, province_code,
                book_type, exam_date, license_class, course,
                box, box_number, total_citizens, total_pages,
                license_sequence, status_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                final_filename,
                self._stored_path(pdf_path),
                self._stored_path(excel_path),
                *self._dossier_values(cover_meta),
                len(citizens),
                cover_meta.get("total_pages", 1),
                cover_meta.get("license_sequence", ""),
                cover_meta.get("status_note", "")
            ))
            dossier_id = cursor.lastrowid

            # Insert citizens
            for c in citizens:
                fn = c.get("full_name", "").strip()
                fn_unacc = remove_vietnamese_accents(fn)
                lic_no = _lookup_license(c.get("license_number"))
                stt_val = c.get("stt", 1)
                by_val = str(c.get("birth_year", "")).strip()
                nat_val = c.get("nationality", "Việt Nam").strip()
                addr_val = c.get("address", "").strip()
                p_num = c.get("page_number", 1)

                cursor.execute("""
                INSERT INTO citizens (
                    dossier_id, stt, full_name, full_name_unaccented,
                    birth_year, nationality, address, license_number, page_number
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (dossier_id, stt_val, fn, fn_unacc, by_val, nat_val, addr_val, lic_no, p_num))
                
                citizen_row_id = cursor.lastrowid

                # Index in FTS5
                cursor.execute("""
                INSERT INTO citizens_fts (rowid, full_name, full_name_unaccented, license_number, address)
                VALUES (?, ?, ?, ?, ?)
                """, (citizen_row_id, fn, fn_unacc, lic_no, addr_val))

            conn.commit()
            return dossier_id

    def search(
        self,
        query: str,
        province_code: Optional[str] = None,
        dossier_id: Optional[int] = None,
        limit: int = 150
    ) -> List[Dict[str, Any]]:
        """
        Fast multi-criteria search by:
        - License Number (exact or partial, e.g. 'A461544', 'C244138')
        - Citizen Name (accented 'Trần Văn Yên' or unaccented 'tran van yen')
        - Birth Year (e.g. '1960')
        - Location
        - Dossier ID (to view all citizens within a specific imported book)
        """
        if not (query or "").strip() and not dossier_id:
            return []
        where, params = self._citizen_filter(query, province_code, dossier_id)
        sql = f"""
            SELECT
                c.id as citizen_id,
                c.stt,
                c.full_name,
                c.birth_year,
                c.nationality,
                c.address,
                c.license_number,
                c.page_number,
                d.id as dossier_id,
                d.final_filename,
                d.pdf_path,
                d.excel_path,
                d.province_code,
                d.box,
                d.box_number,
                d.license_class,
                d.course,
                d.exam_date
            FROM citizens c
            JOIN dossiers d ON c.dossier_id = d.id
            WHERE {where}
            ORDER BY c.id ASC"""
        if not dossier_id:
            sql += " LIMIT ?"
            params.append(limit)
        with self.get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._resolve_row(row) for row in rows]

    @staticmethod
    def _citizen_filter(query, province_code=None, dossier_id=None):
        q = (query or "").strip()
        clauses, params = ["1=1"], []
        if q:
            clauses.append("(c.license_number LIKE ? OR c.full_name_unaccented LIKE ? "
                           "OR c.full_name LIKE ? OR c.birth_year = ?)")
            params.extend([f"%{q.replace(' ', '').upper()}%", f"%{remove_vietnamese_accents(q)}%", f"%{q}%", q])
        if province_code and province_code != "all":
            clauses.append("d.province_code = ?")
            params.append(province_code)
        if dossier_id:
            clauses.append("d.id = ?")
            params.append(dossier_id)
        return " AND ".join(clauses), params

    def count_search(self, query: str, province_code: Optional[str] = None, dossier_id: Optional[int] = None) -> int:
        """Number of citizens search() would find without its limit."""
        if not (query or "").strip() and not dossier_id:
            return 0
        where, params = self._citizen_filter(query, province_code, dossier_id)
        with self.get_connection() as conn:
            return conn.execute(
                f"SELECT COUNT(*) FROM citizens c JOIN dossiers d ON c.dossier_id = d.id WHERE {where}", params
            ).fetchone()[0]

    def get_dossier_id(self, final_filename: str) -> Optional[int]:
        """Id of the dossier stored under this name (a new id after each save or re-scan), or None."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT id FROM dossiers WHERE final_filename = ? ORDER BY id DESC LIMIT 1",
                               (final_filename,)).fetchone()
        return row[0] if row else None

    def get_dossier_files(self, dossier_id: int) -> Optional[Dict[str, str]]:
        """{'pdf_path', 'excel_path'} of a stored dossier (absolute paths; '' when absent), or None."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT pdf_path, excel_path FROM dossiers WHERE id = ?", (dossier_id,)).fetchone()
        if row is None:
            return None
        return {"pdf_path": self.resolve_path(row[0]) if row[0] else "",
                "excel_path": self.resolve_path(row[1]) if row[1] else ""}

    def get_all_dossiers(
        self,
        province_code: Optional[str] = "all",
        box: Optional[str] = "all",
        search_kw: str = "",
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all imported dossiers/Excel registers with box, box_number and license statistics.
        """
        where, params = self._dossier_filter(province_code, box, search_kw)
        sql = f"""
            SELECT
                d.id, d.final_filename, d.pdf_path, d.excel_path, d.province_code, d.book_type,
                d.exam_date, d.license_class, d.course, d.box, d.box_number, d.total_citizens,
                d.total_pages, d.license_sequence, d.status_note, d.created_at
            FROM dossiers d
            WHERE {where}
            ORDER BY d.id DESC LIMIT ?"""
        with self.get_connection() as conn:
            rows = conn.execute(sql, [*params, limit]).fetchall()
        return [self._resolve_row(r) for r in rows]

    @staticmethod
    def _dossier_filter(province_code="all", box="all", search_kw=""):
        clauses, params = ["1=1"], []
        if province_code and province_code != "all":
            clauses.append("d.province_code = ?")
            params.append(province_code)
        if box and box != "all":
            clauses.append("d.box = ?")
            params.append(box)
        if search_kw and search_kw.strip():
            clauses.append("(d.final_filename LIKE ? OR d.box LIKE ? OR d.box_number LIKE ?)")
            kw = f"%{search_kw.strip()}%"
            params.extend([kw, kw, kw])
        return " AND ".join(clauses), params

    def count_dossiers(self, province_code: Optional[str] = "all", box: Optional[str] = "all", search_kw: str = "") -> int:
        """Number of dossiers get_all_dossiers would list without its limit."""
        where, params = self._dossier_filter(province_code, box, search_kw)
        with self.get_connection() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM dossiers d WHERE {where}", params).fetchone()[0]

    def get_inventory_stats(self) -> Dict[str, Any]:
        """
        Calculates aggregate inventory statistics across all imported files and boxes.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(DISTINCT province_code) FROM dossiers")
            total_provinces = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(DISTINCT box) FROM dossiers WHERE box IS NOT NULL AND box != ''")
            total_boxes = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(DISTINCT box || '_' || box_number) FROM dossiers WHERE box_number IS NOT NULL AND box_number != ''")
            total_box_numbers = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM dossiers")
            total_dossiers = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM citizens")
            total_citizens = cursor.fetchone()[0] or 0

            return {
                "total_provinces": total_provinces,
                "total_boxes": total_boxes,
                "total_box_numbers": total_box_numbers,
                "total_dossiers": total_dossiers,
                "total_citizens": total_citizens
            }

    def get_distinct_boxes(self, province_code: str = "all") -> List[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if province_code and province_code != "all":
                cursor.execute("SELECT DISTINCT box FROM dossiers WHERE province_code = ? AND box IS NOT NULL AND box != '' ORDER BY box ASC", (province_code,))
            else:
                cursor.execute("SELECT DISTINCT box FROM dossiers WHERE box IS NOT NULL AND box != '' ORDER BY box ASC")
            return sort_box_labels(str(r[0]) for r in cursor.fetchall())

    def get_stats(self) -> Dict[str, int]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM dossiers")
            total_dossiers = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM citizens")
            total_citizens = cursor.fetchone()[0]
            return {
                "total_dossiers": total_dossiers,
                "total_citizens": total_citizens
            }

    def reindex_from_directory(self, root_dir: str, *, errors=None, removed=None) -> int:
        """
        Scans a directory for companion .xlsx files and re-indexes them into SQLite.

        Dossiers whose PDF was inside root_dir but is gone (saved under another name while the
        database write failed, renamed or deleted by hand) are dropped; their names go to removed.
        """
        dropped = self._drop_missing_dossiers(root_dir)
        if removed is not None:
            removed.extend(dropped)
        indexed_count = 0
        indexed = set()
        summaries = []
        pdf_files = {}
        for root, _, files in os.walk(root_dir):
            pdfs = {os.path.splitext(f)[0].casefold(): f for f in files if f.lower().endswith(".pdf")}
            for name, f in pdfs.items():
                pdf_files.setdefault(name, []).append(os.path.join(root, f))
            for f in files:
                if _SUMMARY_FILE.fullmatch(f):
                    summaries.append(os.path.join(root, f))
                if f.lower().endswith(".xlsx") and not f.lower().startswith(("so_theo_doi_", "~$", ".gplx-")):
                    excel_path = os.path.join(root, f)
                    base_name = f[:-5]
                    pdf_name = pdfs.get(base_name.casefold())
                    if pdf_name:
                        pdf_path = os.path.join(root, pdf_name)
                        try:
                            self._index_single_excel(excel_path, pdf_path, os.path.splitext(pdf_name)[0])
                            indexed_count += 1
                            indexed.add(base_name.casefold())
                        except Exception as e:
                            logger.exception("Could not index workbook %s", excel_path)
                            if errors is not None:
                                errors.append((f, str(e)))
        for summary in summaries:
            try:
                indexed_count += self._index_summary(summary, indexed, pdf_files, errors)
            except Exception as e:
                logger.exception("Could not index province summary %s", summary)
                if errors is not None:
                    errors.append((os.path.basename(summary), str(e)))
        return indexed_count

    def _drop_missing_dossiers(self, root_dir: str) -> List[str]:
        if not os.path.isdir(root_dir):
            return []
        root = os.path.normcase(os.path.abspath(root_dir)).rstrip(os.sep) + os.sep
        dropped = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for row in cursor.execute("SELECT id, final_filename, pdf_path FROM dossiers").fetchall():
                path = self.resolve_path(row["pdf_path"])
                if path and os.path.normcase(os.path.abspath(path)).startswith(root) and not os.path.exists(path):
                    self._delete_dossier(cursor, row["id"])
                    dropped.append(row["final_filename"])
        if dropped:
            logger.info("Dropped %d dossiers whose PDF is gone from %s: %s", len(dropped), root_dir, dropped)
        return dropped

    def _index_summary(self, summary_path: str, indexed: set, pdf_files: Dict[str, List[str]], errors=None) -> int:
        """Restore dossiers saved without an Excel list (quick rename) from a province summary."""
        from src.master_summary import read_rename_details, read_rename_records, read_summary_entries

        province_root = os.path.dirname(summary_path)
        province_code = _SUMMARY_FILE.fullmatch(os.path.basename(summary_path))[1]
        # Read a copy: an open handle would stop a save on this or another machine from replacing the file.
        with open(summary_path, "rb") as handle:
            content = io.BytesIO(handle.read())
        workbook = openpyxl.load_workbook(content, read_only=True, data_only=True)
        try:
            entries = read_summary_entries(workbook)
            targets = {name.strip().casefold().removesuffix(".pdf"): target
                       for name, _source, target in read_rename_records(workbook)}
            details = read_rename_details(workbook)
        finally:
            workbook.close()
        restored = 0
        for entry in entries:
            name = entry["pdf_filename"]
            key = name.casefold()
            if key in indexed:
                continue  # its Excel list was indexed above
            pdf_path = None
            if key in targets:
                candidate = os.path.normpath(os.path.join(province_root, targets[key]))
                if os.path.isfile(candidate):
                    pdf_path = candidate
            if pdf_path is None:
                inside = [path for path in pdf_files.get(key, [])
                          if os.path.normcase(os.path.abspath(path)).startswith(os.path.normcase(province_root + os.sep))]
                if len(inside) == 1:
                    pdf_path = inside[0]
            if pdf_path is None:
                logger.warning("Summary %s lists %s but its PDF was not found", summary_path, name)
                continue
            group, exam_date = details.get(key, ("", ""))
            if (group or _named_group(name)) != "QĐTT":
                # Other groups show the exam date on the summary; a QĐTT row shows the signing date.
                exam_date = entry["cover_date"]
            cover = {
                "province_code": province_code,
                "book_type": entry["book_type"] or "Sổ gốc cấp bằng lái xe cơ giới đường bộ",
                "exam_date": exam_date,
                "license_class": entry["license_class"],
                "box": entry["box"],
                "box_number": entry["box_number"],
                "total_licenses": entry["total_licenses"],
                "total_pages": entry["total_pages"],
                "license_sequence": entry["license_sequence"],
                "status_note": entry["status_note"],
            }
            try:
                self.upsert_dossier_info(name, cover, pdf_path)
            except Exception as e:
                logger.exception("Could not restore %s from %s", name, summary_path)
                if errors is not None:
                    errors.append((name, str(e)))
                continue
            indexed.add(key)
            restored += 1
        return restored

    def _index_single_excel(self, excel_path: str, pdf_path: str, final_filename: str):
        total_pages = get_pdf_page_count(pdf_path)
        # Read a copy: an open handle would stop a save on another machine from replacing this Excel.
        with open(excel_path, "rb") as handle:
            content = io.BytesIO(handle.read())
        workbook = openpyxl.load_workbook(content, read_only=True, data_only=True)
        try:
            reader = _read_source_workbook if WORKBOOK_METADATA in workbook.sheetnames else _read_legacy_workbook
            cover_meta, citizens = reader(workbook, total_pages)
        finally:
            workbook.close()
        cover_meta["total_pages"] = total_pages

        self.insert_or_update_dossier(
            final_filename=final_filename,
            cover_meta=cover_meta,
            citizens=citizens,
            pdf_path=pdf_path,
            excel_path=excel_path
        )
