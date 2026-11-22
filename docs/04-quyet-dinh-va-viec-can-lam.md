# 04. Quyết định đã chốt, thay đổi cần làm và lỗi đã phát hiện

Cập nhật: 22/11/2026. Các mục B*/C* ở mục 2–3 đã xử lý theo `05-ke-hoach-sua-loi.md` (C3 hoãn, B8 giữ nguyên). Mục 3.1 và 3.2 (hai lần rà soát ngày 22/11/2026): **đã sửa cùng ngày**, xem `05-ke-hoach-sua-loi.md` mục 14 và 15. Mục 3.3 và 3.4: **đã sửa** ngày 22/11/2026 (Lỗi 28 phần Hạng/Khóa chiều 22/11; Lỗi 29, 30, 31 theo `05` mục 17). Gộp danh sách thành một cho mỗi PDF, 1 sheet Excel, ghép cột theo vị trí in trên giấy: **đã làm**, xem `05` mục 21.

## 1. Quyết định đã chốt với chủ dự án

| # | Chủ đề | Quyết định |
|---|---|---|
| D1 | Cấu trúc thư mục | Theo code: `DuLieuSoHoa_GPLS/<Tỉnh>/HOP_xx/HoSo_xx` |
| D2 | Nạp file | Người dùng tự chép PDF vào thư mục; app không cần chức năng upload |
| D3 | Mã tỉnh | Dùng mã tỉnh mới sau sáp nhập (`data/province_codes.json`), vd Yên Bái → 15 |
| D4 | File đầu vào | Tên dạng `H38.8.4_SG_000116_V1_20260425_000003` (tên của đơn vị scan); app đổi sang tên theo quy định |
| D5 | Quy tắc tên | 3 nhóm SQL (≤ 31/12/2012), QĐTT (01/01/2013–28/02/2025), QĐSH (từ 01/03/2025); ngày trong tên dùng dấu chấm |
| D6 | Loại hồ sơ bổ sung | Cần thêm 2 loại: đổi GPLX nước ngoài/Công an/Quân đội; cấp phép trung tâm sát hạch — **hoãn, phát triển sau** (21/11/2026) |
| D7 | Đổi tên | **Đổi tên hẳn, không giữ file gốc** |
| D8 | Luồng xử lý | Cả luồng A và luồng B đều là luồng chính |
| D9 | Luồng B và CSDL | Luồng B **ghi CSDL, chỉ thông tin hồ sơ** (bảng `dossiers`), không có danh sách công dân |
| D10 | Excel con | Gộp toàn bộ thành 1 sheet "Danh sách GPLX" duy nhất cho mỗi PDF (ghép cột theo vị trí in trên giấy; `GPLX/3`). Excel cũ nhiều sheet vẫn đọc được và tự động gộp |
| D11 | CSDL | Giữ cấu trúc hiện tại của code |
| D12 | Mạng | ~~1 máy chủ chạy app; máy khác tra cứu qua trình duyệt~~ → **Máy chủ chia sẻ thư mục `So Hoa GPLX`; máy con mở app từ thư mục chia sẻ, OCR trên máy con, dùng chung PDF/Excel/CSDL** (21/11/2026). Kế hoạch: `05-ke-hoach-sua-loi.md` |
| D13 | Tài liệu cũ | Không chính xác; dựa vào code và `docs/`. Giữ nguyên file cũ |
| D14 | STT sổ tổng hợp | Sửa để STT luôn đúng |
| D15 | Format sổ tổng hợp | Theo file mẫu `File tổng soát số hóa GPLX.xlsx`; giữ tên file `So_Theo_Doi_Day_So_GPLX_<mã>.xlsx`; dòng mới luôn thêm cuối bảng |

## 2. Thay đổi cần làm (từ các quyết định)

