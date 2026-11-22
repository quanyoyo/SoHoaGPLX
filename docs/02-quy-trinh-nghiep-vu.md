# 02. Quy trình nghiệp vụ

## 1. Các bước tổng quát

1. Người dùng **tự chép** file PDF scan (qua Explorer) vào đúng thư mục `Tỉnh/Hộp/Hồ sơ` có sẵn. App không có chức năng upload.
2. App đổi tên file PDF theo quy định (mục 4).
3. App chuyển bảng trong PDF sang Excel (luồng A).
4. App ghi thông tin file vào **sổ tổng hợp của tỉnh** (`So_Theo_Doi_Day_So_GPLX_<mã tỉnh>.xlsx`).
5. App ghi dữ liệu vào CSDL SQLite để tra cứu theo các trường.

## 2. Cấu trúc thư mục (chuẩn theo code)

`src/config.py: init_digitization_structure()` tự tạo khi khởi động:

```text
So Hoa GPLX/
├── Chay_Ngay.bat, Xem_Nhat_Ky.bat
├── app/                         (bản exe)
└── DuLieuSoHoa_GPLS/
    ├── HUONG_DAN_LUU_TRU.txt
    ├── LaoCai/HOP_01/HoSo_01/
    ├── TuyenQuang/ ... DienBien/ SonLa/ HaGiang/ YenBai/ CaoBang/
    └── LangSon/ PhuTho/ BacKan/ HoaBinh/ LaiChau/   (mỗi tỉnh có HOP_01/HoSo_01)
```

- Cấp 1: **Tỉnh** (tên thư mục không dấu). Cấp 2: **HỘP** (`HOP_xx`). Cấp 3: **HỘP SỐ / Hồ sơ** (`HoSo_xx`). File PDF nằm ở cấp 3.
- Số Hộp và Hộp số được lấy từ **số cuối cùng trong tên thư mục** (`HOP_48` → `48`, `HO SO 116` → `116`), xem `src/folder_parser.py`.
- Sổ tổng hợp nằm ở thư mục **Tỉnh**.
- Thư mục mẫu `Tỉnh Yên Bái/HOP 49/HO SO 116` cũng được code nhận diện (Hộp 49, Hộp số 116).
- Số Hộp / Hộp số là số đứng ngay sau chữ "Hộp"/"Tủ"/"Hộp số"/"Hồ sơ", có thể có ký hiệu xen giữa (`HOP (49)`, `HOP#49`, `HOP_SO_115`) và có thể kèm chữ cái viết liền hoặc cách (`Hop 49A`, `HOP 49 A` → `49A`; `HO SO 116b` → `116B`). Thư mục bắt đầu bằng "Từ" (vd `Từ 1990 đến 1995`) không bị coi là Tủ. Tên thư mục còn số khác phía sau (vd `HOP 49 (2010)`) thì ô đó để trống kèm lời nhắc nhập tay. Sổ tổng hợp luôn nằm ở thư mục ngay trên thư mục Hộp.

### Mã tỉnh

- Dùng **mã tỉnh mới sau sáp nhập 2025** theo `data/province_codes.json` (34 mã). Ví dụ: thư mục `YenBai` / `Tỉnh Yên Bái` → mã **15** (Lào Cai).
- Người dùng chọn mã tỉnh ở cột trái; mã OCR đọc được trên tài liệu chỉ là **gợi ý**. Nếu khác nhau, phải tích xác nhận trước khi lưu.

## 3. Hai luồng xử lý (cả hai đều là luồng chính)

Cả hai ở tab **"📥 SỐ HÓA & ĐỔI TÊN HỒ SƠ"**, bố cục 3 cột: Hàng đợi | Xem PDF | Rà soát. Kéo vách ngăn để đổi độ rộng hàng đợi và khung Rà soát; mỗi máy nhớ độ rộng đã kéo cho lần mở sau, khung Xem PDF nhận phần còn lại. Lần đầu mở: hàng đợi 246, Xem PDF 630, Rà soát 510 (đơn vị ở Scale 100%; `PANES` trong `src/gui/app.py`), bảng GPLX ở khung Rà soát thấy khoảng 55% bề ngang. Độ rộng kéo nhỏ nhất: 180 · 380 · 470 (khung Rà soát từ 470 trở lên không ô hay nút nào bị ép).

### Luồng A — Số hóa đầy đủ

Nút **"📁 Chọn Thư mục Hồ sơ"** hoặc **"📄 Chọn File PDF lẻ"**, sau đó **"⚡ Chạy OCR Tự Động"** (hoặc bấm từng file).

