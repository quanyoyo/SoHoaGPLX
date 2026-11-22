"""
Portable Build Script for GPLX Management System using PyInstaller.
Creates a complete standalone, 1-click handover package:
📁 So Hoa GPLX/
├── 🚀 Chay_Ngay.bat
├── 📁 app/                           (GPLX_SoHoa_TraCuu.exe + bundled runtimes)
└── 📁 DuLieuSoHoa_GPLS/              (Pre-initialized provinces, boxes, dossiers)
    ├── 📁 LaoCai/HOP_01/HoSo_01/
    ├── 📁 TuyenQuang/HOP_01/HoSo_01/
    ├── 📁 DienBien/HOP_01/HoSo_01/
    └── ...
"""
import os
import sys
import shutil
import subprocess
import tempfile
import zipfile

# Avoid Windows console code pages aborting the build on Vietnamese output.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="replace")

def _runtime_file(filename):
    """Locks, Excel owner files and save leftovers made while the app runs."""
    name = filename.lower()
    return name.endswith((".lock", ".gplx-old", ".old")) or name.startswith(("~$", ".gplx-"))


def _copy_tree_safe(src_dir, dst_dir):
    """Copies src_dir into dst_dir. If a destination file is in use by a running app,
    it renames the active file to .old first so the updated file can be placed."""
    for root, dirs, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        target_root = os.path.join(dst_dir, rel) if rel != "." else dst_dir
        os.makedirs(target_root, exist_ok=True)
        for f in files:
            src_file = os.path.join(root, f)
            dst_file = os.path.join(target_root, f)
            try:
                shutil.copy2(src_file, dst_file)
            except (PermissionError, OSError):
                old_file = dst_file + ".old"
                try:
                    if os.path.exists(old_file):
                        os.remove(old_file)
                except OSError:
                    pass
                try:
                    os.rename(dst_file, old_file)
                    shutil.copy2(src_file, dst_file)
                except OSError as exc:
                    raise exc


