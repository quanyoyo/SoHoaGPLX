"""
Review & Quick Edit Panel (Right Column).
Displays extracted metadata, proposed filename, sequence analysis, and editable citizen grid.
"""
import os
import tkinter as tk
from tkinter import StringVar, messagebox, ttk
from typing import Dict, Any, List, Callable, Optional

import customtkinter as ctk

from src.config import PROVINCE_CODES
from src.gui.table_style import style_table, table_font
from src.naming_rules import (
    DOSSIER_GROUPS, format_exam_date, is_valid_windows_filename_stem, propose_dossier_filename, typed_format_errors,
)
from src.pipeline import summarize_license_tables
from src.table_extractor import apply_cell_edit, suggest_license_numbers, table_citizens

ERRORS_HEADING = "Cần sửa trước khi lưu:"


def naming_errors(fields):
    """The filename proposal and every naming error, including the stricter checks on typed values."""
    proposal = propose_dossier_filename(**fields)
    typed = typed_format_errors(group=proposal.group, exam_date=fields.get("exam_date", ""),
                                first_license_no=fields.get("first_license_no", ""),
                                last_license_no=fields.get("last_license_no", ""))
    return proposal, {**proposal.errors, **typed}


class ReviewPanel(ctk.CTkFrame):
    def __init__(self, master, on_confirm_callback: Callable, on_page_jump_callback: Callable,
                 on_saved_action_callback: Optional[Callable] = None, **kwargs):
        super().__init__(master, **kwargs)
        
        self.on_confirm_callback = on_confirm_callback
        self.on_page_jump_callback = on_page_jump_callback
        self.on_saved_action_callback = on_saved_action_callback
        self.current_data: Optional[Dict[str, Any]] = None
        self.citizen_entries: List[Dict[str, Any]] = []
        self.grid_tree = None
        self._grid_table = None
        self._grid_tables = {}
        self._cell_editor = None
        self._saving = False
        self.group_fields = {}
        self.naming_fields = {field: StringVar(master=self) for field in (
            "exam_date", "decision_number", "decision_date", "first_license_no", "last_license_no",
        )}
        self.province_options = {f"{p['code']} - {p['name']}": p for p in PROVINCE_CODES}

        self._build_ui()
        for value in self.naming_fields.values():
            value.trace_add("write", self._refresh_naming)

    def _build_ui(self):
        # 1. Top Section: Proposed Filename Banner
        self.banner_frame = ctk.CTkFrame(self, fg_color=("#EBF3FB", "#1F2D3D"), corner_radius=6)
        self.banner_frame.pack(fill="x", padx=6, pady=(6, 4))

        lbl_fn_title = ctk.CTkLabel(self.banner_frame, text="TÊN FILE ĐỀ XUẤT (QUY TẮC LƯU TRỮ):", font=("Segoe UI", 11, "bold"), text_color=("#1F497D", "#5B9BD5"))
        lbl_fn_title.pack(anchor="w", padx=10, pady=(6, 2))

        self.txt_proposed_filename = ctk.CTkEntry(self.banner_frame, font=("Consolas", 13, "bold"), height=32)
        self.txt_proposed_filename.pack(fill="x", padx=10, pady=(0, 8))
        self.lbl_naming = ctk.CTkLabel(self.banner_frame, text="", anchor="w", justify="left", wraplength=450)
        self.naming_notes_frame = ctk.CTkFrame(self.banner_frame, fg_color="transparent")
        self.naming_notes_frame.pack(fill="x", padx=10, pady=(0, 6))

        # 2. Middle Section: Metadata Cards in Scrollable Container
        self.scroll_form = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_form.pack(fill="both", expand=True, padx=6, pady=2)

        # Card A: Metadata bìa & Hộp số
        lbl_card_a = ctk.CTkLabel(self.scroll_form, text="THÔNG TIN BÌA SỔ & VỊ TRÍ HỒ SƠ", font=("Segoe UI", 12, "bold"))
        lbl_card_a.pack(anchor="w", pady=(4, 2))

        self.card_a = ctk.CTkFrame(self.scroll_form, corner_radius=6)
        self.card_a.pack(fill="x", pady=2)

        # Grid row 1: Loại sổ
        ctk.CTkLabel(self.card_a, text="Loại sổ:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.txt_book_type = ctk.CTkEntry(self.card_a, height=28)
        self.txt_book_type.grid(row=0, column=1, columnspan=3, sticky="ew", padx=8, pady=4)

        # Grid row 2: Ngày bìa (rộng rãi, không bị che ngày tháng)
        ctk.CTkLabel(self.card_a, text="Ngày thi/sát hạch:").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.txt_cover_date = ctk.CTkEntry(self.card_a, width=180, height=28, textvariable=self.naming_fields["exam_date"])
        self.txt_cover_date.grid(row=1, column=1, columnspan=3, sticky="w", padx=8, pady=4)

        # Grid row 3: Hạng / Khóa (xuống 1 dòng và căn lề trái)
        ctk.CTkLabel(self.card_a, text="Hạng / Khóa:").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        self.frame_hang_khoa = ctk.CTkFrame(self.card_a, fg_color="transparent")
        self.frame_hang_khoa.grid(row=2, column=1, columnspan=3, sticky="w", padx=8, pady=4)
        self.txt_hang = ctk.CTkEntry(self.frame_hang_khoa, width=60, height=28)
        self.txt_hang.pack(side="left", padx=(0, 4))
        self.txt_khoa = ctk.CTkEntry(self.frame_hang_khoa, width=80, height=28)
        self.txt_khoa.pack(side="left")

        # Grid row 4: HỘP, HỘP SỐ
        ctk.CTkLabel(self.card_a, text="HỘP (Tủ HS):").grid(row=3, column=0, sticky="w", padx=8, pady=4)
        self.txt_box = ctk.CTkEntry(self.card_a, width=90, height=28)
        self.txt_box.grid(row=3, column=1, sticky="w", padx=8, pady=4)

        # Its own row (like Hạng / Khóa): two boxes side by side were squeezed in a narrow panel.
        ctk.CTkLabel(self.card_a, text="HỘP SỐ (Hộp giấy):").grid(row=4, column=0, sticky="w", padx=8, pady=4)
        self.txt_box_number = ctk.CTkEntry(self.card_a, width=90, height=28)
        self.txt_box_number.grid(row=4, column=1, sticky="w", padx=8, pady=4)

        ctk.CTkLabel(self.card_a, text="Mã tỉnh lưu trữ:").grid(row=5, column=0, sticky="w", padx=8, pady=4)
        self.cmb_province = ctk.CTkComboBox(
            self.card_a, values=list(self.province_options), state="readonly", command=self._on_province_selected,
        )
        self.cmb_province.grid(row=5, column=1, columnspan=3, sticky="ew", padx=8)
        self.chk_province = ctk.CTkCheckBox(self.card_a, text="Xác nhận dùng mã tỉnh đã chọn", command=self._refresh_naming)
        self.chk_province.grid(row=6, column=0, columnspan=4, sticky="w", padx=8, pady=4)
        self.chk_province.grid_remove()

        ctk.CTkLabel(self.card_a, text="Nhóm nếu thiếu ngày thi:").grid(row=7, column=0, sticky="w", padx=8)
        self.cmb_group = ctk.CTkOptionMenu(self.card_a, values=["Tự động", *DOSSIER_GROUPS], command=self._refresh_naming)
        self.cmb_group.grid(row=7, column=1, columnspan=3, sticky="w", padx=8, pady=4)

        for row, (field, label) in enumerate([
            ("decision_number", "Số quyết định"), ("decision_date", "Ngày ký quyết định"),
            ("first_license_no", "Số GPLX đầu"), ("last_license_no", "Số GPLX cuối"),
        ], start=8):
            caption = ctk.CTkLabel(self.card_a, text=label)
            caption.grid(row=row, column=0, sticky="w", padx=8, pady=4)
            entry = ctk.CTkEntry(self.card_a, textvariable=self.naming_fields[field])
            entry.grid(row=row, column=1, columnspan=3, sticky="ew", padx=8, pady=4)
            self.group_fields[field] = (caption, entry)

        self.card_a.grid_columnconfigure(1, weight=1)
        self.card_a.grid_columnconfigure(3, weight=1)

        # Card B: Rà soát dãy số & Nhận định
        lbl_card_b = ctk.CTkLabel(self.scroll_form, text="RÀ SOÁT DÃY SỐ GPLX & NHẬN ĐỊNH", font=("Segoe UI", 12, "bold"))
        lbl_card_b.pack(anchor="w", pady=(10, 2))

        self.card_b = ctk.CTkFrame(self.scroll_form, corner_radius=6)
        self.card_b.pack(fill="x", pady=2)

        ctk.CTkLabel(self.card_b, text="Tổng số GPLX:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.txt_total_gplx = ctk.CTkEntry(self.card_b, width=80, height=28)
        self.txt_total_gplx.grid(row=0, column=1, sticky="w", padx=8, pady=4)

        # Its own row: beside "Tổng số" both boxes were squeezed in a narrow panel.
        ctk.CTkLabel(self.card_b, text="Nhận định:").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.opt_status_note = ctk.CTkOptionMenu(
            self.card_b,
            values=["Đủ", "Ngắt, không theo thứ tự", "Không có dữ liệu", "Cần rà soát"],
            width=170,
            height=28
        )
        self.opt_status_note.grid(row=1, column=1, sticky="w", padx=8, pady=4)

        # No "Dãy số GPLX" box: the sequence is computed from the lists when saving, and again from the
        # edited Excel by "Cập nhật sổ tổng hợp từ Excel".
        # The PDF's lists are one dossier: a button for each page still to check, in every list.
        self.table_pages_frame = ctk.CTkFrame(self.card_b, fg_color="transparent")
        self.table_pages_frame.grid(row=3, column=0, columnspan=2, sticky="w", padx=4, pady=(2, 4))
        self.table_pages_frame.grid_remove()

        # GPLX numbers the neighbouring rows point to (OCR read them wrong): accepted all at once.
        self._suggestions = {}  # id(table) -> {row index: suggested number}
        self.btn_accept_suggestions = ctk.CTkButton(
            self.card_b, text="", height=28, fg_color="#B45309", hover_color="#92400E",
            font=("Segoe UI", 12, "bold"), command=self._accept_suggestions,
        )
        self.btn_accept_suggestions.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(2, 4))
        self.btn_accept_suggestions.grid_remove()

        self.card_b.grid_columnconfigure(1, weight=1)

        # Card C: Editable Citizens Grid
        self.lbl_card_c = ctk.CTkLabel(self.scroll_form, text="DANH SÁCH TRONG PDF (GIỮ NGUYÊN CỘT CỦA BẢNG GỐC)", font=("Segoe UI", 12, "bold"))
        self.lbl_card_c.pack(anchor="w", pady=(10, 2))

        self.grid_frame = ctk.CTkFrame(self.scroll_form, corner_radius=6)
        self.grid_frame.pack(fill="both", expand=True, pady=2)

        # 3. Bottom Action Bar
        self.bottom_bar = ctk.CTkFrame(self, height=55, fg_color=("gray85", "gray20"))
        self.bottom_bar.pack(fill="x", padx=6, pady=(4, 6))

        # Initially disabled until OCR data is loaded
        self.btn_confirm = ctk.CTkButton(
            self.bottom_bar,
            text="✔ XÁC NHẬN: ĐỔI TÊN PDF & XUẤT EXCEL & CẬP NHẬT TỔNG HỢP",
            font=("Segoe UI", 13, "bold"),
            fg_color="gray50",
            hover_color="#155724",
            state="disabled",
            height=38,
            command=self._handle_confirm
        )
        self.btn_confirm.pack(fill="x", padx=10, pady=8)

        # A saved dossier is only shown: the Excel is edited, then the summary is updated from it.
        self.saved_buttons = [
            ctk.CTkButton(self.bottom_bar, text=text, font=("Segoe UI", 12, "bold"), height=32, fg_color=color,
                          command=lambda action=action: self._saved_action(action))
            for text, action, color in (
                ("📂 Mở file Excel", "open_excel", "#1F6FB2"),
                ("🔄 Cập nhật sổ tổng hợp từ Excel", "refresh", "#0F766E"),
                ("✏ Sửa lại hồ sơ (đọc lại PDF)", "reread", "#B45309"),
            )
        ]

    def _saved_action(self, action):
        if self.on_saved_action_callback and self.current_data and self.current_data.get("saved_view"):
            self.on_saved_action_callback(action)

    def _inputs(self):
        """Every box of the form with its state when it can be typed in."""
        return [(widget, "normal") for widget in (
            self.txt_proposed_filename, self.txt_book_type, self.txt_cover_date, self.txt_hang, self.txt_khoa,
            self.txt_box, self.txt_box_number, self.txt_total_gplx, self.opt_status_note, self.chk_province,
            *(entry for _caption, entry in self.group_fields.values()),
        )] + [(self.cmb_province, "readonly")]

    def _show_saved_view(self, saved, has_excel=False):
        if saved:
            self.btn_confirm.pack_forget()
            for button, action in zip(self.saved_buttons, ("open_excel", "refresh", "reread")):
                if action == "reread" or has_excel:
                    button.pack(fill="x", padx=10, pady=(6 if button is self.saved_buttons[0] else 2, 2))
                else:
                    button.pack_forget()
        else:
            for button in self.saved_buttons:
                button.pack_forget()
            self.btn_confirm.pack(fill="x", padx=10, pady=8)

    def load_data(self, dossier_data: Dict[str, Any]):
        self.current_data = None
        self._saving = False
        self._show_saved_view(False)
        for widget, state in self._inputs():
            widget.configure(state=state)  # boxes locked for a saved dossier are filled again
        self._show_form()
        # Values typed before switching to another file are shown again (store_draft).
        cover = {**dossier_data.get("cover_meta", {}), **dossier_data.get("review_draft", {})}
        
        # Populate form
        for field, var in self.naming_fields.items():
            var.set(cover.get(field, ""))
        # An exam date read by the machine is shown dd-mm-yyyy; one the user typed is shown as typed.
        if "exam_date" not in dossier_data.get("review_draft", {}):
            self.naming_fields["exam_date"].set(format_exam_date(cover.get("exam_date", "")))
        province = next(
            (label for label, item in self.province_options.items() if item["code"] == cover.get("province_code")),
            "Chọn mã tỉnh",
        )
        self.cmb_province.set(province)
        self.cmb_group.set(cover.get("confirmed_group") or "Tự động")
        self.chk_province.deselect()
        if cover.get("province_confirmed"):
            self.chk_province.select()

        self.txt_book_type.delete(0, "end")
        self.txt_book_type.insert(0, cover.get("book_type", "Sổ gốc cấp bằng lái xe cơ giới đường bộ"))

        # Values not read from the PDF or its folders stay empty for the user to type.
        self.txt_hang.delete(0, "end")
        self.txt_hang.insert(0, cover.get("license_class") or "")

        self.txt_khoa.delete(0, "end")
        self.txt_khoa.insert(0, cover.get("course") or "")

        self.txt_box.delete(0, "end")
        self.txt_box.insert(0, cover.get("box") or "")

        self.txt_box_number.delete(0, "end")
        self.txt_box_number.insert(0, cover.get("box_number") or "")

        self._show_table_pages(dossier_data.get("tables", []))
        self._show_table_summary(cover)

        if dossier_data.get("rename_only"):
            self.lbl_card_c.pack_forget()
            self.grid_frame.pack_forget()
            self._clear_grid()
            self._find_suggestions([])
        else:
            self.lbl_card_c.pack(anchor="w", pady=(10, 2))
            self.grid_frame.pack(fill="both", expand=True, pady=2)
            self._find_suggestions(dossier_data.get("tables", []), shown=not dossier_data.get("saved_view"))
            self._populate_grid(dossier_data.get("tables", []))

        self.current_data = dossier_data
        self._refresh_naming()
        if draft := dossier_data.get("review_filename"):
            self.txt_proposed_filename.delete(0, "end")
            self.txt_proposed_filename.insert(0, draft)
        if dossier_data.get("saved_view"):
            # The saved name, not one built again from the boxes.
            self.txt_proposed_filename.delete(0, "end")
            self.txt_proposed_filename.insert(0, os.path.splitext(os.path.basename(dossier_data["original_path"]))[0])
            note = "Hồ sơ đã lưu: chỉ xem. " + (
                "Sửa Excel rồi bấm Cập nhật, hoặc bấm Sửa lại để đọc lại PDF." if dossier_data.get("excel_path")
                else "Bấm Sửa lại để đọc lại PDF.")
            self.lbl_naming.configure(text=note)
            self._render_naming_lines([(note, False)])
            for widget, _state in self._inputs():
                widget.configure(state="disabled")
            self.cmb_group.configure(state="disabled")
            self._show_saved_view(True, has_excel=bool(dossier_data.get("excel_path")))

    def _show_table_summary(self, cover):
        self.txt_total_gplx.delete(0, "end")
        if cover.get("total_licenses") is not None:
            self.txt_total_gplx.insert(0, str(cover["total_licenses"]))
        self.opt_status_note.set(cover.get("status_note") or "Cần rà soát")

    def _show_table_pages(self, tables):
        for button in self.table_pages_frame.winfo_children():
            button.destroy()
        lists = [table for table in tables if table["rows"]]
        if not lists:
            self.table_pages_frame.grid_remove()
            return
        pages = sorted({page for table in lists for page in table.get("unresolved_pages", [])})
        start = lists[0]["rows"][0]["page_number"]
        targets = [(f"Đối chiếu trang {page}", page) for page in pages] or [(f"Xem trang {start} (đầu danh sách)", start)]
        # Three to a row: one long row squeezed the buttons of a book with many pages to check.
        for index, (text, page) in enumerate(targets):
            ctk.CTkButton(self.table_pages_frame, text=text, height=26, width=10,
                          command=lambda page=page: self.on_page_jump_callback(page)).grid(
                row=index // 3, column=index % 3, sticky="w", padx=4, pady=2)
        self.table_pages_frame.grid()

    def _on_province_selected(self, _choice):
        self.chk_province.deselect()
        self._refresh_naming()

    def _naming_inputs(self):
        cover = self.current_data["cover_meta"]
        province = self.province_options.get(self.cmb_province.get(), {})
        return {
            **{field: value.get().strip() for field, value in self.naming_fields.items()},
            "province_code": province.get("code", ""),
            "province_confirmed": bool(self.chk_province.get()),
            "suggested_province_code": cover.get("suggested_province_code", ""),
            "license_column_empty": cover.get("license_column_empty", False),
            "confirmed_group": self.cmb_group.get() if self.cmb_group.get() in DOSSIER_GROUPS else "",
        }

    def _refresh_naming(self, *_, update_filename=True):
        if not self.current_data or self._saving:
            return
        if self.current_data.get("saved_view") and self.txt_box.cget("state") == "disabled":
            return  # shown as saved
        fields = self._naming_inputs()
        suggested = fields["suggested_province_code"]
        if fields["province_code"] and suggested and fields["province_code"] != suggested:
            self.chk_province.grid()
        else:
            self.chk_province.grid_remove()
        self.cmb_group.configure(state="disabled" if fields["exam_date"] else "normal")

        proposal, field_errors = naming_errors(fields)
        if update_filename:
            self.txt_proposed_filename.delete(0, "end")
            if proposal.filename and not field_errors:
                self.txt_proposed_filename.insert(0, proposal.filename)
        rename_only = self.current_data.get("rename_only")
        visible = {
            "decision_number": proposal.group in {None, "QĐTT", "QĐSH"},
            "decision_date": proposal.group in {None, "QĐTT"},
            "first_license_no": proposal.group in {None, "SQL"},
            "last_license_no": proposal.group in {None, "SQL"},
        }
        for field, widgets in self.group_fields.items():
            for widget in widgets:
                if not rename_only or visible[field]:
                    widget.grid()
                else:
                    widget.grid_remove()
        # Only what must be fixed before saving, in red. Notes for information (group, document type,
        # OCR province hint, list review) are left out: the province error names the OCR hint, and the
        # list review shows as the yellow rows and the "Đối chiếu trang n" buttons.
        errors = list(field_errors.values())
        # A folder note (e.g. which number is the box) stays while that required box is still empty.
        typed = {**fields, "box": self.txt_box.get().strip(), "box_number": self.txt_box_number.get().strip()}
        errors += [warning for field, warning in self.current_data["cover_meta"].get("metadata_review", {}).items()
                   if not typed.get(field) and field not in field_errors]
        items = [(ERRORS_HEADING, True)] + [(f"• {text}", True) for text in errors] if errors else []
        self.lbl_naming.configure(text="\n".join(text for text, _ in items))
        render_fn = getattr(self, "_render_naming_lines", None)
        if callable(render_fn):
            render_fn(items)
        self.btn_confirm.configure(
            text="XÁC NHẬN LƯU PDF VÀ SỔ TỔNG HỢP" if rename_only else "✔ XÁC NHẬN: ĐỔI TÊN PDF & XUẤT EXCEL & CẬP NHẬT TỔNG HỢP",
            state="disabled" if field_errors else "normal",
            fg_color="gray50" if field_errors else "#1E7E34",
        )

    def _render_naming_lines(self, items):
        if not hasattr(self, "naming_notes_frame") or not self.naming_notes_frame:
            return
        try:
            for widget in self.naming_notes_frame.winfo_children():
                widget.destroy()
            # An empty frame keeps its default height (200): shown only when there is a line to show.
            if items:
                self.naming_notes_frame.pack(fill="x", padx=10, pady=(0, 6))
            else:
                self.naming_notes_frame.pack_forget()
            for text, is_required in items:
                lbl = ctk.CTkLabel(
                    self.naming_notes_frame,
                    text=text,
                    font=("Segoe UI", 11, "bold" if is_required else "normal"),
                    text_color=("#D32F2F", "#EF5350") if is_required else ("#1C1D1F", "#DCE1E8"),
                    anchor="w",
                    justify="left",
                    wraplength=470,
                )
                lbl.pack(fill="x", anchor="w", pady=1)
        except Exception:
            pass

    def _show_form(self):
        self.scroll_form.pack(fill="both", expand=True, padx=6, pady=2, before=self.bottom_bar)

    def set_saving(self, saving):
        self._saving = saving
        self.txt_proposed_filename.configure(state="disabled" if saving else "normal")
        if saving:
            self.scroll_form.pack_forget()
            self.btn_confirm.configure(text="Đang lưu PDF và sổ tổng hợp…", state="disabled", fg_color="gray50")
        else:
            self._show_form()
            self._refresh_naming(update_filename=False)

    def clear_data(self, message="Chọn PDF để xem và rà soát."):
        self.current_data = None
        self._saving = False
        self._show_saved_view(False)
        for widget, state in self._inputs():
            widget.configure(state=state)
        self.txt_proposed_filename.configure(state="normal")
        self.txt_proposed_filename.delete(0, "end")
        self.lbl_naming.configure(text=message)
        render_fn = getattr(self, "_render_naming_lines", None)
        if callable(render_fn):
            render_fn([(message, False)] if message else [])
        self._show_table_pages([])
        self._find_suggestions([])
        self.scroll_form.pack_forget()
        self.btn_confirm.configure(text="XÁC NHẬN", state="disabled", fg_color="gray50")

    def _clear_grid(self):
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        self.citizen_entries = []
        self.grid_tree = None
        self._grid_table = None
        self._cell_editor = None

    def _populate_grid(self, tables: List[Dict[str, Any]]):
        """Show the selected list with the PDF's own columns; double-click a cell to correct it."""
        self._clear_grid()
        self._grid_tables = {f"Danh sách {i} · {len(t['rows'])} dòng": t for i, t in enumerate(tables, 1)}
        if not tables:
            ctk.CTkLabel(
                self.grid_frame, justify="left", wraplength=480,
                text="Không tìm thấy danh sách có cột Họ và tên và Năm sinh/Ngày sinh trong PDF.",
            ).pack(anchor="w", padx=8, pady=8)
            return
        if len(tables) > 1:
            # A drop-down: a row of buttons cut the labels once a PDF had more than a few lists.
            row = ctk.CTkFrame(self.grid_frame, fg_color="transparent")
            row.pack(anchor="w", fill="x", padx=4, pady=(4, 2))
            ctk.CTkLabel(row, text=f"Đang xem ({len(tables)} danh sách):", font=("Segoe UI", 11, "bold")).pack(
                side="left", padx=(2, 6))
            self.grid_chooser = ctk.CTkOptionMenu(
                row, values=list(self._grid_tables), width=230, font=("Segoe UI", 11),
                command=lambda label: self._show_grid_table(self._grid_tables[label]))
            self.grid_chooser.set(next(iter(self._grid_tables)))
            self.grid_chooser.pack(side="left")
        ctk.CTkLabel(self.grid_frame, text="Nhấp đúp vào ô để sửa · chọn dòng để xem trang PDF · dòng vàng cần đối chiếu",
                     font=("Segoe UI", 10, "italic")).pack(anchor="w", padx=6)
        holder = ctk.CTkFrame(self.grid_frame, fg_color="transparent")
        holder.pack(fill="both", expand=True, padx=2, pady=2)
        tree = ttk.Treeview(holder, show="headings", height=12, style="GPLX.Treeview", selectmode="browse")
        y_scroll = ctk.CTkScrollbar(holder, orientation="vertical", command=tree.yview)
        x_scroll = ctk.CTkScrollbar(holder, orientation="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)
        tree.tag_configure("review", background="#FFF4CC")
        tree.tag_configure("edited", background="#E3F4E8")
        tree.bind("<Double-1>", self._start_cell_edit)
        tree.bind("<MouseWheel>", self._on_grid_wheel)
        tree.bind("<<TreeviewSelect>>", self._jump_to_selected_row)
        self.grid_tree = tree
        self._wheel_rest = 0
        self._grid_widths = {}
        self._grid_stretch = set()
        self._apply_grid_scaling()
        self._show_grid_table(tables[0])

    def _apply_grid_scaling(self):
        """Size the list table like the rest of the window (see table_style)."""
        scale = self._get_widget_scaling()
        style_table(self, "GPLX.Treeview", scale)
        if self.grid_tree is not None:
            for column_id, width in self._grid_widths.items():
                # Name and address only grow: in a narrow panel the list scrolls instead of squeezing them.
                smallest = width if column_id in self._grid_stretch else 40
                self.grid_tree.column(column_id, width=round(width * scale), minwidth=round(smallest * scale))

    def _on_grid_wheel(self, event):
        """The wheel scrolls the list, not the whole form with it; at the list's end the form scrolls."""
        tree = self.grid_tree
        if tree is None or not event.delta:
            return None
        first, last = (float(value) for value in tree.yview())
        up = event.delta > 0
        if (up and first <= 0.0) or (not up and last >= 1.0):
            self._wheel_rest = 0
            return None
        if (self._wheel_rest > 0) != up:
            self._wheel_rest = 0  # turned the other way
        self._wheel_rest += event.delta
        rows = int(self._wheel_rest / 40)  # 3 rows a notch (120); touchpads send smaller steps
        if rows:
            self._wheel_rest -= rows * 40
            tree.yview_scroll(-rows, "units")
        return "break"  # the form (CustomTkinter scrolls it for any wheel event inside) stays put

    def _set_scaling(self, new_widget_scaling, new_window_scaling):
        # Called by CustomTkinter when the window moves to a screen with another display scale.
        super()._set_scaling(new_widget_scaling, new_window_scaling)
        if getattr(self, "grid_tree", None) is not None:
            self._apply_grid_scaling()

    def _show_grid_table(self, table):
        self._finish_cell_edit()
        tree = self.grid_tree
        self._grid_table = table
        tree.delete(*tree.get_children())
        columns = table["columns"]
        ids = [f"c{i}" for i in range(len(columns))] + ["page"]
        tree.configure(columns=ids)
        self._grid_widths = {}
        self._grid_stretch = set()
        for column_id, column in zip(ids, columns):
            tree.heading(column_id, text=column["label"])
            self._grid_widths[column_id] = {"full_name": 170, "address": 200, "photo": 60, "signature": 60,
                                            "stt": 46, "register_index": 76}.get(column["role"], max(80, min(150, len(column["label"]) * 9)))
            # Name and address take the room left, so the table fills the panel.
            if column["role"] in ("full_name", "address"):
                self._grid_stretch.add(column_id)
            tree.column(column_id, stretch=column_id in self._grid_stretch)
        self._grid_widths["page"] = 52
        tree.heading("page", text="Trang")
        tree.column("page", stretch=False, anchor="center")
        self._apply_grid_scaling()
        for index, row in enumerate(table["rows"]):
            tree.insert("", "end", iid=str(index), values=self._grid_values(table, row, index),
                        tags=self._grid_tags(table, row, index))

    def _suggestion(self, table, index):
        return self._suggestions.get(id(table), {}).get(index)

    def _grid_values(self, table, row, index):
        suggestion = self._suggestion(table, index)
        values = [("(ảnh)" if c["role"] in ("photo", "signature") and value else
                   f"{value} → {suggestion}?" if suggestion and c["role"] == "license_number" else value)
                  for c, value in zip(table["columns"], row["cells"])]
        return [*values, row["page_number"]]

    def _grid_tags(self, table, row, index):
        if row.get("_edited"):
            return ("edited",)
        if (row.get("license_state") in ("uncertain", "unknown_column") or not row.get("identity_confident", True)
                or self._suggestion(table, index)):
            return ("review",)
        return ()

    def _find_suggestions(self, tables, shown=True):
        """GPLX numbers the neighbours point to, in every list; the button accepts them all."""
        self._suggestions = {id(table): found for table in tables if (found := suggest_license_numbers(table))}
        count = sum(map(len, self._suggestions.values())) if shown else 0
        if not shown:
            self._suggestions = {}
        if count:
            self.btn_accept_suggestions.configure(text=f"✔ Nhận {count} số GPLX gợi ý")
            self.btn_accept_suggestions.grid()
        else:
            self.btn_accept_suggestions.grid_remove()

    def _accept_suggestions(self):
        if not self.current_data or self._saving or self.current_data.get("saved_view"):
            return
        self._finish_cell_edit()
        tables = self.current_data.get("tables", [])
        for table in tables:
            column = [c["role"] for c in table["columns"]].index("license_number") if id(table) in self._suggestions else None
            for index, number in self._suggestions.get(id(table), {}).items():
                apply_cell_edit(table, table["rows"][index], column, number)
        self._find_suggestions(tables)
        if self._grid_table is not None:
            self._show_grid_table(self._grid_table)
        self._refresh_table_stats()

    def _jump_to_selected_row(self, _event=None):
        if self._cell_editor is not None or not self.grid_tree or self._grid_table is None:
            return
        selection = self.grid_tree.selection()
        if selection:
            self.on_page_jump_callback(self._grid_table["rows"][int(selection[0])]["page_number"])

    def _start_cell_edit(self, event):
        tree = self.grid_tree
        if self.current_data and self.current_data.get("saved_view"):
            return  # a saved list is corrected in its Excel
        if tree is None or tree.identify_region(event.x, event.y) != "cell":
            return
        item, column_id = tree.identify_row(event.y), tree.identify_column(event.x)
        index = int(column_id.lstrip("#")) - 1
        columns = self._grid_table["columns"]
        if not item or index >= len(columns) or columns[index]["role"] in ("photo", "signature"):
            return
        self._finish_cell_edit()
        x, y, width, height = tree.bbox(item, column_id)
        editor = tk.Entry(tree, font=table_font(self._get_widget_scaling()), relief="solid", borderwidth=1)
        editor.insert(0, self._grid_table["rows"][int(item)]["cells"][index])
        editor.select_range(0, "end")
        editor.place(x=x, y=y, width=max(width, round(120 * self._get_widget_scaling())), height=height)
        editor.focus_set()
        editor.bind("<Return>", lambda _e: self._finish_cell_edit())
        editor.bind("<KP_Enter>", lambda _e: self._finish_cell_edit())
        editor.bind("<Escape>", lambda _e: self._finish_cell_edit(save=False))
        editor.bind("<FocusOut>", lambda _e: self._finish_cell_edit())
        self._cell_editor = (editor, int(item), index)

    def _finish_cell_edit(self, save=True):
        if self._cell_editor is None:
            return
        editor, row_index, col_index = self._cell_editor
        self._cell_editor = None
        value = editor.get().strip()
        editor.destroy()
        table = self._grid_table
        row = table["rows"][row_index]
        if not save or value == row["cells"][col_index]:
            return
        apply_cell_edit(table, row, col_index, value)
        if table["columns"][col_index]["role"] == "license_number":
            # A corrected number can make or answer a suggestion anywhere in the list.
            self._find_suggestions(self.current_data.get("tables", []))
            self._show_grid_table(table)
            self.grid_tree.see(str(row_index))
        else:
            self.grid_tree.item(str(row_index), values=self._grid_values(table, row, row_index),
                                tags=self._grid_tags(table, row, row_index))
        # A GPLX number changes the range; a corrected name can complete the count and the status.
        if table["columns"][col_index]["role"] in ("license_number", "full_name"):
            self._refresh_table_stats()

    def _refresh_table_stats(self):
        """A corrected GPLX number or name can change the book's range, count and status."""
        stats = summarize_license_tables(self.current_data.get("tables", []))
        self.current_data["sequence_analysis"] = stats.pop("sequence_analysis")
        cover = self.current_data["cover_meta"]
        cover.update(stats)
        data = self.current_data
        self.current_data = None
        for field in ("first_license_no", "last_license_no"):
            self.naming_fields[field].set(cover[field])
        self.current_data = data
        self._show_table_summary(cover)
        self._refresh_naming()

    def store_draft(self):
        """Keep what was typed with the file before another file is shown. Nothing is saved to disk."""
        if not self.current_data or self._saving or self.current_data.get("saved_view"):
            return
        self._finish_cell_edit()
        group = self.cmb_group.get()
        self.current_data["review_draft"] = {
            **{field: value.get().strip() for field, value in self.naming_fields.items()},
            "province_code": self.province_options.get(self.cmb_province.get(), {}).get("code", ""),
            "province_confirmed": bool(self.chk_province.get()),
            "confirmed_group": group if group in DOSSIER_GROUPS else "",
            "book_type": self.txt_book_type.get().strip(),
            "license_class": self.txt_hang.get().strip(),
            "course": self.txt_khoa.get().strip(),
            "box": self.txt_box.get().strip(),
            "box_number": self.txt_box_number.get().strip(),
            "total_licenses": self.txt_total_gplx.get().strip() or None,
            "status_note": self.opt_status_note.get().strip(),
        }
        self.current_data["review_filename"] = self.txt_proposed_filename.get().strip()

    def _missing_fields(self):
        """Labels of required boxes left empty. "-" records that the paper does not show the value."""
        return [label for entry, label in (
            (self.txt_book_type, "Loại sổ"), (self.txt_hang, "Hạng"), (self.txt_khoa, "Khóa"),
            (self.txt_box, "Hộp"), (self.txt_box_number, "Hộp số"), (self.txt_total_gplx, "Tổng số GPLX"),
        ) if not entry.get().strip()]

    def _handle_confirm(self):
        if not self.current_data or self._saving or self.current_data.get("saved_view"):
            return
        # Apply a cell still being edited first: a corrected GPLX number can change the filename.
        self._finish_cell_edit()

        # Harvest updated values
        final_fn = self.txt_proposed_filename.get().strip()
        fields = self._naming_inputs()
        proposal, field_errors = naming_errors(fields)
        if field_errors:
            messagebox.showwarning(ERRORS_HEADING.rstrip(":"), "\n".join(field_errors.values()))
            return
        if missing := self._missing_fields():
            messagebox.showwarning(
                "Còn ô chưa nhập",
                f"Hãy nhập: {', '.join(missing)}.\n\nNếu giấy tờ không ghi thông tin này, nhập dấu \"-\".",
            )
            return
        if not is_valid_windows_filename_stem(final_fn):
            messagebox.showwarning("Tên file không hợp lệ", "Nhập tên file hợp lệ cho Windows và bỏ phần đuôi .pdf.")
            return

        cover = {**self.current_data["cover_meta"], **fields}
        cover["province_name"] = self.province_options[self.cmb_province.get()]["name"]
        cover["dossier_group"] = proposal.group
        cover["book_type"] = self.txt_book_type.get().strip()
        cover["license_class"] = self.txt_hang.get().strip()
        cover["course"] = self.txt_khoa.get().strip()
        cover["box"] = self.txt_box.get().strip()
        cover["box_number"] = self.txt_box_number.get().strip()
        cover["status_note"] = self.opt_status_note.get().strip()
        count = self.txt_total_gplx.get().strip()
        if count and count != "-" and not (len(count) <= 12 and count.isascii() and count.isdecimal()):
            messagebox.showwarning("Số lượng không hợp lệ", "Nhập tổng số GPLX bằng số nguyên không âm, hoặc \"-\" nếu giấy tờ không ghi.")
            return
        cover["total_licenses"] = "-" if count == "-" else int(count) if count else None

        # The grid edits the source tables in place; the lookup fields are projected from them.
        tables = self.current_data.get("tables", [])
        updated_citizens = [citizen for table in tables for citizen in table_citizens(table)]

        self.on_confirm_callback(
            original_path=self.current_data["original_path"],
            final_filename=final_fn,
            cover_meta=cover,
            citizens=updated_citizens,
            source_tables=tables,
        )
