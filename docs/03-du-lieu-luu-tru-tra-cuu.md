# 03. Dữ liệu, lưu trữ và tra cứu

Đã chốt: **giữ nguyên định dạng Excel và cấu trúc CSDL như code hiện tại.**

## 1. Excel con (mỗi PDF một file, luồng A)

Tạo bởi `src/excel_generator.py: generate_excel_companion`, cùng thư mục và cùng tên với PDF mới (`<tên>.xlsx`).

**Dạng hiện tại (`GPLX/3`) — giữ cột của bảng gốc:**
- Mỗi danh sách GPLX độc lập là một sheet `Danh sách GPLX 1`, `Danh sách GPLX 2`, ...
- Dòng 1–3: tiêu đề và thông tin hồ sơ (loại sổ, mã tỉnh, hạng, khóa, ngày thi/sát hạch, số QĐ, ngày ký).
- Dòng 4 (ẩn): **vai trò** của từng cột (`stt`, `full_name`, `birth_year`, `nationality`, `address`, `license_number`,
  `photo`, `signature`, `issue_date`, `license_class`, `register_index`, `identity`, `expiry_date`, `return_date`, `other`,
  `_page_number`, `_review`). Dùng khi đồng bộ ngược Excel → CSDL.
- Dòng 5: tiêu đề cột **đúng như bảng gốc**, rồi thêm cột `Trang PDF` và cột ẩn `_GPLX`. Người dùng sửa trực tiếp các ô trong lưới ở panel phải (cùng cột với PDF), nên Excel ghi đúng ô đã sửa; cột `_GPLX` chỉ còn dùng khi bảng có nhiều cột cùng vai trò.
- Chỉ đọc bảng có cột **Họ và tên / Họ tên** và **Năm sinh / Ngày sinh / Ngày tháng năm sinh** (kể cả tiêu đề gộp "Năm sinh | Quốc tịch"); bảng khác trong PDF (lệ phí, thống kê...) và các trang nối tiếp của nó bị bỏ qua.
- Từ dòng 6: dữ liệu. Ô cần đối chiếu có comment "Cần đối chiếu ... trang PDF n". Ảnh/chữ ký chỉ nhúng khi cắt được chắc chắn.
- Sheet ẩn `_GPLX`: ô A1 = `GPLX/3`, sau đó các cặp `trường | giá trị` của hồ sơ (`province_code`, `book_type`, `exam_date`, `decision_number`, `box`, ...).

**Dạng cũ (7 cột cố định)** — `_generate_legacy_companion`: STT, Họ và tên, Năm sinh, Quốc tịch, Nơi cư trú, Số bằng, Trang PDF.
File mẫu `HO SO 116/15.SQL.03.1996.C244337-C244498.xlsx` là dạng này. Code vẫn đọc được dạng cũ khi đồng bộ.

## 2. Sổ tổng hợp tỉnh

`<Thư mục tỉnh>/So_Theo_Doi_Day_So_GPLX_<mã tỉnh>.xlsx` — `src/master_summary.py`.

**Format theo file mẫu** `Tỉnh Yên Bái/File tổng soát số hóa GPLX.xlsx` (chủ dự án cung cấp 21/11/2026; tên file mẫu chưa theo quy tắc,
app vẫn dùng tên `So_Theo_Doi_Day_So_GPLX_<mã tỉnh>.xlsx`). Khi chưa có file, app tạo mới theo format này:

- Sheet `DANH SACH SO GOC` (vẫn đọc được sheet `Theo dõi dãy số GPLX` của file tạo bởi bản cũ).
- Dòng 1: tiêu đề "SỔ THEO DÕI, RÀ SOÁT DÃY SỐ GPLX TRONG SỔ GỐC", gộp A1:L1, Times New Roman 17 đậm chữ trắng, nền `#17324F`, cao 36.
- Dòng 2: tiêu đề cột, Times New Roman 11 đậm chữ trắng, nền `#0D766E`, cao 44. Cố định dòng 1–2 và cột A (freeze `B3`).
- Dữ liệu từ dòng 3: Times New Roman 11, căn giữa, xuống dòng, viền mảnh, cao 28.
- Vùng A2:L(dòng cuối) là **Excel Table `SoGocTongHop`** kiểu `TableStyleMedium2`; app mở rộng bảng mỗi khi thêm dòng.
- 12 cột:

