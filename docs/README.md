# Tài liệu dự án Số hóa & Tra cứu hồ sơ GPLX

Bộ tài liệu này được chuẩn hóa và cập nhật toàn diện **dựa trên mã nguồn thực tế** và các quyết định nghiệp vụ đã thống nhất của dự án.
Toàn bộ tài liệu nghiệp vụ, hướng dẫn sử dụng, đặc tả kỹ thuật và kế hoạch đều được tập trung quản lý thống nhất trong thư mục `docs/`.

| File | Nội dung |
|---|---|
| [HUONG_DAN_SU_DUNG.md](HUONG_DAN_SU_DUNG.md) | **Sổ tay hướng dẫn sử dụng phần mềm dành cho người dùng nghiệp vụ (Non-IT)**: Quy trình số hóa 2 luồng, tra cứu 2 chế độ, chia sẻ mạng LAN, phím tắt và xử lý sự cố. |
| [00-yeu-cau-san-pham-prd.md](00-yeu-cau-san-pham-prd.md) | **Tài liệu yêu cầu sản phẩm (PRD)**: Bối cảnh, mục tiêu số hóa GPLX lịch sử, chân dung người dùng, yêu cầu chức năng và phi chức năng. |
| [01-kien-truc-cong-nghe.md](01-kien-truc-cong-nghe.md) | **Kiến trúc & Công nghệ**: Kiến trúc Desktop + LAN Server, cấu trúc module, thư viện đang sử dụng và cách chạy ứng dụng. |
| [02-quy-trinh-nghiep-vu.md](02-quy-trinh-nghiep-vu.md) | **Quy trình nghiệp vụ**: Cấu trúc kho lưu trữ 3 cấp (Tỉnh/Hộp/Hồ sơ), 2 luồng xử lý (Số hóa đầy đủ & Đổi tên nhanh), quy tắc đặt tên 3 giai đoạn (SQL, QĐTT, QĐSH). |
| [03-du-lieu-luu-tru-tra-cuu.md](03-du-lieu-luu-tru-tra-cuu.md) | **Dữ liệu & Tra cứu**: Cấu trúc file Excel con động, Sổ tổng hợp cấp tỉnh 12 cột, CSDL SQLite nhúng FTS5 và máy chủ web nội bộ. |
| [04-quyet-dinh-va-viec-can-lam.md](04-quyet-dinh-va-viec-can-lam.md) | **Quyết định & Việc cần làm**: Tổng hợp các quyết định kỹ thuật đã chốt, danh sách tồn đọng cần tối ưu. |
| [05-ke-hoach-sua-loi.md](05-ke-hoach-sua-loi.md) | **Nhật ký & Kế hoạch sửa lỗi**: Báo cáo chi tiết các lỗi đã khắc phục (xử lý scale màn hình, tối ưu treeview danh sách file, ngắt an toàn OCR, lưu vị trí vách ngăn...). |
| [06-ke-hoach-phien-ban-3.md](06-ke-hoach-phien-ban-3.md) | **Kế hoạch GPLX Phiên bản 3**: Đặc tả chi tiết bộ quy tắc tên theo 3 mốc thời gian, tiêu chí nghiệm thu và kết quả kiểm thử trên dữ liệu đại diện. |

---

## Tóm tắt một câu

Người dùng chép file PDF scan vào thư mục `Tỉnh/Hộp/Hồ sơ`; ứng dụng desktop OCR file, đề xuất tên chuẩn theo quy định, người dùng duyệt rồi xác nhận; ứng dụng đổi tên PDF, xuất Excel danh sách GPLX, ghi một dòng vào sổ tổng hợp của tỉnh và nạp dữ liệu vào SQLite để tra cứu (trên máy chủ hoặc qua trình duyệt từ các máy khác trong mạng).

---

## Dữ liệu mẫu

`D:\So_Hoa_GPLX\Tỉnh Yên Bái\` (ngoài repo) chứa file mẫu để phát triển và kiểm thử:

```text
Tỉnh Yên Bái/
└── HOP 49/
    ├── HO SO 113/   H38.8.4_QD_*.pdf, H38.8.4_SO_*.pdf
    │                15.SQL.06.2010.AP014542-AP014618.pdf  (là QD_000703, đã đổi tên thật khi chạy thử 22/11/2026)
    └── HO SO 116/   H38.8.4_SG_000116_V1_20260425_00000{3..7}.pdf
                     15.SQL.03.1996.C244337-C244498.pdf/.xlsx  (kết quả đã xử lý)
```

Tên dạng `H38.8.4_SG_000116_V1_20260425_000003` là tên do đơn vị scan đặt. Ứng dụng đổi các file này sang tên theo quy định (xem [02-quy-trinh-nghiep-vu.md](02-quy-trinh-nghiep-vu.md#4-quy-tắc-đặt-tên)).
