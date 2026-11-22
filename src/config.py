"""
Configuration and constants for GPLX Digitization and Renaming System.
"""
import os
import sys
import json
import re
import unicodedata
from src.logger import get_logger

logger = get_logger(__name__)

# Determine BASE_DIR (works for both dev source and PyInstaller frozen app)
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_resource_path(relative_path: str) -> str:
    """
    Get absolute path to resource, works for dev and for PyInstaller bundle.
    """
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            cand = os.path.join(meipass, relative_path)
            if os.path.exists(cand):
                return cand
        exe_dir = os.path.dirname(sys.executable)
        cand_exe = os.path.join(exe_dir, relative_path)
        if os.path.exists(cand_exe):
            return cand_exe
    return os.path.join(BASE_DIR, relative_path)

DATA_DIR = os.path.join(BASE_DIR, "data")
PROVINCE_CODES_FILE = get_resource_path(os.path.join("data", "province_codes.json"))

# Default folders
DEFAULT_INPUT_DIR = os.path.join(BASE_DIR, "DuLieu_GPLX", "01_ChuaXuLy")
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "DuLieu_GPLX", "02_DaXuLy_HoanThanh")
DEFAULT_ERROR_DIR = os.path.join(BASE_DIR, "DuLieu_GPLX", "03_CoLoi_CanXemLai")
def _handover_root(base_dir: str) -> str:
    parent = os.path.dirname(base_dir)
    if os.path.basename(base_dir).lower() == "app" or os.path.basename(parent).lower() == "so hoa gplx":
        return parent
    return os.path.join(base_dir, "So Hoa GPLX")


if getattr(sys, "frozen", False):
    # The packaged app is opened from the host's shared "So Hoa GPLX" folder, so every
    # machine uses the same database next to the archive. Older builds kept a private copy
    # in LocalAppData; it seeds the shared database once when the shared file is missing.
    DATABASE_PATH = os.path.join(_handover_root(BASE_DIR), "HeThong", "gplx_index.db")
    LEGACY_DATABASE_PATHS = [
        os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "GPLX", "HeThong", "gplx_index.db"),
        os.path.join(BASE_DIR, "HeThong", "gplx_index.db"),
    ]
else:
    DATABASE_PATH = os.path.join(BASE_DIR, "HeThong", "gplx_index.db")
    LEGACY_DATABASE_PATHS = []
DATABASE_BACKUP_DIR = os.path.join(os.path.dirname(DATABASE_PATH), "SaoLuu")
# Window layout (pane widths) of this machine: each screen differs, so it is not shared with the database.
UI_SETTINGS_PATH = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "GPLX", "giao_dien.json")

# Regex pattern for License Numbers:
# Historical licenses usually start with 1-2 letters (A, B, C, AM,...) followed by 5-7 digits
# E.g. A161541, C244138, AM570000, A466375, C244132
LICENSE_PATTERN = re.compile(r"([A-Za-z]{1,2})\s*([0-9]{5,7})")

def load_province_codes():
    if os.path.exists(PROVINCE_CODES_FILE):
        try:
            with open(PROVINCE_CODES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.warning("Could not load province codes from %s", PROVINCE_CODES_FILE, exc_info=True)
    # Fallback to local data folder if available
    local_path = os.path.join(BASE_DIR, "data", "province_codes.json")
    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.warning("Could not load province codes from %s", local_path, exc_info=True)
    return []

PROVINCE_CODES = load_province_codes()
# Whole-word matching: "huế" must not match inside "thuế".
_PROVINCE_PATTERNS = [
    (prov["code"], re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(unicodedata.normalize("NFC", kw).lower()) for kw in prov["keywords"]) + r")(?!\w)"
    ))
    for prov in PROVINCE_CODES if prov.get("keywords")
]

def find_province_code_by_text(text: str) -> str:
    """
    Search for matching province name or keywords from extracted text.
    Returns a province suggestion only when the text matches one code.
    """
    if not text:
        return ""
    
    text_lower = unicodedata.normalize("NFC", text).lower()
    matches = {code for code, pattern in _PROVINCE_PATTERNS if pattern.search(text_lower)}
    return next(iter(matches)) if len(matches) == 1 else ""

def get_handover_root_dir() -> str:
    """
    Xác định thư mục gốc 'So Hoa GPLX'.
    - Nếu app nằm trong '.../So Hoa GPLX/app': trả về '.../So Hoa GPLX'
    - Nếu chạy từ mã nguồn repo: trả về '[repo]/So Hoa GPLX'
    """
    return _handover_root(BASE_DIR)