| # | Cột | Nguồn / kiểu |
|---|---|---|
| 1 | STT | **tự đánh lại 1..n** từ trên xuống mỗi lần ghi, bỏ qua dòng trống ngăn cách |
| 2 | Loại sổ | `book_type` (từ trang đầu, sửa được) |
| 3 | Ngày tại bìa sổ | ngày thi/sát hạch; nhóm QĐTT ghi **ngày ký quyết định** (cả hai luồng). Kiểu **ngày Excel**, hiển thị `dd/mm/yyyy` |
| 4 | Tên file PDF | tên mới (không đuôi) — **khóa** để cập nhật đè thay vì thêm dòng |
| 5 | HỘP | từ thư mục; lưu dạng **số** (giữ dạng chữ nếu có số 0 đầu, vd `01`) |
| 6 | HỘP SỐ | như HỘP |
| 7 | Hạng | `license_class` |
| 8 | Tổng số lượng GPLX | số dòng danh sách |
| 9 | Số GPLX trong file | dãy số, vd `A161541; C244138-C244248` |
| 10 | Tổng số trang PDF | |
| 11 | Ghi chú / nhận định | `Đủ` / `Ngắt, không theo thứ tự` / `Cần rà soát` |
| 12 | Ngày cập nhật | ngày giờ ghi, hiển thị `dd/mm/yyyy hh:mm` |

- Dòng mới luôn được **thêm ngay sau bản ghi cuối cùng** (không dựa vào `max_row`, vì file mẫu có ô định dạng sẵn tới dòng 197).
  Dòng trống ngăn cách do người dùng tự chèn được giữ nguyên.
- File đã có (kể cả file người dùng tự tạo theo mẫu): app giữ nguyên định dạng, tiêu đề cột (kể cả khoảng trắng thừa) và các dòng cũ; chỉ ghi dòng mới/cập nhật dòng trùng tên file, đánh lại STT và mở rộng bảng.

- Sheet ẩn `_GPLX_Rename`: `Tên file | PDF nguồn | PDF đích | Nhóm hồ sơ | Ngày thi` (đường dẫn tương đối so với thư mục tỉnh; 2 cột cuối có từ 22/11/2026, giữ ngày thi của hồ sơ QĐTT để "🔄 Quét lại từ Excel" khôi phục đúng), **một bản ghi cho mỗi hồ sơ**, đi theo file hiện tại: PDF được **đổi tên thật** (không giữ file tên cũ); lưu lại với tên khác thì bản ghi, dòng sổ, Excel và dòng CSDL đổi theo. Cả hai luồng dùng sheet này để nhận biết file đã lưu ("✅ Xong") và chống trùng tên. File mới nằm đúng đường dẫn "PDF nguồn" của một hồ sơ đã lưu chỉ bị từ chối khi trùng nội dung với PDF đã lưu (bản sao do phiên bản cũ để lại); khác nội dung thì là hồ sơ mới.
- Khóa liên máy: trong lúc ghi sổ, app tạo file `.<tên sổ>.lock` cạnh sổ (ghi tên máy + giờ). Máy khác chờ tối đa 15 giây rồi báo "máy khác đang ghi sổ"; khóa quá 2 phút coi là bỏ dở và được lấy lại.
- Lưu hồ sơ là một thao tác trọn vẹn: Excel ghi ra file tạm → ghi bản ghi + dòng sổ → đổi tên PDF → thay Excel → lưu sổ. Lỗi ở bước nào thì đổi tên PDF về như cũ, bỏ Excel tạm. CSDL ghi sau cùng; lỗi CSDL chỉ cảnh báo (dùng "🔄 Quét lại từ Excel" để cập nhật lại).
- Lưu nguyên tử: ghi ra file tạm `.gplx-*.xlsx` rồi thay thế; nếu file đang mở trong Excel thì báo lỗi, đóng Excel rồi xác nhận lại.

## 3. CSDL SQLite

File `gplx_index.db` (vị trí xem file 01). Tạo bởi `src/database.py: DatabaseManager.init_db`.

```sql
dossiers(
  id INTEGER PK, final_filename TEXT UNIQUE, pdf_path, excel_path, province_code,
  book_type, exam_date, license_class, course, box, box_number,
  total_citizens INTEGER, total_pages INTEGER, license_sequence, status_note,
  created_at DATETIME)

citizens(
  id INTEGER PK, dossier_id → dossiers.id, stt INTEGER, full_name, full_name_unaccented,
  birth_year, nationality, address, license_number, page_number INTEGER)

-- index: citizens(license_number), citizens(full_name_unaccented), citizens(birth_year), dossiers(final_filename)
-- citizens_fts: FTS5(full_name, full_name_unaccented, license_number, address), content='citizens'
```