| # | Thay đổi | Chỗ liên quan |
|---|---|---|
| C1 | Đổi tên thật thay vì sao chép (D7). Cần xem lại: cache theo đường dẫn, `source_stamp`, sheet `_GPLX_Rename` (nguồn = đích sau đổi tên), rollback khi lưu sổ/Excel lỗi, nhận diện file "đã xong" khi quét lại thư mục | `pipeline._copy_named_pdf`, `commit_dossier`, `commit_folder_dossier`, `list_folder_review_pdfs`, `batch_copy_and_rename_folder_pdfs` |
| C2 | Luồng B ghi bảng `dossiers` (D9); cần quyết định `excel_path` khi không có Excel con (cột đang `NOT NULL`) và cách "Đồng bộ từ Excel" xử lý hồ sơ không có Excel | `commit_folder_dossier`, `database.insert_or_update_dossier` |
| C3 | Thêm 2 loại hồ sơ mới vào quy tắc đặt tên, giao diện rà soát, nhận diện tài liệu (D6) | `naming_rules.py`, `cover_parser.py`, `review_panel.py` |
| C4 | ~~STT sổ tổng hợp luôn đúng (D14)~~ — **đã làm 21/11/2026** cùng D15 (`test_master_summary_format.py`) | `master_summary.write_summary_entry` |
| C5 | Bổ sung keyword cho tỉnh cũ đã sáp nhập (Hà Giang, Bắc Kạn, Hòa Bình chưa có keyword; app vẫn tạo thư mục cho các tỉnh này) | `data/province_codes.json` |

## 3. Lỗi / điểm đáng ngờ đã phát hiện (chưa sửa)

| # | Mức | Mô tả | Vị trí |
|---|---|---|---|
| B1 | Cao | `/api/pdf?path=` và `/api/excel?path=` nhận **đường dẫn bất kỳ** → máy khác trong mạng tải được mọi file `.pdf`/`.xlsx` trên máy chủ; không có xác thực; CORS mở cho mọi nguồn. Nguy hiểm nếu mở ra WAN | `src/server/lan_server.py:50-57, 128-156` |
| B2 | Cao | Giá trị mặc định cứng khi thiếu dữ liệu: Hộp `48`, Hộp số `115`, Hạng `A1`, Khóa `25`, mã tỉnh `15` → có thể lưu sai mà không báo | `folder_parser.py:282-283`, `pipeline.py:158-159, 272-274, 371`, `database.py:273-283`, `review_panel.py:189-201`, `master_summary.py:203-205` |
| B3 | Cao | Hai luồng tìm thư mục tỉnh khác nhau: luồng A dùng `find_province_root_dir` (luôn lùi 2 cấp, không kiểm tra tên), luồng B dùng `folder_review_location` → sổ tổng hợp có thể bị ghi ở 2 nơi; chọn file không nằm đúng 3 cấp thì luồng A ghi sai chỗ | `pipeline.py:372` vs `pipeline.py:292`, `folder_parser.py:301-319` |
| B4 | Trung bình | Luồng A ghi dòng sổ tổng hợp nhưng không ghi `_GPLX_Rename`; sau đó dùng luồng B cho cùng hồ sơ sẽ báo "đã có tên cho hồ sơ khác" | `pipeline.commit_dossier`, `master_summary.record_folder_rename` |
| B5 | Trung bình | Quét thư mục đưa cả file đã đổi tên (vd `15.SQL....pdf`) vào hàng đợi như file nguồn mới: luồng A luôn bị; luồng B bị nếu file chưa có trong `_GPLX_Rename` | `batch_queue._scan_and_populate_folder`, `pipeline.list_folder_review_pdfs` |
| B6 | Trung bình | Luồng A không nguyên tử: PDF + Excel con tạo trước; nếu ghi sổ tổng hợp lỗi (đang mở) thì 2 file vẫn còn; lỗi CSDL chỉ cảnh báo → CSDL lệch file | `pipeline.commit_dossier:358-391` |
| B7 | ~~Thấp~~ | ~~STT sổ tổng hợp = số dòng − 2, sai khi có dòng trống/xóa dòng~~ — **đã sửa** (C4); dòng mới cũng không còn bị ghi sau các ô định dạng trống | `master_summary.py` |
| B8 | Thấp | Tìm kiếm dùng `LIKE '%…%'` (quét toàn bảng); bảng FTS5 được ghi nhưng không dùng | `database.search` |
| B9 | Thấp | CSDL bản exe nằm ở `%LOCALAPPDATA%` của máy chạy app, không nằm cạnh kho dữ liệu; chép kho sang máy khác sẽ không mang theo CSDL | `config.py:41-48` |
| B10 | Thấp | `DatabaseManager()` được tạo ngay khi import `lan_server` | `lan_server.py:59` |
| B11 | Thấp | Docstring sai: `'A461S44-' → 'A161541'` (code thực tế trả `A461544`) | `naming_rules.normalize_license_code` |
| B12 | Thấp | Repo không có `requirements.txt`; `Chay_UngDung_GPLX.bat` gọi `python` hệ thống | thư mục gốc |
| B13 | Thấp | `src/win_ocr.ps1` không được dùng | `src/` |

