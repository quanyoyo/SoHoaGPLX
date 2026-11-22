"""
Parser for folder path hierarchy:
Format: [Tỉnh] / [Hộp / Tủ hồ sơ] / [Hộp số / Hộp giấy] / [file.pdf]
E.g.: DuLieu_GPLX/LaoCai/HOP_48/HOP_SO_115/scan_001.pdf
      -> Tỉnh: LaoCai
      -> Hộp: 48
      -> Hộp số: 115
"""
import os
import re
import unicodedata
from pathlib import Path
from typing import Dict, Any

def extract_clean_number_or_name(folder_name: str) -> str:
    """
    Extracts number if present (e.g. 'HOP_48' -> '48', 'Hop so 115' -> '115'),
    otherwise returns clean uppercase string.
    """
    if not folder_name:
        return ""
        
    cleaned = folder_name.strip()
    # Try extracting digits
    digits = re.findall(r"\d+", cleaned)
    if digits:
        return digits[-1] # Usually the number at the end: HOP 48 -> 48
        
    # Remove common prefix words: HOP, TU, HO SO, HOP SO
    name = re.sub(r"(?i)^(HỘP|HOP|TỦ|TU|HỒ SƠ|HO SO|HỘP SỐ|HOP SO)[\s_\-]*", "", cleaned)
    return name.strip() or cleaned

def parse_folder_hierarchy(pdf_path: str) -> Dict[str, str]:
    """
    Parses full or relative file path to determine Box (Hộp) and Box Number (Hộp số).
    """
    abs_path = os.path.abspath(pdf_path)
    parts = abs_path.replace("\\", "/").split("/")
    
    # Defaults
    info = {
        "province_folder": "",
        "box": "",         # HỘP (Tủ hồ sơ)
        "box_number": ""    # HỘP SỐ (Hộp giấy)
    }
    
    if len(parts) >= 2:
        # Parent folder of the PDF is typically Hộp số (Hop so 115, Ho so 115)
        box_num_raw = parts[-2]
        info["box_number"] = extract_clean_number_or_name(box_num_raw)
        
    if len(parts) >= 3:
        # Grandparent folder is typically Hộp (HOP 48, Tu 48)
        box_raw = parts[-3]
        info["box"] = extract_clean_number_or_name(box_raw)
        
    if len(parts) >= 4:
        info["province_folder"] = parts[-4]
        
    return info

def find_province_root_dir(pdf_path: str) -> str:
    """
    Finds the province root folder in the path hierarchy:
    E.g. D:/Data/LaoCai/HOP_48/HOP_SO_115/scan.pdf -> D:/Data/LaoCai
    If path is less than 3 levels deep, returns the immediate directory of the PDF.
    """
    abs_dir = os.path.dirname(os.path.abspath(pdf_path))
    parts = abs_dir.replace("\\", "/").split("/")
    
    # Check if grandparent is Hộp and great-grandparent is Province
    if len(parts) >= 3:
        # Check if parent folder looks like Hộp số / Ho so
        # and grandparent looks like Hộp / Tu
        # Then province root is 2 levels above:
        prov_dir = os.path.abspath(os.path.join(abs_dir, "..", ".."))
        if os.path.exists(prov_dir):
            return prov_dir

    return abs_dir


# Any punctuation may stand between the word and the number: "HOP (49)", "HOP#49", "HOP_SO_115".
_SEPARATOR = r"[^a-z0-9]*"
_END = r"(?![a-z0-9])"
# The number right after the word and its letter, joined ("49A") or apart ("49 A"); then the rest of the name.
_NUMBER = rf"([0-9]+)(?:([a-z]{{1,2}}){_END}|[ _\-.]+([a-z]){_END}|{_END})(.*)"
_BOX_NUMBER_FOLDER = re.compile(rf"(?:hop{_SEPARATOR}so|ho{_SEPARATOR}so){_SEPARATOR}{_NUMBER}")
_BOX_FOLDER = re.compile(rf"(?:hop|tu){_SEPARATOR}{_NUMBER}")


def _folded(name):
    text = unicodedata.normalize("NFD", name.casefold().replace("đ", "d"))
    return "".join(c for c in text if not unicodedata.combining(c)).strip()


def _box_value(match, folder_name, label):
    """The box value, or "" and a note when another number follows ("HOP 49 (2010)")."""
    if re.search(r"[0-9]", match[4]):
        return "", f"Tên thư mục \"{folder_name}\" có nhiều số, hãy đối chiếu và nhập {label}."
    return f"{match[1]}{match[2] or match[3] or ''}".upper(), ""


def folder_review_location(pdf_path: str) -> Dict[str, Any]:
    """Find the province and box fields for folders selected at any archive level."""
    parent = Path(pdf_path).resolve().parent
    lineage = [*reversed(parent.parents), parent]
    root = parent
    archive_province = None
    box = box_number = ""
    found_box = False
    review = {}
    for index, folder in enumerate(lineage):
        key = re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFD", folder.name.casefold()))
        name = _folded(folder.name)
        if key in {"dulieusohoagpls", "dulieusohoagplx", "dulieugplx"} and index + 1 < len(lineage):
            next_folder = lineage[index + 1]
            if re.fullmatch(r"0[123]_.*", next_folder.name) and index + 2 < len(lineage):
                next_folder = lineage[index + 2]
            root = archive_province = next_folder
        elif (match := _BOX_NUMBER_FOLDER.fullmatch(name)) or re.fullmatch(r"(?:hopso|hoso)[a-z][a-z0-9]*", key):
            if match:
                box_number, note = _box_value(match, folder.name, "Hộp số")
            else:
                box_number, note = extract_clean_number_or_name(folder.name), ""
            review.pop("box_number", None)
            if note:
                review["box_number"] = note
            if not found_box and root == parent:
                root = folder.parent
        elif (not found_box and (match := _BOX_FOLDER.fullmatch(name))
              # "Từ 1990 đến 1995" (from … to) folds to the same letters as "Tủ" (cabinet).
              and not unicodedata.normalize("NFC", folder.name).casefold().startswith("từ")):
            if not archive_province or archive_province == folder:
                root = folder.parent
            box, note = _box_value(match, folder.name, "Hộp")
            found_box = True
            if note:
                review["box"] = note
    return {"province_root": str(root), "province_folder": root.name, "box": box, "box_number": box_number,
            "box_review": review}
