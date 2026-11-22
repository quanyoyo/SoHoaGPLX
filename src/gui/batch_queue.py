"""
Batch Queue Component (Left Sidebar).
Manages folder loading, queue list, status badges, and province selection.
"""
import os
import threading
import tkinter.font as tkfont
import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk
from typing import List, Dict, Any, Callable, Optional
from src.config import PROVINCE_CODES, get_default_dulieu_dir
from src.gui.table_style import style_table, table_font
from src.logger import get_logger

logger = get_logger(__name__)

FOLDER_BUTTON_TEXT = "📁 Chọn Thư mục Hồ sơ"
FILES_BUTTON_TEXT = "📄 Chọn File PDF lẻ"
RENAME_BUTTON_TEXT = "📑 Đổi tên file nhanh (chọn theo folder)"
STATUS_COLUMN_WIDTH = 74  # at 100% display scale
NAME_COLUMN_WIDTH = 170
CELL_PADDING = 8  # room the table keeps around a cell's text
ACTIVE_ROW_COLOR = "#DBEAFE"  # the file shown in the viewer


class BatchQueueFrame(ctk.CTkFrame):
    def __init__(self, master, on_select_file_callback: Callable, on_batch_start_callback: Callable, dispatch_to_ui: Callable, on_worker_start: Callable, on_worker_finish: Callable,
                 on_batch_stop_callback: Optional[Callable] = None, on_refresh_all_callback: Optional[Callable] = None,
                 **kwargs):
        super().__init__(master, **kwargs)
        
        self.on_select_file_callback = on_select_file_callback
        self.on_batch_start_callback = on_batch_start_callback
        self.on_batch_stop_callback = on_batch_stop_callback
        self.on_refresh_all_callback = on_refresh_all_callback
        self._view = "pending"  # "pending": files to work on; "done": saved files
        self._stopping = False
        self.dispatch_to_ui = dispatch_to_ui
        self.on_worker_start = on_worker_start
        self.on_worker_finish = on_worker_finish
        self.queue_items: List[Dict[str, Any]] = []
        self.rename_mode = False
        self._folder_scan = None
        self._rows: Dict[int, list] = {}  # id(item) -> [row id in the table, shown state, item]
        self._row_items: List[Dict[str, Any]] = []
        self._active = None  # the file shown in the viewer
        self._pressed_row = ""
        self._name_room = 0  # pixels a name may take; longer names are cut in the middle
        self._fitted: Dict[str, str] = {}
        self._refit_job = None

        # Loading animation state
        self.is_loading: bool = False
        self.spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_idx: int = 0

        self._build_ui()

    def _build_ui(self):
        # 1. Header & Actions
        self.lbl_title = ctk.CTkLabel(self, text="HÀNG ĐỢI HỒ SƠ", font=("Segoe UI", 13, "bold"))
        self.lbl_title.pack(anchor="w", padx=10, pady=(8, 4))

        # Province selector
        lbl_prov = ctk.CTkLabel(self, text="Mã Tỉnh / Thành phố:", font=("Segoe UI", 11))
        lbl_prov.pack(anchor="w", padx=10, pady=(2, 0))

        prov_options = [f"{p['code']} - {p['name']}" for p in PROVINCE_CODES]
        self.cmb_province = ctk.CTkComboBox(self, values=prov_options, height=28, state="readonly")
        self.cmb_province.set("Chọn mã tỉnh")
        self.cmb_province.pack(fill="x", padx=10, pady=(2, 8))

        # Folder button
        self.btn_open_folder = ctk.CTkButton(
            self,
            text=FOLDER_BUTTON_TEXT,
            font=("Segoe UI", 12, "bold"),
            fg_color="#0066CC",
            hover_color="#004C99",
            height=32,
            command=self._choose_folder
        )
        self.btn_open_folder.pack(fill="x", padx=10, pady=3)

        # File button (Prominent emerald color)
        self.btn_open_files = ctk.CTkButton(
            self,
            text=FILES_BUTTON_TEXT,
            font=("Segoe UI", 11, "bold"),
            fg_color="#10B981",
            hover_color="#059669",
            text_color="white",
            height=30,
            command=self._choose_files
        )
        self.btn_open_files.pack(fill="x", padx=10, pady=(2, 4))

        # Folder Batch Copy & Rename button
        self.btn_rename_folder = ctk.CTkButton(
            self,
            text=RENAME_BUTTON_TEXT,
            font=("Segoe UI", 11, "bold"),
            fg_color="#D97706",
            hover_color="#B45309",
            text_color="white",
            height=30,
            command=self._choose_rename_folder
        )
        self.btn_rename_folder.pack(fill="x", padx=10, pady=(2, 6))

        # Progress info
        self.lbl_stats = ctk.CTkLabel(self, text="0 file trong hàng đợi", font=("Segoe UI", 11, "italic"))
        self.lbl_stats.pack(anchor="w", padx=10, pady=2)

        self.progress_bar = ctk.CTkProgressBar(self, height=8)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=10, pady=(2, 8))

        # Run Batch button (Initially disabled until files are uploaded)
        self.btn_run_batch = ctk.CTkButton(
            self,
            text="⚡ Chạy OCR Tự Động",
            font=("Segoe UI", 12, "bold"),
            fg_color="gray50",
            hover_color="#D35400",
            state="disabled",
            height=32,
            command=self._start_batch
        )
        self.btn_run_batch.pack(fill="x", padx=10, pady=(0, 8))

        # Saved files have their own list: opening one shows what was saved, without OCR.
        self.view_switch = ctk.CTkSegmentedButton(self, values=self._view_labels(), command=self._on_view_switch,
                                                  font=("Segoe UI", 11, "bold"))
        self.view_switch.set(self._view_labels()[0])
        self.view_switch.pack(fill="x", padx=10, pady=(0, 4))
        self.btn_refresh_all = ctk.CTkButton(
            self, text="🔄 Cập nhật tất cả từ Excel", font=("Segoe UI", 11, "bold"), height=28,
            fg_color="#0F766E", hover_color="#115E59", command=self._refresh_all,
        )

        # 2. File list: one table for any number of files. A card of widgets per file took 8 Windows
        # handles each: 1,300 files used up the 10,000 a program may have, 1,000 took 13 s to show.
        self.list_holder = ctk.CTkFrame(self, fg_color="transparent")
        self.list_holder.pack(fill="both", expand=True, padx=6, pady=4)
        self.file_tree = ttk.Treeview(self.list_holder, columns=("status", "name"), show="headings",
                                      style="GPLXFiles.Treeview", selectmode="browse")
        self.file_tree.heading("status", text="Trạng thái", anchor="w")
        self.file_tree.heading("name", text="Tên file", anchor="w")
        self.file_tree.column("status", stretch=False, anchor="w")
        self.file_tree.column("name", stretch=True, anchor="w")
        y_scroll = ctk.CTkScrollbar(self.list_holder, orientation="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=y_scroll.set)
        self.file_tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        self.list_holder.grid_rowconfigure(0, weight=1)
        self.list_holder.grid_columnconfigure(0, weight=1)
        for status, (_, color) in self._BADGES.items():
            self.file_tree.tag_configure(status, foreground=color)
        self.file_tree.tag_configure("active", background=ACTIVE_ROW_COLOR)
        # Opening a file starts reading it: a click or Enter opens, the arrow keys only move.
        self.file_tree.bind("<ButtonPress-1>", self._on_file_press)
        self.file_tree.bind("<ButtonRelease-1>", self._on_file_click)
        self.file_tree.bind("<Return>", self._on_file_enter)
        self.file_tree.bind("<KP_Enter>", self._on_file_enter)
        self.file_tree.bind("<Configure>", self._schedule_refit)
        self._apply_list_scaling()

    def _apply_list_scaling(self):
        """Size the list like the rest of the window (see table_style)."""
        scale = self._get_widget_scaling()
        style_table(self, "GPLXFiles.Treeview", scale)
        self._name_font = tkfont.Font(self, font=table_font(scale))
        self.file_tree.column("status", width=round(STATUS_COLUMN_WIDTH * scale),
                              minwidth=round(STATUS_COLUMN_WIDTH * scale))
        self.file_tree.column("name", width=round(NAME_COLUMN_WIDTH * scale), minwidth=round(60 * scale))
        self._name_room = -1  # names are fitted again
        self._refit_names()

    def _schedule_refit(self, _event=None):
        if self._refit_job is None:
            self._refit_job = self.after(100, self._refit_names)  # once the table has its new width

    def _refit_names(self):
        self._refit_job = None
        room = int(self.file_tree.column("name", "width")) - round(CELL_PADDING * self._get_widget_scaling())
        if room != self._name_room:
            self._name_room = room
            self._fitted = {}
            for item in self._row_items:
                self._update_row(item)

    def _fit_name(self, name):
        """The whole name when it fits, else its start and end: "15.SQL.03.19…37-C244498"."""
        fitted = self._fitted.get(name)
        if fitted is None:
            fitted = self._fitted[name] = self._shorten(name)
        return fitted

    def _shorten(self, name):
        measure = self._name_font.measure
        if self._name_room <= 0 or measure(name) <= self._name_room:
            return name
        low, high = 1, len(name) - 1  # characters kept around the "…"
        while low < high:
            keep = (low + high + 1) // 2
            if measure(self._cut_middle(name, keep)) <= self._name_room:
                low = keep
            else:
                high = keep - 1
        return self._cut_middle(name, low)

    @staticmethod
    def _cut_middle(name, keep):
        head = keep // 2  # the end holds the license numbers: it keeps the larger half
        return name[:head] + "…" + name[len(name) - (keep - head):]

    def destroy(self):
        if self._refit_job is not None:
            self.after_cancel(self._refit_job)
            self._refit_job = None
        super().destroy()

    def _set_scaling(self, new_widget_scaling, new_window_scaling):
        # Called by CustomTkinter when the window moves to a screen with another display scale.
        super()._set_scaling(new_widget_scaling, new_window_scaling)
        if hasattr(self, "file_tree"):
            self._apply_list_scaling()

    def get_selected_province_code(self) -> str:
        code, separator, _ = self.cmb_province.get().partition(" - ")
        return code if separator else ""

    def _choose_folder(self):
        folder = filedialog.askdirectory(
            title="Chọn thư mục chứa các file scan PDF",
            initialdir=get_default_dulieu_dir()
        )
        if folder:
            self._load_queue(folder=folder, rename=False)

    def _choose_files(self):
        files = filedialog.askopenfilenames(
            title="Chọn các file PDF scan",
            filetypes=[("PDF Files", "*.pdf")],
            initialdir=get_default_dulieu_dir()
        )
        if files:
            self._load_queue(files=list(files), rename=False)

    def _choose_rename_folder(self):
        folder = filedialog.askdirectory(
            title="Chọn thư mục PDF để rà soát và đổi tên",
            initialdir=get_default_dulieu_dir(),
        )
        if folder:
            self._load_queue(folder=folder, rename=True)

    def _queue_is_saving(self):
        if any(item["status"] == "SAVING" for item in self.queue_items):
            messagebox.showinfo("Đang lưu hồ sơ", "Đang lưu một hồ sơ. Hãy đợi lưu xong rồi chọn lại.")
            return True
        return False

    def _set_choosers_busy(self, busy):
        for button, text in ((self.btn_open_folder, FOLDER_BUTTON_TEXT), (self.btn_open_files, FILES_BUTTON_TEXT),
                             (self.btn_rename_folder, RENAME_BUTTON_TEXT)):
            button.configure(state="disabled" if busy else "normal", text="Đang đọc danh sách…" if busy else text)

    def _load_queue(self, *, folder=None, files=None, rename):
        """Each chooser replaces the whole list (files already saved are marked done)."""
        if self._queue_is_saving():
            return
        token = self._folder_scan = object()
        self._set_choosers_busy(True)

        def scan():
            try:
                from src.pipeline import list_folder_review_pdfs
                if folder:
                    entries = list_folder_review_pdfs(folder, require_excel=not rename)
                else:
                    wanted = {os.path.normcase(os.path.realpath(path)): path for path in files}
                    found = {}
                    for parent in dict.fromkeys(os.path.dirname(os.path.realpath(path)) for path in files):
                        for path, saved in list_folder_review_pdfs(parent, require_excel=not rename):
                            found[os.path.normcase(path)] = (path, saved)
                    entries = [found.get(key, (path, None)) for key, path in wanted.items()]
                self.dispatch_to_ui(self._finish_folder_scan, token, entries, None, rename)
            except Exception as exc:
                logger.exception("Could not list PDF files in %s", folder or files)
                self.dispatch_to_ui(self._finish_folder_scan, token, [], str(exc), rename)
            finally:
                self.on_worker_finish()

        self.on_worker_start()
        try:
            threading.Thread(target=scan, daemon=True).start()
        except Exception:
            self.on_worker_finish()
            self._set_choosers_busy(False)
            raise

    def _finish_folder_scan(self, token, entries, error=None, rename=True):
        self._set_choosers_busy(False)
        if token is not self._folder_scan:
            return
        self._folder_scan = None
        if error:
            messagebox.showerror("Không đọc được thư mục", error)
            return
        if not entries:
            messagebox.showinfo("Thư mục trống", "Không tìm thấy file PDF để rà soát.")
            return
        if self._queue_is_saving():
            return
        for item in self.queue_items:
            item["cancelled"] = True  # queued OCR for the old list is skipped
        self.rename_mode = rename
        self.queue_items = [
            {"path": path, "filename": os.path.basename(path), "status": "COMPLETED" if saved else "PENDING",
             "data": None, "rename_only": rename, "saved_pdf": saved}
            for path, saved in entries
        ]
        self.lbl_title.configure(text="RÀ SOÁT PDF THEO THƯ MỤC" if rename else "HÀNG ĐỢI HỒ SƠ")
        if rename:
            self.btn_run_batch.pack_forget()
        else:
            self.btn_run_batch.pack(fill="x", padx=10, pady=(0, 8), before=self.view_switch)
        self._view = "pending" if any(not self._is_done(item) for item in self.queue_items) else "done"
        self._render_queue()
        self._update_batch_button()
        self.on_select_file_callback(None)
        if rename:
            first = next((item for item in self.queue_items if item["status"] == "PENDING"), self.queue_items[0])
            self.on_select_file_callback(first["path"])

    def _update_batch_button(self):
        if self.is_loading:
            return
        if any(item["status"] == "PENDING" for item in self.queue_items) and not self.rename_mode:
            self.btn_run_batch.configure(state="normal", fg_color="#E67E22")
        else:
            self.btn_run_batch.configure(state="disabled", fg_color="gray50")

    def _add_files_to_queue(self, paths: List[str]):
        """Append files without registration lookup (kept for scripts and tests)."""
        for p in paths:
            if any(item["path"] == p for item in self.queue_items):
                continue
            self.queue_items.append({"path": p, "filename": os.path.basename(p), "status": "PENDING", "data": None})
        self._render_queue()
        self._update_batch_button()

    # Status shown in the list and the colour of its row (no emoji variation selector: Tk draws it
    # as a wide blank).
    _BADGES = {
        "PENDING": ("⏳ Chờ", "#4B5563"),
        "PROCESSING": ("⚙ OCR...", "#1F6FB2"),
        "READY": ("👁 Duyệt", "#1E8449"),
        "SAVING": ("💾 Đang lưu", "#1F6FB2"),
        "COMPLETED": ("✅ Xong", "#239B56"),
        "ERROR": ("❌ Lỗi", "#C0392B"),
    }

    def _row_state(self, item):
        status = item["status"] if item["status"] in self._BADGES else "PENDING"
        if item.get("saved_pdf") and status in {"PENDING", "READY"}:
            status = "COMPLETED"  # a saved file opened again for corrections keeps its done marker
        name = self._fit_name(os.path.splitext(item["filename"])[0])  # every file here is a PDF
        return self._BADGES[status][0], status, name, item is self._active

    @staticmethod
    def _is_done(item):
        return item["status"] == "COMPLETED"

    def _visible_items(self):
        done = self._view == "done"
        return [item for item in self.queue_items if self._is_done(item) == done]

    def _view_labels(self):
        done = sum(1 for item in self.queue_items if self._is_done(item))
        return [f"Đang xử lý ({len(self.queue_items) - done})", f"Đã xong ({done})"]

    def _on_view_switch(self, label):
        self._view = "done" if label.startswith("Đã xong") else "pending"
        self._render_queue()

    def _refresh_all(self):
        if self.on_refresh_all_callback:
            self.on_refresh_all_callback([item for item in self.queue_items if self._is_done(item)])

    def _render_queue(self):
        """Fill the table again when the list itself changed; otherwise only update rows whose state changed."""
        visible = self._visible_items()
        if len(self._row_items) != len(visible) or any(a is not b for a, b in zip(self._row_items, visible)):
            self._rebuild_rows()
        else:
            for item in visible:
                self._update_row(item)
        self._refresh_counts()

    def _rebuild_rows(self):
        tree = self.file_tree
        tree.delete(*tree.get_children())
        self._rows = {}
        self._row_items = self._visible_items()
        for index, item in enumerate(self._row_items):
            tree.insert("", "end", iid=str(index))
            self._rows[id(item)] = [str(index), None, item]  # the item is kept, so its id stays unique
            self._update_row(item)
        if self._active is not None and self._rows.get(id(self._active)):
            self.show_active(self._active)  # still in the list after files were added

    def _update_row(self, item):
        row = self._rows.get(id(item))
        if row is None or row[2] is not item:
            return False
        state = self._row_state(item)
        if row[1] != state:
            badge, status, name, active = state
            self.file_tree.item(row[0], values=(badge, name), tags=(status, "active") if active else (status,))
            row[1] = state
        return True

    def _row_at(self, event):
        if self.file_tree.identify_region(event.x, event.y) not in ("cell", "tree"):
            return ""  # a heading, a column border or the space below the files
        return self.file_tree.identify_row(event.y)

    def _on_file_press(self, event):
        self._pressed_row = self._row_at(event)

    def _on_file_click(self, event):
        pressed, self._pressed_row = self._pressed_row, ""
        self._schedule_refit()  # a column border may have been dragged
        if pressed and self._row_at(event) == pressed:
            self._open_row(pressed)

    def _on_file_enter(self, _event=None):
        selection = self.file_tree.selection()
        if selection:
            self._open_row(selection[0])

    def _open_row(self, row_id):
        index = int(row_id)
        if index < len(self._row_items):
            self.on_select_file_callback(self._row_items[index]["path"])  # the path changes when saved

    def show_active(self, item):
        """Mark the file shown in the viewer, also when the app moves on to the next file itself."""
        previous, self._active = self._active, item
        if item is not None and item in self.queue_items and self._is_done(item) != (self._view == "done"):
            self._view = "done" if self._is_done(item) else "pending"  # the shown file is in the list on screen
            self._render_queue()
            return
        for changed in (previous, item):
            if changed is not None:
                self._update_row(changed)
        row = self._rows.get(id(item)) if item is not None else None
        if row is None or row[2] is not item:
            self.file_tree.selection_set(())
            return
        self.file_tree.selection_set(row[0])
        self.file_tree.focus(row[0])  # the arrow keys go on from here
        self.file_tree.see(row[0])

    def _refresh_counts(self):
        total = len(self.queue_items)
        done_count = sum(1 for item in self.queue_items if item["status"] == "COMPLETED" or item.get("saved_pdf"))
        self.lbl_stats.configure(text=f"Đã duyệt: {done_count} / {total} file")
        self.progress_bar.set(done_count / total if total > 0 else 0)
        labels = self._view_labels()
        self.view_switch.configure(values=labels)
        self.view_switch.set(labels[self._view == "done"])
        # Only digitized files have an Excel to update the summary from.
        if self._view == "done" and not self.rename_mode:
            self.btn_refresh_all.pack(fill="x", padx=10, pady=(0, 4), before=self.list_holder)
        else:
            self.btn_refresh_all.pack_forget()

    def update_item_status(self, path: str, new_status: str, data: Optional[Dict[str, Any]] = None):
        if item := self.get_item(path):
            self.update_entry(item, new_status, data)

    def update_entry(self, item, status, data=None):
        item["status"] = status
        if data is not None:
            item["data"] = data
        if self.get_item(item["path"]) is item:
            in_view = self._is_done(item) == (self._view == "done")
            if in_view and self._update_row(item):
                self._refresh_counts()
                return
            if not in_view and item is self._active:
                self._view = "done" if self._is_done(item) else "pending"  # the open file stays on screen
            self._render_queue()  # the file moved to the other list, or was not shown yet

    def get_item(self, path: str) -> Optional[Dict[str, Any]]:
        for item in self.queue_items:
            if item["path"] == path:
                return item
        return None

    def start_loading(self):
        """Starts the rotating circle loading indicator on the OCR button."""
        self.is_loading = True
        self._stopping = False
        # While OCR runs the same button stops it (files not read yet go back to "Chờ").
        self.btn_run_batch.configure(state="normal" if self.on_batch_stop_callback else "disabled",
                                     fg_color="#C0392B", command=self._stop_batch)
        self._animate_spinner()

    def _stop_batch(self):
        if not self.is_loading or self._stopping:
            return
        self._stopping = True
        self.btn_run_batch.configure(state="disabled")
        self.on_batch_stop_callback()

    def _animate_spinner(self):
        if not self.is_loading:
            return
        frame = self.spinner_frames[self.spinner_idx % len(self.spinner_frames)]
        self.spinner_idx += 1
        if self._stopping:
            self.btn_run_batch.configure(text=f"{frame}  Đang dừng sau file đang đọc…")
        else:
            self.btn_run_batch.configure(text=f"{frame}  Đang chạy OCR… (bấm để dừng)")
        self.after(90, self._animate_spinner)

    def stop_loading(self):
        """Stops the loading indicator and restores standard state."""
        self.is_loading = False
        self._stopping = False
        self.btn_run_batch.configure(text="⚡ Chạy OCR Tự Động", command=self._start_batch)
        self._update_batch_button()

    def _start_batch(self):
        prov_code = self.get_selected_province_code()
        self.on_batch_start_callback(prov_code)