### 3.1. Rà soát 22/11/2026 — đã sửa cùng ngày (xem `05-ke-hoach-sua-loi.md` mục 14)

Số thứ tự nối tiếp các lỗi 1–13 đã sửa (ghi ở `05-ke-hoach-sua-loi.md` mục 10–13). Số đo lấy trên máy này với CSDL nháp và bản sao PDF, không đụng dữ liệu thật. Thứ tự đề xuất: 14 + 18 (cùng tab Tra cứu), rồi 15, 17, 16, sau đó 2 lỗi nhỏ. Hướng sửa dưới đây chưa được duyệt.

| # | Mức | Lỗi, số đo / cách tái hiện | Vị trí | Hướng sửa |
|---|---|---|---|---|
| Lỗi 14 | Cao | Tab Tra cứu dựng mỗi dòng kết quả bằng hàng chục ô/nút riêng: ~37 đối tượng cửa sổ cho một dòng công dân, ~46 cho một dòng sổ; Windows giới hạn 10.000 đối tượng cho mỗi chương trình. Đứng hình: tìm "Nguyễn Văn" (200 kết quả) 14,3 s; "👥 Xem Dân" sổ 150 GPLX 12 s, sổ 198 GPLX (bằng sổ lớn nhất trong "File tổng soát số hóa GPLX.xlsx") 24 s; mở "Danh mục sổ" khi CSDL có từ 200 sổ 19,7 s, bấm "Lọc Danh Sách" lại 27,6 s. Hết hạn mức: Danh mục 200 sổ (~9.300) cộng khoảng 60 file ở danh sách bên trái → các nút Xem Dân/PDF/Excel cuối bảng không hiện, cửa sổ/hộp thoại mới không mở được; "Xem Dân" sổ 300 GPLX tự chạm 10.000; sổ 500 GPLX → ứng dụng tắt hẳn ("Windows fatal exception: access violation"), mất phần đang nhập dở ở màn hình duyệt. | `src/gui/search_screen.py`: `_render_citizen_results` (dòng 245), `_render_dossier_results` (dòng 360) | Hiện kết quả trong một bảng `ttk.Treeview` (như bảng ở màn hình duyệt) với một hàng nút dùng chung cho dòng đang chọn, hoặc chia trang. Sửa cùng lỗi 18. |
| Lỗi 15 | Trung bình | Danh sách file bên trái xóa và dựng lại mọi dòng mỗi khi một file đổi trạng thái. Mỗi lần đứng hình: 50 file 0,9 s; 100 file 2,1 s; 200 file 3,4 s; 500 file 10,6 s. Lưu một file kéo theo 2–4 lần đổi trạng thái (Đang lưu, Xong, file kế tiếp OCR, Duyệt) → 200 file ≈ 7–13 s đứng hình cho mỗi file; khi OCR tự động, giao diện khựng mỗi lần một file đọc xong. Vị trí cuộn vẫn giữ đúng. | `src/gui/batch_queue.py`: `update_entry` (dòng 298) gọi `_render_queue` (dòng 242) | Chỉ đổi nhãn trạng thái của dòng thay đổi; dựng lại cả danh sách chỉ khi đổi danh sách. |
| Lỗi 16 | Trung bình | Nhiều máy: khi chọn thư mục, máy đọc thẳng sổ tổng hợp tỉnh (giữ file mở trong lúc đọc) để đánh dấu "✅ Xong". Máy khác lưu đúng lúc đó bị báo "Không ghi được PDF hoặc sổ So_Theo_Doi_… Hãy đóng sổ trong Excel…" — sai nguyên nhân vì không ai mở Excel. Đã tái hiện: `os.replace` trong `edit_master_summary` lỗi `PermissionError [WinError 5]`. Không mất dữ liệu (việc lưu được trả lại như cũ), xác nhận lại thì được. Cùng cơ chế, chưa thử riêng: "Quét lại từ Excel" đọc thẳng từng file Excel con. | `src/pipeline.py`: `_registered_names` (dòng 459); `src/database.py`: `_index_single_excel` (dòng 783) | Đọc file vào `io.BytesIO` trước, như `database._index_summary`. |
| Lỗi 17 | Trung bình | Lưu lại một hồ sơ dưới tên khác mà bước ghi CSDL lỗi → ứng dụng bảo "bấm 'Đồng bộ từ Excel'". Làm theo thì CSDL giữ cả tên cũ lẫn tên mới: "Danh mục sổ" hiện 2 sổ, mỗi công dân hiện 2 lần khi tra cứu, một kết quả trỏ tới PDF không còn ("Tệp PDF không tồn tại"). Nguyên nhân: "Quét lại" chỉ thêm/cập nhật, không bỏ dòng có PDF đã mất (kể cả file đổi tên/xóa bằng tay). Đã tái hiện trên bản sao. Ngoài ra không có nút nào tên "Đồng bộ từ Excel": nút thật là "🔄 Quét lại từ Excel" (`docs/03` cũng dùng tên cũ). | `src/database.py`: `reindex_from_directory` (dòng 680); chữ ở `src/gui/app.py:355`, `src/gui/search_screen.py:21`, `docs/03` | Khi quét lại, bỏ các dòng CSDL có PDF nằm trong thư mục được quét mà file không còn; sửa tên nút trong thông báo và tài liệu. |
| Lỗi 18 | Trung bình | Tra cứu cắt bớt kết quả mà không báo. Tìm công dân lấy 200 người nạp sớm nhất (`ORDER BY c.id ASC`) nhưng ghi "Tìm thấy 200 kết quả công dân": thử 300 người tên "Nguyễn Văn…" → hiện 200, không ai thuộc sổ nạp sau cùng, người dùng tưởng không có trong CSDL. "Danh mục sổ" lấy 200 sổ mới nhất nhưng ghi "Có 200 cuốn sổ / file Excel trong CSDL" (dòng thống kê ngay trên ghi đúng tổng). Trang web LAN lấy 100, ghi "(100 kết quả)". | `src/database.py`: `search` (dòng 559), `get_all_dossiers` (dòng 623); `src/gui/search_screen.py` dòng 239, 250, 353, 365; `src/server/static/index.html` dòng 586 | Đếm tổng riêng và ghi "Hiện 200/300 kết quả đầu, hãy gõ cụ thể hơn", hoặc chia trang. Sửa cùng lỗi 14. |
| Nhỏ a | Thấp | Trong vài giây file đang "Đang lưu", bấm vào chính file đó ở danh sách (hoặc mở nó từ tab Tra cứu) thì khung xem mở lại PDF → lưu thất bại "Không đổi tên được …: file đang được mở"; xác nhận lại thì được. Đã tái hiện. | `src/gui/app.py`: `on_file_selected` (dòng 169 mở PDF trước khi xét trạng thái), `on_search_view_pdf` (dòng 139) | Không mở PDF vào khung xem khi file đó đang lưu. |
| Nhỏ b | Thấp | Khi "Chạy OCR tự động" không có nút dừng và không đóng được ứng dụng (bị chặn như khi đang lưu); phải đợi hết hàng đợi hoặc tắt bằng Task Manager. OCR chỉ đọc file nên dừng giữa chừng không hại gì. | `src/gui/app.py`: `on_close` (dòng 384–388), `on_batch_run_requested` | Thêm nút dừng (đánh dấu `cancelled` cho các file còn chờ), hoặc cho đóng khi việc nền chỉ còn là OCR. |