1. `process_dossier_pdf(path)`:
   - Đọc trang 1: thử lớp text của PDF trước, nếu thiếu thì OCR (`cover_parser`).
   - OCR **tất cả các trang**, tìm bảng GPLX (`LicenseTableExtractor`), có cache theo (đường dẫn, kích thước, thời gian sửa).
     * **Cơ chế tự động khôi phục cột STT & Bóc tách TT B.Kê / Họ tên:**
       - Với các tài liệu scan cũ có đường kẻ dọc nét đứt mờ hoặc mép quét bị cắt mất chữ `"STT"` ở dòng tiêu đề, OCR chỉ bắt được 3 cột `TT B.Kê` | `Họ và tên` | `Năm sinh`. Dẫn đến số thứ tự (`69, 70, 71...`) lọt vào cột đầu, còn mã số hồ sơ/bảng kê (`201117, 201118...`) dính vào trước họ tên (`201117 Vu Thi Thanh`, `:201122HaVanHai`), hoặc bị gom chung ở cột 1 (`76 201124`).
       - Hệ thống tự động phân tích mẫu dữ liệu (`_recover_missing_columns`). Điều kiện: ít nhất 30% dòng có mã 4–10 chữ số dính trước họ tên hoặc dính sau STT ở cột đầu. Nếu bảng chưa có cột STT và ít nhất 50% ô cột đầu là số 1–4 chữ số, máy tách cột đầu thành STT và TT B.Kê. Máy không kiểm tra STT có tăng dần hay không.
       - Bảng đã có cả STT và TT B.Kê: dòng nào ô TT B.Kê trống mà họ tên bắt đầu bằng mã thì mã được chuyển sang ô TT B.Kê. Ô TT B.Kê dạng "mã Họ" (ví dụ "201109 Nguyén") thì mã giữ lại, phần chữ ghép lên đầu họ tên.
       - Mã có ký tự lạ phía trước ("I 201061", "|201063") hoặc có "/" giữa mã và tên ("201062/Vu Durc Cong") vẫn được tách. Ô cột đầu dạng "STT mã Họ" ("28 201076 Tran Quy") hoặc "mã Họ" ("201052 Nguyén") được tách thành STT, mã, và phần chữ ghép lên đầu họ tên.
       - Tự động tách và tái lập đầy đủ 4 cột chuẩn: `STT` (vị trí 0) | `TT B.Kê` (vị trí 1) | `Họ và tên` (vị trí 2) | `Năm sinh` (vị trí 3).
       - Tự động phân tách từ CamelCase dính liền khi OCR không có dấu cách (ví dụ `:201122HaVanHai` → mã `201122`, họ tên `Ha Van Hai`; `201127TranMinh Quang` → `Tran Minh Quang`).
       - Cả giao diện rà soát và file Excel xuất ra đều có đầy đủ, sạch sẽ 4 cột.
       - Dòng tô vàng: khôi phục cột giữ nguyên độ tin cậy OCR của ô họ tên. Thêm vào đó, dòng mà máy phải đoán chỗ bắt đầu họ tên (phần họ nằm ở cột khác) hoặc họ tên chỉ còn một chữ cũng tô vàng.
   - Tính số GPLX đầu/cuối, tổng số, dãy số, nhận định cho **cả cuốn sổ** (`summarize_license_tables`). Một PDF có nhiều danh sách vẫn là một hồ sơ: một tên file, một dòng sổ tổng hợp, một file Excel (mỗi danh sách một sheet "Danh sách GPLX n"), CSDL nhận công dân của mọi danh sách. Nhóm SQL: số đầu là số GPLX đầu của danh sách đầu, số cuối là số GPLX cuối của danh sách cuối (theo thứ tự trang); tổng số là tổng số dòng OCR đọc được ở mọi danh sách (điền cả khi còn dòng hoặc trang chưa rõ; khi đó nhận định là "Cần rà soát"); dãy số và nhận định tính trên toàn bộ. Danh sách cuối còn trang cần đối chiếu thì số cuối để trống. Danh sách nào chưa kết luận được thì nhận định "Cần rà soát" (lý do theo từng danh sách, ví dụ "Danh sách 3: Cần đối chiếu trang 11…", được lưu trong `table_review` nhưng không hiện ở khung ghi chú; trên giao diện là dòng vàng và nút "Đối chiếu trang n").
   - Lấy Hộp / Hộp số từ thư mục, đề xuất tên file.
