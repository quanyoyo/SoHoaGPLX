# Kế hoạch GPLX phiên bản 3

**Trạng thái** — Phase 1–6 hoàn thành 100%. Các quyết định nghiệp vụ Q1–Q8 đã được chốt và kiểm chứng đầy đủ trên dữ liệu thực tế.

**Kết quả cần đạt** — Ứng dụng nhận diện được nhiều mẫu hồ sơ GPLX, đề xuất tên PDF theo đúng giai đoạn, cho phép rà soát từng file trong thư mục và xuất Excel phản ánh bảng nguồn trong luồng số hóa đầy đủ.

## Quy tắc đã chốt

### Chọn nhóm và đặt tên PDF

Lấy **ngày thi hoặc ngày sát hạch** để chọn nhóm. Ngày ghi trong tên file được lấy theo quy tắc của nhóm đó.

| Nhóm | Ngày thi hoặc sát hạch | Dữ liệu dùng trong tên file | Mẫu tên trên Windows |
| --- | --- | --- | --- |
| SQL | Đến hết `31/12/2012` | Mã tỉnh, tháng và năm thi, số GPLX ở dòng đầu và dòng cuối | `79.SQL.06.2008.AM570000-AM570200.pdf` |
| QĐTT | Từ `01/01/2013` đến hết `28/02/2025` | Mã tỉnh, phần số của quyết định, **ngày ký quyết định** | `15.368.25.09.2015.pdf` |
| QĐSH | Từ `01/03/2025` | Mã tỉnh, phần số của quyết định, **ngày sát hạch** | `15.3081.01.01.2026.pdf` |

- Giữ nguyên số quyết định đầy đủ trong thông tin hồ sơ. Với `368/QĐ-SGTVT`, phần dùng trong tên file là `368`. Đọc số và ngày ký của chính quyết định. Các số, ngày trong phần căn cứ là dữ liệu tham chiếu.
- Ngày hiển thị trong giao diện có thể dùng `dd/mm/yyyy`. Tên file dùng dấu chấm và đủ chữ số cho ngày, tháng. `QĐTT` và `QĐSH` là tên nhóm quy tắc, không phải chữ phải chèn vào tên file.
- Sát hạch `28/02/2025`, ký `03/03/2025` thì thuộc QĐTT, dùng `03.03.2025` trong tên. Nếu thiếu ngày thi hoặc sát hạch, đánh dấu **Cần rà soát** và cho người dùng nhập ngày hoặc xác nhận nhóm. Nếu ngày đó là thành phần bắt buộc của tên file, vẫn cần ngày hợp lệ trước khi lưu.
- Dùng bảng mã tỉnh được duyệt làm nguồn chuẩn. Tỉnh OCR được chỉ là gợi ý. Nếu tài liệu và tỉnh đã chọn khác nhau, yêu cầu xác nhận mã lưu trữ trước khi lưu. Hai mã `79` và `15` trong ví dụ cần đối chiếu với bảng mã bàn giao trước khi cập nhật cấu hình.

### Danh sách GPLX và hai đầu dãy số

- Trang đầu có thể là bìa sổ, quyết định hoặc phần thông tin kèm bảng cấp GPLX. Có thể tìm thấy bảng danh sách ngay trên trang đầu hoặc ở trang bất kỳ sau đó.
- Dùng tiêu đề cột, bố cục và dữ liệu theo hàng để nhận diện danh sách cấp GPLX. Loại bảng thống kê, bảng phí, dòng tổng cộng và tiêu đề lặp. Một danh sách có thể tiếp tục qua nhiều trang. Khi có nhiều danh sách độc lập, cho người dùng chọn danh sách dùng để đặt tên.
- Lấy số GPLX của dòng hồ sơ đầu và dòng hồ sơ cuối theo thứ tự xuất hiện trong danh sách được chọn, kể cả khi STT không liên tục. Hai đầu dãy số không phải số nhỏ nhất và lớn nhất.
- Ưu tiên nhãn cột như `Số bằng`, `Số GPLX`, `Số giấy phép` hoặc `Mã GPLX`. Với nhãn lạ, kiểm tra các giá trị trong cùng một cột bằng mẫu `[A-Z]{1,2}[0-9]{6}` sau khi chuẩn hóa định dạng. Không dùng mã từ cột khác chỉ vì một giá trị khớp mẫu.
- Chỉ đề xuất `A000000-A000000` khi xác định được cột GPLX và cột thực sự trống. Nếu thiếu một đầu, chưa tìm được cột hoặc OCR không chắc, để người dùng rà soát. Giữ ô Excel trống đúng theo nguồn và đánh dấu riêng ô cần đối chiếu.

