# SỔ TAY HƯỚNG DẪN SỬ DỤNG HỆ THỐNG
## PHẦN MỀM SỐ HÓA, TỰ ĐỘNG ĐỔI TÊN & TRA CỨU HỒ SƠ GIẤY PHÉP LÁI XE (GPLX)
*Dành riêng cho cán bộ nghiệp vụ và nhân viên số hóa (Không yêu cầu kiến thức Công nghệ thông tin)*

---

## 1. GIỚI THIỆU TỔNG QUAN

Hệ thống được thiết kế chuyên biệt phục vụ công tác số hóa, lưu trữ, quản lý và tra cứu hồ sơ cấp Giấy phép lái xe (GPLX) cơ giới đường bộ qua các thời kỳ lịch sử (trước 2012, 2013–2025 và sau 2025) theo đúng quy chuẩn lưu trữ quốc gia.

### 🌟 Các tính năng và ưu điểm nổi bật:
1. **Khởi chạy 1-Click (Dành cho Non-IT)**: Toàn bộ hệ thống được đóng gói trọn gói dạng Portable trong thư mục `So Hoa GPLX`. Chỉ cần nhấp đúp vào **`Chay_Ngay.bat`** là ứng dụng mở và hoạt động ngay lập tức, không cần cài đặt Python, không cần cài đặt CSDL hay cấu hình môi trường.
2. **Bố cục 3 khung thông minh & Tự nhớ vị trí**:
   - Giao diện số hóa chia 3 khung linh hoạt; khi mở lần đầu: **Hàng đợi file (246)** · **Xem PDF (630)** · **Rà soát dữ liệu (510)**.
   - Khi mở lần đầu, bảng danh sách GPLX ở khung Rà soát hiển thị khoảng **55%** bề ngang; kéo ngang bảng để xem các cột còn lại.
   - Người dùng có thể kéo vách ngăn để tùy chỉnh độ rộng hàng đợi và khung Rà soát; khung Xem PDF nhận phần còn lại. Phần mềm tự ghi nhớ vị trí vách ngăn cho các lần mở sau, riêng từng máy.
3. **Quy tắc đặt tên 3 giai đoạn tự động**:
   - Nhận diện chính xác loại tài liệu (Sổ quản lý `SQL`, Quyết định trúng tuyển `QĐTT`, Quyết định sát hạch `QĐSH`) dựa trên ngày thi / ngày sát hạch và ngày ký quyết định.
4. **Đổi tên thật, an toàn khi lỗi**:
   - File PDF scan được **đổi tên hẳn** sang tên chuẩn ngay trong thư mục của nó (không giữ bản mang tên scan cũ); file Excel con được tạo cạnh đó.
   - Nếu lưu sổ tổng hợp hoặc Excel bị lỗi, file PDF được đổi về tên cũ. Đã có file khác trùng tên thì phần mềm báo lỗi, không ghi đè.
5. **Xuất Excel động trung thực theo bảng scan**:
   - Tự động sinh file Excel con (`.xlsx`) phản ánh trung thực thứ tự cột, nội dung và số trang PDF của tài liệu gốc. Hỗ trợ tài liệu có nhiều danh sách độc lập thành nhiều sheet tương ứng.
6. **Sổ theo dõi dãy số GPLX cấp tỉnh (Master Summary)**:
   - Tự động tạo và cập nhật file Excel tổng hợp `So_Theo_Doi_Day_So_GPLX_<MãTỉnh>.xlsx` với 12 cột chuẩn, tự động phân tích dãy số liên tục ("Đủ") hay ngắt quãng ("Ngắt, không theo thứ tự").
7. **Tra cứu siêu tốc & 1-Click lật đúng trang PDF**:
   - Tìm kiếm công dân theo Họ tên (có dấu / không dấu), Số GPLX, Năm sinh. Bấm vào kết quả là trình xem PDF tự động lật đến đúng trang scan của người dân.
8. **Chia sẻ mạng nội bộ (LAN Server 1-Click)**:
   - Máy chủ bật chia sẻ là các máy tính khác hoặc điện thoại trong phòng có thể tra cứu, xem PDF và tải Excel qua trình duyệt mà không cần cài đặt phần mềm.

---

## 2. CẤU TRÚC THƯ MỤC BÀN GIAO CHUẨN

Gói ứng dụng bàn giao chuẩn được tổ chức như sau:

