"""
Normalization of Vietnamese lookup fields.

Personal names keep the letters and accents that were read; known administrative place names
in addresses get their accents from a fixed gazetteer.
"""
import re
import unicodedata
from typing import Dict, List

# Administrative Gazetteer (Địa danh hành chính)
ADMIN_LOCATIONS: Dict[str, str] = {
    "yen bai": "Yên Bái", "luc yen": "Lục Yên", "van chan": "Văn Chấn",
    "van yen": "Văn Yên", "tran yen": "Trấn Yên", "tram tau": "Trạm Tấu",
    "mu cang chai": "Mù Cang Chải", "nghia lo": "Nghĩa Lộ",
    "lao cai": "Lào Cai", "bao thang": "Bảo Thắng", "bao yen": "Bảo Yên",
    "bat xat": "Bát Xát", "bac ha": "Bắc Hà", "sa pa": "Sa Pa",
    "si ma cai": "Si Ma Cai", "muong khuong": "Mường Khương",
    "tuyen quang": "Tuyên Quang", "phu tho": "Phú Thọ", "ha noi": "Hà Nội",
    "viet nam": "Việt Nam", "iviet nam": "Việt Nam"
}

def clean_vietnamese_name(raw_name: str) -> str:
    """Tidy a personal name without changing its letters or accents.

    Accents are never guessed: 'Thanh' may be Thanh or Thành, 'Nguyen' may be Nguyễn or
    Nguyên. Only Unicode form, spacing and punctuation stuck to a word ('(Ha') are cleaned,
    and a name written all in capitals is shown as 'Trần Thị Bích'.
    """
    words = [re.sub(r"^\W+|\W+$", "", word) for word in unicodedata.normalize("NFC", raw_name or "").split()]
    name = " ".join(word for word in words if word)
    if name.isupper():
        name = " ".join(word.capitalize() for word in name.split())
    return name


def normalize_vietnamese_address(raw_addr: str) -> str:
    """
    Restores accents and standardizes Vietnamese administrative addresses.
    E.g. 'H.Luc yen tinh Yen bai' -> 'H. Lục Yên, Tỉnh Yên Bái'
    """
    if not raw_addr:
        return ""
        
    addr = raw_addr.strip()
    addr_lower = addr.lower()

    # Normalize common abbreviations
    addr = re.sub(r"(?i)\bh\.\s*", "H. ", addr)
    addr = re.sub(r"(?i)\btp\.\s*", "TP. ", addr)
    addr = re.sub(r"(?i)\btx\.\s*", "TX. ", addr)
    addr = re.sub(r"(?i)\btinh\s+", "Tỉnh ", addr)
    addr = re.sub(r"(?i)\bhuyen\s+", "Huyện ", addr)

    # Replace known administrative names with accented versions
    for key, val in ADMIN_LOCATIONS.items():
        pattern = re.compile(re.escape(key), re.IGNORECASE)
        addr = pattern.sub(val, addr)

    # Clean spacing and punctuation
    addr = re.sub(r"\s+", " ", addr)
    if "Tỉnh" in addr and not addr.startswith("Tỉnh") and ", Tỉnh" not in addr:
        # Add a comma only where the address has no separator of its own ("- Tỉnh" stays).
        addr = re.sub(r"(?<=[^\s,;\-–])\s+(?=Tỉnh\b)", ", ", addr)
        
    return addr.strip()

def normalize_nationality(raw_nat: str) -> str:
    """Normalizes nationality string to 'Việt Nam'."""
    if not raw_nat or raw_nat.strip() in ['"', "''", ""]:
        return "Việt Nam"
    clean = raw_nat.lower().strip()
    if "viet" in clean or "nam" in clean:
        return "Việt Nam"
    return raw_nat.strip()
