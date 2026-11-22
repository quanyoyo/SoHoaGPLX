"""Rules for proposing and validating GPLX dossier filenames."""
import re
from dataclasses import dataclass
from datetime import date

from src.config import PROVINCE_CODES

FORBIDDEN_CHARS = re.compile(r'[\\/:*?"<>|]')
LICENSE_NUMBER = re.compile(r"[A-Z]{1,2}[0-9]{6}")
DOSSIER_GROUPS = ("SQL", "QĐTT", "QĐSH")
STANDARD_DOSSIER_PDF = re.compile(
    r"[0-9]{2}\.(?:SQL\.[0-9]{2}\.[0-9]{4}\..+|[0-9]+\.[0-9]{2}\.[0-9]{2}\.[0-9]{4})\.pdf",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FilenameProposal:
    group: str | None
    filename: str | None  # Stem only. Callers append the file extension.
    errors: dict[str, str]

def clean_filename(filename: str) -> str:
    """Removes or replaces characters forbidden in Windows filenames."""
    return FORBIDDEN_CHARS.sub("-", filename).strip()


def is_valid_windows_filename_stem(filename: str) -> bool:
    return (
        bool(filename)
        and filename == clean_filename(filename)
        and not filename.endswith(".")
        and not filename.lower().endswith(".pdf")
        and not any(ord(char) < 32 for char in filename)
        and not re.fullmatch(r"CON|PRN|AUX|NUL|(?:COM|LPT)[1-9¹²³]", filename.split(".", 1)[0].rstrip(), re.IGNORECASE)
    )

def normalize_license_code(raw_code: str) -> str:
    """
    Normalizes a license code:
    E.g.: 'A 161541' -> 'A161541'
          'c244138'  -> 'C244138'
          'A461S44-' -> 'A461544'  (S read as 5, trailing '-' dropped)
    """
    if not raw_code:
        return "UNKNOWN"
    
    cleaned = raw_code.strip().replace(" ", "").upper()
    # Strip any trailing or leading punctuation like '-', '.', ','
    cleaned = re.sub(r"^[^A-Z0-9]+|[^A-Z0-9]+$", "", cleaned)
    
    if not cleaned:
        return "UNKNOWN"

    # Identify prefix letters (1 or 2 letters)
    prefix_match = re.match(r"^([A-Z]{1,2})(.*)", cleaned)
    if prefix_match:
        prefix = prefix_match.group(1)
        suffix = prefix_match.group(2)
        
        # Convert common handwriting OCR errors in numeric suffix to digits:
        char_to_digit = {
            'S': '5', 's': '5',
            'O': '0', 'o': '0', 'D': '0', 'Q': '0',
            'I': '1', 'i': '1', 'L': '1', 'l': '1', '|': '1',
            'Z': '2', 'z': '2',
            'B': '8', 'b': '8',
            'G': '6'
        }
        converted_suffix = "".join([char_to_digit.get(ch, ch) for ch in suffix])
        # Keep only digits in suffix
        digits_only = re.sub(r"[^0-9]", "", converted_suffix)
        if digits_only:
            return f"{prefix}{digits_only}"
        return f"{prefix}{suffix}"

    return clean_filename(cleaned)

def _read_date(value: str, field: str, label: str, errors: dict[str, str]) -> date | None:
    if not value.strip():
        errors[field] = f"Thiếu {label}."
        return None
    match = re.fullmatch(r"([0-9]{1,2})\s*([/.-])\s*([0-9]{1,2})\s*\2\s*([0-9]{4})", value.strip())
    if match:
        day, _, month, year = match.groups()
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            pass
    errors[field] = f"{label.capitalize()} không hợp lệ. Nhập ngày/tháng/năm."
    return None


EXAM_DATE_FORMAT = re.compile(r"([0-9]{2})-([0-9]{2})-([0-9]{4})")


def format_exam_date(value: str) -> str:
    """An exam date read by the machine, written dd-mm-yyyy; a value that is not a real date is kept as read."""
    parsed = _read_date(value, "exam_date", "", {}) if value.strip() else None
    return f"{parsed.day:02d}-{parsed.month:02d}-{parsed.year:04d}" if parsed else value


def typed_format_errors(*, group: str | None, exam_date: str = "", first_license_no: str = "",
                        last_license_no: str = "") -> dict[str, str]:
    """Checks on what the user typed in the review panel, stricter than the naming rules.

    The naming rules accept other date separators, spaces and lower case, for values read by the
    machine (quick rename). A typed exam date must be dd-mm-yyyy and the SQL endpoints upper case.
    Empty boxes are left to the naming rules.
    """
    errors = {}
    match = EXAM_DATE_FORMAT.fullmatch(exam_date.strip())
    if exam_date.strip() and not (match and _read_date(exam_date, "exam_date", "", {})):
        errors["exam_date"] = "Ngày thi/sát hạch phải là ngày có thật, nhập dạng dd-mm-yyyy (ví dụ 29-03-1996)."
    if group == "SQL":
        for field, label, value in (("first_license_no", "đầu", first_license_no), ("last_license_no", "cuối", last_license_no)):
            if value.strip() and not LICENSE_NUMBER.fullmatch(value.strip()):
                errors[field] = f"Số GPLX {label} phải viết hoa, gồm 1–2 chữ cái và 6 chữ số liền nhau (ví dụ AM570000)."
    return errors


def propose_dossier_filename(
    *,
    province_code: str = "",
    suggested_province_code: str = "",
    province_confirmed: bool = False,
    exam_date: str = "",
    decision_date: str = "",
    decision_number: str = "",
    first_license_no: str = "",
    last_license_no: str = "",
    license_column_empty: bool = False,
    confirmed_group: str = "",
) -> FilenameProposal:
    """Return the filename stem or errors keyed by the fields that need review."""
    errors = {}
    code = province_code.strip()
    if not code:
        # The OCR hint is named only when OCR read a province on the document.
        hint = next((p for p in PROVINCE_CODES if p["code"] == suggested_province_code.strip()), None)
        errors["province_code"] = (f"Chưa chọn mã tỉnh lưu trữ (OCR gợi ý: {hint['code']} – {hint['name']})."
                                   if hint else "Chưa chọn mã tỉnh lưu trữ.")
    elif not re.fullmatch(r"[0-9]{2}", code) or not any(p["code"] == code for p in PROVINCE_CODES):
        errors["province_code"] = "Mã tỉnh không có trong danh mục cấu hình."
    elif suggested_province_code and suggested_province_code != code and not province_confirmed:
        errors["province_code"] = f"OCR gợi ý mã {suggested_province_code}. Hãy xác nhận mã lưu trữ {code}."

    exam = None
    if exam_date.strip():
        exam = _read_date(exam_date, "exam_date", "ngày thi/sát hạch", errors)
        if exam is None:
            return FilenameProposal(None, None, errors)
        if exam < date(2013, 1, 1):
            group = "SQL"
        elif exam < date(2025, 3, 1):
            group = "QĐTT"
        else:
            group = "QĐSH"
    elif confirmed_group in DOSSIER_GROUPS:
        group = confirmed_group
        if group != "QĐTT":
            errors["exam_date"] = "Nhóm này cần ngày thi/sát hạch để đặt tên."
    else:
        errors["exam_date"] = "Nhập ngày thi/sát hạch hoặc xác nhận nhóm hồ sơ."
        return FilenameProposal(None, None, errors)

    if group == "SQL":
        endpoints = [re.sub(r"\s+", "", value).upper() for value in (first_license_no, last_license_no)]
        if license_column_empty and not any(endpoints):
            endpoints = ["A000000", "A000000"]
        for field, label, value in zip(("first_license_no", "last_license_no"), ("đầu", "cuối"), endpoints):
            if not LICENSE_NUMBER.fullmatch(value):
                errors[field] = f"Số GPLX {label} phải gồm 1–2 chữ cái và 6 chữ số."
        if errors:
            return FilenameProposal(group, None, errors)
        filename = f"{code}.SQL.{exam.month:02d}.{exam.year:04d}.{endpoints[0]}-{endpoints[1]}"
    else:
        decision = re.fullmatch(r"([0-9]+)(?:\s*/\s*[^\s/][^\r\n]*)?", decision_number.strip())
        if not decision:
            errors["decision_number"] = "Nhập số quyết định, ví dụ 368/QĐ-SGTVT hoặc 368."
        name_date = _read_date(decision_date, "decision_date", "ngày ký quyết định", errors) if group == "QĐTT" else exam
        if errors:
            return FilenameProposal(group, None, errors)
        filename = f"{code}.{decision[1]}.{name_date.day:02d}.{name_date.month:02d}.{name_date.year:04d}"

    return FilenameProposal(group, filename, errors)