```text
📁 So Hoa GPLX/
│
├── 🚀 Chay_Ngay.bat                 <-- [QUAN TRỌNG] Nhấp đúp chuột để mở ứng dụng
├── 📝 Xem_Nhat_Ky.bat               <-- Mở nhanh thư mục log để chẩn đoán lỗi khi cần
├── 📄 HUONG_DAN_SU_DUNG.txt         <-- Hướng dẫn tóm tắt kèm theo gói
│
├── 📁 app/                          <-- Phần mềm chạy độc lập (.exe) cùng thư viện nhúng
│   ├── GPLX_SoHoa_TraCuu.exe        <-- File thực thi chính
│   └── _internal/                   <-- Lõi OCR, PDF Engine, SQLite nhúng
│
└── 📁 DuLieuSoHoa_GPLS/             <-- KHO LƯU TRỮ HỒ SƠ CHUẨN 3 CẤP
    ├── HUONG_DAN_LUU_TRU.txt
    │
    ├── 📁 LaoCai/                   <-- Cấp 1: Thư mục Tỉnh (không dấu)
    │   ├── So_Theo_Doi_Day_So_GPLX_15.xlsx  <-- Sổ tổng hợp cấp tỉnh
    │   └── 📁 HOP_01/               <-- Cấp 2: HỘP / Tủ hồ sơ (HOP_xx)
    │       └── 📁 HoSo_01/          <-- Cấp 3: HỘP SỐ / Tập hồ sơ (HoSo_xx)
    │           ├── scan_002.pdf                     <-- File scan chưa xử lý (tên do đơn vị scan đặt)
    │           ├── 15.SQL.03.1996.C244501-C244608.pdf   <-- File scan đã đổi tên chuẩn (tên cũ không còn)
    │           └── 15.SQL.03.1996.C244501-C244608.xlsx  <-- Excel trích xuất kèm
    │
    ├── 📁 YenBai/
    ├── 📁 TuyenQuang/
    ├── 📁 PhuTho/
    └── 📁 ... (các tỉnh khác)
```

> [!TIP]
> Ứng dụng tự động nhận diện cấu trúc phân cấp từ đường dẫn:
> - Tên thư mục cấp 2 (`HOP_49`, `Hộp 49`, `TU-49`) -> Nhận diện HỘP: **49**.
> - Tên thư mục cấp 3 (`HoSo_116`, `HO SO 116`) -> Nhận diện HỘP SỐ: **116**.

---

## 3. HƯỚNG DẪN KHỞI CHẠY ỨNG DỤNG