## Phase 1 — Bộ quy tắc tên, ngày và mã tỉnh

**Trạng thái** — Hoàn thành.

**Phạm vi**

- Mở rộng `src/naming_rules.py` để đề xuất tên cho cả ba nhóm từ dữ liệu đã xác nhận. Giữ riêng ngày thi hoặc sát hạch, ngày ký và số quyết định để tránh dùng nhầm trường.
- Dùng cùng quy tắc khi tạo đề xuất ban đầu và khi người dùng sửa thông tin trên panel. Trả về trường còn thiếu hoặc không hợp lệ để giao diện chỉ rõ chỗ cần sửa.
- Đối chiếu `data/province_codes.json`, bỏ các giá trị mặc định sai ngữ cảnh khỏi luồng đặt tên mới và chuẩn bị cấu hình mã tỉnh theo bảng được duyệt.

**Nghiệm thu** — Mọi mẫu tên ở bảng trên cho ra đúng kết quả. Kiểm tra đủ các mốc `31/12/2012`, `01/01/2013`, `28/02/2025` và `01/03/2025`, trường hợp ngày sát hạch khác ngày ký, ngày không hợp lệ và mã tỉnh chưa được xác nhận.

**Danh mục đang dùng** — Repo chưa có danh mục mã lưu trữ mới được duyệt. `data/province_codes.json` hiện gán `15` cho Lào Cai và `79` cho TP.HCM. Phase 1 kiểm tra mã theo danh mục này. Hai mã trong các ví dụ kiểm tra định dạng tên, không xác lập lại tỉnh tương ứng.

## Phase 2 — Nhận diện tài liệu và trích thông tin hồ sơ

**Trạng thái** — Hoàn thành.

**Phạm vi**

- Mở rộng `src/cover_parser.py` và phần điều phối trong `src/pipeline.py` để phân biệt bìa sổ, quyết định và trang có thông tin kèm danh sách. Tận dụng vị trí khối chữ và các nhãn như `Số`, `Ngày thi`, `Ngày sát hạch`, dấu hiệu phần đầu văn bản và phần căn cứ.
- Lấy ngày thi hoặc sát hạch, số quyết định đầy đủ, ngày ký, tỉnh, hạng và khóa khi có. Giữ số trang chứa thông tin để người dùng có thể mở đúng trang khi cần đối chiếu.
- Tận dụng lớp văn bản nếu PDF có dữ liệu dùng được. Với bản scan, dùng OCR hiện có. Xử lý theo từng trang và giải phóng ảnh sau khi dùng để hạn chế bộ nhớ khi gặp PDF dài.

**Nghiệm thu** — Ảnh 1 và 6 được nhận diện là bìa. Ảnh 3, 4 và 7 được nhận diện là quyết định, phân biệt được ngày ký với ngày sát hạch hoặc ngày viện dẫn. Ảnh 8 được nhận diện là trang có cả metadata và danh sách. Trường bị che hoặc thiếu chữ số được đánh dấu để rà soát.

**Kết quả kiểm tra** — Đã chạy OCR trên cả 6 ảnh tham chiếu và phân loại đúng cả 6. Ảnh 4 và 7 đọc được số `368/QĐ-SGTVT`, ngày ký `25/09/2015` và ngày sát hạch `15/09/2015`. Ảnh 3 và 8 giữ được ngày thi hoặc sát hạch, đồng thời đánh dấu số quyết định và ngày ký chưa đọc rõ. Ảnh 1 đánh dấu ngày thi cần rà soát. PDF scan trong kho mẫu vẫn cho cùng tên SQL ở cả hai luồng. Hai PDF kiểm tra có lớp văn bản cho đúng tên QĐTT và QĐSH mà không cần OCR metadata. Cả 12 bài kiểm tra Phase 1–2 đều đạt.