### 3.2. Rà soát 22/11/2026 (lần 2) — đã sửa cùng ngày (xem `05-ke-hoach-sua-loi.md` mục 15)

Số đo trên máy này (Windows Scale 200%, cửa sổ phóng to 2880 px), CSDL nháp và bản sao PDF.

| # | Mức | Lỗi, số đo / cách tái hiện | Vị trí |
|---|---|---|---|
| Lỗi 19 | Trung bình | Ở Scale 200% ba khung tab Số hóa chỉ rộng một nửa: danh sách file 140 thay vì 280, khung xem PDF 270 thay vì 540 (`tk.PanedWindow` tính theo điểm ảnh màn hình, không theo Scale). Nút bị cắt chữ: "📁 Chọn Thư mục Hồ sơ" cần 282 px có 240, "📑 Đổi tên file nhanh (chọn theo folder)" cần 415 có 240, "⚡ Chạy OCR Tự Động" cần 261 có 240; tên file `15.SQL.03.1996.C244337-C244498` cần 325 px có 68, chỉ hiện "15.S". | `src/gui/app.py`: `_build_ingest_tab` |
| Lỗi 20 | Cao | Danh sách file dựng mỗi file bằng một thẻ CustomTkinter (8 đối tượng cửa sổ Windows mỗi file), và chọn thư mục thì lấy cả thư mục con. Đứng hình khi nạp: 300 file 3,5 s; 1.000 file 12,7 s; 1.300 file 20,2 s và chạm hạn mức 10.000 đối tượng: cửa sổ/hộp thoại mới không tạo được (id 0). | `src/gui/batch_queue.py`: `_rebuild_cards` |
| Lỗi 21 | Trung bình | Đóng ứng dụng khi đang OCR: cửa sổ đóng nhưng chương trình chạy ngầm tới khi đọc xong file đang đọc (đo được ~160 s với PDF mẫu 13 MB), giữ PDF mở: đổi tên/xóa PDF đó lỗi `WinError 32`. | `src/gui/app.py`: `on_close`; `app_desktop.py`: `main` |
| Lỗi 22 | Thấp | Đang OCR tự động, mở một file đang chờ lượt rồi bấm dừng: file về "⏳ Chờ" nhưng khung rà soát vẫn ghi "Đang đọc thông tin PDF…". | `src/gui/app.py`: `_finish_batch` |
| Lỗi 23 | Thấp | Bảng kết quả tab Tra cứu: phím Enter chỉ mở dòng đang chọn khi con trỏ chuột nằm trên một dòng (phím mang theo tọa độ chuột, bị kiểm tra như nhấp đúp). | `src/gui/search_screen.py`: `_on_result_double_click` |
| Lỗi 24 | Trung bình | "👥 Xem Dân" lấy cả tỉnh đang chọn ở ô lọc của chế độ tìm công dân: chọn tỉnh khác trước đó thì sổ hiện trống, báo "Không tìm thấy người dân nào khớp với từ khóa". | `src/gui/search_screen.py`: `perform_citizen_search` |
| Lỗi 25 | Thấp | Hồ sơ đổi tên nhanh (Danh mục ghi "160 bằng") bấm "👥 Xem Dân" cũng báo "không khớp với từ khóa", không nói là hồ sơ chưa số hóa danh sách. | `src/gui/search_screen.py`: `_render_citizen_results` |
| Lỗi 26 | Trung bình | Sau "🔄 Quét lại từ Excel" (và sau khi lưu hồ sơ) bảng đang hiện không đọc lại: hồ sơ vừa bị bỏ vẫn nằm trong Danh mục, bấm vào thì báo không tìm thấy PDF. | `src/gui/search_screen.py`: `_finish_sync`; `src/gui/app.py`: `_finish_save` |
| Lỗi 27 | Thấp | Lăn chuột trên bảng danh sách GPLX ở khung rà soát cuộn cả bảng lẫn cả khung rà soát cùng lúc. | `src/gui/review_panel.py`: `_populate_grid` |