2. Người dùng rà soát ở cột phải (sửa ngày, số QĐ, mã tỉnh, số đầu/cuối, sửa từng dòng công dân, sửa tên đề xuất). Thẻ "Rà soát dãy số" có nút "Đối chiếu trang n" cho mọi trang chưa rõ của mọi danh sách (3 nút một hàng); không còn ô chọn danh sách để đặt tên. Ô "Đang xem" của bảng chỉ để chọn danh sách hiển thị. Sửa số GPLX hoặc họ tên ở bất kỳ danh sách nào cũng tính lại tên file, tổng số và nhận định của cả sổ.
   Kiểm tra giá trị gõ ở panel (chặt hơn quy tắc đặt tên, `typed_format_errors`): Ngày thi/sát hạch phải là ngày có thật dạng `dd-mm-yyyy` (ví dụ `29-03-1996`); nhóm SQL: Số GPLX đầu/cuối viết hoa, 1–2 chữ cái và 6 chữ số liền nhau (ví dụ `AM570000`). Sai thì hiện lỗi đỏ, không đề xuất tên file và nút xác nhận xám. Ngày thi do máy đọc (OCR) được tự đổi sang `dd-mm-yyyy` khi mở file (`15/09/2015` → `15-09-2015`); giá trị người dùng đã gõ giữ nguyên. Đổi tên tự động theo folder (không qua panel) vẫn nhận dạng cũ.
   Ghi chú đặt tên **chỉ hiện lỗi** (chữ đỏ, dưới tiêu đề "Cần sửa trước khi lưu:"): lỗi đặt tên làm nút xác nhận còn xám, và ghi chú thư mục cho ô Hộp / Hộp số còn trống (ví dụ tên thư mục có nhiều số), mất đi khi đã nhập ô đó. Không còn dòng chữ đen (nhóm hồ sơ, loại giấy tờ, "Mã tỉnh OCR gợi ý", lý do theo từng danh sách). Không có lỗi thì khung ghi chú trống. "Cần rà soát" chỉ là một giá trị của ô Nhận định. Chưa chọn mã tỉnh mà OCR đọc được mã trên giấy tờ thì lỗi ghi kèm gợi ý, ví dụ "Chưa chọn mã tỉnh lưu trữ (OCR gợi ý: 15 – Tỉnh Lào Cai)."; OCR không đọc được thì không gợi ý.
   Nút xác nhận chỉ sáng khi đủ dữ liệu hợp lệ.
   Áp dụng cho cả hai luồng:
   - Trước khi lưu phải nhập đủ các ô: Loại sổ, Mã tỉnh, Ngày thi (hoặc chọn nhóm khi thiếu ngày thi), Hộp, Hộp số, Hạng, Khóa, Tổng số GPLX, Dãy số GPLX, Nhận định và các ô đặt tên của nhóm (số QĐ, ngày ký, số GPLX đầu/cuối). Giấy tờ không ghi thông tin nào thì nhập dấu `-`, sổ tổng hợp và Excel cũng ghi `-`. Dãy số được để trống khi máy đã xác nhận cột số GPLX trống, hoặc khi đổi tên nhanh đã có số đầu/cuối (sổ ghi "Đầu … · Cuối …").
   - Ngày máy đọc mà đáng ngờ thì được để trống kèm lời nhắc: năm trước 1990 hoặc sau hôm nay, ngày ký trước ngày thi (hồ sơ thi trước 01/03/2025), hoặc chữ số OCR đọc với độ tin cậy dưới 0,50.
   - Chuyển sang file khác (hoặc mở PDF từ tab tra cứu) trước khi xác nhận thì các ô đã nhập được giữ lại; quay lại file đó sẽ thấy đúng giá trị đã gõ. Chưa bấm xác nhận thì chưa có gì được lưu.
3. Bấm **"✔ XÁC NHẬN: ĐỔI TÊN PDF & XUẤT EXCEL & CẬP NHẬT TỔNG HỢP"** → `commit_dossier` (cả hai luồng cùng dùng `save_dossier`):
   - Đổi tên thật file PDF trong cùng thư mục (không giữ tên scan cũ).
   - Tạo Excel con cùng tên (`excel_generator.generate_excel_companion`).
   - Ghi/cập nhật dòng trong sổ tổng hợp tỉnh.
   - Ghi hồ sơ + danh sách công dân vào SQLite.
   - Tự chuyển sang file kế tiếp.

### Luồng B — Rà soát và đổi tên theo folder

Nút **"📑 Đổi tên file nhanh (chọn theo folder)"**.

1. `list_folder_review_pdfs(folder)` liệt kê PDF (kể cả thư mục con); file đã lưu trước đó (ghi trong sheet ẩn `_GPLX_Rename` của sổ tổng hợp) hiện trạng thái "Xong".
2. Chọn từng file → `process_dossier_pdf(..., rename_only=True)`: đọc như luồng A nhưng không hiển thị lưới công dân.
3. Bấm **"XÁC NHẬN LƯU PDF VÀ SỔ TỔNG HỢP"** → `commit_folder_dossier`:
   - Ghi liên kết nguồn → đích vào `_GPLX_Rename` (chống trùng tên với hồ sơ khác).
   - Đổi tên thật file PDF; ghi dòng sổ tổng hợp; nếu lưu sổ lỗi thì đổi tên PDF về như cũ.
   - Ghi thông tin hồ sơ vào SQLite (`save_dossier(..., with_excel=False)`), không có danh sách công dân. **Không tạo Excel con.**

