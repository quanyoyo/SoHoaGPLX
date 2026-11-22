# 01. Kiến trúc và công nghệ

## 1. Mô hình tổng thể

- **Ứng dụng desktop Windows** viết bằng Python, chạy trên **một máy chủ** (máy giữ kho dữ liệu). Chỉ máy này số hóa, đổi tên, ghi Excel và CSDL.
- **Máy chủ web nội bộ** (FastAPI) bật/tắt từ tab "Chia sẻ mạng LAN" trong app. Các máy khác trong mạng LAN/WAN (mạng đã được setup sẵn)
  mở trình duyệt để **tra cứu**, xem PDF và tải Excel. Máy khác không số hóa.
- Không cần cài DBMS: CSDL là một file SQLite.

```text
┌──────────────────────── MÁY CHỦ ────────────────────────┐
│ app_desktop.py → GPLXApp (CustomTkinter, 3 tab)          │
│   Tab 1 Số hóa & đổi tên ─┐                              │
│   Tab 2 Tra cứu ──────────┼──► src/pipeline.py ...       │
│   Tab 3 Chia sẻ LAN ──► src/server/lan_server.py (:8080) │
│                                                          │
│ Kho file: Tỉnh/Hộp/Hồ sơ/*.pdf, *.xlsx, sổ tổng hợp tỉnh │
│ CSDL: gplx_index.db (SQLite)                             │
└──────────────────────────────────────────────────────────┘
          ▲ HTTP (trình duyệt)
   Máy trạm 1, 2, ... (chỉ tra cứu)
```

## 2. Công nghệ đang dùng (theo code)

| Thành phần | Thư viện |
|---|---|
| Giao diện | `customtkinter` + `tkinter.PanedWindow` (3 cột kéo giãn) |
| Đọc / render PDF | `pypdfium2` (render 200 DPI, đọc lớp text nếu có), `Pillow` |
| OCR | `rapidocr_onnxruntime` (PaddleOCR dạng ONNX, chạy CPU) |
| Phân tích lưới bảng, cắt ảnh | `opencv` (`cv2`), `numpy` |
| Excel | `openpyxl` |
| CSDL | `sqlite3` (có bảng FTS5 nhưng tìm kiếm đang dùng `LIKE`) |
| Máy chủ LAN | `fastapi`, `uvicorn`, `qrcode`; giao diện web là 1 file `src/server/static/index.html` thuần HTML/JS |
| Đóng gói | `PyInstaller` qua `build_portable.py` / `Build_So_Hoa_GPLX.bat` → `So Hoa GPLX.zip` |
| Log | `logging` + `RotatingFileHandler`, ghi ở `%LOCALAPPDATA%\GPLX\logs\app_YYYY-MM-DD.log` |

> `TECH_ARCHITECTURE.md` cũ nhắc tới Tauri/Electron, PaddleOCR + VietOCR, PyMuPDF, `gplx_data.db` — **không có trong code**.

## 3. Bản đồ module