### 3.3. Rà soát 22/11/2026 (lần 3) — đã sửa (phần còn lại là Lỗi 30, đã sửa theo `05` mục 17)

Phát hiện khi đổi khung Rà soát mặc định sang 511 (bảng GPLX thấy 55%, `05-ke-hoach-sua-loi.md` mục 16). Số đo ở đơn vị Scale 100%, trên máy này với mẫu `15.SQL.03.1996`.

| # | Mức | Lỗi, số đo / cách tái hiện | Vị trí |
|---|---|---|---|
| Lỗi 28 | Thấp | Thẻ "THÔNG TIN BÌA SỔ & VỊ TRÍ HỒ SƠ" cần 558 mới đủ chỗ. Hẹp hơn thì hai cột ô nhập (cột 1: Ngày thi, HỘP; cột 3: Hạng/Khóa, HỘP SỐ) bị ép đều nhau, và ô "Khóa" (xếp sau ô "Hạng" 50) mất chỗ trước. Khung Rà soát 566 (mặc định cũ): Khóa 52/60, vẫn đọc được. 511 (mặc định mới): Khóa 25/60, chữ "26" bị cắt. 480: Khóa 10/60. Ngày thi, HỘP, HỘP SỐ ở 511 còn 79/120, vẫn đọc đủ "29-03-1996". Từ 600 trở lên không ô nào bị ép. | `src/gui/review_panel.py`: thẻ `card_a` (cột 1 và 3 cùng `weight=1`, `frame_hang_khoa`) |

### 3.4. Rà soát 22/11/2026 (lần 4) — đã sửa 22/11/2026 (`05` mục 17)

