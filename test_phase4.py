"""
Verification and Test script for Phase 4: Multi-PC LAN Server & Web Client.
Tests background FastAPI server, Web Client UI, REST APIs, QR generation, and file streaming.
"""
import os
import sys
import time
import json
import urllib.request
import urllib.parse

# Ensure src is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.server.lan_server import lan_server, get_lan_ip
from src.database import DatabaseManager

def run_test():
    print("=" * 65)
    print("BẮT ĐẦU KIỂM THỬ GIAI ĐOẠN 4: MÁY CHỦ MẠNG LAN & WEB CLIENT")
    print("=" * 65)

    # 1. Test LAN IP detection
    ip = get_lan_ip()
    print(f"\n[1] Kiểm tra nhận diện địa chỉ IP mạng nội bộ (LAN):")
    print(f"  -> Địa chỉ IP máy chính phát hiện được: {ip}")
    assert ip and len(ip.split(".")) == 4, "Lỗi: Không nhận diện được địa chỉ IPv4 hợp lệ"

    # 2. Ensure Database has data
    db = DatabaseManager()
    stats = db.get_stats()
    print(f"\n[2] Kiểm tra kết nối CSDL SQLite:")
    print(f"  -> Tổng số sổ: {stats['total_dossiers']} | Tổng số công dân: {stats['total_citizens']}")

    # 3. Start LAN Server on test port 8088
    test_port = 8088
    print(f"\n[3] Khởi động máy chủ FastAPI mạng LAN trên cổng {test_port}...")
    server_url = lan_server.start(port=test_port)
    print(f"  -> Trạng thái máy chủ: Đang hoạt động (is_running = {lan_server.is_running})")
    print(f"  -> Đường dẫn phát sóng: {server_url}")
    assert lan_server.is_running, "Lỗi: Máy chủ LAN không thể khởi động!"

    time.sleep(1.0) # Ensure socket is fully bound

    base_url = f"http://127.0.0.1:{test_port}"

    try:
        # 4. Test Web Client HTML (GET /)
        print(f"\n[4] Kiểm tra phân hệ Web Client cho máy phụ (GET /)...")
        req = urllib.request.Request(f"{base_url}/")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200, f"Lỗi HTTP {resp.status}"
            html_content = resp.read().decode("utf-8")
            assert "HỆ THỐNG TRA CỨU HỒ SƠ GIẤY PHÉP LÁI XE" in html_content
            assert "resultsTableBody" in html_content
            assert "pdfModal" in html_content
            print(f"  -> Giao diện Web Client tải thành công (HTML {len(html_content)} bytes).")

        # 5. Test Status API (GET /api/status)
        print(f"\n[5] Kiểm tra API Trạng thái (GET /api/status)...")
        with urllib.request.urlopen(f"{base_url}/api/status") as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "online"
            assert "stats" in data
            print(f"  -> API Status phản hồi: {data['status']} | URL: {data['url']}")

        # 6. Test Provinces API (GET /api/provinces)
        print(f"\n[6] Kiểm tra API Danh mục Tỉnh (GET /api/provinces)...")
        with urllib.request.urlopen(f"{base_url}/api/provinces") as resp:
            assert resp.status == 200
            prov_data = json.loads(resp.read().decode("utf-8"))
            assert "provinces" in prov_data
            print(f"  -> Số lượng tỉnh trong hệ thống: {len(prov_data['provinces'])} tỉnh.")

        # 7. Test Search API (GET /api/search)
        print(f"\n[7] Kiểm tra API Tìm kiếm siêu tốc FTS5 qua mạng LAN (GET /api/search)...")
        search_query = urllib.parse.quote("Trần")
        with urllib.request.urlopen(f"{base_url}/api/search?q={search_query}") as resp:
            assert resp.status == 200
            search_res = json.loads(resp.read().decode("utf-8"))
            print(f"  -> Từ khóa: 'Trần' | Số kết quả: {search_res['total']} | Độ trễ CSDL: {search_res['latency_ms']} ms")
            assert search_res["total"] > 0, "Lỗi: Không tìm thấy kết quả cho từ khóa mẫu 'Trần'"
            
            first_row = search_res["results"][0]
            print(f"  -> Bản ghi đầu tiên: {first_row.get('full_name')} | GPLX: {first_row.get('license_number')} | Trang: {first_row.get('page_number')}")
            sample_dossier_id = first_row.get("dossier_id")
            sample_has_excel = first_row.get("has_excel")

        # 8. Test PDF Streaming (GET /api/pdf)
        print(f"\n[8] Kiểm tra truyền tải Stream File PDF qua mạng LAN (GET /api/pdf)...")
        if sample_dossier_id:
            with urllib.request.urlopen(f"{base_url}/api/pdf/{sample_dossier_id}") as resp:
                assert resp.status == 200
                content_type = resp.headers.get("Content-Type", "")
                assert "application/pdf" in content_type
                pdf_bytes = resp.read()
                assert len(pdf_bytes) > 0
                print(f"  -> File PDF stream thành công ({len(pdf_bytes)} bytes | MIME: {content_type}).")
        else:
            print(f"  -> Bỏ qua kiểm tra stream file PDF (chưa có tệp trên ổ).")

        # 9. Test Excel File Download (GET /api/excel)
        print(f"\n[9] Kiểm tra tải File Excel đồng hành qua mạng LAN (GET /api/excel)...")
        if sample_dossier_id and sample_has_excel:
            with urllib.request.urlopen(f"{base_url}/api/excel/{sample_dossier_id}") as resp:
                assert resp.status == 200
                content_type = resp.headers.get("Content-Type", "")
                assert "spreadsheetml" in content_type or "octet-stream" in content_type
                xlsx_bytes = resp.read()
                assert len(xlsx_bytes) > 0
                print(f"  -> File Excel tải thành công ({len(xlsx_bytes)} bytes | MIME: {content_type}).")
        else:
            print(f"  -> Bỏ qua kiểm tra tải file Excel (chưa có tệp trên ổ).")

        # 10. Test QR Code Generation API (GET /api/qr)
        print(f"\n[10] Kiểm tra API Tạo mã QR Code kết nối tức thì (GET /api/qr)...")
        with urllib.request.urlopen(f"{base_url}/api/qr") as resp:
            assert resp.status == 200
            content_type = resp.headers.get("Content-Type", "")
            assert "image/png" in content_type
            qr_bytes = resp.read()
            # Check PNG magic bytes: \x89PNG\r\n\x1a\n
            assert qr_bytes.startswith(b"\x89PNG\r\n\x1a\n")
            print(f"  -> Sinh mã QR thành công ({len(qr_bytes)} bytes PNG).")

    finally:
        # 11. Stop LAN Server cleanly
        print(f"\n[11] Dừng máy chủ mạng LAN an toàn...")
        lan_server.stop()
        print(f"  -> Trạng thái sau dừng: is_running = {lan_server.is_running}")
        assert not lan_server.is_running, "Lỗi: Máy chủ không thể dừng"

    print("\n" + "=" * 65)
    print(">>> KIỂM THỬ GIAI ĐOẠN 4 HOÀN TẤT THÀNH CÔNG 100%! <<<")
    print("=" * 65)
    return True

if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
