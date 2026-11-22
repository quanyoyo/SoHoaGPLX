"""
PDF Viewer Component for CustomTkinter with Bidirectional (Horizontal & Vertical) Scrolling.
Renders high-resolution pages, supports zooming, rotation, scrollbars, and Shift+Wheel panning.
"""
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
from typing import Optional
import pypdfium2 as pdfium
from src.pdf_processor import PDFIUM_LOCK, render_pdf_page

class PDFViewerFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.pdf_path: Optional[str] = None
        self.pdf_doc: Optional[pdfium.PdfDocument] = None
        self.total_pages: int = 0
        self.current_page_idx: int = 0
        self.zoom_level: float = 1.0
        self.rotation_angle: int = 0
        self.current_pil_img: Optional[Image.Image] = None
        self.tk_image_ref: Optional[ImageTk.PhotoImage] = None

        self._build_ui()

    def _build_ui(self):
        # 1. Top Toolbar: page navigation on the first row, view controls on the second,
        # so every button stays visible at the pane's default width.
        self.toolbar = ctk.CTkFrame(self, fg_color=("gray85", "gray20"))
        self.toolbar.pack(fill="x", padx=4, pady=(4, 2))
        nav_row = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        nav_row.pack(fill="x")
        tool_row = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        tool_row.pack(fill="x")

        self.btn_first = ctk.CTkButton(nav_row, text="⏮ Trang đầu", width=90, height=28, command=self.first_page)
        self.btn_first.pack(side="left", padx=(4, 2), pady=4)

        self.btn_prev = ctk.CTkButton(nav_row, text="◀ Trang trước", width=95, height=28, command=self.prev_page)
        self.btn_prev.pack(side="left", padx=2, pady=4)

        self.lbl_page = ctk.CTkLabel(nav_row, text="Trang 0 / 0", font=("Segoe UI", 12, "bold"))
        self.lbl_page.pack(side="left", padx=8, pady=4)

        self.btn_next = ctk.CTkButton(nav_row, text="Trang sau ▶", width=95, height=28, command=self.next_page)
        self.btn_next.pack(side="left", padx=2, pady=4)

        self.btn_last = ctk.CTkButton(nav_row, text="Trang cuối ⏭", width=90, height=28, command=self.last_page)
        self.btn_last.pack(side="left", padx=2, pady=4)

        # Zoom & Rotate Controls (left-aligned)
        self.btn_rotate = ctk.CTkButton(tool_row, text="🔄 Xoay", width=65, height=28, command=self.rotate_page)
        self.btn_rotate.pack(side="left", padx=(4, 6), pady=(0, 4))

        self.btn_zoom_in = ctk.CTkButton(tool_row, text="🔍 +", width=45, height=28, command=self.zoom_in)
        self.btn_zoom_in.pack(side="left", padx=3, pady=(0, 4))

        self.lbl_zoom = ctk.CTkLabel(tool_row, text="100%", font=("Segoe UI", 11))
        self.lbl_zoom.pack(side="left", padx=4, pady=(0, 4))

        self.btn_zoom_out = ctk.CTkButton(tool_row, text="🔍 -", width=45, height=28, command=self.zoom_out)
        self.btn_zoom_out.pack(side="left", padx=3, pady=(0, 4))
        self._update_nav_buttons()

        # 2. Canvas Container with Horizontal & Vertical Scrollbars
        self.canvas_container = ctk.CTkFrame(self, fg_color="transparent")
        self.canvas_container.pack(fill="both", expand=True, padx=4, pady=2)

        # Scrollbars
        self.v_scrollbar = ctk.CTkScrollbar(self.canvas_container, orientation="vertical")
        self.v_scrollbar.pack(side="right", fill="y")

        self.h_scrollbar = ctk.CTkScrollbar(self, orientation="horizontal")
        self.h_scrollbar.pack(fill="x", padx=4, pady=(0, 4))

        # Tkinter Canvas for smooth bidirectional scrolling
        bg_color = "#E5E5E5" if ctk.get_appearance_mode() == "Light" else "#1F1F1F"
        self.canvas = tk.Canvas(
            self.canvas_container,
            bg=bg_color,
            highlightthickness=0,
            xscrollcommand=self.h_scrollbar.set,
            yscrollcommand=self.v_scrollbar.set
        )
        self.canvas.pack(side="left", fill="both", expand=True)

        self.v_scrollbar.configure(command=self.canvas.yview)
        self.h_scrollbar.configure(command=self.canvas.xview)

        # Bind mousewheel events:
        # Standard wheel -> vertical scroll
        # Shift + wheel -> horizontal scroll
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_shift_mousewheel)

        # Placeholder message on canvas
        self.placeholder_text = self.canvas.create_text(
            200, 150,
            text="Chưa nạp tệp PDF scan",
            font=("Segoe UI", 13, "italic"),
            fill="gray"
        )

    def _on_mousewheel(self, event):
        if event.state & 0x0001: # Shift key pressed
            self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
        else:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_shift_mousewheel(self, event):
        self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

    def load_pdf(self, pdf_path: str, initial_page: int = 1):
        self.pdf_path = pdf_path
        try:
            self.close_pdf()
            with PDFIUM_LOCK:
                self.pdf_doc = pdfium.PdfDocument(pdf_path)
                self.total_pages = len(self.pdf_doc)
            self.current_page_idx = max(0, min(initial_page - 1, self.total_pages - 1))
            self.rotation_angle = 0
            self.zoom_level = 1.0
            self._render_current_page()
        except Exception as e:
            self.close_pdf()
            self.canvas.delete("all")
            self.canvas.create_text(250, 150, text=f"Lỗi khi đọc file PDF: {e}", fill="red", font=("Segoe UI", 11))

    def _render_current_page(self):
        if not self.pdf_doc or self.total_pages == 0:
            return

        pil_img = render_pdf_page(self.pdf_doc, self.current_page_idx, dpi=150 * self.zoom_level)

        if self.rotation_angle != 0:
            pil_img = pil_img.rotate(self.rotation_angle, expand=True)

        self.current_pil_img = pil_img

        # Convert to Tkinter PhotoImage
        self.tk_image_ref = ImageTk.PhotoImage(pil_img)

        # Clear canvas and draw image
        self.canvas.delete("all")
        # Draw image centered or at (0, 0)
        img_w, img_h = pil_img.size
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image_ref)

        # Set scrollable region
        self.canvas.config(scrollregion=(0, 0, img_w, img_h))

        # Update labels and button states
        self.lbl_page.configure(text=f"Trang {self.current_page_idx + 1} / {self.total_pages}")
        self.lbl_zoom.configure(text=f"{round(self.zoom_level * 100)}%")
        self._update_nav_buttons()

    def _update_nav_buttons(self):
        has_previous = self.pdf_doc is not None and self.current_page_idx > 0
        has_next = self.pdf_doc is not None and self.current_page_idx < self.total_pages - 1
        for button, enabled in ((self.btn_first, has_previous), (self.btn_prev, has_previous),
                                (self.btn_next, has_next), (self.btn_last, has_next)):
            button.configure(state="normal" if enabled else "disabled")

    def close_pdf(self):
        if self.pdf_doc:
            with PDFIUM_LOCK:
                self.pdf_doc.close()
                self.pdf_doc = None

    def clear_preview(self):
        self.close_pdf()
        self.pdf_path = None
        self.total_pages = 0
        self.current_page_idx = 0
        self.current_pil_img = None
        self.tk_image_ref = None
        self.canvas.delete("all")
        self.canvas.create_text(200, 150, text="Chưa nạp tệp PDF scan", font=("Segoe UI", 13, "italic"), fill="gray")
        self.canvas.configure(scrollregion=(0, 0, 0, 0))
        self.lbl_page.configure(text="Trang 0 / 0")
        self._update_nav_buttons()

    def first_page(self):
        self.go_to_page(1)

    def last_page(self):
        self.go_to_page(self.total_pages)

    def prev_page(self):
        if self.current_page_idx > 0:
            self.current_page_idx -= 1
            self._render_current_page()

    def next_page(self):
        if self.current_page_idx < self.total_pages - 1:
            self.current_page_idx += 1
            self._render_current_page()

    def go_to_page(self, page_num: int):
        target = max(0, min(page_num - 1, self.total_pages - 1))
        if target != self.current_page_idx:
            self.current_page_idx = target
            self._render_current_page()

    def zoom_in(self):
        if self.zoom_level < 2.5:
            self.zoom_level = round(self.zoom_level + 0.1, 2)
            self._render_current_page()

    def zoom_out(self):
        if self.zoom_level > 0.4:
            self.zoom_level = round(self.zoom_level - 0.1, 2)
            self._render_current_page()

    def rotate_page(self):
        self.rotation_angle = (self.rotation_angle + 90) % 360
        self._render_current_page()