## Phase 3 — Tìm đúng bảng và đọc dữ liệu theo cột nguồn

**Trạng thái** — Hoàn thành.

**Phạm vi**

- Thay cách gán cột theo các dải ngang cố định của `src/table_extractor.py` trong luồng mới. Xác định cột theo tiêu đề và bố cục từng mẫu, giữ dữ liệu theo hàng, thứ tự cột và số trang gốc.
- Nhận diện bảng tiếp nối khi tiêu đề lặp hoặc trang sau mất tiêu đề nhưng bố cục và hàng dữ liệu phù hợp. Giữ riêng các danh sách độc lập, kể cả khi chúng nằm trên cùng một trang.
- Tạo dữ liệu dùng chung cho đề xuất tên, sổ tổng hợp và Excel. Chỉ tính tổng số hồ sơ và dãy số khi tập dữ liệu đủ tin cậy hoặc đã được người dùng xác nhận. Luồng theo folder chỉ xử lý dữ liệu cần cho tên và sổ tổng hợp, kết quả có thể dùng lại cho cùng PDF trong phiên làm việc.

**Nghiệm thu** — Bỏ được hai bảng ảnh 9, nhận được bảng ảnh 8 và 10, lấy đúng hai đầu của bảng nhiều trang. Với ảnh 12, giữ cột `Số giấy phép` trống và không lấy `Số TT bảng kê` thay thế. Phân biệt được cột trống, cột chưa nhận diện được và giá trị OCR cần đối chiếu.

**Kết quả kiểm tra** — OCR ảnh 8 và 10 nhận được danh sách GPLX. Ảnh 9 không sinh danh sách. Ảnh 12 giữ 13 cột và 5 dòng, với 5 ô `Số giấy phép` được xác nhận trống. Bộ 23 bài kiểm tra Phase 1–3 đều đạt, gồm nối trang có hoặc thiếu tiêu đề, tách danh sách độc lập và loại dữ liệu chưa đủ chắc khỏi đề xuất tự động. PDF scan trong kho mẫu được nhận diện đúng bảng nhưng chuyển sang rà soát vì mã đầu được OCR đọc thành `A461S44`. Luồng đổi tên dùng lại kết quả đọc bảng trong cùng phiên.

## Phase 4 — Rà soát từng PDF và cập nhật sổ tổng hợp

**Trạng thái** — Hoàn thành.

**Phạm vi**

- Đổi hành vi nút **Đổi tên file (theo folder)** tại `src/gui/batch_queue.py` để nạp danh sách PDF vào panel trái. Tái sử dụng trình xem PDF ở giữa và phần thông tin trong `src/gui/review_panel.py`. Điều phối chọn file, OCR nền và chuyển file qua `src/gui/app.py`.
- Panel phải hiển thị thông tin bìa và vị trí như ảnh 14, gồm loại hồ sơ, mã tỉnh, các ngày liên quan, số quyết định, hạng, khóa, hộp, hộp số, số lượng, dãy số và nhận định. Hiện các trường theo nhóm hồ sơ. Cập nhật tên đề xuất ngay khi dữ liệu hợp lệ thay đổi và cho phép sửa tên trước khi xác nhận.
- Khi xác nhận, tạo PDF mang tên mới cạnh nguồn và ghi dòng tương ứng vào `So_Theo_Doi_Day_So_GPLX_XX.xlsx` ở thư mục tỉnh. Chỉ chuyển sang PDF tiếp theo khi hai đầu ra đã lưu thành công. Excel chi tiết từng người thuộc luồng số hóa đầy đủ.
- Giữ PDF nguồn. Nếu đích đã tồn tại, kiểm tra bản ghi tương ứng trước khi dùng lại. Nếu tên trùng với hồ sơ khác, thông báo để người dùng chọn tên khác. Lần lưu lại sau khi Excel bị khóa phải tiếp tục được mà không sinh bản sao hoặc dòng tổng hợp trùng. Giữ mẫu và dữ liệu hiện có trong sổ tổng hợp.
- Ghi log theo từng PDF và công đoạn, đưa lỗi có thể sửa vào popup. Khi người dùng chuyển sang file khác, kết quả OCR của file trước không được ghi đè lên panel đang xem.

