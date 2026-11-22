"""
Search & Discovery Screen (Màn hình Tra cứu Hồ sơ & Mở file scan).
Provides:
- Mode 1: 👤 Tra Cứu Công Dân: Sub-millisecond query by citizen name, license number, birth year.
- Mode 2: 📁 Danh Mục Sổ / File Excel Đã Import: Complete inventory of imported Excel files,
          boxes (Hộp), folders (Hộp số), and provinces with 1-click citizen drill-down.
Includes 1-click jump to PDF page, open companion Excel, and open Windows Explorer.
"""
import os
import subprocess
import customtkinter as ctk
from tkinter import messagebox, filedialog, ttk
from typing import List, Dict, Any, Optional, Callable

from src.database import DatabaseManager
from src.config import PROVINCE_CODES, get_default_dulieu_dir
from src.gui.pdf_viewer import PDFViewerFrame
from src.logger import get_logger

from src.gui.table_style import style_table

logger = get_logger(__name__)
SYNC_BUTTON_TEXT = "🔄 Quét lại từ Excel"
RESULT_LIMIT = 200
CITIZEN_COLUMNS = [
    ("stt", "STT", 50), ("full_name", "Họ và tên", 190), ("birth_year", "Năm sinh", 80),
    ("license_number", "Số bằng", 110), ("address", "Nơi cư trú", 240), ("box", "HỘP", 60),
    ("box_number", "HỘP SỐ", 70), ("page", "Trang", 60), ("final_filename", "Hồ sơ", 240),
]
STRETCH_COLUMNS = ("full_name", "address", "final_filename")  # take the room left on wide windows
DOSSIER_COLUMNS = [
    ("idx", "STT", 50), ("province_code", "Tỉnh", 55), ("box", "HỘP", 60), ("box_number", "H.SỐ", 60),
    ("final_filename", "Tên File PDF / Excel", 260), ("license_class", "Hạng", 60), ("exam_date", "Ngày bìa", 90),
    ("total", "Số GPLX", 80), ("license_sequence", "Dãy số GPLX", 220), ("status_note", "Đánh giá", 130),
]