- Chỉ các trường trên được lưu. Các cột khác của bảng gốc (CCCD, ngày cấp, hạng từng người, số TT bảng kê, ...) **chỉ có trong Excel**.
- Ghi lại cùng `final_filename` = xóa hồ sơ cũ + công dân cũ rồi chèn mới.
- Các trường `decision_number`, `decision_date`, `dossier_group` **chưa có cột** trong bảng `dossiers`.

### Truy vấn theo trường

Có thể truy vấn trực tiếp bằng SQL (DB Browser for SQLite, `sqlite3`, Python), ví dụ:

```sql
-- Công dân theo tên không dấu + năm sinh, kèm file và trang PDF
SELECT c.full_name, c.birth_year, c.address, c.license_number, c.page_number, d.final_filename, d.pdf_path
FROM citizens c JOIN dossiers d ON d.id = c.dossier_id
WHERE c.full_name_unaccented LIKE '%tran van yen%' AND c.birth_year = '1960';

-- Hồ sơ theo tỉnh / hộp / hộp số
SELECT * FROM dossiers WHERE province_code = '15' AND box = '49' AND box_number = '116';
```

Trong app:
- **Tab Tra cứu → "👤 Tra Cứu Công Dân"**: 1 ô tìm kiếm khớp *một trong* số GPLX (chứa chuỗi), họ tên có/không dấu (chứa chuỗi), năm sinh (bằng); lọc theo tỉnh; tối đa 200 kết quả (`RESULT_LIMIT`), nhiều hơn thì ghi "Hiện 200/N kết quả đầu". Nút xem PDF đúng trang, mở Excel, mở thư mục.
- **"📁 Danh Mục Sổ / File Excel Đã Import"**: lọc theo tỉnh, hộp, từ khóa (tên file/hộp/hộp số); thống kê số tỉnh/hộp/hộp số/file; xem toàn bộ công dân của một sổ.
- **"🔄 Quét lại từ Excel"**: quét thư mục, mỗi cặp `X.pdf` + `X.xlsx` (bỏ qua `So_Theo_Doi_*`, `~$*`, `.gplx-*`) được nạp lại vào CSDL — dùng khi sửa Excel bằng tay. Sau đó đọc các sổ `So_Theo_Doi_Day_So_GPLX_<mã>.xlsx`: hồ sơ có trong sổ mà chưa có Excel (đổi tên nhanh) được tạo lại từ dòng sổ (mã tỉnh lấy từ tên sổ; PDF tìm theo `_GPLX_Rename`, không có thì tìm theo tên file trong thư mục tỉnh). Dòng sổ không còn PDF thì bỏ qua và ghi log (B9b). Trước khi nạp, các dòng CSDL có PDF nằm trong thư mục được quét mà file không còn (đã đổi tên/xóa, hoặc lưu với tên mới nhưng ghi CSDL lỗi) bị bỏ và liệt kê trong thông báo kết quả. Excel con và sổ tổng hợp được đọc từ bản sao trong bộ nhớ để máy khác vẫn lưu được trong lúc quét.

## 4. Tra cứu qua mạng (LAN/WAN)

Mô hình đã chốt: **1 máy chủ chạy app, các máy khác tra cứu bằng trình duyệt.**

- Tab **"🌐 CHIA SẺ MẠNG LAN"**: bật/tắt server (mặc định `0.0.0.0:8080`), hiện IP, QR, sao chép địa chỉ.
- Máy khác mở `http://<IP máy chủ>:8080`:

| API | Chức năng |
|---|---|
| `GET /` | Giao diện web tra cứu |
| `GET /api/status` | Trạng thái + số hồ sơ, số công dân |
| `GET /api/provinces` | Danh sách tỉnh có trong CSDL |
| `GET /api/search?q=&province=&limit=` | Tìm công dân (cùng logic tìm của desktop, tối đa 200). Kết quả có `dossier_id`, `has_excel`; **không** gửi đường dẫn file trên máy chủ |
| `GET /api/pdf/{dossier_id}` | Xem PDF của hồ sơ (trình duyệt nhảy trang bằng `#page=n`) |
| `GET /api/excel/{dossier_id}` | Tải Excel con (404 nếu hồ sơ đổi tên nhanh chưa có Excel) |
| `GET /api/qr?url=` | Ảnh QR |

- Không có đăng nhập; chỉ dùng trong LAN nội bộ. Máy chủ chỉ trả file của hồ sơ có trong CSDL (đã sửa B1), không nhận đường dẫn tùy ý.
- CSDL chỉ được mở khi máy chủ LAN khởi động hoặc có yêu cầu đầu tiên (B10).
