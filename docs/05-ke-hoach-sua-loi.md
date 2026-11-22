# 05. Kế hoạch sửa lỗi (đợt 21/11/2026)

Trạng thái: **đợt 1 và đợt 2 đã làm xong 22/11/2026** (xem mục 6, 7). B8 giữ nguyên theo đề xuất. Gồm 7 yêu cầu mới (R1–R7) và các lỗi/việc còn tồn ở `04-quyet-dinh-va-viec-can-lam.md` (B*, C*).

## 0. Thông tin đã xác nhận cho đợt này

| # | Nội dung |
|---|---|
| Q1 | Mô hình chạy: **1 máy chủ giữ thư mục `So Hoa GPLX` (chia sẻ mạng); máy con mở `\\máy-chủ\...\So Hoa GPLX\Chay_Ngay.bat`**, app chạy trên máy con (OCR trên máy con), đọc/ghi PDF, Excel và **CSDL dùng chung** trên máy chủ. Thay cho D12. |
| Q2 | R1: cả **Excel** lẫn **lưới sửa dữ liệu** ở panel phải đều theo đúng cột của bảng trong PDF. |
| Q3 | R4: đổi tên nhanh chỉ đọc trang đầu. TH1 (SQL) tự điền ngày thi; TH2 (QĐTT) tự điền số QĐ + ngày ký; TH3 (QĐSH) tự điền số QĐ + ngày sát hạch. Số GPLX đầu/cuối, tổng số GPLX, dãy số, nhận định: nhập tay. |
| Q4 | 2 loại hồ sơ mới (C3): **để phát triển sau**, không làm đợt này. |
| Q5 | **Giữ SQLite** (file trên thư mục chia sẻ của máy chủ). Máy con **chỉ dùng LAN nội bộ**, không dùng WAN. |
| Q6 | Mã tỉnh: **mã hành chính** theo QĐ 19/2025/QĐ-TTg (Phú Thọ 25, Lào Cai 15), không dùng đầu biển số xe. |
| Q7 | Bàn giao 22/11/2026. Đợt 1 (bàn giao): R1–R6, B9, B9c, Q1, B2, B3, C1, B4, B5, B6, C2, R5, C5, B14, B12. Đợt 2 (sau bàn giao): B9b, B1, B10, B11, B13, B8. |

## 1. Các yêu cầu mới

| # | Yêu cầu | Cách làm |
|---|---|---|
| R1 | Excel và lưới sửa theo cột của PDF | Lưới ở panel phải dựng động theo `table["columns"]` của từng danh sách (tiêu đề cột gốc, thứ tự gốc, có chọn danh sách nếu có nhiều), sửa trực tiếp vào ô nguồn. Excel ghi đúng các ô đã sửa (bỏ cơ chế "trường tra cứu" + cột ẩn `_GPLX` cho phần sửa). CSDL vẫn lấy các trường tra cứu (họ tên, năm sinh, địa chỉ, số GPLX, trang) bằng cách chiếu từ bảng đã sửa (`table_citizens`). Giữ khả năng "Đồng bộ từ Excel" với cả Excel cũ. |
| R2 | Chỉ lấy bảng có cột **Họ và tên / Họ tên** và **Năm sinh / Ngày sinh / Ngày tháng năm sinh** | Trong `LicenseTableExtractor.read_page`, bỏ tiêu đề bảng nào thiếu cột `birth_year`. Trang tiếp nối không có tiêu đề vẫn nối vào bảng hợp lệ trước đó như hiện tại. Kiểm tra lại trên các PDF mẫu `Tỉnh Yên Bái`. |
| R3 | Đổi tên nút | `📑 Đổi tên file nhanh (chọn theo folder)`; cập nhật chữ trong `HUONG_DAN_LUU_TRU.txt` và docs. |
| R4 | Đổi tên nhanh chỉ đọc trang đầu | `process_dossier_pdf(rename_only=True)` chỉ gọi đọc trang đầu (lớp text, thiếu thì OCR trang 1), **không OCR các trang bảng**. Panel phải: điền ngày/số QĐ đọc được; các ô còn lại để trống cho người dùng nhập. Nút xác nhận chỉ sáng khi đủ trường để đặt tên. |
| R5 | Mỗi lần bấm "Chọn Thư mục", "Chọn File PDF lẻ", "Đổi tên file nhanh" thì **làm mới danh sách** | Thay danh sách cũ bằng danh sách mới (hiện "Chọn thư mục/file" đang cộng dồn). Đang **lưu** một file thì không cho đổi danh sách (báo "đang lưu"). Đang OCR thì dừng hàng đợi cũ, bỏ kết quả về muộn. |
| R6 | Build bằng `Build_So_Hoa_GPLX.bat` ra `So Hoa GPLX/`, chạy `Chay_Ngay.bat` kiểm tra crash | Cài `pyinstaller` vào `.venv`; `Build_So_Hoa_GPLX.bat` ưu tiên `.venv\Scripts\python.exe` (máy hiện không có `python` thật trên PATH). Build, chạy `Chay_Ngay.bat`, kiểm tra tiến trình còn sống, log `%LOCALAPPDATA%\GPLX\logs` và `native_crash.log` không có lỗi; chạy thêm kịch bản xử lý PDF mẫu bằng chính code đóng gói nếu được. |
| R7 | Trình xem PDF: thêm nút **⏮ Trang đầu** và **Trang cuối ⏭** | **Đã làm 21/11/2026** (`src/gui/pdf_viewer.py`): thanh công cụ tách 2 hàng (điều hướng trang / xoay + zoom) để đủ chỗ ở độ rộng mặc định; nút tự khóa khi đang ở trang đầu/cuối hoặc chưa mở PDF. |

## 2. Lỗi / việc tồn từ đợt trước