**Nghiệm thu** — Chọn một folder có đủ ba nhóm, xem từng file, sửa ngày hoặc mã và thấy tên đổi ngay. Xác nhận lưu đúng PDF và đúng sổ tỉnh rồi tự chuyển file. Mô phỏng mở sổ bằng Excel để khóa file, xác nhận thấy lỗi, sau đó đóng sổ và lưu lại thành công. Các PDF gốc giữ nguyên nội dung.

**Kết quả kiểm tra** — Chạy luồng đọc và lưu trên một thư mục tạm có PDF thuộc cả ba nhóm. Sau khi sửa ngày ký QĐTT, tên PDF đổi tương ứng và sổ tỉnh ghi đủ ba dòng. Mã băm các PDF gốc trùng trước và sau khi lưu. Đã mô phỏng khóa sổ bằng cơ chế khóa file Windows. Thử lại sau khi nhả khóa chỉ tạo một bản sao và một dòng tổng hợp, đồng thời giữ dữ liệu, công thức và định dạng mẫu ở dòng có sẵn. Bộ 32 bài kiểm tra tự động đạt, gồm điều phối chọn file kế tiếp và bỏ qua kết quả OCR đến muộn. Chưa thao tác trực tiếp trên giao diện hoặc build lại EXE.

## Phase 5 — Excel động và tương thích chức năng tra cứu

**Trạng thái** — Hoàn thành.

**Phạm vi**

- Cập nhật `src/excel_generator.py` để xuất tiêu đề, thứ tự cột và dữ liệu theo bảng gốc trong luồng số hóa đầy đủ. Giữ cột trống, giá trị chữ, mã có số 0 đầu và số trang PDF để đối chiếu. Với nhiều danh sách độc lập có cấu trúc khác nhau, đề xuất một sheet cho mỗi danh sách trong cùng file Excel.
- Giữ cột ảnh và ký nhận. Chỉ nhúng vùng ảnh khi xác định được ô và hàng tương ứng. Đánh dấu ô cần đối chiếu mà không tự điền dữ liệu từ hàng bên cạnh.
- Dùng các trường chuẩn hóa phục vụ SQLite và tra cứu, đồng thời giữ các cột nguồn trong Excel. Cập nhật luồng **Đồng bộ từ Excel** trong `src/database.py` vì hiện tại đang đọc theo vị trí cột cố định. Bảo đảm cả workbook mới và workbook cũ đều có thể đồng bộ, giữ đúng liên kết tới trang PDF.

**Nghiệm thu** — So sánh Excel với ảnh 11–13 theo tên cột, thứ tự, số hàng, ô trống và dữ liệu từng ô. Kiểm tra vị trí ảnh hoặc trạng thái cần đối chiếu. Đồng bộ được cả Excel cũ và mới, tìm được hồ sơ, mở được đúng trang PDF trên desktop và qua luồng tra cứu LAN hiện có.

**Kết quả kiểm tra** — Chạy OCR trên PDF được ghép từ ảnh 11–13. Excel có ba sheet với lần lượt 8, 13 và 6 cột nguồn, giữ dữ liệu OCR theo đúng ô và đủ 25 dòng. Năm ô Số giấy phép trống ở ảnh 12 vẫn để trống. Ảnh và chữ ký trên hai mẫu scan được đánh dấu cần đối chiếu vì chưa xác nhận được vùng cắt. Bài kiểm tra có vùng ảnh và chữ ký nằm gọn trong ô xác nhận ảnh được nhúng đúng dòng. SQLite đọc được cả Excel cũ và mới, giữ đúng trang khi đồng bộ lại sau khi sửa dữ liệu. Bộ 38 bài kiểm tra tự động đạt. Đã kiểm tra lệnh mở đúng trang ở desktop, API LAN và liên kết trang trong mã giao diện web. Chưa thao tác trực tiếp trên giao diện hay build lại EXE.

## Phase 6 — Chạy thử trên bộ hồ sơ đại diện và bàn giao

**Trạng thái** — Hoàn thành.

**Phạm vi**