def get_default_dulieu_dir() -> str:
    """
    Trả về đường dẫn tới thư mục DuLieuSoHoa_GPLS.
    """
    root = get_handover_root_dir()
    dulieu_dir = os.path.join(root, "DuLieuSoHoa_GPLS")
    if not os.path.exists(dulieu_dir):
        dulieu_dir = os.path.join(BASE_DIR, "DuLieu_GPLX")
    return dulieu_dir

def init_digitization_structure(root_dir: str = None) -> str:
    """
    Tự động khởi tạo cấu trúc thư mục chuẩn bàn giao cho người dùng Non-IT:
    📁 So Hoa GPLX/
    ├── 🚀 Chay_Ngay.bat
    ├── 📁 app/
    └── 📁 DuLieuSoHoa_GPLS/
        ├── LaoCai/HOP_01/HoSo_01/
        ├── TuyenQuang/HOP_01/HoSo_01/
        ├── DienBien/HOP_01/HoSo_01/
        ├── SonLa/HOP_01/HoSo_01/
        ├── HaGiang/HOP_01/HoSo_01/
        ├── YenBai/HOP_01/HoSo_01/
        ├── CaoBang/HOP_01/HoSo_01/
        ├── LangSon/HOP_01/HoSo_01/
        ├── PhuTho/HOP_01/HoSo_01/
        ├── BacKan/HOP_01/HoSo_01/
        ├── HoaBinh/HOP_01/HoSo_01/
        └── LaiChau/HOP_01/HoSo_01/
    Trả về đường dẫn tới thư mục DuLieuSoHoa_GPLS.
    """
    if not root_dir:
        root_dir = get_handover_root_dir()

    os.makedirs(root_dir, exist_ok=True)

    # 1. Tạo file Chay_Ngay.bat ở thư mục gốc So Hoa GPLX
    bat_path = os.path.join(root_dir, "Chay_Ngay.bat")
    # Client machines open this from a network share (\\server\...): cmd cannot "cd" into a UNC
    # path, so the exe is started by its absolute path. "&" in the title must be escaped.
    bat_content = (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "title HỆ THỐNG SỐ HÓA ^& TRA CỨU GIẤY PHÉP LÁI XE\r\n"
        "echo ========================================================\r\n"
        "echo   HỆ THỐNG SỐ HÓA VÀ TRA CỨU GIẤY PHÉP LÁI XE (GPLX)\r\n"
        "echo ========================================================\r\n"
        "echo.\r\n"
        "echo [*] Đang khởi động ứng dụng, vui lòng chờ trong giây lát...\r\n"
        "set \"APP_DIR=%~dp0app\"\r\n"
        "if exist \"%APP_DIR%\\GPLX_SoHoa_TraCuu.exe\" (\r\n"
        "    start \"\" /D \"%APP_DIR%\" \"%APP_DIR%\\GPLX_SoHoa_TraCuu.exe\"\r\n"
        ") else (\r\n"
        "    if exist \"%~dp0app_desktop.py\" (\r\n"
        "        python \"%~dp0app_desktop.py\"\r\n"
        "    ) else (\r\n"
        "        echo [!] Không tìm thấy GPLX_SoHoa_TraCuu.exe trong thư mục app.\r\n"
        "        pause\r\n"
        "    )\r\n"
        ")\r\n"
        "exit\r\n"
    )
    try:
        current = None
        if os.path.exists(bat_path):
            with open(bat_path, encoding="utf-8", errors="replace", newline="") as f:
                current = f.read()
        if current != bat_content:
            with open(bat_path, "w", encoding="utf-8", newline="") as f:
                f.write(bat_content)
    except OSError:
        logger.exception("Could not create startup script at %s", bat_path)

    # Shortcut to open the latest readable application log.
    log_viewer_path = os.path.join(root_dir, "Xem_Nhat_Ky.bat")
    if not os.path.exists(log_viewer_path):
        log_viewer_content = (
            "@echo off\r\n"
            "setlocal\r\n"
            "if not defined LOCALAPPDATA set \"LOCALAPPDATA=%APPDATA%\"\r\n"
            "set \"LOG_DIR=%LOCALAPPDATA%\\GPLX\\logs\"\r\n"
            "if not exist \"%LOG_DIR%\" (\r\n"
            "  echo Chua co log. Hay mo ung dung va thuc hien lai thao tac gap loi.\r\n"
            "  pause\r\n"
            "  exit /b 1\r\n"
            ")\r\n"
            "for /f \"delims=\" %%F in ('dir /b /o-d \"%LOG_DIR%\\app_*.log\" 2^>nul') do (\r\n"
            "  start \"\" notepad \"%LOG_DIR%\\%%F\"\r\n"
            "  exit /b 0\r\n"
            ")\r\n"
            "echo Chua co file log ung dung trong: %LOG_DIR%\r\n"
            "pause\r\n"
        )
        try:
            with open(log_viewer_path, "w", encoding="utf-8") as f:
                f.write(log_viewer_content)
        except OSError:
            logger.exception("Could not create log viewer at %s", log_viewer_path)

    # 2. Tạo thư mục app
    app_dir = os.path.join(root_dir, "app")
    os.makedirs(app_dir, exist_ok=True)

    # 3. Tạo kho dữ liệu số hóa theo tỉnh/hộp/hồ sơ
    dulieu_dir = os.path.join(root_dir, "DuLieuSoHoa_GPLS")
    os.makedirs(dulieu_dir, exist_ok=True)

    provinces = [
        "LaoCai", "TuyenQuang", "DienBien", "SonLa",
        "HaGiang", "YenBai", "CaoBang", "LangSon",
        "PhuTho", "BacKan", "HoaBinh", "LaiChau"
    ]
    for prov in provinces:
        hoso_dir = os.path.join(dulieu_dir, prov, "HOP_01", "HoSo_01")
        os.makedirs(hoso_dir, exist_ok=True)

    # 4. Tạo file hướng dẫn lưu trữ tại DuLieuSoHoa_GPLS
    readme_path = os.path.join(dulieu_dir, "HUONG_DAN_LUU_TRU.txt")
    if True:  # rewritten when the app's instructions change
        readme_content = (
            "====================================================================\r\n"
            "QUY TẮC LƯU TRỮ VÀ TỔ CHỨC FILE SCAN PDF SỐ HÓA GPLX\r\n"
            "====================================================================\r\n\r\n"
            "1. CẤU TRÚC THƯ MỤC:\r\n"
            "   DuLieuSoHoa_GPLS/\r\n"
            "   ├── [Tên_Tỉnh]/              (Ví dụ: LaoCai, TuyenQuang, DienBien,...)\r\n"
            "   │   └── HOP_[Số_Hộp]/        (Ví dụ: HOP_01, HOP_02, ...)\r\n"
            "   │       └── HoSo_[Số_Hồ_Sơ]/ (Ví dụ: HoSo_01, HoSo_02, ...)\r\n"
            "   │           └── [Các file scan PDF]\r\n\r\n"
            "2. ĐỔI TÊN FILE NHANH (CHỈ ĐỌC TRANG ĐẦU):\r\n"
            "   - Đặt các file PDF scan gốc vào thư mục HoSo tương ứng.\r\n"
            "   - Mở ứng dụng, chọn tab 'Số hóa & Đổi tên hồ sơ'.\r\n"
            "   - Nhấn nút '📑 Đổi tên file nhanh (chọn theo folder)' và chọn thư mục HoSo.\r\n"
            "   - Ứng dụng đọc trang đầu để điền ngày và số quyết định; số GPLX đầu/cuối,\r\n"
            "     tổng số GPLX, dãy số và nhận định do người dùng nhập.\r\n"
            "   - Bấm 'Xác nhận lưu PDF và sổ tổng hợp' sau khi kiểm tra tên đề xuất.\r\n\r\n"
            "3. SỐ HÓA ĐẦY ĐỦ:\r\n"
            "   - Nhấn '📁 Chọn Thư mục Hồ sơ' hoặc '📄 Chọn File PDF lẻ', đọc OCR, rà soát bảng\r\n"
            "     rồi xác nhận để đổi tên PDF, xuất Excel và cập nhật sổ tổng hợp.\r\n\r\n"
            "4. LƯU Ý:\r\n"
            "   - PDF được ĐỔI TÊN THẬT, không giữ file tên cũ. Tên cũ được ghi trong sheet ẩn\r\n"
            "     _GPLX_Rename của sổ tổng hợp tỉnh.\r\n"
            "   - Mỗi lần chọn thư mục/file, danh sách bên trái được làm mới. File đã lưu có dấu '✅ Xong'\r\n"
            "     và vẫn mở được để sửa và lưu lại.\r\n"
            "   - Nếu sổ tổng hợp đang mở trong Excel, đóng sổ rồi xác nhận lại.\r\n"
            "   - Không mở PDF đang đổi tên bằng chương trình khác (kể cả trên máy khác).\r\n"
        )
        try:
            current = None
            if os.path.exists(readme_path):
                with open(readme_path, encoding="utf-8", errors="replace", newline="") as f:
                    current = f.read()
            if current != readme_content:
                with open(readme_path, "w", encoding="utf-8", newline="") as f:
                    f.write(readme_content)
        except OSError:
            logger.exception("Could not create storage instructions at %s", readme_path)

    return dulieu_dir