| File | Vai trò |
|---|---|
| `app_desktop.py` | Điểm vào: cấu hình log, tạo cấu trúc thư mục, mở `GPLXApp` |
| `src/config.py` | Đường dẫn gốc, đường dẫn CSDL, nạp `data/province_codes.json`, tự tạo cây thư mục bàn giao |
| `src/logger.py` | Log file, bắt lỗi chưa xử lý, popup lỗi |
| `src/pdf_processor.py` | Mở PDF, đếm trang, đọc text, render trang (có khóa `PDFIUM_LOCK` vì OCR và preview chạy song song) |
| `src/ocr_engine.py` | Khởi tạo RapidOCR một lần, `run_ocr(image)` → `[box, text, score]` |
| `src/cover_parser.py` | Nhận diện trang đầu: bìa sổ / quyết định / quyết định kèm danh sách; trích ngày thi, số QĐ, ngày ký, tỉnh, hạng, khóa |
| `src/table_extractor.py` | `LicenseTableExtractor`: tìm bảng GPLX theo tiêu đề cột, gán vai trò cột, nối bảng qua nhiều trang, tách các danh sách độc lập; tự động khôi phục cột STT bị thiếu do quét OCR mất mép trái và bóc tách mã bảng kê (TT B.Kê) dính vào họ tên |
| `src/vietnamese_utils.py` | Làm gọn họ tên (giữ nguyên chữ và dấu đã đọc, không đoán dấu), chuẩn hóa địa chỉ, quốc tịch |
| `src/naming_rules.py` | Quy tắc đặt tên 3 nhóm SQL / QĐTT / QĐSH, kiểm tra tên file hợp lệ trên Windows |
| `src/sequence_analyzer.py` | Gom dãy số GPLX liên tiếp, đánh giá "Đủ" / "Ngắt, không theo thứ tự" |
| `src/folder_parser.py` | Lấy Tỉnh / Hộp / Hồ sơ từ đường dẫn PDF |
| `src/excel_generator.py` | Xuất Excel con (dạng mới giữ cột nguồn; còn hàm dạng cũ 7 cột) |
| `src/master_summary.py` | Tạo/cập nhật sổ tổng hợp tỉnh, lưu nguyên tử qua file tạm |
| `src/database.py` | `DatabaseManager`: tạo bảng, ghi hồ sơ + công dân, tìm kiếm, đồng bộ lại từ Excel |
| `src/pipeline.py` | Điều phối: `process_dossier_pdf` (đọc), `commit_dossier` (lưu luồng A), `commit_folder_dossier` (lưu luồng B), `list_folder_review_pdfs` |
| `src/gui/app.py` | Cửa sổ chính, luồng nền OCR (1 worker), hàng đợi tác vụ UI |
| `src/gui/batch_queue.py` | Cột trái: chọn tỉnh, chọn thư mục / file / thư mục đổi tên, danh sách file (một bảng `ttk.Treeview`: trạng thái, tên file) |
| `src/gui/pdf_viewer.py` | Cột giữa: xem PDF, zoom, xoay, nhảy trang |
| `src/gui/review_panel.py` | Cột phải: form thông tin hồ sơ, tên đề xuất, lưới công dân, nút xác nhận |
| `src/gui/search_screen.py` | Tab tra cứu: tìm công dân, danh mục sổ đã import, đồng bộ từ Excel |
| `src/gui/lan_screen.py` | Tab LAN: bật/tắt server, IP, QR, thống kê |
| `src/server/lan_server.py` | API `/api/status`, `/api/provinces`, `/api/search`, `/api/pdf/{dossier_id}`, `/api/excel/{dossier_id}`, `/api/qr` |
| `test_*.py` (thư mục gốc) | Script kiểm thử theo phase |

## 4. Đường dẫn quan trọng (theo `src/config.py`)

| Mục | Chạy từ mã nguồn | Chạy bản đóng gói (exe) |
|---|---|---|
| `BASE_DIR` | thư mục repo | thư mục chứa exe (`So Hoa GPLX/app`) |
| Kho dữ liệu | `<repo>/So Hoa GPLX/DuLieuSoHoa_GPLS` (nếu chưa có thì `<repo>/DuLieu_GPLX`) | `So Hoa GPLX/DuLieuSoHoa_GPLS` |
| CSDL | `<repo>/HeThong/gplx_index.db` | `So Hoa GPLX/HeThong/gplx_index.db` — **dùng chung** cho mọi máy mở app từ thư mục chia sẻ của máy chủ (LAN). Lần đầu nếu chưa có thì chép từ CSDL cũ `%LOCALAPPDATA%\GPLX\HeThong` hoặc `app/HeThong`. Sao lưu hằng ngày vào `HeThong/SaoLuu/gplx_index_YYYYMMDD.db` (giữ 7 bản). Đường dẫn PDF/Excel lưu **tương đối** so với `So Hoa GPLX` vì mỗi máy thấy ổ chia sẻ theo đường dẫn khác. |
| Danh mục tỉnh | `data/province_codes.json` | đóng gói kèm exe |
| Log | `%LOCALAPPDATA%\GPLX\logs` | như bên trái (log riêng từng máy) |
| Độ rộng khung đã kéo (tab Số hóa) | `%LOCALAPPDATA%\GPLX\giao_dien.json` | như bên trái (riêng từng máy vì mỗi máy một màn hình; xóa file thì về độ rộng lần đầu) |

## 5. Chạy và kiểm thử

- Cần Python 3.10+ và các thư viện ở bảng trên, ghi kèm phiên bản trong `requirements.txt`. `.venv` (Python 3.14) đã được tạo ngày 21/11/2026. Cài thư viện: `.venv\Scripts\python.exe -m pip install -r requirements.txt`.
- Chạy app: `.venv\Scripts\python.exe app_desktop.py` (PowerShell).
- Chạy test (thư mục gốc repo): `.venv\Scripts\python.exe -m unittest test_folder_review_v3 test_master_summary_format test_license_tables_v3 test_document_metadata_v3 test_excel_v3 test_naming_rules_v3 test_phase6_representative test_logger`. Không chạy `test_phase2.py` cùng bộ này: nó OCR thật và ghi vào `samples/`.
- Đóng gói: `Build_So_Hoa_GPLX.bat` → `build_portable.py`.