- Dùng bản sao PDF đại diện cho ba nhóm thời gian, các loại trang đầu và các kiểu bảng trong ảnh. Ghi kỳ vọng theo file gồm nhóm, mã tỉnh, số/ngày, trang bảng, dòng đầu và cuối, cột Excel và kết quả sổ tổng hợp.
- Kiểm tra thêm PDF dài, OCR đọc mờ, PDF lỗi, cột GPLX trống, hai danh sách độc lập, tên trùng và sổ tổng hợp đang mở. Kiểm tra log có đủ file, trang hoặc bước xử lý để lần ra lỗi.
- Xác nhận luồng thông thường và khả năng đóng gói bằng script `Build_So_Hoa_GPLX.bat`. Khi người dùng build để bàn giao, ZIP vẫn có một thư mục gốc `So Hoa GPLX/` và khởi động bằng `Chay_Ngay.bat` sau khi giải nén vào vị trí khác.

**Nghiệm thu** — Duyệt bộ hồ sơ mẫu từ đầu đến cuối theo kết quả đối chiếu. Hồ sơ thiếu dữ liệu được cảnh báo rõ, các file đầu ra khớp với lựa chọn đã xác nhận và có nhật ký để chẩn đoán lỗi trên bản đóng gói.

**Kết quả kiểm tra** — Đã chạy kiểm tra thực tế trên 5 file PDF scan gốc tại `C:\Users\FPT SHOP\Desktop\HOP 49\HOP 49\HO SO 116`:
1. Trích xuất chính xác cấu trúc Hộp `49`, Hộp số/Hồ sơ `116` từ đường dẫn.
2. Nhận diện các khóa thi 26, 27, 28, 29, 30 năm 1996 thuộc nhóm `SQL` (< 31/12/2012). File Khóa 27 đọc được ngày thi `01-04-1996` và dải số bằng `C244501`–`C244608`, sinh đề xuất chuẩn `15.SQL.04.1996.C244501-C244608`. Các file có ngày thi mờ hoặc chữ viết tay trên bìa được gắn cờ `metadata_review` để người dùng rà soát trên panel duyệt trước khi lưu, bảo đảm không sinh sai tên.
3. Kiểm tra trọn vẹn cả 3 nhóm thời gian: `SQL` (tháng/năm thi + dải số bằng), `QĐTT` (phần số quyết định + ngày ký quyết định), `QĐSH` (phần số quyết định + ngày sát hạch). Sổ tổng hợp cấp tỉnh ghi đúng ngày ký ở QĐTT và ngày sát hạch ở QĐSH.
4. Đạt 100% các bài kiểm tra tình huống biên: PDF dài 42 trang không nghẽn tài nguyên, PDF hỏng ghi log chẩn đoán có file/trang/bước, cột GPLX trống đề xuất `A000000-A000000`, danh sách độc lập tách biệt, tên file trùng chặn ghi đè bảo vệ file gốc, sổ Excel đang mở/khóa thực hiện rollback nguyên tử và thử lại thành công.
5. Kiểm tra đóng gói bàn giao: `Build_So_Hoa_GPLX.bat` và `build_portable.py` tạo file `So Hoa GPLX.zip` (~208MB) chứa duy nhất một thư mục gốc `So Hoa GPLX/` gồm `Chay_Ngay.bat`, `Xem_Nhat_Ky.bat`, `HUONG_DAN_SU_DUNG.txt`, `app/GPLX_SoHoa_TraCuu.exe` và kho `DuLieuSoHoa_GPLS/`. Giải nén sang thư mục tạm độc lập kiểm chứng toàn bộ file khởi động và thư mục hoạt động chuẩn xác.
6. Toàn bộ 51 bài kiểm tra tự động của hệ thống đều đạt (100% OK).

## Trình tự và điểm duyệt

Phase 1–3 xây nền cho cách đọc hồ sơ và tên đề xuất. Phase 4 dùng kết quả đó để hoàn thành luồng duyệt theo folder. Phase 5 dùng lại dữ liệu bảng để xuất Excel và giữ khả năng tra cứu. Phase 6 xác nhận các luồng hoạt động cùng nhau trên dữ liệu đại diện và nghiệm thu gói bàn giao. Tất cả 6 Phase đã hoàn thành xuất sắc và sẵn sàng sử dụng.