| # | Việc | Cách làm |
|---|---|---|
| B9 + Q1 | CSDL dùng chung trên thư mục chia sẻ | Bản exe: CSDL tại `So Hoa GPLX/HeThong/gplx_index.db` (cạnh `app/`), không còn ở `%LOCALAPPDATA%`. SQLite: `timeout=30s`, giữ chế độ journal mặc định (không dùng WAL trên ổ mạng). CSDL cũ đang nằm riêng ở từng máy: dựng lại bằng nút "Đồng bộ từ Excel" trên kho dữ liệu sau khi cập nhật. `build_portable.py` không được ghi đè CSDL dùng chung khi build lại. |
| Q1 | Nhiều máy cùng ghi sổ tổng hợp | Thêm khóa liên máy bằng file khóa cạnh sổ (`.<tên sổ>.lock`, tạo độc quyền, chờ tối đa ~15 giây, coi là bỏ dở nếu quá 2 phút) trong `edit_master_summary`; hết thời gian thì báo "máy khác đang ghi sổ, thử lại". |
| B9b | Khôi phục cả hồ sơ đổi tên nhanh khi dựng lại CSDL (đã duyệt) | "Đồng bộ từ Excel" đọc thêm sổ tổng hợp tỉnh (`So_Theo_Doi_Day_So_GPLX_*.xlsx`) + sheet `_GPLX_Rename`: hồ sơ có trong sổ mà không có Excel con thì tạo lại dòng `dossiers` từ dòng sổ (tên file, ngày, hộp, hộp số, hạng, tổng số, dãy số, nhận định). |
| B9c | Tự sao lưu CSDL hằng ngày (đã duyệt) | Khi mở app: nếu hôm nay chưa có bản sao lưu thì chép `HeThong/gplx_index.db` bằng SQLite backup API vào `HeThong/SaoLuu/gplx_index_YYYYMMDD.db`, giữ 7 bản gần nhất. Lỗi sao lưu chỉ ghi log, không chặn app. |
| B14 | Từ khóa `huế` / `hue` khớp nhầm chữ `thuế` | Văn bản có chữ "thuế" bị gợi ý mã 46. Sửa: so khớp theo ranh giới từ thay vì chuỗi con. |
| C1 (D7) | Đổi tên thật, không giữ file gốc | Thay sao chép bằng `os.replace`-an toàn (`os.rename`, đích đã tồn tại thì báo trùng). Đóng PDF trong trình xem trước khi đổi tên (Windows khóa file đang mở), mở lại file mới sau khi lưu. File đang mở ở máy khác → báo lỗi rõ ràng. Sổ `_GPLX_Rename` ghi `tên file / nguồn cũ / đích`. Cho phép lưu lại một file đã đổi tên (cùng tên → cập nhật; tên khác → đổi tên tiếp và cập nhật bản ghi). |
| B6 | Lưu luồng A không trọn vẹn | Thứ tự mới: kiểm tra → ghi Excel ra file tạm → trong `edit_master_summary`: ghi bản ghi đổi tên + dòng tổng hợp, đổi tên PDF, chuyển Excel tạm thành chính thức → lưu sổ. Lỗi ở bất kỳ bước nào: đổi tên PDF về như cũ, xóa Excel tạm. Ghi CSDL sau cùng; lỗi CSDL vẫn báo cảnh báo + hướng dẫn "Đồng bộ từ Excel". |
| B4 | Luồng A không ghi `_GPLX_Rename` | Dùng chung một hàm lưu cho cả hai luồng (luồng A thêm bước Excel + CSDL đầy đủ). |
| C2 (D9) | Luồng B ghi CSDL thông tin hồ sơ | Ghi/cập nhật dòng `dossiers` (`excel_path` rỗng, không đụng tới danh sách công dân nếu hồ sơ đã có từ luồng A). Tab tra cứu: ẩn/khóa nút "Mở Excel" khi không có Excel. |
| B5 | File đã đổi tên bị đưa lại vào hàng đợi | Cả hai luồng dùng một hàm liệt kê. Luồng B: file là đích đã đăng ký trong sổ → "Xong". Luồng A: "Xong" khi đã đăng ký **và** có Excel cùng tên. Bấm vào file "Xong" vẫn mở được để sửa và lưu lại. |
| B2 | Giá trị mặc định cứng (Hộp 48, Hộp số 115, Hạng A1, Khóa 25, mã tỉnh 15) | Bỏ hết; thiếu thì để trống cho người dùng nhập. Mã tỉnh bắt buộc chọn (đã có kiểm tra). |
| B3 | Hai cách tìm thư mục tỉnh | Dùng `folder_review_location` cho cả hai luồng; bỏ `find_province_root_dir` / mặc định trong `parse_folder_hierarchy`. |
| B1 | API LAN đọc được file bất kỳ | `/api/pdf/{dossier_id}` và `/api/excel/{dossier_id}`: chỉ trả file có trong CSDL; sửa `index.html` tương ứng. (Không thêm đăng nhập.) |
| B10 | `DatabaseManager` tạo khi import `lan_server` | Tạo khi máy chủ LAN khởi động. |
| C5 | Từ khóa tỉnh cũ đã sáp nhập | Thêm vào `data/province_codes.json` theo danh sách sáp nhập 2025 (mục 4). |
| B11 | Docstring sai | Sửa. |
| B12 | Thiếu `requirements.txt`; `Chay_UngDung_GPLX.bat` gọi `python` hệ thống | Thêm `requirements.txt` (phiên bản đang chạy được trong `.venv`); bat dùng `.venv\Scripts\python.exe` nếu có. |
| B13 | `src/win_ocr.ps1` không dùng | Xóa. |
| B8 | Tìm kiếm dùng `LIKE`, FTS5 không dùng | **Đề xuất không sửa**: `LIKE '%...%'` cho đúng kiểu tìm "chứa chuỗi" người dùng đang dùng; FTS5 tìm theo từ nên sẽ đổi kết quả. Chỉ sửa tài liệu cho đúng. |
| C3 | 2 loại hồ sơ mới | Hoãn (Q4). |

## 3. Thứ tự thực hiện

1. **Môi trường**: `pyinstaller` + `requirements.txt` + 2 file bat dùng `.venv` (R6 phần chuẩn bị, B12).
2. **Dùng chung qua mạng**: vị trí CSDL, timeout, khóa sổ tổng hợp liên máy, sao lưu CSDL hằng ngày, `lan_server` tạo CSDL muộn (B9, B9c, Q1, B10).
3. **Thư mục & mặc định**: B2, B3.
4. **Lưu & đổi tên**: một hàm lưu chung cho 2 luồng, đổi tên thật, nguyên tử, ghi CSDL cho luồng B, liệt kê file "Xong" (C1, B4, B5, B6, C2) + làm mới danh sách (R5).
5. **Đổi tên nhanh**: R3, R4.
6. **Bảng & Excel**: lọc bảng (R2), lưới + Excel theo cột PDF (R1); chạy OCR thật trên PDF mẫu `Tỉnh Yên Bái` để kiểm tra.
7. **Còn lại**: đồng bộ khôi phục cả hồ sơ đổi tên nhanh (B9b), B1, C5 + B14 (từ khóa tỉnh), B11, B13, cập nhật docs.
8. **Build & chạy thử** (R6).

Mỗi bước: viết/cập nhật test trước, chạy toàn bộ test v3 sau khi xong. Không commit nếu chưa được yêu cầu.

## 4. Từ khóa tỉnh cũ (C5) — đã đối chiếu 63 tỉnh cũ với 34 tỉnh mới