Phát hiện khi đối chiếu code sửa chiều 22/11 (khôi phục cột STT / TT B.Kê, bố cục 246 · 630 · 510, Hạng/Khóa xuống dòng riêng) với tài liệu. Đọc bảng kiểm tra trên OCR đã lưu của 10 PDF mẫu `Tỉnh Yên Bái` (không OCR lại), so code hiện tại với cùng code khi tắt `_recover_missing_columns`. Giao diện đo trên cửa sổ thật ở Scale 200%, số ở đơn vị Scale 100%.

| # | Mức | Lỗi, số đo / cách tái hiện | Vị trí |
|---|---|---|---|
| Lỗi 29 | Cao | Khôi phục cột coi mọi dòng có chữ ở ô họ tên là đã đọc chắc (`identity_confident = bool(tên)`), bỏ qua độ tin cậy OCR của ô tên (bình thường phải ≥ 0,62). Với `QD_000493`: dòng tô vàng cần rà soát giảm 14 → 4. Trang 5 lặp lại tiêu đề nên được đọc theo 2 bố cục và chọn bên có điểm `_quality` cao hơn; điểm đổi từ 46/40 (bố cục trang trước thắng) sang 47/49 (bố cục riêng của trang thắng). Kết quả: 6 họ tên bị cắt chỉ còn chữ cuối: dòng 28 "Tran Quy Quan" → "Quan", 36 → "Sang", 37 → "Kien", 46 → "Phu", 47 → "Thiem", 49 → "Ding". Mã bảng kê và phần đầu tên lọt vào ô STT ("28 201076 Tran Quy"). Cả 6 dòng không tô vàng, nên lưu là vào Excel/CSDL mà không có cảnh báo. Thử giữ nguyên cờ tin cậy cũ thì cả 6 tên đủ và vẫn tách được mã (201076 · "Tran Quy Quan"). Tổng số dòng và số GPLX hợp lệ của 10 PDF không đổi (821 / 601). | `src/table_extractor.py`: `_recover_missing_columns` (3 chỗ gán `identity_confident`), `LicenseTableExtractor.read_page` (so `_quality`); `src/pipeline.py:105` cũng dựa vào cờ này |
| Lỗi 30 | Thấp | Phần còn lại của Lỗi 28: Hạng 60/60 và Khóa 80/80 ở mọi độ rộng, nhưng thẻ vẫn cần 498 (khung Rà soát khoảng 533). Hẹp hơn thì ô HỘP và HỘP SỐ bị ép: ở 510 (mặc định) còn 78/90, ở 484 (độ rộng đang lưu trên máy này) còn 66/90, ở 400 (độ rộng nhỏ nhất mới, trước là 420) còn 24/90 và không đọc được "116". Ở 400, nút xác nhận (434 → 368) và 2 ô chọn cũng bị ép. Danh sách file ở 246 không bị ép; ở 180 (nhỏ nhất mới) một nút 220 → 160. | `src/gui/review_panel.py`: `card_a` hàng 3 (HỘP, HỘP SỐ ở cột 1 và 3 `weight=1`); `src/gui/app.py`: `PANES` (minsize) |
| Lỗi 31 | Thấp | Khôi phục cột chưa tách được mã khi trước mã có ký tự lạ, hoặc giữa mã và tên có "/": `QD_000493` dòng 13 "I 201061 Nguyen Dang Khoa", dòng 14 "201062/Vu Durc Cong". Khi OCR gộp mã với họ thành một ô ở cột đầu, cả cụm nằm trong ô STT (dòng 4 "201052 Nguyén", dòng 34, 43) hoặc ô TT B.Kê (dòng 61 "201109 Nguyén", dòng 68), và tên mất họ. Trước khi có khôi phục, các dòng này cũng sai, nhưng cụm nằm ở cột TT B.Kê. | `_recover_missing_columns` (`re_code_and_name`, ô cột đầu) |

Tài liệu chưa khớp code: **đã sửa tài liệu ngày 22/11/2026** (`01`, `02`, `03`, `05` mục 16, `HUONG_DAN_SU_DUNG.md`). Danh sách giữ lại để đối chiếu:

- `02` mục 3 (dòng đầu), `HUONG_DAN_SU_DUNG.md` mục 1, mục 4 và câu hỏi 1 ghi bố cục lần đầu là 280 · 540 · 566, thấy 62% bảng GPLX. Code (`PANES`) là 246 · 630 · 510; đo trên cửa sổ thật thấy 54,8%. `05` mục 16 vẫn ghi 511.
- `HUONG_DAN_SU_DUNG.md` mục 8 ghi "Ctrl + con lăn" để phóng to/thu nhỏ PDF. Code chưa có: con lăn chỉ cuộn dọc, Shift + con lăn cuộn ngang. Nút +/- mỗi lần đổi 10%.
- `HUONG_DAN_SU_DUNG.md` mục 1.4 và cây thư mục mục 2 (file scan gốc nằm cạnh file tên mới), `02` mục 4 ("Hiện code sao chép… chưa làm vậy"): code đã đổi tên thật (`os.rename`), không giữ file gốc.
- `02` luồng B ("không tạo Excel con và không ghi CSDL"), `HUONG_DAN_SU_DUNG.md` mục 4.2 ("Chỉ cập nhật PDF và Sổ tổng hợp"): luồng B có ghi CSDL (`save_dossier(..., with_excel=False)`), chỉ không tạo Excel. Tên nút ở `02` là "Đổi tên file (theo folder)", trên giao diện là "Đổi tên file nhanh (chọn theo folder)".
- `HUONG_DAN_SU_DUNG.md` mục 4 bước 3 và mục 8 ghi "bấm số trang P.2, P.3". Bảng không có nút P.x: bấm vào một dòng thì khung PDF nhảy tới trang của dòng đó.
- `HUONG_DAN_SU_DUNG.md` câu hỏi 1 ("vách ngăn bị lệch do máy khác kéo"): độ rộng lưu riêng từng máy, nên máy khác kéo không ảnh hưởng.
- `02` luồng A ghi việc khôi phục cột "phát hiện cột đầu chứa chuỗi số thứ tự tăng dần". Code chỉ cần ≥ 50% ô cột đầu là số 1–4 chữ số, không kiểm tra tăng dần.
- `01` mục 5 ghi "Repo chưa có `requirements.txt`". File này đã có từ 21/11.

### 3.5. Rà soát 22/11/2026 (lần 5) — chưa sửa

| # | Mức | Lỗi, số đo / cách tái hiện | Vị trí |
|---|---|---|---|
| Lỗi 33 (đã sửa 22/11/2026, `05` mục 20) | Thấp | Từ khi ghi chú đặt tên chỉ hiện lỗi (`05` mục 17, đã có trong commit b443c83): không có lỗi nào thì khung ghi chú (`naming_notes_frame`, CTkFrame rỗng) vẫn giữ chiều cao mặc định 200 (đo trên cửa sổ thật Scale 200%: cao 400 điểm ảnh, 0 dòng chữ), để lại một mảng trống lớn dưới ô tên file, đẩy các thẻ xuống. | `src/gui/review_panel.py`: `naming_notes_frame`, `_render_naming_lines` |
| Lỗi 32 | Thấp | Cột hàng đợi kéo về độ rộng tối thiểu 180: chữ nút "📑 Đổi tên file nhanh (chọn theo folder)" cần 415 điểm ảnh nhưng nút chỉ rộng 320 (Scale 200%), bị cắt. Có từ trước, phát hiện khi đo nút mới "🔄 Cập nhật tất cả từ Excel" (nút mới đã rút gọn chữ, cần 286). | `src/gui/batch_queue.py`: `btn_rename_folder` |

## 4. Môi trường và giới hạn

- Đã tạo `.venv` (Python 3.14) ngày 21/11/2026. Chạy test: `.venv\Scripts\python.exe -m unittest test_folder_review_v3 test_master_summary_format ...`.
- Đã cài đủ thư viện, gồm `rapidocr_onnxruntime` 1.2.3 (onnxruntime 1.32) và `httpx2` (cho FastAPI TestClient).
- Ngày 22/11/2026: 173 test, tất cả đạt, 1 bỏ qua (sau `05` mục 21). `test_phase6...test_11` cần `So Hoa GPLX.zip` đã build (đã có).
- Trang PDF mẫu render được bằng `pypdfium2`.
- Không chạy `test_phase2.py` cùng bộ test: nó OCR thật và ghi vào `samples/`.
- File mẫu `HO SO 113/H38.8.4_QD_000703_…` đã bị đổi tên thật thành `15.SQL.06.2010.AP014542-AP014618.pdf` khi chạy thử chiều 22/11; sổ tổng hợp tỉnh trong thư mục mẫu cũng đã được ghi.