> `batch_copy_and_rename_folder_pdfs` / `fast_extract_rename_metadata` trong `pipeline.py` là luồng đổi tên tự động không duyệt;
> giao diện không gọi, chỉ test dùng.

## 4. Quy tắc đặt tên

Căn cứ quy định (ảnh văn bản do chủ dự án cung cấp). Tên file **không dùng dấu `/`** (Windows cấm).
Nhóm được chọn theo **ngày thi / ngày sát hạch** (`src/naming_rules.py: propose_dossier_filename`).

| Nhóm | Điều kiện ngày thi/sát hạch | Cấu trúc tên | Ví dụ |
|---|---|---|---|
| **SQL** — Sổ quản lý GPLX | đến hết 31/12/2012 | `MãTỉnh.SQL.Tháng.Năm.SốGPLXĐầu-SốGPLXCuối` | `15.SQL.03.1996.A466375-C244132` |
| **QĐTT** — Quyết định trúng tuyển kèm danh sách | 01/01/2013 – 28/02/2025 | `MãTỉnh.SốQĐ.Ngày.Tháng.Năm` (ngày **ký** quyết định) | `15.3080.01.01.2008` |
| **QĐSH** — Hồ sơ sát hạch (công văn/QĐ/biên bản kèm danh sách) | từ 01/03/2025 | `MãTỉnh.SốQĐ.Ngày.Tháng.Năm` (ngày **sát hạch**) | `15.3081.01.01.2026` |

Chi tiết:
- Ngày trong tên dùng **dấu chấm** (đã chốt, giữ như code). Ví dụ trong văn bản `79.SQL.06/2008...` → viết đúng là `15.SQL.06.2008.AM570000-AM570200` (mã đúng là 15, không phải 79).
- Số QĐ: chỉ lấy phần số (`368/QĐ-SGTVT` → `368`); số đầy đủ vẫn giữ trong thông tin hồ sơ.
- Số GPLX: 1–2 chữ cái + 6 chữ số (`[A-Z]{1,2}[0-9]{6}`). Lấy dòng **đầu** và dòng **cuối** theo thứ tự xuất hiện trong danh sách (không phải số nhỏ nhất/lớn nhất).
  Nếu cột GPLX được xác định là trống hoàn toàn → `A000000-A000000`.
- Thiếu ngày thi: người dùng nhập ngày hoặc chọn nhóm thủ công (QĐTT có thể đặt tên chỉ với ngày ký).
- Ranh giới: sát hạch 28/02/2025 → QĐTT; từ 01/03/2025 → QĐSH. (Tin nhắn có ghi "28/5/2025", văn bản quy định ghi **28/02/2025** — dùng theo văn bản.)
- Trùng tên: báo lỗi để người dùng chọn tên khác, không ghi đè. Áp dụng cho tên trong sổ tổng hợp, PDF và Excel: đã có `<tên>.pdf` hoặc `<tên>.xlsx` của file khác trong thư mục thì không lưu, không đổi tên file nào. Chỉ Excel trùng tên với chính PDF đang lưu (số hóa lại hồ sơ cùng tên) mới được thay bằng bản mới.

### Loại hồ sơ trong quy định nhưng code **chưa hỗ trợ** (đã chốt: cần bổ sung)

| Loại | Cấu trúc tên | Ví dụ |
|---|---|---|
| Đổi GPLX nước ngoài; đổi lần đầu từ GPLX Công an, Quân đội sang dân sự | `MãTỉnh.MãĐịnhDanhCáNhân/HộChiếu` | `15.xxxxxxxxxxxx` |
| Cấp phép trung tâm sát hạch loại 1, 2 (từ 01/07/2026), loại 3 và sân tập mô tô (từ 01/03/2025) | `MãTỉnh.MãTrungTâmSH.SốQĐCấpPhép.Ngày.Tháng.Năm` | `92.92501.1368.01.07.2026` (văn bản ghi `.../01/07/2026`, đổi `/` thành `.`) |

### Đổi tên thật, không giữ file gốc (đã chốt, code đã làm)

Cả hai luồng **đổi tên hẳn** file PDF (`os.rename` trong `save_dossier`), không giữ bản có tên scan cũ. Nếu bước sau (lưu sổ tổng hợp, Excel) lỗi thì file được đổi tên về như cũ. Hàm sao chép cũ `_copy_named_pdf` vẫn còn trong `pipeline.py` nhưng không còn chỗ nào gọi.