class SearchScreenFrame(ctk.CTkFrame):
    def __init__(self, master, on_open_pdf_callback: Optional[Callable] = None, *,
                 dispatch_to_ui: Optional[Callable] = None, run_in_background: Optional[Callable] = None, **kwargs):
        super().__init__(master, **kwargs)
        
        self.on_open_pdf_callback = on_open_pdf_callback
        # Long folder scans run off the UI thread; without hooks (scripts) they run in place.
        self.dispatch_to_ui = dispatch_to_ui or (lambda callback, *args, **kw: callback(*args, **kw))
        self.run_in_background = run_in_background or (lambda job: job())
        self.db = DatabaseManager()
        self.current_citizen_results: List[Dict[str, Any]] = []
        self.current_dossier_results: List[Dict[str, Any]] = []
        self.current_citizen_total = 0
        self.current_dossier_total = 0
        self._last_search = None  # (query, province, book id, book name) of the citizens listed
        self.current_mode = "👤 Tra Cứu Công Dân"

        self._build_ui()
        self.refresh_stats()

    def _build_ui(self):
        # 1. Top Header Banner
        self.top_frame = ctk.CTkFrame(self, fg_color=("#F0F4F8", "#1E2229"), corner_radius=6)
        self.top_frame.pack(fill="x", padx=10, pady=(10, 6))

        top_header_row = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        top_header_row.pack(fill="x", padx=14, pady=(8, 4))

        lbl_title = ctk.CTkLabel(
            top_header_row,
            text="HỆ THỐNG TRA CỨU & QUẢN LÝ HỒ SƠ GIẤY PHÉP LÁI XE LỊCH SỬ",
            font=("Segoe UI", 13, "bold"),
            text_color=("#1F497D", "#5B9BD5")
        )
        lbl_title.pack(side="left")

        # Mode Selector (Toggle between Citizen search & Dossier Inventory)
        self.mode_toggle = ctk.CTkSegmentedButton(
            top_header_row,
            values=["👤 Tra Cứu Công Dân", "📁 Danh Mục Sổ / File Excel Đã Import"],
            font=("Segoe UI", 11, "bold"),
            selected_color="#0066CC",
            height=28,
            command=self.on_mode_change
        )
        self.mode_toggle.set(self.current_mode)
        self.mode_toggle.pack(side="right")

        # --- SUB-PANEL 1: Citizen Search Controls ---
        self.citizen_search_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.citizen_search_frame.pack(fill="x", padx=14, pady=(4, 8))

        prov_options = ["Tất cả các tỉnh"] + [f"{p['code']} - {p['name']}" for p in PROVINCE_CODES]
        self.cmb_prov_filter = ctk.CTkComboBox(self.citizen_search_frame, values=prov_options, width=170, height=34)
        self.cmb_prov_filter.set("Tất cả các tỉnh")
        self.cmb_prov_filter.pack(side="left", padx=(0, 8))

        self.txt_query = ctk.CTkEntry(
            self.citizen_search_frame,
            placeholder_text="Nhập Số bằng (VD: A461544, C244138), Họ tên (có/không dấu: tran van yen), hoặc Năm sinh...",
            font=("Segoe UI", 12),
            height=34
        )
        self.txt_query.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.txt_query.bind("<Return>", lambda e: self.perform_citizen_search())

        self.btn_search = ctk.CTkButton(
            self.citizen_search_frame,
            text="🔍 Tìm Kiếm",
            font=("Segoe UI", 12, "bold"),
            fg_color="#0066CC",
            hover_color="#004C99",
            width=110,
            height=34,
            command=self.perform_citizen_search
        )
        self.btn_search.pack(side="left", padx=(0, 8))

        self.btn_sync = ctk.CTkButton(
            self.citizen_search_frame,
            text=SYNC_BUTTON_TEXT,
            font=("Segoe UI", 11),
            fg_color=("gray75", "gray30"),
            width=135,
            height=34,
            command=self._sync_from_excel_folder
        )
        self.btn_sync.pack(side="left")

        # --- SUB-PANEL 2: Dossier Inventory Controls (Initially Hidden) ---
        self.dossier_search_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")

        self.cmb_dossier_prov = ctk.CTkComboBox(self.dossier_search_frame, values=prov_options, width=170, height=34, command=lambda e: self._on_dossier_prov_changed())
        self.cmb_dossier_prov.set("Tất cả các tỉnh")
        self.cmb_dossier_prov.pack(side="left", padx=(0, 8))

        self.cmb_dossier_box = ctk.CTkComboBox(self.dossier_search_frame, values=["Tất cả các Hộp"], width=130, height=34)
        self.cmb_dossier_box.set("Tất cả các Hộp")
        self.cmb_dossier_box.pack(side="left", padx=(0, 8))

        self.txt_dossier_kw = ctk.CTkEntry(
            self.dossier_search_frame,
            placeholder_text="Lọc theo Tên file Excel/PDF, Số Hộp, hoặc Hộp số...",
            font=("Segoe UI", 12),
            height=34
        )
        self.txt_dossier_kw.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.txt_dossier_kw.bind("<Return>", lambda e: self.perform_dossier_search())

        self.btn_filter_dossier = ctk.CTkButton(
            self.dossier_search_frame,
            text="🔍 Lọc Danh Sách",
            font=("Segoe UI", 12, "bold"),
            fg_color="#0D9488",
            hover_color="#0F766E",
            width=120,
            height=34,
            command=self.perform_dossier_search
        )
        self.btn_filter_dossier.pack(side="left", padx=(0, 8))

        self.btn_refresh_dossier = ctk.CTkButton(
            self.dossier_search_frame,
            text="🔄 Làm mới",
            font=("Segoe UI", 11),
            fg_color=("gray75", "gray30"),
            width=90,
            height=34,
            command=self.perform_dossier_search
        )
        self.btn_refresh_dossier.pack(side="left")

        # 2. Stats & Summary Bar
        self.stats_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.stats_bar.pack(fill="x", padx=12, pady=(0, 4))

        self.lbl_stats = ctk.CTkLabel(
            self.stats_bar,
            text="Đang kết nối CSDL...",
            font=("Segoe UI", 11, "italic"),
            text_color=("gray40", "gray70")
        )
        self.lbl_stats.pack(side="left")

        self.lbl_result_count = ctk.CTkLabel(
            self.stats_bar,
            text="",
            font=("Segoe UI", 11, "bold"),
            text_color="#1E7E34"
        )
        self.lbl_result_count.pack(side="right")

        # 3. Results: one table for any number of rows. Building a row of widgets per result used
        # ~40 Windows handles each (10,000 per program), froze the window for seconds and could crash it.
        self.results_frame = ctk.CTkFrame(self, fg_color=("gray95", "gray12"), corner_radius=6)
        self.results_frame.pack(fill="both", expand=True, padx=10, pady=(2, 10))

        self.action_bar = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        self.action_bar.pack(fill="x", padx=8, pady=(6, 2))
        self.lbl_selection = ctk.CTkLabel(self.action_bar, text="", font=("Segoe UI", 11, "bold"), anchor="w")
        self.lbl_selection.pack(side="left", fill="x", expand=True)
        self.btn_open_folder = ctk.CTkButton(
            self.action_bar, text="📂 Thư mục", width=90, height=28, font=("Segoe UI", 11),
            fg_color=("gray70", "gray35"), hover_color=("gray60", "gray45"),
            command=lambda: self._run_on_selection(lambda row: self._open_containing_folder(row.get("pdf_path", ""))))
        self.btn_open_folder.pack(side="right", padx=2)
        self.btn_open_excel = ctk.CTkButton(
            self.action_bar, text="📊 Excel", width=80, height=28, font=("Segoe UI", 11),
            fg_color="#16A34A", hover_color="#15803D",
            command=lambda: self._run_on_selection(lambda row: self._open_external_file(row.get("excel_path", ""))))
        self.btn_open_excel.pack(side="right", padx=2)
        self.btn_view_pdf = ctk.CTkButton(
            self.action_bar, text="👁️ Xem PDF", width=110, height=28, font=("Segoe UI", 11, "bold"),
            fg_color="#0066CC", hover_color="#004C99",
            command=lambda: self._run_on_selection(self._view_selected_pdf))
        self.btn_view_pdf.pack(side="right", padx=2)
        self.btn_view_citizens = ctk.CTkButton(
            self.action_bar, text="👥 Xem Dân", width=95, height=28, font=("Segoe UI", 11, "bold"),
            fg_color="#2563EB", hover_color="#1D4ED8",
            command=lambda: self._run_on_selection(
                lambda row: self.drill_down_to_dossier_citizens(row.get("id"), row.get("final_filename", ""))))

        self.table_holder = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        self.results_tree = ttk.Treeview(self.table_holder, show="headings", style="GPLXSearch.Treeview",
                                         selectmode="browse")
        self._columns = []
        self._apply_table_scaling()
        y_scroll = ctk.CTkScrollbar(self.table_holder, orientation="vertical", command=self.results_tree.yview)
        x_scroll = ctk.CTkScrollbar(self.table_holder, orientation="horizontal", command=self.results_tree.xview)
        self.results_tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.results_tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.table_holder.grid_rowconfigure(0, weight=1)
        self.table_holder.grid_columnconfigure(0, weight=1)
        self.results_tree.tag_configure("odd", background="#F8FAFC")
        self.results_tree.tag_configure("complete", foreground="#16A34A")
        self.results_tree.tag_configure("attention", foreground="#C2410C")
        self.results_tree.bind("<<TreeviewSelect>>", lambda e: self._update_action_bar())
        self.results_tree.bind("<Double-1>", self._on_result_double_click)
        # Enter opens the selected row wherever the mouse is (a key carries the pointer position too).
        self.results_tree.bind("<Return>", self._on_result_enter)
        self.results_tree.bind("<KP_Enter>", self._on_result_enter)
        self.lbl_placeholder = ctk.CTkLabel(self.results_frame, text="", font=("Segoe UI", 12, "italic"),
                                            text_color="gray50")
        self._rows: List[Dict[str, Any]] = []
        self._rows_kind = "citizen"

        self._render_empty_placeholder("Nhập từ khóa và nhấn 'Tìm Kiếm' để tra cứu hồ sơ người lái xe.")

    def on_mode_change(self, mode: str):
        self.current_mode = mode
        if mode == "👤 Tra Cứu Công Dân":
            self.dossier_search_frame.pack_forget()
            self.citizen_search_frame.pack(fill="x", padx=14, pady=(4, 8))
            self.refresh_stats()
            if self.current_citizen_results:
                self._render_citizen_results(self.current_citizen_results, self.current_citizen_total)
            else:
                self._render_empty_placeholder("Nhập từ khóa và nhấn 'Tìm Kiếm' để tra cứu hồ sơ người lái xe.")
        else:
            self.citizen_search_frame.pack_forget()
            self.dossier_search_frame.pack(fill="x", padx=14, pady=(4, 8))
            self._update_box_filter_options()
            self.perform_dossier_search()

    def refresh_stats(self):
        try:
            inv = self.db.get_inventory_stats()
            if self.current_mode == "📁 Danh Mục Sổ / File Excel Đã Import":
                self.lbl_stats.configure(
                    text=f"📊 Đã import: {inv['total_provinces']} tỉnh | {inv['total_boxes']} Tủ/Hộp | {inv['total_box_numbers']} Hộp số | {inv['total_dossiers']} cuốn sổ/file Excel ({inv['total_citizens']} GPLX)"
                )
            else:
                self.lbl_stats.configure(
                    text=f"📊 Cơ sở dữ liệu: {inv['total_citizens']} công dân | {inv['total_dossiers']} cuốn sổ quản lý (gplx_index.db)"
                )
        except Exception:
            self.lbl_stats.configure(text="CSDL đã sẵn sàng.")

    def _on_dossier_prov_changed(self):
        self._update_box_filter_options()
        self.perform_dossier_search()

    def _update_box_filter_options(self):
        prov_sel = self.cmb_dossier_prov.get().strip()
        prov_code = "all"
        if prov_sel and "-" in prov_sel:
            prov_code = prov_sel.split("-")[0].strip()

        boxes = self.db.get_distinct_boxes(province_code=prov_code)
        options = ["Tất cả các Hộp"] + [f"Hộp {b}" for b in boxes]
        self.cmb_dossier_box.configure(values=options)
        self.cmb_dossier_box.set("Tất cả các Hộp")

    # ==========================================
    # MODE 1: CITIZEN SEARCH
    # ==========================================

    def perform_citizen_search(self, dossier_id: Optional[int] = None, dossier_name: str = ""):
        q = "" if dossier_id else self.txt_query.get().strip()
        if not q and not dossier_id:
            self._last_search = None
            self._render_empty_placeholder("Vui lòng nhập từ khóa tìm kiếm (Số bằng, Họ tên, hoặc Năm sinh).")
            return

        prov_sel = self.cmb_prov_filter.get().strip()
        prov_code = None
        # A book is shown whole: the province box only narrows keyword searches (with another
        # province chosen, "Xem Dân" used to show an empty list).
        if not dossier_id and prov_sel and "-" in prov_sel:
            prov_code = prov_sel.split("-")[0].strip()
        self._last_search = (q, prov_code, dossier_id, dossier_name)
        self._run_citizen_search(q, prov_code, dossier_id, dossier_name)

    def _run_citizen_search(self, q, prov_code, dossier_id=None, dossier_name="", quiet=False):
        try:
            results = self.db.search(query=q, province_code=prov_code, dossier_id=dossier_id, limit=RESULT_LIMIT)
            total = len(results) if dossier_id else self.db.count_search(q, province_code=prov_code)
            empty_book = self._empty_book_message(dossier_id, dossier_name) if dossier_id and not results else ""
        except Exception as e:
            if quiet:
                logger.warning("Could not refresh the search results: %s", e)
            else:
                messagebox.showerror("Lỗi Tra Cứu", f"Không thể tra cứu CSDL:\n{e}")
            return
        self.current_citizen_results = results
        self.current_citizen_total = total
        if empty_book:
            self._render_empty_placeholder(empty_book)
            return
        self._render_citizen_results(results, total)

    def _empty_book_message(self, dossier_id, name):
        files = self.db.get_dossier_files(dossier_id)
        if files is None:
            return f"Cuốn sổ {name} không còn trong CSDL (PDF đã đổi tên hoặc bị xóa). Hãy lọc lại danh mục."
        if not files["excel_path"]:
            return (f"Hồ sơ {name} mới được đổi tên nhanh, chưa số hóa danh sách GPLX "
                    "nên chưa có danh sách công dân để xem.")
        return f"Cuốn sổ {name} chưa có công dân nào trong CSDL."

    def refresh_results(self):
        """Show the listed rows again from the database (after a re-scan or a save), without error popups."""
        if self.current_mode != "👤 Tra Cứu Công Dân":
            self.perform_dossier_search(quiet=True)
            return
        if self._last_search is None:
            return
        q, prov_code, dossier_id, name = self._last_search
        if dossier_id and name:
            # A re-scan or a new save records the book again under a new id: find it by name.
            try:
                dossier_id = self.db.get_dossier_id(name)
            except Exception as exc:
                logger.warning("Could not refresh the book %s: %s", name, exc)
                return
            if dossier_id is None:
                self._render_empty_placeholder(f"Cuốn sổ {name} không còn trong CSDL (PDF đã đổi tên hoặc bị xóa).")
                return
            self._last_search = (q, prov_code, dossier_id, name)
        self._run_citizen_search(q, prov_code, dossier_id, name, quiet=True)

    def _render_citizen_results(self, results: List[Dict[str, Any]], total: Optional[int] = None):
        total = len(results) if total is None else total
        if not results:
            self._render_empty_placeholder("Không tìm thấy người dân nào khớp với từ khóa tìm kiếm.")
            return
        if total > len(results):
            text = f"Hiện {len(results)}/{total} kết quả đầu — hãy gõ cụ thể hơn (họ tên đầy đủ, số bằng, năm sinh)"
        else:
            text = f"Tìm thấy {total} kết quả công dân"
        self._show_rows("citizen", CITIZEN_COLUMNS, results, [
            (row.get("stt", ""), row.get("full_name", ""), row.get("birth_year", ""), row.get("license_number", ""),
             row.get("address", ""), row.get("box", ""), row.get("box_number", ""), row.get("page_number", 1),
             row.get("final_filename", ""))
            for row in results
        ], text, [None] * len(results))

    # ==========================================
    # MODE 2: DOSSIER & EXCEL INVENTORY
    # ==========================================

    def perform_dossier_search(self, quiet=False):
        prov_sel = self.cmb_dossier_prov.get().strip()
        prov_code = "all"
        if prov_sel and "-" in prov_sel:
            prov_code = prov_sel.split("-")[0].strip()

        box_sel = self.cmb_dossier_box.get().strip()
        box_val = "all"
        if box_sel and box_sel != "Tất cả các Hộp":
            box_val = box_sel.replace("Hộp", "").strip()

        kw = self.txt_dossier_kw.get().strip()

        try:
            dossiers = self.db.get_all_dossiers(province_code=prov_code, box=box_val, search_kw=kw, limit=RESULT_LIMIT)
            total = self.db.count_dossiers(province_code=prov_code, box=box_val, search_kw=kw)
        except Exception as e:
            if quiet:
                logger.warning("Could not refresh the book list: %s", e)
            else:
                messagebox.showerror("Lỗi Truy Vấn", f"Không thể lấy danh sách cuốn sổ đã nạp:\n{e}")
            return
        self.current_dossier_results = dossiers
        self.current_dossier_total = total
        self._render_dossier_results(dossiers, total)
        self.refresh_stats()

    def _render_dossier_results(self, dossiers: List[Dict[str, Any]], total: Optional[int] = None):
        total = len(dossiers) if total is None else total
        if not dossiers:
            self._render_empty_placeholder("Chưa có cuốn sổ hoặc file Excel nào được import vào hệ thống phù hợp với bộ lọc.")
            return
        if total > len(dossiers):
            text = f"Hiện {len(dossiers)}/{total} cuốn sổ mới nhất — lọc theo tỉnh, hộp hoặc tên file để thu hẹp"
        else:
            text = f"Có {total} cuốn sổ / file Excel trong CSDL"
        values, tags = [], []
        for idx, d in enumerate(dossiers, start=1):
            note = d.get("status_note") or ""
            values.append((idx, d.get("province_code", ""), d.get("box") or "-", d.get("box_number") or "-",
                           d.get("final_filename", ""), d.get("license_class") or "-", d.get("exam_date") or "-",
                           f"{d.get('total_citizens') or 0} bằng", d.get("license_sequence") or "-", note or "-"))
            tags.append("complete" if note.startswith("Đủ") else "attention" if note else None)
        self._show_rows("dossier", DOSSIER_COLUMNS, dossiers, values, text, tags)

    def drill_down_to_dossier_citizens(self, dossier_id: int, dossier_name: str):
        """Switches view to Citizen Mode and displays all citizens belonging to this dossier."""
        self.mode_toggle.set("👤 Tra Cứu Công Dân")
        self.current_mode = "👤 Tra Cứu Công Dân"
        self.dossier_search_frame.pack_forget()
        self.citizen_search_frame.pack(fill="x", padx=14, pady=(4, 8))
        self.txt_query.delete(0, "end")
        self.lbl_stats.configure(text=f"📂 Đang hiển thị danh sách công dân trong cuốn sổ: {dossier_name}")
        self.perform_citizen_search(dossier_id=dossier_id, dossier_name=dossier_name)

    # ==========================================
    # COMMON UTILITIES
    # ==========================================

    def _apply_table_scaling(self):
        """Size the table like the rest of the window (see table_style)."""
        scale = self._get_widget_scaling()
        style_table(self, "GPLXSearch.Treeview", scale)
        for key, _, width in self._columns:
            # Wide columns only grow: on a narrow window the table scrolls instead of squeezing names.
            smallest = width if key in STRETCH_COLUMNS else 40
            self.results_tree.column(key, width=round(width * scale), minwidth=round(smallest * scale))

    def _set_scaling(self, new_widget_scaling, new_window_scaling):
        # Called by CustomTkinter when the window moves to a screen with another display scale.
        super()._set_scaling(new_widget_scaling, new_window_scaling)
        if hasattr(self, "results_tree"):
            self._apply_table_scaling()

    def _show_rows(self, kind, columns, rows, values, count_text, tags):
        tree = self.results_tree
        tree.delete(*tree.get_children())
        tree["columns"] = [key for key, _, _ in columns]
        for key, label, _ in columns:
            tree.heading(key, text=label)
            tree.column(key, stretch=key in STRETCH_COLUMNS,
                        anchor="w" if key in ("full_name", "address", "final_filename", "license_sequence") else "center")
        self._columns = columns
        self._apply_table_scaling()
        for index, (row_values, tag) in enumerate(zip(values, tags)):
            row_tags = tuple(t for t in (tag, "odd" if index % 2 else None) if t)
            tree.insert("", "end", iid=str(index), values=["" if v is None else str(v) for v in row_values],
                        tags=row_tags)
        self._rows, self._rows_kind = rows, kind
        self.lbl_result_count.configure(text=count_text)
        self.lbl_placeholder.pack_forget()
        self.action_bar.pack(fill="x", padx=8, pady=(6, 2))
        self.table_holder.pack(fill="both", expand=True, padx=6, pady=(2, 6))
        if kind == "dossier":
            self.btn_view_citizens.pack(side="right", padx=2, before=self.btn_view_pdf)
        else:
            self.btn_view_citizens.pack_forget()
        tree.yview_moveto(0)
        first = tree.get_children()[:1]
        if first:
            tree.selection_set(first)
            tree.focus(first[0])
        self._update_action_bar()

    def _selected_row(self) -> Optional[Dict[str, Any]]:
        selection = self.results_tree.selection()
        if not selection:
            return None
        index = int(selection[0])
        return self._rows[index] if index < len(self._rows) else None

    def _run_on_selection(self, action):
        row = self._selected_row()
        if row is not None:
            action(row)

    def _update_action_bar(self):
        row = self._selected_row()
        state = "normal" if row else "disabled"
        for button in (self.btn_view_pdf, self.btn_open_excel, self.btn_open_folder, self.btn_view_citizens):
            button.configure(state=state)
        if row is None:
            self.lbl_selection.configure(text="")
        elif self._rows_kind == "citizen":
            self.btn_view_pdf.configure(text=f"👁️ Xem PDF (trang {row.get('page_number', 1)})")
            self.lbl_selection.configure(text=f"{row.get('full_name', '')} — {row.get('final_filename', '')}")
        else:
            self.btn_view_pdf.configure(text="👁️ Xem PDF")
            self.lbl_selection.configure(text=row.get("final_filename", ""))

    def _view_selected_pdf(self, row):
        page = row.get("page_number", 1) if self._rows_kind == "citizen" else 1
        self._open_pdf_viewer(row.get("pdf_path", ""), page)

    def _on_result_double_click(self, event):
        if self.results_tree.identify_region(event.x, event.y) not in ("cell", "tree"):
            return  # double-click on a heading or column separator
        self._open_selected_row()

    def _on_result_enter(self, _event=None):
        self._open_selected_row()

    def _open_selected_row(self):
        """Double-click or Enter: a book shows its citizens, a citizen opens the PDF page."""
        row = self._selected_row()
        if row is None:
            return
        if self._rows_kind == "dossier":
            self.drill_down_to_dossier_citizens(row.get("id"), row.get("final_filename", ""))
        else:
            self._view_selected_pdf(row)

    def _render_empty_placeholder(self, text: str):
        self.results_tree.delete(*self.results_tree.get_children())
        self._rows = []
        self.lbl_result_count.configure(text="")
        self.action_bar.pack_forget()
        self.table_holder.pack_forget()
        self.lbl_placeholder.configure(text=text)
        self.lbl_placeholder.pack(pady=40)

    def _open_pdf_viewer(self, pdf_path: str, page_num: int):
        if not os.path.exists(pdf_path):
            messagebox.showwarning("Không tìm thấy tệp", f"Tệp PDF không tồn tại tại đường dẫn:\n{pdf_path}")
            return

        if self.on_open_pdf_callback:
            self.on_open_pdf_callback(pdf_path, page_num)
        else:
            self._show_standalone_pdf_modal(pdf_path, page_num)

    def _show_standalone_pdf_modal(self, pdf_path: str, page_num: int):
        modal = ctk.CTkToplevel(self)
        modal.title(f"Hồ sơ PDF: {os.path.basename(pdf_path)} - Đang hiển thị trang {page_num}")
        modal.geometry("900x750")
        modal.after(100, modal.lift)

        viewer = PDFViewerFrame(modal)
        viewer.pack(fill="both", expand=True, padx=4, pady=4)
        viewer.load_pdf(pdf_path, initial_page=page_num)

    def _open_external_file(self, file_path: str):
        if not file_path:
            messagebox.showinfo("Chưa có Excel", "Hồ sơ này mới được đổi tên nhanh, chưa số hóa nên chưa có file Excel.")
            return
        if not os.path.exists(file_path):
            messagebox.showwarning("Không tìm thấy tệp", f"Tệp Excel không tồn tại:\n{file_path}")
            return
        try:
            os.startfile(file_path)
        except Exception as e:
            messagebox.showerror("Lỗi mở tệp", f"Không thể mở tệp:\n{e}")

    def _open_containing_folder(self, file_path: str):
        if not os.path.exists(file_path):
            messagebox.showwarning("Không tìm thấy tệp", f"Đường dẫn không tồn tại:\n{file_path}")
            return
        try:
            subprocess.run(["explorer.exe", "/select,", os.path.abspath(file_path)])
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể mở thư mục:\n{e}")

    def _sync_from_excel_folder(self):
        folder = filedialog.askdirectory(
            title="Chọn thư mục kho dữ liệu (Excel và sổ tổng hợp tỉnh) để đồng bộ vào CSDL",
            initialdir=get_default_dulieu_dir()
        )
        if not folder:
            return
        self.btn_sync.configure(state="disabled", text="⏳ Đang đồng bộ…")

        def job():
            errors, removed = [], []
            try:
                count = self.db.reindex_from_directory(folder, errors=errors, removed=removed)
            except Exception as exc:
                logger.exception("Could not sync from %s", folder)
                self.dispatch_to_ui(self._finish_sync, 0, errors, str(exc))
            else:
                self.dispatch_to_ui(self._finish_sync, count, errors, None, removed)

        try:
            self.run_in_background(job)
        except Exception:
            self.btn_sync.configure(state="normal", text=SYNC_BUTTON_TEXT)
            raise

    def _finish_sync(self, count, errors, failure, removed=()):
        self.btn_sync.configure(state="normal", text=SYNC_BUTTON_TEXT)
        if failure:
            messagebox.showerror("Lỗi đồng bộ", f"Có lỗi xảy ra khi quét thư mục:\n{failure}")
            return
        self.refresh_stats()
        self.refresh_results()  # dossiers just dropped were still listed and led to missing files
        dropped = ""
        if removed:
            names = ", ".join(removed[:4]) + (", …" if len(removed) > 4 else "")
            dropped = f"\n\nĐã bỏ {len(removed)} hồ sơ không còn PDF trong thư mục (đã đổi tên hoặc xóa): {names}"
        if errors:
            details = "\n".join(f"• {name}: {error}" for name, error in errors[:4])
            messagebox.showwarning("Kết quả đồng bộ", f"Đã đồng bộ {count} hồ sơ. Có {len(errors)} mục gặp lỗi.\n\n{details}{dropped}")
        else:
            messagebox.showinfo("Đồng bộ thành công", f"Đã đồng bộ {count} hồ sơ vào CSDL (gồm cả hồ sơ đổi tên nhanh trong sổ tổng hợp tỉnh).{dropped}")