def build():
    print("=" * 70)
    print(" BẮT ĐẦU ĐÓNG GÓI PORTABLE ỨNG DỤNG SỐ HÓA GPLX CHO NGƯỜI DÙNG NON-IT ")
    print("=" * 70)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(base_dir, "dist")
    build_dir = os.path.join(base_dir, "build")
    handover_dir = os.path.join(base_dir, "So Hoa GPLX")
    app_target_dir = os.path.join(handover_dir, "app")
    zip_path = os.path.join(base_dir, "So Hoa GPLX.zip")

    # Data files
    data_json = os.path.join(base_dir, "data", "province_codes.json")
    static_html = os.path.join(base_dir, "src", "server", "static", "index.html")

    datas = [
        f"{data_json};data/",
        f"{static_html};src/server/static/"
    ]

    datas_args = []
    for d in datas:
        datas_args.extend(["--add-data", d])

    collect_packages = [
        "customtkinter",
        "rapidocr_onnxruntime",
        "pypdfium2",
        "openpyxl",
        "fastapi",
        "uvicorn",
        "starlette"
    ]
    collect_args = []
    for pkg in collect_packages:
        collect_args.extend(["--collect-all", pkg])

    hidden_imports = [
        "PIL",
        "PIL.ImageTk",
        "qrcode",
        "sqlite3"
    ]
    hidden_args = []
    for h in hidden_imports:
        hidden_args.extend(["--hidden-import", h])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "GPLX_SoHoa_TraCuu",
        "--onedir",
        "--windowed",
        "--noconfirm",
        "--clean",
    ] + datas_args + collect_args + hidden_args + [
        os.path.join(base_dir, "app_desktop.py")
    ]

    package_only = "--package-only" in sys.argv
    built_app_dir = os.path.join(dist_dir, "GPLX_SoHoa_TraCuu")

    if package_only:
        print("[*] Chế độ --package-only: Bỏ qua bước build PyInstaller...")
        if not os.path.exists(built_app_dir):
            print(f"[!] Không tìm thấy thư mục dist sẵn có: {built_app_dir}")
            return False
    else:
        print("[*] Đang thực thi lệnh PyInstaller (vui lòng đợi khoảng 1-2 phút)...")
        result = subprocess.run(cmd, cwd=base_dir)
        if result.returncode != 0:
            print("\n[!] Đóng gói thất bại với mã lỗi:", result.returncode)
            return False

        if not os.path.exists(built_app_dir):
            print(f"[!] Không tìm thấy thư mục dist: {built_app_dir}")
            return False

    print("\n[*] Đang tổ chức thư mục bàn giao chuẩn 'So Hoa GPLX'...")
    os.makedirs(handover_dir, exist_ok=True)

    # 1. Update the runtime bundle in place and preserve the database as a
    # one-time migration seed. PyInstaller's onedir output is version matched;
    # overlaying avoids Windows denying deletion of loaded/protected DLL files.
    seed_db = os.path.join(app_target_dir, "HeThong", "gplx_index.db")
    with tempfile.TemporaryDirectory(prefix="gplx-build-") as temp_dir:
        saved_seed = os.path.join(temp_dir, "gplx_index.db")
        if os.path.isfile(seed_db):
            shutil.copy2(seed_db, saved_seed)
        os.makedirs(app_target_dir, exist_ok=True)
        try:
            _copy_tree_safe(built_app_dir, app_target_dir)
        except (PermissionError, shutil.Error, OSError) as exc:
            print("[!] Không thể cập nhật gói vì file ứng dụng đang được sử dụng.")
            print("    Hãy đóng GPLX_SoHoa_TraCuu.exe rồi mở lại Build_So_Hoa_GPLX.bat.")
            print(f"    Chi tiết: {exc}")
            return False
        if os.path.isfile(saved_seed):
            os.makedirs(os.path.dirname(seed_db), exist_ok=True)
            shutil.copy2(saved_seed, seed_db)
    print(f"    -> Đã đưa ứng dụng vào: {app_target_dir}")

    # 2. Khởi tạo cấu trúc thư mục DuLieuSoHoa_GPLS và Chay_Ngay.bat
    sys.path.insert(0, base_dir)
    from src.config import init_digitization_structure
    dulieu_dir = init_digitization_structure(root_dir=handover_dir)
    print(f"    -> Đã khởi tạo kho dữ liệu: {dulieu_dir}")

    # 3. Sao chép sample PDF vào LaoCai/HOP_01/HoSo_01 để người dùng test ngay
    sample_src = os.path.join(base_dir, "samples", "sample_input.pdf")
    if os.path.exists(sample_src):
        sample_dst = os.path.join(dulieu_dir, "LaoCai", "HOP_01", "HoSo_01", "sample_input.pdf")
        shutil.copyfile(sample_src, sample_dst)
        print(f"    -> Đã sao chép file scan mẫu: {sample_dst}")

    # 4. Add a short customer guide at the package root.
    guide_path = os.path.join(handover_dir, "HUONG_DAN_SU_DUNG.txt")
    with open(guide_path, "w", encoding="utf-8") as guide:
        guide.write(
            "HUONG DAN SU DUNG SO HOA GPLX\n\n"
            "1. Giai nen nguyen folder 'So Hoa GPLX' vao vi tri ban muon.\n"
            "2. Mo folder vua giai nen va nhap dup 'Chay_Ngay.bat'.\n"
            "3. Chon cac file PDF trong kho DuLieuSoHoa_GPLS de xu ly.\n\n"
            "Khong can cai Python hoac thu vien. Nen giai nen vao noi ban co quyen ghi du lieu.\n\n"
            "DUNG CHUNG QUA MANG LAN:\n"
            "- May chu: chia se folder 'So Hoa GPLX' (quyen doc + ghi) cho cac may con.\n"
            "- May con: mo folder chia se qua mang LAN va chay 'Chay_Ngay.bat'. OCR chay tren may con;\n"
            "  PDF, Excel va co so tra cuu dung chung trong folder nay.\n"
            "- Co so tra cuu: So Hoa GPLX\\HeThong\\gplx_index.db. Moi ngay tu sao luu 1 ban vao\n"
            "  HeThong\\SaoLuu (giu 7 ban gan nhat).\n\n"
            "Xem log loi bang cach mo file Xem_Nhat_Ky.bat (log luu tren tung may, LocalAppData\\GPLX\\logs).\n"
            "Goi nay danh cho Windows 64-bit.\n"
        )

    required_files = [
        os.path.join(handover_dir, "Chay_Ngay.bat"),
        os.path.join(handover_dir, "Xem_Nhat_Ky.bat"),
        os.path.join(handover_dir, "HUONG_DAN_SU_DUNG.txt"),
        os.path.join(app_target_dir, "GPLX_SoHoa_TraCuu.exe"),
        os.path.join(app_target_dir, "_internal"),
        os.path.join(handover_dir, "DuLieuSoHoa_GPLS"),
    ]
    missing = [path for path in required_files if not os.path.exists(path)]
    if missing:
        print("[!] Gói bàn giao thiếu thành phần bắt buộc:")
        for path in missing:
            print(f"    - {path}")
        return False

    # 5. Zip the entire handover directory, including empty folders, and keep
    # the single root folder so extraction can happen anywhere.
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for current_dir, dirnames, filenames in os.walk(handover_dir):
            if os.path.normcase(current_dir) == os.path.normcase(handover_dir):
                # The shared database and its backups are created at run time, never shipped.
                dirnames[:] = [d for d in dirnames if d.lower() != "hethong"]
            for dirname in dirnames:
                folder_path = os.path.join(current_dir, dirname)
                folder_name = os.path.relpath(folder_path, base_dir).replace(os.sep, "/") + "/"
                archive.writestr(folder_name, "")
            for filename in filenames:
                if _runtime_file(filename):
                    continue
                file_path = os.path.join(current_dir, filename)
                archive_name = os.path.relpath(file_path, base_dir).replace(os.sep, "/")
                archive.write(file_path, archive_name)
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        if not names or any(not name.startswith("So Hoa GPLX/") for name in names):
            print("[!] ZIP không đúng cấu trúc gốc 'So Hoa GPLX/'.")
            return False
        if "So Hoa GPLX/app/GPLX_SoHoa_TraCuu.exe" not in names:
            print("[!] ZIP thiếu file ứng dụng EXE.")
            return False

    print("\n" + "=" * 70)
    print(">>> ĐÓNG GÓI HOÀN TẤT VÀ SẴN SÀNG BÀN GIAO CHO NGƯỜI DÙNG NON-IT! <<<")
    print(f"Vị trí gói bàn giao: {handover_dir}")
    print(f"ZIP sẵn sàng gửi khách hàng: {zip_path}")
    print("Cấu trúc:")
    print("  So Hoa GPLX/")
    print("  ├── Chay_Ngay.bat                (Nhấp đúp chuột để mở app)")
    print("  ├── app/                        (Ứng dụng độc lập + thư viện)")
    print("  │   └── GPLX_SoHoa_TraCuu.exe")
    print("  └── DuLieuSoHoa_GPLS/           (Kho dữ liệu chuẩn hóa Tỉnh/Hộp/Hồ sơ)")
    print("=" * 70)
    return True

if __name__ == "__main__":
    sys.exit(0 if build() else 1)
