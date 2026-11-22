"""
LAN Server Control Screen for Multi-PC Sharing.
Allows turning the internal FastAPI server on/off, viewing the LAN URL,
and displaying the QR code for instant mobile/PC access.
"""
import io
import webbrowser
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from PIL import Image

from src.server.lan_server import lan_server, get_lan_ip
from src.database import DatabaseManager
from src.logger import get_logger

logger = get_logger(__name__)

class LANScreenFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.db = DatabaseManager()
        self.qr_image_tk = None

        self._build_ui()
        self.refresh_state()

    def _build_ui(self):
        # 1. Header Banner
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(15, 10))

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="🌐 MÁY CHỦ CHIA SẺ DỮ LIỆU QUA MẠNG NỘI BỘ (LAN SERVER)",
            font=("Segoe UI", 18, "bold"),
            anchor="w"
        )
        title_lbl.pack(side="left")

        self.lbl_status_badge = ctk.CTkLabel(
            header_frame,
            text="🔴 Máy chủ: Đang tắt",
            font=("Segoe UI", 12, "bold"),
            fg_color="#FEE2E2",
            text_color="#991B1B",
            corner_radius=12,
            padx=12,
            pady=4
        )
        self.lbl_status_badge.pack(side="right")

        # 2. Main Content (2 Columns: Left Control, Right QR & Guide)
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=20, pady=10)
        content_frame.grid_columnconfigure(0, weight=3)
        content_frame.grid_columnconfigure(1, weight=2)
        content_frame.grid_rowconfigure(0, weight=1)

        # --- LEFT CARD: Controls & Network Info ---
        left_card = ctk.CTkFrame(content_frame, corner_radius=10)
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=5)

        ctk.CTkLabel(
            left_card,
            text="⚙️ THIẾT LẬP MÁY CHỦ CHÍNH (HOST)",
            font=("Segoe UI", 14, "bold"),
            anchor="w"
        ).pack(fill="x", padx=16, pady=(16, 8))

        # Server Toggle Button
        toggle_box = ctk.CTkFrame(left_card, fg_color=("white", "#2B2B2B"), corner_radius=8)
        toggle_box.pack(fill="x", padx=16, pady=8)

        self.btn_toggle = ctk.CTkButton(
            toggle_box,
            text="▶ BẬT CHIA SẺ MẠNG LAN",
            font=("Segoe UI", 13, "bold"),
            fg_color="#10B981",
            hover_color="#059669",
            height=42,
            command=self.toggle_server
        )
        self.btn_toggle.pack(fill="x", padx=12, pady=12)

        # Network details form
        details_box = ctk.CTkFrame(left_card, fg_color="transparent")
        details_box.pack(fill="x", padx=16, pady=8)

        # IP Row
        row_ip = ctk.CTkFrame(details_box, fg_color="transparent")
        row_ip.pack(fill="x", pady=4)
        ctk.CTkLabel(row_ip, text="Địa chỉ IP máy chính (LAN):", width=180, anchor="w", font=("Segoe UI", 12)).pack(side="left")
        self.lbl_ip = ctk.CTkLabel(row_ip, text=get_lan_ip(), font=("Segoe UI", 13, "bold"), text_color="#2563EB", anchor="w")
        self.lbl_ip.pack(side="left", fill="x", expand=True)

        # Port Row
        row_port = ctk.CTkFrame(details_box, fg_color="transparent")
        row_port.pack(fill="x", pady=4)
        ctk.CTkLabel(row_port, text="Cổng dịch vụ (Port):", width=180, anchor="w", font=("Segoe UI", 12)).pack(side="left")
        self.entry_port = ctk.CTkEntry(row_port, width=80, font=("Segoe UI", 12))
        self.entry_port.insert(0, "8080")
        self.entry_port.pack(side="left")

        # Full URL Row
        row_url = ctk.CTkFrame(details_box, fg_color="transparent")
        row_url.pack(fill="x", pady=8)
        ctk.CTkLabel(row_url, text="Đường dẫn truy cập:", width=180, anchor="w", font=("Segoe UI", 12)).pack(side="left")
        self.lbl_url = ctk.CTkLabel(
            row_url,
            text=f"http://{get_lan_ip()}:8080",
            font=("Consolas", 13, "bold"),
            text_color="#0D9488",
            anchor="w"
        )
        self.lbl_url.pack(side="left", fill="x", expand=True)

        # Action Buttons
        btn_box = ctk.CTkFrame(left_card, fg_color="transparent")
        btn_box.pack(fill="x", padx=16, pady=12)

        self.btn_copy_url = ctk.CTkButton(
            btn_box,
            text="📋 Sao Chép Địa Chỉ",
            font=("Segoe UI", 12, "bold"),
            fg_color="#3B82F6",
            hover_color="#2563EB",
            height=34,
            command=self.copy_url
        )
        self.btn_copy_url.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.btn_open_browser = ctk.CTkButton(
            btn_box,
            text="🌐 Mở Trên Trình Duyệt",
            font=("Segoe UI", 12, "bold"),
            fg_color="#6366F1",
            hover_color="#4F46E5",
            height=34,
            command=self.open_browser
        )
        self.btn_open_browser.pack(side="left", fill="x", expand=True)

        # Database Stats Card
        stats_box = ctk.CTkFrame(left_card, fg_color=("white", "#2B2B2B"), corner_radius=8)
        stats_box.pack(fill="x", padx=16, pady=(10, 16))

        ctk.CTkLabel(
            stats_box,
            text="📊 DỮ LIỆU SẴN SÀNG PHỤC VỤ TRA CỨU",
            font=("Segoe UI", 11, "bold"),
            text_color="#64748B",
            anchor="w"
        ).pack(fill="x", padx=12, pady=(10, 4))

        self.lbl_stats = ctk.CTkLabel(
            stats_box,
            text="Đang tải thông tin CSDL...",
            font=("Segoe UI", 12),
            anchor="w"
        )
        self.lbl_stats.pack(fill="x", padx=12, pady=(0, 10))

        # --- RIGHT CARD: QR Code & User Instructions ---
        right_card = ctk.CTkFrame(content_frame, corner_radius=10)
        right_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=5)

        ctk.CTkLabel(
            right_card,
            text="📱 KẾT NỐI TỨC THÌ (QR CODE)",
            font=("Segoe UI", 14, "bold"),
            anchor="w"
        ).pack(fill="x", padx=16, pady=(16, 8))

        # QR Code Display
        self.qr_canvas = ctk.CTkLabel(right_card, text="", width=200, height=200)
        self.qr_canvas.pack(pady=10)

        # Guide box
        guide_box = ctk.CTkFrame(right_card, fg_color=("white", "#2B2B2B"), corner_radius=8)
        guide_box.pack(fill="both", expand=True, padx=16, pady=(4, 16))

        ctk.CTkLabel(
            guide_box,
            text="📌 HƯỚNG DẪN DÀNH CHO MÁY PHỤ TRONG PHÒNG",
            font=("Segoe UI", 11, "bold"),
            text_color="#2563EB",
            anchor="w"
        ).pack(fill="x", padx=12, pady=(10, 6))

        instructions = (
            "1. Cắm máy tính này vào mạng LAN (dây mạng hoặc Wi-Fi văn phòng).\n"
            "2. Bấm nút 'BẬT CHIA SẺ MẠNG LAN' ở cột bên trái.\n"
            "3. Trên các máy tính phụ khác hoặc điện thoại / máy tính bảng:\n"
            "   • Mở trình duyệt Chrome hoặc Edge.\n"
            "   • Gõ đường dẫn hiển thị ở trên (hoặc quét mã QR).\n"
            "4. Cán bộ máy phụ có thể tìm kiếm tên/số bằng, xem ngay trang PDF scan và tải file Excel trực tiếp mà không cần cài thêm phần mềm."
        )
        ctk.CTkLabel(
            guide_box,
            text=instructions,
            font=("Segoe UI", 11),
            justify="left",
            anchor="nw",
            wraplength=380
        ).pack(fill="both", expand=True, padx=12, pady=(0, 10))

    def toggle_server(self):
        """Starts or stops the LAN server."""
        if lan_server.is_running:
            lan_server.stop()
            self.refresh_state()
            messagebox.showinfo("Thông báo", "Đã tắt máy chủ chia sẻ mạng LAN.")
        else:
            try:
                url = lan_server.start(port=self._entered_port())
                self.refresh_state()
                messagebox.showinfo("Khởi chạy thành công", f"Máy chủ mạng LAN đã được kích hoạt!\n\nĐường dẫn: {url}")
            except Exception as exc:
                logger.exception("Could not start LAN sharing server")
                messagebox.showerror("Không thể bật chia sẻ mạng LAN", f"Lỗi: {exc}\n\nChi tiết đã được ghi vào log.")

    def _entered_port(self):
        """The typed port; an empty box means the default 8080."""
        text = self.entry_port.get().strip() or "8080"
        if not (text.isascii() and text.isdigit()):
            raise ValueError(f"Cổng \"{text}\" không hợp lệ. Cổng phải là số từ 1 đến 65535 (mặc định 8080).")
        return int(text)

    def refresh_state(self):
        """Refreshes UI state, labels, stats, and QR code."""
        ip = get_lan_ip()
        self.lbl_ip.configure(text=ip)

        # While sharing, the address is the port in use, not what was typed since.
        if lan_server.is_running:
            port = lan_server.port
        else:
            port = self.entry_port.get().strip() if hasattr(self, "entry_port") else "8080"
        url = f"http://{ip}:{port}"
        self.lbl_url.configure(text=url)

        # Update stats
        stats = self.db.get_stats()
        self.lbl_stats.configure(
            text=f"• Tổng số cuốn sổ đã số hóa: {stats['total_dossiers']} cuốn\n"
                 f"• Tổng số công dân tra cứu: {stats['total_citizens']} người\n"
                 f"• CSDL SQLite dùng chung: đang hoạt động"
        )

        if lan_server.is_running:
            self.lbl_status_badge.configure(
                text=f"🟢 Đang phát: {url}",
                fg_color="#D1FAE5",
                text_color="#065F46"
            )
            self.btn_toggle.configure(
                text="⏹ TẮT CHIA SẺ MẠNG LAN",
                fg_color="#EF4444",
                hover_color="#DC2626"
            )
            self._render_qr_code(url)
        else:
            self.lbl_status_badge.configure(
                text="🔴 Máy chủ: Đang tắt",
                fg_color="#FEE2E2",
                text_color="#991B1B"
            )
            self.btn_toggle.configure(
                text="▶ BẬT CHIA SẺ MẠNG LAN",
                fg_color="#10B981",
                hover_color="#059669"
            )
            self._render_qr_code(url)

    def _render_qr_code(self, url: str):
        """Renders the QR code onto the canvas label."""
        try:
            import qrcode
            qr = qrcode.QRCode(box_size=6, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            pil_img = qr.make_image(fill_color="#1E293B", back_color="#FFFFFF")
            self.qr_ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(190, 190))
            self.qr_canvas.configure(image=self.qr_ctk_img)
        except Exception as e:
            self.qr_canvas.configure(text=f"[Mã QR]\n{url}")

    def copy_url(self):
        """Copies the LAN URL to clipboard."""
        url = self.lbl_url.cget("text")
        self.clipboard_clear()
        self.clipboard_append(url)
        messagebox.showinfo("Đã sao chép", f"Đã sao chép đường dẫn vào bộ nhớ tạm:\n{url}")

    def open_browser(self):
        """Opens the web client in default browser."""
        if not lan_server.is_running:
            try:
                lan_server.start(port=self._entered_port())
                self.refresh_state()
            except Exception as exc:
                logger.exception("Could not start LAN sharing server from browser action")
                messagebox.showerror("Không thể bật chia sẻ mạng LAN", f"Lỗi: {exc}\n\nChi tiết đã được ghi vào log.")
                return
        url = self.lbl_url.cget("text")
        webbrowser.open(url)