Nguồn (tra ngày 21/11/2026):
- 34 tỉnh mới và mã: Quyết định 19/2025/QĐ-TTg, hiệu lực 01/07/2025 ([thuviennhadat.vn](https://thuviennhadat.vn/phap-luat/danh-muc-va-ma-so-34-tinh-thanh-viet-nam-tu-01-7-2025-690649.html); bản dự thảo trên [vtcnews.vn](https://vtcnews.vn/ma-so-hanh-chinh-cua-34-tinh-thanh-pho-sau-sap-nhap-thay-doi-the-nao-ar950542.html) cùng mã).
- Tỉnh cũ nhập vào tỉnh mới: Nghị quyết 202/2025/QH15, Điều 1 ([luatvietnam.vn](https://luatvietnam.vn/hanh-chinh/nghi-quyet-202-2025-qh15-cua-quoc-hoi-ve-viec-sap-xep-don-vi-hanh-chinh-cap-tinh-402728-d1.html)).
- 63 tỉnh cũ và mã cũ: bảng mã theo Quyết định 124/2004/QĐ-TTg ([thuviennhadat.vn](https://thuviennhadat.vn/phap-luat/danh-muc-ma-so-cac-don-vi-hanh-chinh-cap-tinh-viet-nam-640775.html)). Danh sách dùng để đối chiếu là 63 tỉnh trước 01/07/2025 (trang nguồn còn dòng Hà Tây — đã nhập Hà Nội từ 2008, không tính).

Kết quả: 34 mã và tên trong `data/province_codes.json` **khớp hoàn toàn** Quyết định 19/2025. 52 tỉnh cũ nhập vào 23 tỉnh mới, 11 tỉnh giữ nguyên: 52 + 11 = 63, không sót tỉnh nào.

| Mã mới | Tỉnh mới | Tỉnh cũ (mã cũ) | Từ khóa cần thêm |
|---|---|---|---|
| 01 | TP Hà Nội | giữ nguyên (01) | — |
| 04 | Cao Bằng | giữ nguyên (04) | — |
| 08 | Tuyên Quang | Hà Giang (02), Tuyên Quang (08) | Hà Giang |
| 11 | Điện Biên | giữ nguyên (11) | — |
| 12 | Lai Châu | giữ nguyên (12) | — |
| 14 | Sơn La | giữ nguyên (14) | — |
| 15 | Lào Cai | Lào Cai (10), Yên Bái (15) | (đã có Yên Bái) |
| 19 | Thái Nguyên | Bắc Kạn (06), Thái Nguyên (19) | Bắc Kạn, Bắc Cạn |
| 20 | Lạng Sơn | giữ nguyên (20) | — |
| 22 | Quảng Ninh | giữ nguyên (22) | — |
| 24 | Bắc Ninh | Bắc Giang (24), Bắc Ninh (27) | Bắc Giang |
| 25 | Phú Thọ | Hòa Bình (17), Phú Thọ (25), Vĩnh Phúc (26) | Hòa Bình, Hoà Bình, Vĩnh Phúc |
| 31 | TP Hải Phòng | Hải Dương (30), Hải Phòng (31) | Hải Dương |
| 33 | Hưng Yên | Hưng Yên (33), Thái Bình (34) | Thái Bình |
| 37 | Ninh Bình | Hà Nam (35), Nam Định (36), Ninh Bình (37) | Hà Nam, Nam Định |
| 38 | Thanh Hóa | giữ nguyên (38) | Thanh Hoá (cách viết khác) |
| 40 | Nghệ An | giữ nguyên (40) | — |
| 42 | Hà Tĩnh | giữ nguyên (42) | — |
| 44 | Quảng Trị | Quảng Bình (44), Quảng Trị (45) | Quảng Bình |
| 46 | TP Huế | Thừa Thiên Huế (46) | — |
| 48 | TP Đà Nẵng | Đà Nẵng (48), Quảng Nam (49) | Quảng Nam |
| 51 | Quảng Ngãi | Quảng Ngãi (51), Kon Tum (62) | Kon Tum |
| 52 | Gia Lai | Bình Định (52), Gia Lai (64) | Bình Định |
| 56 | Khánh Hòa | Khánh Hòa (56), Ninh Thuận (58) | Ninh Thuận, Khánh Hoà |
| 66 | Đắk Lắk | Phú Yên (54), Đắk Lắk (66) | Phú Yên, Đăk Lăk |
| 68 | Lâm Đồng | Bình Thuận (60), Đắk Nông (67), Lâm Đồng (68) | Bình Thuận, Đắk Nông, Đăk Nông |
| 75 | Đồng Nai | Bình Phước (70), Đồng Nai (75) | Bình Phước |
| 79 | TP Hồ Chí Minh | Bình Dương (74), Bà Rịa - Vũng Tàu (77), TP HCM (79) | Bình Dương, Bà Rịa, Vũng Tàu |
| 80 | Tây Ninh | Tây Ninh (72), Long An (80) | Long An |
| 82 | Đồng Tháp | Tiền Giang (82), Đồng Tháp (87) | Tiền Giang |
| 86 | Vĩnh Long | Bến Tre (83), Trà Vinh (84), Vĩnh Long (86) | Bến Tre, Trà Vinh |
| 91 | An Giang | An Giang (89), Kiên Giang (91) | Kiên Giang |
| 92 | TP Cần Thơ | Cần Thơ (92), Hậu Giang (93), Sóc Trăng (94) | Hậu Giang, Sóc Trăng |
| 96 | Cà Mau | Bạc Liêu (95), Cà Mau (96) | Bạc Liêu |

Mỗi từ khóa thêm cả dạng không dấu (vd `ha giang`).

Lưu ý: tỉnh mới dùng mã của một tỉnh cũ, **không nhất thiết là tỉnh trùng tên**. Ví dụ Lào Cai mới mang mã 15 (mã cũ của Yên Bái), Bắc Ninh mới là 24 (mã cũ của Bắc Giang), Gia Lai mới là 52 (mã cũ của Bình Định). Sổ cũ ghi "Lào Cai" thì vẫn đặt tên file bằng mã 15, không phải 10.

App so khớp theo nguyên từ (B14) và chỉ gợi ý khi văn bản khớp đúng một mã (`config.find_province_code_by_text`). Văn bản nhắc tới hai tỉnh (vd "Gia Lai - Kon Tum") thì không gợi ý, người dùng tự chọn.

## 5. Rủi ro cần biết

- **SQLite trên thư mục chia sẻ**: chạy được khi ít máy ghi cùng lúc, nhưng mất mạng giữa lúc ghi có thể làm hỏng file. App tự sao lưu mỗi ngày (B9c); nếu hỏng có thể lấy bản sao lưu hoặc dựng lại bằng "Đồng bộ từ Excel" (hồ sơ đổi tên nhanh chỉ khôi phục được sau khi làm B9b ở đợt 2).
- **Đổi tên thật** làm mất tên file scan gốc; tên cũ chỉ còn lưu trong sheet ẩn `_GPLX_Rename` của sổ tổng hợp.
- **Kiểm tra crash (R6)** chỉ tự động được ở mức: app khởi động, chạy vài phút, log không lỗi, và các hàm xử lý chạy được trong bản đóng gói. Thao tác bấm nút trên giao diện cần bạn thử lại sau khi build.

## 6. Kết quả đợt 1 (22/11/2026)

| Mục | Đã làm |
|---|---|
| R1 | Lưới ở panel phải dựng theo cột của từng danh sách trong PDF (có nút chọn danh sách khi có nhiều). Nhấp đúp để sửa ô; chọn dòng thì nhảy tới trang PDF; dòng vàng cần đối chiếu, dòng xanh đã sửa. Sửa ô số GPLX thì cập nhật lại số đầu/cuối và tên đề xuất. Excel ghi đúng ô đã sửa. |
| R2 | Chỉ đọc bảng có cột Họ và tên/Họ tên và Năm sinh/Ngày sinh/Ngày tháng năm sinh; trang nối tiếp của bảng bị bỏ cũng bị bỏ. Sửa thêm: tiêu đề gộp "Năm sinh \| Quốc tịch" của sổ 1996 (OCR đọc thành `NAM SINHIQUOCTICH`) được tách đúng, nếu không sổ 1996 mất ~75% dòng. Đã chạy OCR trên 11 PDF mẫu `Tỉnh Yên Bái`. |
| R3 | Nút `📑 Đổi tên file nhanh (chọn theo folder)`; `HUONG_DAN_LUU_TRU.txt` viết lại (tự cập nhật khi mở app). |
| R4 | Đổi tên nhanh chỉ đọc trang đầu; số GPLX đầu/cuối, tổng số, dãy số, nhận định để trống. Bỏ mặc định A1/25/48/115 ở panel phải. |
| R5 | Mỗi nút chọn thay cả danh sách; đang lưu thì không đổi; OCR của danh sách cũ bị bỏ qua. |
| R6 | `Build_So_Hoa_GPLX.bat` dùng `.venv`; build ra `So Hoa GPLX/` + zip (zip không chứa `HeThong/`, file khóa, file tạm). Mở `Chay_Ngay.bat` cả từ ổ đĩa lẫn đường dẫn mạng `\localhost\D$\...`: app chạy, phản hồi, log không lỗi, sao lưu CSDL chạy. |
| Sửa thêm | `Chay_Ngay.bat` cũ không chạy được từ đường dẫn mạng (cmd không `cd` vào UNC) và báo lỗi `'TRA' is not recognized` (dấu `&` trong `title`): đã sửa, file tự ghi lại khi mở app. Tên công dân viết HOA có dấu bị mất chữ khi lưu CSDL (`NGUYỄN` → `Nguyn`): đã sửa trong `restore_vietnamese_name`. |
| Khác | B2, B3, B4, B5 ("✅ Xong", mở lại để sửa và lưu lại), B6, B9, B9c, B12 (`requirements.txt`), B14, C1, C2 (nút "Mở Excel" báo chưa có Excel), C5, Q1. |

Còn tồn: 2 lỗi đọc PDF, đã sửa ở mục 8.

## 7. Kết quả đợt 2 (22/11/2026)

| Mục | Đã làm |
|---|---|
| B9b | "Đồng bộ từ Excel" đọc thêm sổ tổng hợp tỉnh và tạo lại hồ sơ đổi tên nhanh (không có Excel) từ dòng sổ: mã tỉnh, ngày, hộp, hộp số, hạng, tổng số, dãy số, nhận định, đường dẫn PDF. Chạy lại nhiều lần không tạo trùng; hồ sơ đã có danh sách công dân thì giữ danh sách. |
| B1 | Bỏ `/api/pdf?path=` và `/api/excel?path=`; thay bằng `/api/pdf/{dossier_id}`, `/api/excel/{dossier_id}` chỉ trả file của hồ sơ trong CSDL. `/api/search` không còn gửi đường dẫn file trên máy chủ. Trang web ẩn nút "Tải Excel" khi hồ sơ chưa có Excel, bỏ mặc định hạng "A1". |
| B10 | `lan_server` mở CSDL khi máy chủ khởi động hoặc có yêu cầu đầu tiên, không mở lúc import. |
| B11 | Sửa docstring `normalize_license_code` (`'A461S44-' → 'A461544'`), docstring `database.py`/`/api/search` và dòng "SQLite FTS5 siêu tốc" ở tab Máy chủ LAN (tìm kiếm thực tế dùng `LIKE`, B8). |
| B13 | Xóa `src/win_ocr.ps1`. |
| B8 | Giữ `LIKE` (không đổi kết quả tìm kiếm), chỉ sửa tài liệu. |

## 8. Sửa 2 lỗi đọc PDF (22/11/2026)

Kiểm tra bằng OCR đã lưu của 11 PDF mẫu `Tỉnh Yên Bái`, so với bản trước khi sửa: không PDF nào ít dòng hơn; tổng 788 → 873 dòng, 596 → 674 số GPLX hợp lệ; trong mỗi danh sách đã nối, số GPLX vẫn tăng dần (trừ 1 chỗ OCR đọc sai số ngay trong một trang của sổ 1996, có từ trước).

| Lỗi | Nguyên nhân | Đã sửa |
|---|---|---|
| `QD_000493` (2009) không ra bảng nào | Tiêu đề "Họ / và tên" xuống 2 dòng; kẻ ngang dưới tiêu đề bị đứt; tên "Công" (OCR mất dấu) bị coi là dòng "Cộng"; trang 5 lặp tiêu đề nhưng mép cột lệch; tên/địa chỉ xuống hàng thành dòng rỗng; một vệt kẻ ngang cắt qua dòng cuối; dấu "：" full-width trước số GPLX | Ghép tiêu đề 2 dòng; nối các đoạn kẻ đứt; "Cộng" chỉ kết thúc danh sách khi bên dưới không còn số GPLX/STT; trang lặp tiêu đề được đọc theo cả bố cục riêng và bố cục trang trước, giữ cách cho nhiều số GPLX hợp lệ và tên chắc chắn hơn; dòng chỉ có tên + địa chỉ, không bị kẻ ngang ngăn cách được gộp vào người phía trên; biên dưới dòng cuối phải nằm dưới mọi chữ của dòng đó; chuẩn hóa NFKC số GPLX. Kết quả: 1 danh sách 80 dòng, đủ AH515361–AH515440. |
| Sổ 1996 không đọc ngày thi ở trang đầu | OCR đọc nhãn liền "NGAYTHI:"; ô viết tay "29" bị đọc chồng lên "9.-.03-.1996" | Nhãn chấp nhận "NGAYTHI"; ghép 2 box chồng nhau trên trang khi phần cuối box trước trùng phần đầu box sau. 000003, `15.SQL.03.1996...` (29-03-1996), 000004 (01-04-1996), 000005 (22-04-1996) đã ra ngày và nhóm. |

Theo đó cũng tốt hơn: `QD_000833` nối được trang 3 (10 → 31 dòng), `SO_0000847` đủ STT 111–167 (47 → 56 dòng).

Còn lại: bìa sổ 1996 `SG_000116_..._000006` và `_000007` có ngày viết tay OCR đọc nát ("3...4/5...499.6", "05...199..."), đã thử phóng to/tăng tương phản vẫn không ổn định. Máy không đoán ngày: thẻ đổi tên báo ngày thi chưa đọc rõ, người dùng nhập tay vào ô "Ngày thi".

## 9. Không ghi đè Excel của file khác (22/11/2026)

Trước đây khi số hóa, nếu thư mục đã có `<tên mới>.xlsx` không thuộc hồ sơ nào (file làm tay, chép từ nơi khác...), file đó bị ghi đè không hỏi, trong khi PDF trùng tên thì bị từ chối. Nay `save_dossier` từ chối giống PDF: báo "Đã có file Excel mang tên … của file khác", không đổi tên PDF, không ghi sổ, không ghi CSDL. Excel trùng tên với chính PDF đang lưu vẫn được thay (số hóa lại cùng tên). Test: `test_excel_v3.test_existing_excel_of_another_file_is_not_overwritten`.

## 10. Rà soát thêm: 2 lỗi giao diện (22/11/2026)

| Lỗi | Đã sửa |
|---|---|
| PDF bị thay đổi sau khi đọc: lưu báo lỗi nhưng chọn lại file chỉ nạp dữ liệu cũ, xác nhận lần nào cũng lỗi | `save_dossier` báo `StalePdfError`. Giao diện bỏ dữ liệu cũ, đưa file về "Chờ xử lý", báo người dùng và tự đọc lại PDF đang mở. Test: `test_pdf_changed_after_reading_is_read_again`. |
| Đang sửa dở ô số GPLX rồi bấm xác nhận (chưa nhấn Enter): tên file lấy dãy số cũ, còn Excel/CSDL lấy số mới | `_handle_confirm` chốt ô đang sửa trước khi lấy tên file và kiểm tra. Test: `test_confirm_applies_the_cell_being_edited_before_naming`. |

## 11. Rà soát thêm: bản quét trùng tên cũ, ngày của hồ sơ QĐTT (22/11/2026)

| Lỗi | Đã sửa |
|---|---|
| Bản quét mới trùng tên file quét đã lưu (vd. `scan.pdf`) hiện "chưa lưu" nhưng lưu bị từ chối "PDF này đã được lưu thành … trước đây" | Chỉ từ chối khi file trùng nội dung với PDF đã lưu (bản sao phiên bản cũ để lại); khác nội dung thì lưu như hồ sơ mới. Test: `test_new_scan_with_the_name_of_a_saved_scan_can_be_saved`. |
| Hồ sơ QĐTT đổi tên nhanh: "Đồng bộ từ Excel" đưa ngày ký vào "Ngày thi" của CSDL | Đã chốt: cột "Ngày tại bìa sổ" ghi **ngày ký** cho QĐTT ở cả hai luồng (trước đây luồng số hóa ghi ngày thi). Sheet `_GPLX_Rename` thêm cột "Nhóm hồ sơ", "Ngày thi"; đồng bộ lấy ngày thi QĐTT từ đó. Bản ghi cũ (chưa có 2 cột) thì nhận nhóm theo tên file và để trống ngày thi QĐTT thay vì ghi ngày ký. Test: `test_sync_from_excel_restores_quick_rename_dossiers_from_summary`, `test_sync_of_older_qdtt_record_does_not_use_signing_date_as_exam_date`, `test_digitized_qdtt_summary_uses_signing_date_and_exam_date_stays_in_database`. |

Chưa sửa (ít gặp): thư mục cha tên dạng `HoSo2024` khi PDF không nằm trong thư mục Hộp thì thư mục tỉnh bị nhận là ổ đĩa (`D:\`).

## 12. Rà soát thêm: tra cứu, thống kê dãy số, tên công dân (22/11/2026)

| Lỗi | Đã sửa |
|---|---|
| Sửa họ tên chưa đọc rõ trong bảng xong, ô "Tổng số GPLX" và ghi chú không tính lại (sổ ghi tổng trống, "Cần rà soát") | Sửa ô họ tên cũng tính lại tổng số, dãy số và ghi chú như khi sửa số GPLX. Test: `test_correcting_an_unclear_name_updates_total_and_status`. |
| Danh sách chỉ có 1 GPLX bị ghi "Ngắt, không theo thứ tự" | Một số GPLX duy nhất là "Đủ". Test: `test_list_with_one_license_is_complete`. |
| Chuẩn hóa địa chỉ tạo chuỗi lạ "… -, Tỉnh Yên Bái" | Chỉ thêm dấu phẩy trước "Tỉnh" khi địa chỉ chưa có dấu ngăn cách riêng. Test: `test_address_keeps_its_own_separator_before_the_province`. |
| Đoán dấu họ tên sai (`Thanh` → `Thành`, `Nguyen` → `Nguyễn`) trong CSDL tra cứu | Đã chốt phương án (a): bỏ đoán dấu, họ tên lưu đúng chữ OCR/người duyệt (`clean_vietnamese_name` chỉ làm gọn khoảng trắng, dấu câu dính chữ, và đổi tên viết HOA thành dạng thường). Tìm không dấu vẫn ra như cũ. Dữ liệu cũ đổi theo khi "Quét lại từ Excel". Test: `test_names_are_stored_as_read_without_guessing_accents`. |
| "Quét lại từ Excel" chạy trên luồng giao diện, kho lớn qua LAN làm cửa sổ "Not Responding" | Chạy nền; nút hiện "Đang đồng bộ…" và khóa tới khi xong; đóng app khi đang đồng bộ bị chặn như các tác vụ nền khác. Sổ tổng hợp được đọc từ bản sao trong bộ nhớ để máy này hoặc máy khác vẫn lưu được trong lúc đồng bộ. Test: `test_sync_from_excel_runs_in_the_background`. |

## 13. Chia sẻ LAN, giữ ô đã nhập, ngày đáng ngờ, bắt buộc nhập đủ (22/11/2026)

| Việc | Đã làm |
|---|---|
| Bật chia sẻ LAN khi cổng đang bị dùng: báo "Khởi chạy thành công" nhưng không có máy chủ | Chỉ báo chạy khi máy chủ đã mở được cổng; nếu không thì báo "Không mở được cổng …, hãy chọn cổng khác" và giữ trạng thái tắt. Test: `test_lan_server_on_a_busy_port_reports_failure`. |
| Chuyển sang file khác thì mất các ô đã nhập tay chưa xác nhận (quay lại thấy lại giá trị máy đọc) | Trước khi rời hồ sơ, các ô được giữ thành bản nháp (`review_draft`) đi cùng file; dữ liệu máy đọc không bị ghi đè. Test: `test_typed_values_are_kept_when_switching_to_another_file`. |
| Ngày máy đọc sai nhưng vẫn được điền | Để trống kèm lời nhắc khi: năm < 1990 hoặc sau hôm nay; ngày ký trước ngày thi (thi trước 01/03/2025); mọi chỗ ghi ngày đó có độ tin cậy OCR < 0,50. Đo trên mẫu: ngày viết tay đọc đúng có độ tin cậy 0,59–0,79 nên ngưỡng 0,80 ban đầu sẽ xóa nhầm 5/7 ngày đúng; mẫu chưa có ngày đọc sai để đo khả năng bắt lỗi của ngưỡng này. Test: `test_implausible_dates_are_left_blank_for_review`, `test_signed_before_exam_leaves_both_dates_blank`, `test_date_read_with_very_low_confidence_is_left_blank`. |
| Bắt buộc nhập đủ các ô trước khi lưu | Xem `docs/02` mục Luồng A bước 2. Dấu `-` = giấy không ghi. Test: `test_every_box_must_be_filled_before_saving`. |
| Bấm lại đúng file đang mở trong danh sách thì mất ô vừa gõ; bản nháp cũ có thể đè giá trị đã xác nhận khi lưu thất bại | Luôn giữ bản nháp trước khi nạp lại màn hình (kể cả khi bấm lại cùng file); bấm xác nhận thì xóa bản nháp cũ. Test: `test_clicking_the_open_file_again_keeps_typed_values`, `test_confirmed_values_replace_an_older_draft`. |
| Số cổng LAN không hợp lệ (70000, -5, chữ) bị báo là "cổng đang được dùng", hoặc lặng lẽ dùng 8080 | Báo "Cổng … không hợp lệ. Cổng phải là số từ 1 đến 65535"; đang chia sẻ thì địa chỉ hiển thị theo cổng đang chạy. Test: `test_lan_server_rejects_ports_outside_the_valid_range`. |
| Thư mục Hộp có chữ cái (`Hop 49A`) không được nhận: ô Hộp trống và sổ tổng hợp bị tạo riêng trong thư mục Hộp đó; Hộp số có chữ cái (`HO SO 116B`) để trống | Nhận số kèm chữ cái (`49A`, `116B`); sổ tổng hợp nằm ở thư mục trên Hộp như các Hộp khác. Test: `test_box_numbers_with_a_letter_are_kept_and_the_province_stays_above`. |
| `HOP 49 (2010)` cho Hộp = 2010 | Lấy số đứng ngay sau chữ Hộp; tên còn số khác thì để trống kèm lời nhắc (ẩn khi đã nhập). Test: `test_other_numbers_in_a_box_folder_name_leave_the_box_for_review`, `test_box_folder_note_is_shown_until_the_box_is_typed`. |
| Bản sửa trên làm hỏng ngược tên có ký hiệu giữa chữ và số (`HOP (49)`, `HOP#49`, `HOP [49]`, `HO SO (116)`): Hộp trống, sổ tổng hợp tạo riêng | Chấp nhận mọi ký hiệu như bản cũ; đã so bản cũ và bản mới trên 2640 tổ hợp tên: không còn tên nào bản cũ nhận được mà bản mới nhận khác. Chữ cái viết cách (`HOP 49 A`) được giữ (`49A`). `Từ 1990 đến 1995` không bị coi là Tủ. Test: `test_box_numbers_with_a_letter_are_kept_and_the_province_stays_above`. |
| Danh sách lọc theo Hộp ở tab tra cứu sắp theo chữ (1, 10, 100, 2…) | Sắp theo số rồi chữ cái (1, 2, 10, 49, 49A, 100). Test: `test_box_filter_lists_boxes_in_number_order`. |

## 14. Tra cứu nhanh, danh sách file, nhiều máy, quét lại, dừng OCR (22/11/2026)

Các lỗi ghi ở `04-quyet-dinh-va-viec-can-lam.md` mục 3.1. Số đo trước/sau trên cùng máy, CSDL nháp.

| Lỗi | Đã sửa |
|---|---|
| 14. Tab Tra cứu dựng mỗi dòng bằng hàng chục ô/nút: đứng 14–28 s với 200 dòng, hết hạn mức 10.000 đối tượng cửa sổ của Windows (mất nút, không mở được hộp thoại), sổ 500 GPLX làm tắt ứng dụng | Kết quả hiện trong một bảng `ttk.Treeview` với một hàng nút dùng chung cho dòng đang chọn (👥 Xem Dân / 👁️ Xem PDF (trang N) / 📊 Excel / 📂 Thư mục); nhấp đúp: sổ → xem dân, công dân → mở PDF đúng trang. Sau sửa: Danh mục 200 sổ 0,3 s, "Xem Dân" sổ 198 GPLX 0,1 s, tìm 200 kết quả 0,1 s; sổ 2.000 GPLX 0,2 s và chỉ dùng 90 đối tượng cửa sổ. Bỏ luôn giá trị giả "A1"/"Đủ" khi sổ chưa có hạng/nhận định. Test: `test_search_results_are_one_table_and_say_when_cut`, `test_book_catalogue_says_when_cut_and_opens_a_book`. |
| 15. Danh sách file dựng lại toàn bộ mỗi lần một file đổi trạng thái (2,1 s/100 file, 10,6 s/500 file) | Chỉ cập nhật thẻ của file thay đổi; chỉ dựng lại khi đổi danh sách. Sau sửa: 0,01–0,02 s với 50–500 file. Test: `test_status_change_updates_only_that_file`. |
| 16. Mở thư mục ở máy này giữ file sổ tổng hợp mở → máy khác lưu bị báo "Hãy đóng sổ trong Excel" | `_registered_names` và `_index_single_excel` đọc file vào bộ nhớ trước. Test: `test_folder_listing_does_not_block_a_save_of_the_summary`. |
| 17. Quét lại từ Excel không bỏ hồ sơ có PDF đã mất → hồ sơ/công dân trùng sau khi lưu đổi tên mà ghi CSDL lỗi; thông báo nhắc nút "Đồng bộ từ Excel" không tồn tại | Quét lại bỏ các dòng CSDL có PDF nằm trong thư mục được quét mà file không còn, báo tên trong kết quả (thư mục không truy cập được thì không bỏ gì). Thông báo và docs dùng đúng tên nút "🔄 Quét lại từ Excel". Test: `test_resync_drops_dossiers_whose_pdf_is_gone`. |
| 18. Kết quả bị cắt ở 200 (web LAN: 100) nhưng vẫn ghi "Tìm thấy 200 kết quả" / "Có 200 cuốn sổ" | Đếm tổng riêng (`count_search`, `count_dossiers`); bị cắt thì ghi "Hiện 200/300 kết quả đầu — hãy gõ cụ thể hơn" / "Hiện 200/950 cuốn sổ mới nhất — lọc …". API `/api/search` trả thêm `total_matches`, trang web ghi "100/300 đầu tiên". Test: `test_search_counts_all_matches_beyond_the_shown_rows`. |
| Nhỏ a. Bấm vào file đang lưu (hoặc mở nó từ tab Tra cứu) làm khung xem mở PDF → lưu lỗi "file đang được mở" | File đang lưu không được mở vào khung xem; mở từ tab Tra cứu thì báo "Hồ sơ này đang được lưu". Test: `test_file_being_saved_is_not_opened_in_the_preview`. |
| Nhỏ b. OCR tự động không dừng được, không đóng được ứng dụng khi đang OCR | Nút OCR thành "Đang chạy OCR… (bấm để dừng)": dừng sau file đang đọc, các file chưa đọc về "Chờ". Đóng ứng dụng khi chỉ còn OCR thì hỏi xác nhận rồi đóng (OCR chỉ đọc file); đang lưu, quét thư mục hay đồng bộ CSDL thì vẫn chặn như cũ. Test: `test_batch_ocr_can_be_stopped`, `test_app_can_close_while_only_ocr_runs`. |

Bổ sung 22/11/2026: bảng kết quả tab Tra cứu (`ttk.Treeview`) không phóng theo mức Scale của Windows như các phần CustomTkinter, ở 200% chữ cao 20 px so với 31 px của bảng cũ. Cỡ chữ, chiều cao dòng và độ rộng cột giờ nhân theo `_get_widget_scaling()` (cập nhật lại khi cửa sổ sang màn hình có mức Scale khác), thanh cuộn đổi sang `CTkScrollbar`. Chữ lại cao 31 px như trước; sổ 2.000 GPLX vẫn vẽ trong 0,2 s. Test: `test_result_table_follows_the_windows_display_scale`.

Bổ sung 22/11/2026 (2): bảng danh sách GPLX ở tab Số hóa bị cùng lỗi (chữ cao 17 px ở 200%, cột chỉ chiếm nửa khung) và được sửa cùng cách; phần chia tỷ lệ dùng chung ở `src/gui/table_style.py`. Cột Họ tên và Nơi cư trú giãn ra cho bảng phủ hết khung. Hàng nút chọn danh sách (bị cắt chữ khi PDF có nhiều danh sách, ví dụ 10) đổi thành ô chọn thả xuống "Đang xem (N danh sách)". Test: `test_list_table_follows_the_display_scale_and_lists_are_a_drop_down`.

## 15. Khung theo Scale, danh sách file dạng bảng, đóng khi OCR, tab Tra cứu (22/11/2026)

Các lỗi ghi ở `04-quyet-dinh-va-viec-can-lam.md` mục 3.2. Số đo trước/sau trên cùng máy (Scale 200%), CSDL nháp, bản sao PDF.

| Lỗi | Đã sửa |
|---|---|
| 19. Ở Scale 200% danh sách file và khung xem PDF chỉ rộng một nửa, nút bị cắt chữ, tên file chỉ hiện "15.S" | Độ rộng và độ rộng tối thiểu của ba khung (280/230, 540/380, 580/420) nhân theo Scale, tính lại khi cửa sổ sang màn hình có Scale khác. Sau sửa: 280 / 540 / 566, không nút nào bị cắt. Trong bảng danh sách GPLX và bảng tra cứu, cột Họ tên, Nơi cư trú, Hồ sơ không bị ép nhỏ hơn độ rộng thiết kế: khung hẹp thì bảng cuộn ngang. (Khung Rà soát mặc định đổi sang 511 ở mục 16.) Test: `test_first_start_uses_the_default_widths_for_the_display_scale`, `test_list_table_follows_the_display_scale_and_lists_are_a_drop_down`, `test_result_table_follows_the_windows_display_scale`. |
| 20. Danh sách file mỗi file một thẻ: 1.000 file đứng 12,7 s, 1.300 file 20,2 s và hết hạn mức đối tượng cửa sổ | Danh sách là một bảng `ttk.Treeview` hai cột "Trạng thái" và "Tên file", màu chữ theo trạng thái. Bấm (nhả chuột đúng dòng vừa bấm) hoặc Enter để mở file; phím mũi tên chỉ di chuyển, không mở (mở là bắt đầu OCR). File đang mở được tô nền xanh nhạt, kể cả khi ứng dụng tự chuyển sang file kế tiếp sau khi lưu. Tên dài cắt ở giữa cho vừa cột, giữ đầu và đuôi (`HO SO 116 - ba… lan 2 (anh mo)`), đổi độ rộng khung thì tính lại; bỏ đuôi `.pdf`. Sau sửa: 300 file 0,1 s, 1.000 file 0,2 s, 1.300 file 0,3 s, 3.000 file 0,6 s; số đối tượng cửa sổ không đổi theo số file. Test: `test_a_long_file_list_is_one_table`, `test_status_change_updates_only_that_file`, `test_long_file_names_keep_their_start_and_end`. |
| 21. Đóng khi đang OCR: chương trình chạy ngầm ~160 s, khóa PDF | Vẫn hỏi xác nhận như trước; đồng ý thì sau khi đóng cửa sổ chương trình kết thúc ngay (`GPLXApp.run`, ghi log trước). Chỉ áp dụng khi việc nền duy nhất là OCR (chỉ đọc file); đang lưu, quét thư mục hay đồng bộ CSDL thì vẫn chặn đóng như cũ. Sau sửa: kết thúc 0,1 s sau khi đóng cửa sổ, đổi tên PDF được ngay. Test: `test_app_can_close_while_only_ocr_runs`, `test_closing_during_ocr_ends_the_process_at_once`. |
| 22. Dừng OCR, file đang mở về "Chờ" mà khung rà soát vẫn ghi "Đang đọc thông tin PDF…" | Khung rà soát ghi "Đã dừng OCR trước khi đọc file này. Bấm lại vào file để đọc." Test: `test_batch_ocr_can_be_stopped`. |
| 23. Enter trong bảng tra cứu chỉ chạy khi chuột nằm trên một dòng | Enter (cả Enter bàn phím số) mở dòng đang chọn, không xét vị trí chuột; nhấp đúp vẫn bỏ qua tiêu đề cột. Test: `test_enter_opens_the_selected_row_wherever_the_mouse_is`. |
| 24. "👥 Xem Dân" bị lọc theo tỉnh đang chọn ở chế độ tìm công dân | Xem dân của một sổ luôn hiện cả sổ; ô tỉnh chỉ lọc khi tìm theo từ khóa. Test: `test_a_book_lists_all_its_citizens_and_says_why_it_is_empty`. |
| 25. Sổ không có công dân báo "không khớp với từ khóa" | Hồ sơ đổi tên nhanh: "Hồ sơ … mới được đổi tên nhanh, chưa số hóa danh sách GPLX nên chưa có danh sách công dân để xem." Sổ có Excel mà không có dòng: "Cuốn sổ … chưa có công dân nào trong CSDL." Sổ đã bị bỏ khỏi CSDL: "… không còn trong CSDL". Test: như lỗi 24. |
| 26. Bảng tra cứu không đọc lại sau "Quét lại từ Excel" và sau khi lưu | Quét lại xong, hoặc lưu hồ sơ xong mà CSDL ghi được, bảng đang hiện được đọc lại: Danh mục theo bộ lọc đang chọn, kết quả tìm theo từ khóa đã tìm, danh sách dân của một sổ tìm lại sổ theo tên (lưu/quét lại tạo mã sổ mới). Lỗi khi đọc lại chỉ ghi log, không bật hộp thoại. Test: `test_rows_shown_are_read_again_after_a_rescan`, `test_save_failure_reopens_pdf_then_success_follows_renamed_file`. |
| 27. Lăn chuột trên bảng danh sách GPLX cuộn cả khung rà soát | Lăn chuột trên bảng chỉ cuộn bảng (3 dòng mỗi nấc; bàn di chuột cộng dồn các bước nhỏ); bảng đã tới đầu/cuối thì khung rà soát cuộn tiếp. Test: `test_wheel_over_the_list_scrolls_the_list_not_the_form`. |

## 16. Khung Rà soát mở ở 55% bảng GPLX, nhớ vị trí vách ngăn (22/11/2026)

Yêu cầu của chủ dự án: lần đầu mở app, bảng GPLX ở khung Rà soát thấy 55% bề ngang (trước là 62%); các lần sau mở đúng chỗ đã kéo vách ngăn. Độ rộng ghi ở đơn vị Scale 100% (nhân theo Scale khi hiển thị).

| Việc | Cách làm |
|---|---|
| Độ rộng lần đầu | Danh sách file 280, khung Rà soát 511. Khung Xem PDF nhận phần còn lại của cửa sổ (`stretch="always"`, hai khung bên `"never"`), nên phóng to/thu nhỏ cửa sổ hay đổi màn hình chỉ làm đổi khung PDF. Đo trên máy này (2880 px, Scale 200%, mẫu `15.SQL.03.1996`, danh sách 1 rộng 829): 280 / 595 / 511, bảng GPLX thấy 54,9% (hiện "55%"). Trước: 280 / 540 / 566, 62%. |
| Nhớ vách ngăn | Kéo vách trái thì nhớ độ rộng danh sách file, kéo vách phải thì nhớ độ rộng khung Rà soát. Ghi vào `%LOCALAPPDATA%\GPLX\giao_dien.json` 0,1 s sau khi nhả chuột, khi Tk đã xếp lại khung. File riêng từng máy (mỗi máy một màn hình), không nằm cạnh CSDL dùng chung. Chỉ ghi khi độ rộng đổi, và chỉ ghi khung của vách vừa kéo: cửa sổ hẹp làm Tk ép tạm các khung khác, không được lưu độ rộng bị ép đó. Đổi Scale (kéo cửa sổ sang màn hình khác) dùng độ rộng đã nhớ. File hỏng hoặc giá trị lạ (chữ, `true`, nhỏ hơn độ rộng tối thiểu, lớn hơn 4000) thì bỏ qua, dùng độ rộng lần đầu; ghi file không được thì chỉ ghi log. Xóa file để về lại độ rộng lần đầu. |
| Kiểm tra trên cửa sổ thật (Scale 200%) | Kéo vách phải 100 sang trái: 280 / 495 / 611, lưu Rà soát 611. Kéo vách trái 40 sang phải: 320 / 455 / 611, lưu danh sách file 320. Mở lại: 320 / 455 / 611. Thu nhỏ cửa sổ (1400): 320 / 415 / 611. Phóng to lại: 320 / 455 / 611. Đã nhớ Rà soát 726 (rộng nhất màn hình cho phép) thì mở lại đúng 280 / 380 / 726, dù cửa sổ mở ở 1400 rồi mới phóng to (Tk chỉ ép tạm). |
| Test | `PaneLayoutTest` (7 test): độ rộng lần đầu theo Scale; nhớ cho lần mở sau và khi đổi Scale; mỗi vách chỉ ghi khung của nó; bấm mà không kéo thì không ghi; đọc độ rộng sau khi Tk xếp lại khung; file hỏng; không ghi được file. |

Ở 511, ô "Khóa" (cạnh ô "Hạng") bị ép còn 25/60 và cắt chữ "26": ghi ở `04-quyet-dinh-va-viec-can-lam.md` mục 3.3 (lỗi 28).

Thay đổi sau đó cùng ngày (chiều 22/11, chủ dự án sửa):

- Độ rộng lần đầu đổi thành danh sách file 246, Xem PDF 630, khung Rà soát 510; độ rộng nhỏ nhất 180 · 380 · 400 (`PANES` trong `src/gui/app.py`). Đo trên cửa sổ thật: bảng GPLX thấy 54,8%. Test `PaneLayoutTest` đã đổi số theo.
- Lỗi 28: "Hạng / Khóa" có dòng riêng (Hạng 60, Khóa 80), ô Ngày thi có dòng riêng (180), HỘP và HỘP SỐ rộng 90. Khóa không còn bị ép. HỘP và HỘP SỐ vẫn bị ép khi khung Rà soát hẹp hơn khoảng 533: Lỗi 30, `04` mục 3.4.
- Ghi chú đặt tên tách thành từng dòng; mục bắt buộc chữ đỏ (test `test_naming_notes_render_required_items_in_red_and_others_in_black`).
- Khung Xem PDF: nút Xoay, +, − dồn sang trái; mỗi lần phóng to/thu nhỏ 10%.
- Đọc bảng: thêm `_recover_missing_columns` khôi phục cột STT / TT B.Kê (xem `02` luồng A); test `test_missing_stt_column_reconstructed_from_sequential_codes_and_names`, `test_missing_register_index_header_reconstructed`. Còn Lỗi 29 và 31, `04` mục 3.4.
- Đóng gói: file zip giữ cả thư mục rỗng (`build_portable.py`).

## 17. Kế hoạch: đặt tên và tổng hợp theo cả sổ, ghi chú rõ hơn, Lỗi 29–31 (22/11/2026 — đã làm, kết quả ở cuối mục)

Hiện trạng (theo code): xác nhận một PDF có nhiều danh sách **đã** tạo đúng 1 PDF (đổi tên một lần) và 1 Excel (mỗi danh sách một sheet "Danh sách GPLX n"), CSDL nhận công dân của mọi danh sách. Nhưng tên file (SQL: số GPLX đầu–cuối), tổng số, dãy số và nhận định ghi vào sổ tổng hợp chỉ lấy từ **một** danh sách người dùng chọn ở ô "Danh sách n · trang …". Vì vậy sổ tổng hợp lệch với Excel/CSDL, và giao diện trông như mỗi danh sách là một hồ sơ riêng.

| Bước | Việc | Cách làm | Test (viết trước) |
|---|---|---|---|
| 1 | Lỗi 29 | `_recover_missing_columns` giữ cờ tin cậy OCR của ô họ tên, không gán lại `bool(tên)`. Dòng mà máy phải đoán cách tách (cụm dồn vào ô STT/TT B.Kê, tên còn 1 chữ) thì đánh dấu cần đối chiếu. | `QD_000493` dựng từ OCR đã lưu thành dữ liệu test: trang 5 giữ đủ 6 tên ("Tran Quy Quan"…), dòng cần đối chiếu không giảm so với khi tắt khôi phục. |
| 2 | Lỗi 31 | Cho phép ký tự rác trước mã ("I", "l", "\|", ":") và "/" giữa mã và tên. Ô cột đầu dạng "STT mã Họ…" tách thành STT, mã, phần chữ ghép lên đầu họ tên; ô TT B.Kê dạng "mã Họ" cũng vậy. Các dòng này tô vàng. | Dòng 4, 13, 14, 23, 34, 43, 61, 68 của `QD_000493`. |
| 3 | Đặt tên và tổng hợp theo cả sổ | Nhóm SQL: số GPLX đầu = số đầu của danh sách đầu, số cuối = số cuối của danh sách cuối (theo thứ tự trang). Tổng số = cộng các danh sách; dãy số và nhận định tính trên toàn bộ (hàm tổng hợp nhận nhiều danh sách). Danh sách nào còn trang cần đối chiếu hoặc dòng chưa chắc thì nhận định "Cần rà soát" kèm lý do theo từng danh sách. Bỏ ô chọn "danh sách dùng để đặt tên"; thay bằng nút "Đối chiếu trang n" cho mọi trang chưa rõ của mọi danh sách. Ô "Đang xem" của bảng giữ nguyên. | Sổ 8 danh sách: tên lấy đầu của DS1, cuối của DS8; tổng = tổng các DS; sổ tổng hợp khớp số dòng Excel/CSDL; không còn lỗi "Hãy chọn danh sách". |
| 4 | Ghi chú đặt tên | Dòng đỏ "Cần rà soát" đổi thành tiêu đề "Cần sửa trước khi lưu:" và các mục bên dưới thụt vào; "Cần rà soát" chỉ còn là giá trị Nhận định. Lỗi mã tỉnh ghi kèm gợi ý: "Chưa chọn mã tỉnh lưu trữ (OCR gợi ý: 15 – Tỉnh Lào Cai)"; OCR không đọc được thì gợi ý theo tên thư mục tỉnh (`Tỉnh Yên Bái`, `YenBai` → 15) và ghi rõ nguồn; không có gì thì ghi "(OCR không đọc được mã tỉnh)". | Test chữ hiện ra cho 3 trường hợp; test tên thư mục có/không dấu cách. |
| 5 | Lỗi 30 | HỘP và HỘP SỐ mỗi ô một dòng (như Hạng/Khóa). Đo lại trên cửa sổ thật; đặt độ rộng nhỏ nhất của khung Rà soát bằng mức không ô/nút nào bị ép (dự kiến khoảng 470, hiện 400), hoặc rút gọn chữ nút xác nhận nếu chủ dự án muốn giữ 400. | Đo bằng cửa sổ thật ở 400/484/510; test `PaneLayoutTest` theo số mới. |
| 6 | Hoàn tất | Cập nhật `02`, `04`, sổ tay; chạy đủ bộ test; build lại exe. | |

Cần chủ dự án chốt trước khi làm: (a) Excel giữ mỗi danh sách một sheet (đề xuất, vì các danh sách có thể khác cột) hay gộp vào một sheet có thêm cột "Danh sách"; (b) cách lấy số đầu/cuối ở bước 3; (c) gợi ý mã tỉnh theo tên thư mục; (d) độ rộng nhỏ nhất khung Rà soát ở bước 5.

Chủ dự án chốt (22/11/2026): (a) Excel giữ mỗi danh sách một sheet; (b) số đầu/cuối như bước 3; (c) **không** gợi ý mã tỉnh theo tên thư mục: OCR không đọc được mã thì không gợi ý; (d) khung Rà soát nhỏ nhất 470.

Kết quả:

| Bước | Đã làm | Kiểm tra |
|---|---|---|
| 1–2 (Lỗi 29, 31) | `_recover_missing_columns` (`src/table_extractor.py`) giữ cờ tin cậy OCR (`_keep_review`); dòng phải đoán chỗ bắt đầu họ tên hoặc tên một chữ thì tô vàng. Mẫu mã nhận ký tự lạ trước mã và "/" sau mã; ô "STT mã Họ" / "mã Họ" ở cột đầu hoặc ô TT B.Kê được tách, phần chữ ghép lên đầu họ tên. | Test `ColumnRecoveryReviewTest` (3 test). OCR đã lưu của `QD_000493`: dòng vàng 14 → 15 (trước khi sửa là 4); 6 tên trang 5 đủ ("Tran Quy Quan"…); dòng 4, 13, 14, 23, 34, 43, 61, 68 tách đúng mã và họ tên; dòng vàng mới duy nhất là dòng 61 "Nguyén Manh Hung" (họ nằm ở ô TT B.Kê). |
| 3 | `summarize_license_tables` (`src/pipeline.py`) tổng hợp mọi danh sách; `process_dossier_pdf` và đổi tên theo folder (`fast_extract_rename_metadata`) dùng nó, không còn báo "Có nhiều danh sách GPLX". Panel bỏ ô chọn danh sách; nút "Đối chiếu trang n" cho mọi trang chưa rõ, 3 nút một hàng; sửa ô ở bất kỳ danh sách nào cũng tính lại cả sổ. | Test `WholeBookSummaryTest`, `test_folder_naming_of_several_sql_lists_spans_the_book`, `test_several_lists_are_named_and_summarized_as_one_book`, `test_every_unclear_page_of_the_book_has_a_button`, `test_page_buttons_wrap_three_to_a_row`. |
| 4 | Tiêu đề "Cần sửa trước khi lưu:", mục lỗi có dấu "•". Lỗi mã tỉnh ghi kèm gợi ý OCR (`src/naming_rules.py`); khi đã có lỗi này thì không lặp dòng "Mã tỉnh OCR gợi ý". | `test_missing_province_names_the_ocr_suggestion_only_when_there_is_one`, `test_naming_notes_render_required_items_in_red_and_others_in_black`. |
| 5 (Lỗi 30) | HỘP SỐ và Nhận định có dòng riêng; khung Rà soát nhỏ nhất 400 → 470 (`PANES`). Độ rộng đã lưu nhỏ hơn 470 bị bỏ, dùng lại 510. | Cửa sổ thật Scale 200%, mẫu `15.SQL.03.1996`: 470 / 480 / 510 không ô hay nút nào bị ép (bảng GPLX thấy 49,9% / 51,1% / 54,8%). Dưới 470 chỉ nút xác nhận bị ép (434 → 428 ở 460). Test `test_box_fields_have_their_own_rows`, `PaneLayoutTest`. |
| 6 | Cập nhật `02`, `04`, sổ tay. Bộ test 136 test OK (1 bỏ qua). | |

Bổ sung 22/11/2026 (theo yêu cầu chủ dự án): khung ghi chú đặt tên chỉ còn lỗi chữ đỏ. Bỏ các dòng chữ đen: nhóm hồ sơ, loại giấy tờ, "Mã tỉnh OCR gợi ý", lý do theo từng danh sách (`table_review`). Ghi chú thư mục cho ô Hộp / Hộp số còn trống chuyển thành lỗi đỏ, vì ô này bắt buộc trước khi lưu. Test `test_naming_notes_show_only_the_errors_in_red`, `test_box_folder_note_is_shown_until_the_box_is_typed`.

Bổ sung 22/11/2026 (2) (theo yêu cầu chủ dự án):
- Tổng số GPLX tự điền bằng số dòng OCR đọc được ở mọi danh sách, kể cả khi còn dòng hoặc trang chưa rõ (trước đó để trống). Nhận định vẫn "Cần rà soát" nếu chưa chắc. Mẫu `15.SQL.03.1996` (10 danh sách): 127.
- Kiểm tra giá trị gõ: Ngày thi/sát hạch dạng `dd-mm-yyyy` và là ngày có thật; Số GPLX đầu/cuối (nhóm SQL) viết hoa, 1–2 chữ cái + 6 chữ số liền nhau. Ngày thi do máy đọc tự đổi sang `dd-mm-yyyy`. `typed_format_errors`, `format_exam_date` (`src/naming_rules.py`); test `test_exam_dates_read_by_the_machine_are_written_dd_mm_yyyy`, `test_typed_exam_date_and_sql_endpoints_must_be_in_the_stored_form`, `test_an_exam_date_read_by_the_machine_is_shown_dd_mm_yyyy`, `test_a_typed_exam_date_must_be_dd_mm_yyyy`, `test_typed_gplx_endpoints_must_be_upper_case`.