1. Chép hoặc giải nén toàn bộ thư mục **`So Hoa GPLX`** vào vị trí bạn muốn (khuyến nghị để ở ổ cứng SSD di động hoặc ổ `D:\`, nơi bạn có toàn quyền ghi file).
2. Nhấp đúp chuột trái vào file **🚀 `Chay_Ngay.bat`**.
3. Ứng dụng sẽ tự động khởi động và phóng to cửa sổ làm việc. Toàn bộ CSDL và cấu hình đều tự khởi tạo "Zero-Config".

---

## 4. QUY TRÌNH SỐ HÓA & ĐỔI TÊN HỒ SƠ (TAB 1)

Giao diện Tab 1 gồm **3 khung làm việc song song**:
- **Khung 1 (Trái - 246 khi mở lần đầu)**: Hàng đợi danh sách file và các nút chọn thư mục, chạy OCR.
- **Khung 2 (Giữa - phần còn lại, 630 trên màn hình rộng)**: Trình xem trước bản scan PDF (phóng to/thu nhỏ, xoay trang, cuộn 2 chiều).
- **Khung 3 (Phải - 510 khi mở lần đầu)**: Màn hình rà soát bìa sổ, dải số và bảng dữ liệu công dân (thấy khoảng 55% bề ngang bảng khi mở lần đầu).

*Các số trên là độ rộng ở Scale 100% của Windows; màn hình đặt Scale 200% thì khung rộng gấp đôi theo điểm ảnh.*

Có **2 luồng xử lý chính** tùy theo nhu cầu nghiệp vụ:

### 4.1. Luồng A — Số hóa đầy đủ (Xuất cả PDF + Excel con + CSDL)
*Áp dụng khi cần trích xuất chi tiết từng công dân trong cuốn sổ để phục vụ tra cứu sau này.*

* **Bước 1: Nạp file vào hàng đợi**:
  * Chọn **Mã tỉnh** tương ứng ở menu thả xuống tại cột trái.
  * Bấm **`📁 Chọn Thư mục Hồ sơ`** để đưa toàn bộ file PDF trong một tập vào danh sách, hoặc bấm **`📄 Chọn File PDF lẻ`** để thêm từng file riêng lẻ.
* **Bước 2: Chạy OCR tự động**:
  * Bấm **`⚡ Chạy OCR Tự Động`**.
  * Tiến trình nền sẽ quét từng trang của tài liệu. Khi đang chạy, nút này đổi thành **`Đang chạy OCR… (bấm để dừng)`**: bấm vào thì phần mềm dừng sau file đang đọc, các file chưa đọc trở về trạng thái "Chờ".
* **Bước 3: Rà soát & Đối soát dữ liệu (Cột phải)**:
  * Nhấp chuột vào file cần rà soát trong danh sách.
  * Cột giữa hiển thị bản scan gốc. Cột phải hiển thị thông tin trích xuất:
    * Thẻ **Tên file đề xuất**: Xem tên file chuẩn được sinh tự động. Có thể chỉnh sửa trực tiếp nếu muốn. Bên dưới là các ghi chú đặt tên: các mục **chữ đỏ** dưới tiêu đề **"Cần sửa trước khi lưu:"** là việc bắt buộc phải làm trước khi lưu (ví dụ chưa chọn mã tỉnh, cần nhập ngày thi), không có lỗi thì khung này trống. Nếu OCR đọc được mã tỉnh trên giấy tờ, lỗi mã tỉnh ghi kèm gợi ý, ví dụ "Chưa chọn mã tỉnh lưu trữ (OCR gợi ý: 15 – Tỉnh Lào Cai).".
    * Thẻ **Thông tin bìa sổ & Vị trí hồ sơ**: Kiểm tra Loại sổ, Ngày thi, Hạng, Khóa, Hộp, Hộp số, Mã tỉnh lưu trữ và các ô đặt tên (Số quyết định, Ngày ký, Số GPLX đầu/cuối).
    * Ô **Ngày thi** nhập theo dạng **dd-mm-yyyy** (ví dụ `29-03-1996`). Ô **Số GPLX đầu/cuối** nhập **chữ in hoa**, 1–2 chữ cái và 6 chữ số liền nhau (ví dụ `AM570000`). Nhập sai dạng thì khung ghi chú báo lỗi đỏ và chưa lưu được.
    * Thẻ **Rà soát dãy số GPLX & Nhận định**: Kiểm tra Tổng số GPLX, Nhận định, Dãy số GPLX. **Tổng số GPLX** tự điền bằng số dòng đọc được ở mọi danh sách; nếu Nhận định là "Cần rà soát" thì hãy đối chiếu lại số này. Các số này tính cho **cả cuốn sổ**: PDF có nhiều danh sách vẫn ra một tên file (số GPLX đầu của danh sách đầu đến số cuối của danh sách cuối), một dòng sổ tổng hợp và một file Excel (mỗi danh sách một sheet). Nhận định **"Cần rà soát"** nghĩa là máy chưa kết luận được "Đủ" hay "Ngắt" (còn trang chưa rõ, dòng tô vàng hoặc ô số GPLX đọc chưa rõ). Bấm các nút **"Đối chiếu trang n"** để xem những trang còn chưa rõ danh sách có tiếp tục hay không.
    * Thẻ **Danh sách trong PDF (giữ nguyên cột của bảng gốc)**: Bảng đối soát từng dòng người dân. Bấm chọn một dòng thì khung PDF nhảy đến trang của dòng đó để đối chiếu ảnh scan; nhấp đúp vào ô để sửa. Dòng tô vàng là dòng cần đối chiếu, dòng tô xanh là dòng đã sửa. Sổ có nhiều danh sách thì chọn danh sách để xem ở ô "Đang xem" (chỉ đổi bảng đang hiển thị, không ảnh hưởng tên file).
* **Bước 4: Xác nhận lưu**:
  * Bấm nút **`✔ XÁC NHẬN: ĐỔI TÊN PDF & XUẤT EXCEL & CẬP NHẬT TỔNG HỢP`** (nút chỉ bấm được khi đã nhập đủ các ô bắt buộc).
  * Phần mềm đổi tên file PDF sang tên chuẩn, tạo file Excel con `.xlsx`, ghi dòng vào Sổ tổng hợp của tỉnh và nạp vào CSDL để tra cứu ngay.

---

### 4.2. Luồng B — Rà soát & Đổi tên nhanh theo Folder (Đổi tên PDF, cập nhật Sổ tổng hợp và CSDL, không tạo Excel con)
*Áp dụng khi chỉ cần phân loại, chuẩn hóa tên file PDF và quản lý dải số trong sổ tổng hợp tỉnh một cách nhanh chóng.*

1. Bấm nút **`📑 Đổi tên file nhanh (chọn theo folder)`** và chọn thư mục hồ sơ.
2. Danh sách file PDF trong thư mục sẽ xuất hiện ở cột trái.
3. Bấm vào từng file để xem bản scan ở giữa và thông tin bìa/vị trí hồ sơ ở cột phải.
4. Kiểm tra mã tỉnh, ngày thi/ngày ký để hệ thống tự động sinh tên chuẩn. Bạn có thể chỉnh sửa trực tiếp các ô trước khi xác nhận.
5. Bấm nút **`XÁC NHẬN LƯU PDF VÀ SỔ TỔNG HỢP`**: Ứng dụng đổi tên file PDF sang tên chuẩn, cập nhật dòng vào `So_Theo_Doi_Day_So_GPLX_<MãTỉnh>.xlsx` ở thư mục tỉnh, ghi thông tin hồ sơ vào CSDL (không có danh sách công dân) và tự động chuyển sang file kế tiếp.

---

## 5. QUY TẮC ĐẶT TÊN 3 GIAI ĐOẠN HỒ SƠ

Hệ thống tự động căn cứ vào **Ngày thi hoặc Ngày sát hạch** để áp dụng bộ quy tắc chuẩn:

| Nhóm | Giai đoạn áp dụng | Dữ liệu cấu thành tên file | Định dạng tên file mẫu |
| :--- | :--- | :--- | :--- |
| **SQL** | Đến hết **31/12/2012** | `[MãTỉnh].SQL.[Tháng].[Năm].[SốĐầu]-[SốCuối]` | `15.SQL.03.1996.C244501-C244608.pdf` |
| **QĐTT** | Từ **01/01/2013** đến **28/02/2025** | `[MãTỉnh].[SốQĐ].[NgàyKýQĐ]` | `15.368.25.09.2015.pdf` |
| **QĐSH** | Từ **01/03/2025** trở đi | `[MãTỉnh].[SốQĐ].[NgàySátHạch]` | `15.3081.01.01.2026.pdf` |

*Lưu ý:*
- Tên file sử dụng dấu chấm `.` ngăn cách các thành phần; tuyệt đối không dùng dấu gạch chéo `/`.
- Dấu gạch ngang `-` chỉ dùng giữa số bằng đầu và số bằng cuối trong nhóm `SQL`.
- Số quyết định chỉ lấy phần số nguyên bản (ví dụ quyết định `368/QĐ-SGTVT` -> lấy `368`).

---

## 6. HƯỚNG DẪN TRA CỨU HỒ SƠ & MỞ FILE SCAN (TAB 2)

Tab 2 cung cấp 2 chế độ tra cứu toàn diện:

### 6.1. Chế độ 1: 👤 Tra Cứu Công Dân
* **Ô tìm kiếm thông minh**: Gõ bất kỳ thông tin nào cần tìm:
  * Số bằng lái: `A461544`, `C244501`...
  * Họ và tên: Gõ có dấu hoặc không dấu đều tìm thấy (ví dụ: `Trần Văn Bình` hoặc `tran van binh`).
  * Năm sinh: `1960`, `1985`...
* **Số kết quả**: hiện tối đa 200 dòng mỗi lần tìm. Nếu nhiều hơn, phần mềm ghi "Hiện 200/N kết quả đầu"; hãy gõ cụ thể hơn (họ tên đầy đủ, số bằng, năm sinh).
* **Thao tác nhanh**:
  * Phím **`Enter`**: trong ô tìm kiếm thì tìm ngay; trên bảng kết quả thì mở dòng đang chọn (công dân: mở PDF đúng trang; sổ: hiện danh sách người dân của sổ). Nhấp đúp vào dòng cũng vậy.
  * **`👁️ Xem PDF`**: Mở trực tiếp và lật đúng trang scan chứa tên người lái xe.
  * **`📊 Excel`**: Mở file Excel con tương ứng.
  * **`📂 Thư mục`**: Mở thư mục chứa file trong Windows Explorer.

### 6.2. Chế độ 2: 📁 Danh Mục Sổ / File Excel Đã Import
* **Thống kê tổng thể**: Hiển thị tổng số Tỉnh, Hộp, Hộp số và tổng số lượng hồ sơ/file Excel đã số hóa trong CSDL.
* **Nút `👥 Xem Dân`**: Bấm vào nút này để lọc và xem toàn bộ danh sách người dân có trong cuốn sổ đó.
* **Nút `🔄 Quét lại từ Excel`**: Cho phép quét và đồng bộ lại CSDL từ các file Excel trong thư mục khi bạn có chỉnh sửa dữ liệu thủ công bên ngoài bằng Microsoft Excel.

---

## 7. HƯỚNG DẪN CHIA SẺ MẠNG LAN CHO MÁY TRẠM (TAB 3)

Hệ thống cho phép các máy tính khác hoặc điện thoại trong cùng mạng cơ quan cùng tra cứu mà không cần cắm ổ cứng:

1. Tại máy tính chính, mở tab **`🌐 CHIA SẺ MẠNG LAN (MÁY CHỦ NỘI BỘ)`**.
2. Bấm nút: **`▶ BẬT CHIA SẺ MẠNG LAN`**.
3. Màn hình sẽ hiển thị:
   - Địa chỉ mạng nội bộ (Ví dụ: `http://192.168.1.15:8080`).
   - Mã **QR Code** để quét bằng điện thoại/máy tính bảng.
4. **Tại các máy trạm khác**:
   - Mở trình duyệt web (Google Chrome, Microsoft Edge, Cốc Cốc...).
   - Nhập địa chỉ hiển thị trên máy chính (hoặc quét mã QR).
   - Giao diện tra cứu web hiện ra tức thì: hỗ trợ tìm kiếm công dân, xem bản PDF trực tiếp và tải file Excel về máy.

---

## 8. CÁC PHÍM TẮT & THAO TÁC TIỆN ÍCH

| Phím tắt / Thao tác | Chức năng |
| :--- | :--- |
| **Kéo vách ngăn giữa các khung** | Tùy chỉnh độ rộng cột Hàng đợi và cột Rà soát (khung Xem PDF nhận phần còn lại); mỗi máy tự nhớ vị trí cho lần sau |
| **Shift + Con lăn chuột** | Cuộn ngang trang scan PDF khi xem tài liệu khổ A3 nằm ngang |
| **Nút 🔍 + / 🔍 -** (khung Xem PDF) | Phóng to / Thu nhỏ trang scan PDF, mỗi lần 10% (từ khoảng 40% đến 250%). Con lăn chuột chỉ cuộn trang, không phóng to |
| **Phím Enter** (ở bảng kết quả Tra cứu) | Mở trang PDF của công dân, hoặc danh sách người dân của sổ đang chọn |
| **Bấm chọn một dòng** (ở bảng Danh sách trong PDF, khung Rà soát) | Khung Xem PDF nhảy đến trang của dòng đó; nhấp đúp vào ô để sửa |
| **Lăn chuột trên bảng GPLX** | Cuộn danh sách người dân (3 dòng/nấc), khung rà soát đứng yên; khi bảng đã cuộn tới đầu/cuối thì lăn tiếp sẽ cuộn khung rà soát |

---

## 9. CÂU HỎI THƯỜNG GẶP & XỬ LÝ SỰ CỐ (FAQ)

1. **Hỏi**: Đã kéo vách ngăn lệch, muốn đặt lại độ rộng như lúc mới cài thì làm sao?
   * **Trả lời**: Bạn chỉ cần xóa file cấu hình giao diện tại `%LOCALAPPDATA%\GPLX\giao_dien.json` (hoặc mở Run gõ `%LOCALAPPDATA%\GPLX` rồi xóa file). Khi mở lại, app sẽ quay về kích thước mặc định: 246 · 630 · 510 (thấy khoảng 55% bảng GPLX). File này lưu riêng trên từng máy, nên kéo vách ngăn trên máy này không ảnh hưởng máy khác.
2. **Hỏi**: Khi bấm xác nhận lưu mà báo lỗi `"đóng sổ trong Excel"`?
   * **Trả lời**: Do file sổ tổng hợp `So_Theo_Doi_Day_So_GPLX_XX.xlsx` đang được mở bằng ứng dụng Microsoft Excel bên ngoài nên Windows khóa không cho ghi. Bạn chỉ cần đóng cửa sổ Excel đó lại rồi bấm nút xác nhận một lần nữa.
3. **Hỏi**: Đang chạy OCR mà muốn đóng ứng dụng thì có bị khóa file PDF không?
   * **Trả lời**: Không. Ứng dụng có cơ chế ngắt an toàn: khi bạn đóng cửa sổ lúc đang OCR, ứng dụng sẽ hỏi xác nhận và kết thúc tiến trình ngay lập tức, giải phóng hoàn toàn file PDF, không làm treo máy.
4. **Hỏi**: Muốn xem chi tiết nhật ký lỗi thì làm thế nào?
   * **Trả lời**: Nhấp đúp vào file **`Xem_Nhat_Ky.bat`** trong thư mục `So Hoa GPLX`. Thư mục nhật ký chứa các file log hàng ngày (`app_YYYY-MM-DD.log`) sẽ tự động mở ra.

