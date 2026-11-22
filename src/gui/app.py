"""
Main Application Window for GPLX Digitization, Renaming & Verification.
Features Dual-Mode Interface:
Tab 1: 📥 Số hóa & Đổi tên (3-column resizable layout with PanedWindow)
Tab 2: 🔍 Tra cứu Hồ sơ (Sub-millisecond query, 1-click jump to PDF page)
"""
import json
import logging
import os
import queue
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
import customtkinter as ctk
from tkinter import messagebox
from typing import Dict, Any, Optional

from src.config import UI_SETTINGS_PATH
from src.gui.batch_queue import BatchQueueFrame
from src.gui.pdf_viewer import PDFViewerFrame
from src.gui.review_panel import ReviewPanel
from src.gui.search_screen import SearchScreenFrame
from src.gui.lan_screen import LANScreenFrame
from src.pipeline import StalePdfError, process_dossier_pdf, commit_dossier, commit_folder_dossier
from src.logger import get_logger, set_exception_notifier

logger = get_logger(__name__)

class GPLXApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("HỆ THỐNG SỐ HÓA, ĐỔI TÊN & TRA CỨU HỒ SƠ GPLX LỊCH SỬ (v2.0)")
        self.geometry("1400x850")
        self.minsize(1200, 700)

        # Set appearance
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        self.active_file_path: Optional[str] = None
        self.active_item = None
        self.is_processing_batch: bool = False
        self._closing = False
        self._ui_tasks = queue.Queue()
        self._worker_lock = threading.Lock()
        self._active_workers = 0
        self._active_ocr = 0  # OCR only reads PDFs: closing during it is allowed
        self._batch_stop = None
        self.exit_now = False  # closed while OCR was reading (see on_close and run)
        self._ocr = ThreadPoolExecutor(max_workers=1, thread_name_prefix="GPLX-OCR")
        set_exception_notifier(
            lambda title, message: self._dispatch_to_ui(self._show_error_popup, title, message)
        )

        self._build_layout()
        threading.Thread(target=self._backup_database, name="GPLX-DB-Backup", daemon=True).start()
        self.report_callback_exception = self._report_callback_exception
        self.after(50, self._drain_ui_tasks)

        # Handle window close to shutdown LAN server gracefully
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Default to Full Screen (Maximized window) on startup
        try:
            self.after(100, lambda: self.state("zoomed"))
        except Exception:
            pass

    @staticmethod
    def _backup_database():
        """One copy of the shared database per day; failures are logged only."""
        try:
            from src.database import DatabaseManager
            if made := DatabaseManager().backup_daily():
                logger.info("Database backup saved: %s", made)
        except Exception:
            logger.exception("Daily database backup failed")

    def _build_layout(self):
        # Top Tabview
        self.tabview = ctk.CTkTabview(self, corner_radius=6)
        self.tabview.pack(fill="both", expand=True, padx=6, pady=(4, 6))

        self.tab_ingest = self.tabview.add("📥 SỐ HÓA & ĐỔI TÊN HỒ SƠ")
        self.tab_search = self.tabview.add("🔍 TRA CỨU HỒ SƠ & MỞ FILE SCAN")
        self.tab_lan = self.tabview.add("🌐 CHIA SẺ MẠNG LAN (MÁY CHỦ NỘI BỘ)")

        self._build_ingest_tab()
        self._build_search_tab()
        self._build_lan_tab()

    def _build_lan_tab(self):
        self.lan_screen = LANScreenFrame(self.tab_lan)
        self.lan_screen.pack(fill="both", expand=True)

    def _build_ingest_tab(self):
        # 3-column split layout using PanedWindow for draggable resizing
        sash_color = "#B0B8C4" if ctk.get_appearance_mode() == "Light" else "#3A3D40"
        self.paned = tk.PanedWindow(
            self.tab_ingest,
            orient=tk.HORIZONTAL,
            sashrelief=tk.RAISED,
            sashwidth=6,
            sashpad=2,
            bg=sash_color,
            bd=0
        )
        self.paned.pack(fill="both", expand=True, padx=2, pady=2)

        # Pane 1: Sidebar Batch Queue
        self.sidebar = BatchQueueFrame(
            self.paned,
            width=246,
            on_select_file_callback=self.on_file_selected,
            on_batch_start_callback=self.on_batch_run_requested,
            dispatch_to_ui=self._dispatch_to_ui,
            on_worker_start=self._worker_started,
            on_worker_finish=self._worker_finished,
            on_batch_stop_callback=self.on_batch_stop_requested,
        )
        self.paned.add(self.sidebar, stretch="never")

        # Pane 2: PDF Viewer with Bidirectional Scrolling. It takes the width the side panes leave, so they
        # keep their widths when the window or the screen changes.
        self.viewer = PDFViewerFrame(self.paned)
        self.paned.add(self.viewer, stretch="always")

        # Pane 3: Review & Edit Panel
        self.review = ReviewPanel(
            self.paned,
            width=510,
            on_confirm_callback=self.on_confirm_commit,
            on_page_jump_callback=self.on_page_jump
        )
        self.paned.add(self.review, stretch="never")
        self.pane_widths = self._load_pane_widths()
        self._dragged = None
        self._apply_pane_scaling()
        self.paned.bind("<ButtonPress-1>", self._on_sash_pressed, add="+")
        self.paned.bind("<ButtonRelease-1>", self._on_sash_released, add="+")

    # (pane, width, smallest width) at 100% display scale. The side panes start at these widths, then keep
    # the widths the user drags them to on this machine (UI_SETTINGS_PATH).
    PANES = (("sidebar", 246, 180), ("viewer", 630, 380), ("review", 510, 470))

    def _apply_pane_scaling(self, scale=None):
        """tk.PanedWindow takes sizes in screen pixels: at 200% the file list and the viewer got half
        their width (cut buttons, file names shown as "15.S"). Scale them like CustomTkinter does."""
        scale = scale or self.sidebar._get_widget_scaling()
        self.paned.configure(sashwidth=round(6 * scale))
        for name, width, smallest in self.PANES:
            width = self.pane_widths.get(name, width)
            self.paned.paneconfigure(getattr(self, name), width=round(width * scale), minsize=round(smallest * scale))

    def _load_pane_widths(self):
        """Side pane widths (100% units) the user left on this machine; the defaults on the first start."""
        widths = {name: width for name, width, _ in self.PANES if name != "viewer"}
        try:
            with open(UI_SETTINGS_PATH, encoding="utf-8") as f:
                saved = json.load(f).get("panes", {})
            for name, _, smallest in self.PANES:
                value = saved.get(name)
                if name in widths and type(value) in (int, float) and smallest <= value <= 4000:
                    widths[name] = round(value)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, AttributeError):
            logger.warning("Window layout %s is unreadable: default pane widths used", UI_SETTINGS_PATH, exc_info=True)
        return widths

    def _save_pane_widths(self):
        try:
            os.makedirs(os.path.dirname(UI_SETTINGS_PATH), exist_ok=True)
            temporary = UI_SETTINGS_PATH + ".tmp"
            with open(temporary, "w", encoding="utf-8") as f:
                json.dump({"panes": self.pane_widths}, f, indent=2)
            os.replace(temporary, UI_SETTINGS_PATH)
        except OSError:
            logger.warning("Could not save the window layout to %s", UI_SETTINGS_PATH, exc_info=True)

    def _pane_width(self, name):
        """Width of a pane as shown now, in 100% units."""
        return round(getattr(self, name).winfo_width() / self.sidebar._get_widget_scaling())

    def _on_sash_pressed(self, event):
        # Presses on the paned window land on a divider: the one left of the PDF viewer moves the file list,
        # the other the review pane. Only that pane is stored, since a narrow window squeezes the others.
        name = "sidebar" if event.x < self.viewer.winfo_x() else "review"
        self._dragged = (name, self._pane_width(name))

    def _on_sash_released(self, _event):
        self.after(100, self._remember_dragged_pane)  # Tk moves the panes when it next lays them out

    def _remember_dragged_pane(self):
        if self._dragged is None:
            return
        name, before = self._dragged
        self._dragged = None
        width = self._pane_width(name)
        if width != before:
            self.pane_widths[name] = width
            self._save_pane_widths()

    def _set_scaling(self, new_widget_scaling, new_window_scaling):
        # Called by CustomTkinter when the window moves to a screen with another display scale.
        super()._set_scaling(new_widget_scaling, new_window_scaling)
        if hasattr(self, "paned"):
            self._apply_pane_scaling(new_widget_scaling)

    def _build_search_tab(self):
        self.search_screen = SearchScreenFrame(
            self.tab_search,
            on_open_pdf_callback=self.on_search_view_pdf,
            dispatch_to_ui=self._dispatch_to_ui,
            run_in_background=self._launch_worker,
        )
        self.search_screen.pack(fill="both", expand=True)

    def on_search_view_pdf(self, pdf_path: str, page_num: int):
        """Switches to Ingestion tab and loads the PDF at the specific page."""
        if any(item["status"] == "SAVING" and os.path.normcase(os.path.abspath(item["path"]))
               == os.path.normcase(os.path.abspath(pdf_path)) for item in self.sidebar.queue_items):
            # Opening it now would block the rename of the save in progress.
            messagebox.showinfo("Đang lưu hồ sơ", "Hồ sơ này đang được lưu. Hãy mở lại sau khi lưu xong.")
            return
        if self.active_file_path != pdf_path:
            self.review.store_draft()  # typed values come back when the file is selected again
            self.active_file_path = None
            self.active_item = None
            self.sidebar.show_active(None)
            self.review.clear_data()
        self.tabview.set("📥 SỐ HÓA & ĐỔI TÊN HỒ SƠ")
        self.viewer.load_pdf(pdf_path, initial_page=page_num)

    def _is_active(self, item):
        return self.active_item is item and self.sidebar.get_item(item["path"]) is item

    def on_file_selected(self, file_path: Optional[str]):
        if file_path is None:
            self.active_file_path = None
            self.active_item = None
            self.sidebar.show_active(None)
            self.review.clear_data()
            self.viewer.clear_preview()
            return
        item = self.sidebar.get_item(file_path)
        if not item:
            return

        # Typed values are kept before the panel is filled again, also when the same file is clicked.
        self.review.store_draft()
        if self.active_item is not item:
            self.review.clear_data()
        self.active_item = item
        self.active_file_path = file_path
        self.sidebar.show_active(item)
        if item["status"] == "SAVING":
            # The save renames this PDF; opening it in the preview would block the rename.
            self.viewer.clear_preview()
        else:
            self.viewer.load_pdf(file_path, initial_page=1)

        saved = item.get("saved_pdf")
        if item["status"] == "COMPLETED" and saved and os.path.normcase(saved) != os.path.normcase(file_path):
            # Scan kept by an older version next to the PDF it was saved as.
            self.review.clear_data(f"PDF này đã được lưu thành {os.path.basename(saved)}")
        elif item["status"] in {"READY", "SAVING"} and item["data"]:
            self.review.load_data(item["data"])
            if item["status"] == "SAVING":
                self.review.set_saving(True)
        elif item["status"] == "PROCESSING":
            self.review.clear_data("Đang đọc thông tin PDF…")
        elif item["status"] in {"PENDING", "ERROR", "COMPLETED"}:
            # A saved PDF is read again so it can be corrected and saved again.
            self._process_single_file_async(file_path)

    def _process_single_file_async(self, file_path: str):
        item = self.sidebar.get_item(file_path)
        if not item:
            return
        self.sidebar.update_entry(item, "PROCESSING")
        self.review.clear_data("Đang đọc thông tin PDF…")
        prov_code = self.sidebar.get_selected_province_code()
        rename_only = item.get("rename_only", False)

        def worker():
            if item.get("cancelled"):
                return
            try:
                res = process_dossier_pdf(file_path, default_province=prov_code, rename_only=rename_only)
                logger.info("PDF review data ready: %s", file_path)
                self._dispatch_to_ui(self._on_single_file_processed, item, res)
            except Exception as exc:
                logger.exception("OCR failed for %s", file_path)
                self._dispatch_to_ui(self._on_single_file_error, item, str(exc))

        logger.info("Queued PDF review: %s, rename_only=%s", file_path, rename_only)
        try:
            self._launch_worker(worker, ocr=True)
        except Exception:
            self.sidebar.update_entry(item, "ERROR")
            raise

    def _on_single_file_processed(self, item, data: Dict[str, Any]):
        self.sidebar.update_entry(item, "READY", data)
        if self._is_active(item):
            self.review.load_data(data)

    def _on_single_file_error(self, item, err_msg: str):
        self.sidebar.update_entry(item, "ERROR")
        if self._is_active(item):
            self.review.clear_data("Lỗi đọc PDF. Chọn lại file để thử lại.")
            messagebox.showerror("Lỗi OCR", f"Không thể xử lý file:\n{item['filename']}\n\nChi tiết: {err_msg}")

    def on_batch_run_requested(self, prov_code: str):
        if self.sidebar.rename_mode:
            return
        if self.is_processing_batch:
            messagebox.showinfo("Thông báo", "Đang trong tiến trình chạy hàng loạt!")
            return

        pending_items = [it for it in self.sidebar.queue_items if it["status"] == "PENDING"]
        if not pending_items:
            messagebox.showinfo("Thông báo", "Không có tệp nào ở trạng thái Chờ xử lý!")
            return

        self.is_processing_batch = True
        stop = self._batch_stop = threading.Event()
        self.sidebar.start_loading()
        for item in pending_items:
            item["status"] = "PROCESSING"
        self.sidebar._render_queue()

        def batch_worker():
            try:
                for item in pending_items:
                    if item.get("cancelled") or stop.is_set():
                        continue  # the list was replaced, or the user stopped the batch
                    path = item["path"]
                    try:
                        res = process_dossier_pdf(path, default_province=prov_code)
                        self._dispatch_to_ui(self._on_single_file_processed, item, res)
                    except Exception as exc:
                        logger.exception("Batch OCR failed for %s", path)
                        self._dispatch_to_ui(self._on_single_file_error, item, str(exc))
            finally:
                self._dispatch_to_ui(self._finish_batch, pending_items, stopped=stop.is_set())

        try:
            self._launch_worker(batch_worker, ocr=True)
        except Exception:
            for item in pending_items:
                item["status"] = "PENDING"
            self._finish_batch(show_dialog=False)
            raise

    def on_batch_stop_requested(self):
        """Stop after the file being read; the files not read yet go back to "Chờ"."""
        if self._batch_stop is not None:
            self._batch_stop.set()

    def _finish_batch(self, batch_items=(), show_dialog=True, stopped=False):
        self.is_processing_batch = False
        self._batch_stop = None
        for item in batch_items:
            if item["status"] == "PROCESSING" and not item.get("cancelled"):
                item["status"] = "PENDING"  # skipped after the user stopped the batch
                if self._is_active(item):
                    # It said "Đang đọc thông tin PDF…" while waiting for its turn.
                    self.review.clear_data("Đã dừng OCR trước khi đọc file này. Bấm lại vào file để đọc.")
        self.sidebar.stop_loading()
        self.sidebar._render_queue()
        if stopped and show_dialog and not self._closing:
            messagebox.showinfo("Đã dừng OCR", "Đã dừng đọc OCR. Các file chưa đọc trở lại trạng thái Chờ.")
        elif show_dialog and not self.sidebar.rename_mode and any(
                item["status"] == "READY" for item in self.sidebar.queue_items):
            messagebox.showinfo("Hoàn tất", "Đã xử lý OCR xong hàng đợi. Bạn có thể duyệt từng PDF.")

    def on_page_jump(self, page_num: int):
        self.viewer.go_to_page(page_num)

    def on_confirm_commit(self, original_path: str, final_filename: str, cover_meta: Dict[str, Any], citizens: list,
                          source_tables=None):
        item = self.sidebar.get_item(original_path)
        if item and self._is_active(item) and item["status"] == "READY":
            self._save_item(item, final_filename, cover_meta, citizens, source_tables)

    def _save_item(self, item, final_filename, cover_meta, citizens, source_tables=None):
        """Both flows save in the background: rename the PDF, update the summary, Excel and database."""
        data = item["data"]
        data["cover_meta"] = cover_meta
        data["review_filename"] = final_filename
        data.pop("review_draft", None)  # the confirmed values replace an older draft
        stamp = data.get("source_stamp")
        rename_only = item.get("rename_only", False)
        path = item["path"]
        page = self.viewer.current_page_idx + 1
        # Windows cannot rename a PDF while the preview keeps it open.
        self.viewer.close_pdf()
        self.sidebar.update_entry(item, "SAVING")
        self.review.set_saving(True)

        def save():
            try:
                if rename_only:
                    result = commit_folder_dossier(path, final_filename, cover_meta, source_stamp=stamp)
                else:
                    result = commit_dossier(path, final_filename, cover_meta, citizens,
                                            source_tables=source_tables, source_stamp=stamp)
            except StalePdfError as exc:
                logger.warning("PDF changed after it was read: %s", path)
                self._dispatch_to_ui(self._finish_save, item, None, str(exc), page, reread=True)
            except Exception as exc:
                logger.exception("Save failed for %s", path)
                self._dispatch_to_ui(self._finish_save, item, None, str(exc), page)
            else:
                self._dispatch_to_ui(self._finish_save, item, result, None, page)

        try:
            self._launch_worker(save)
        except Exception as exc:
            logger.exception("Could not start saving %s", path)
            self._finish_save(item, None, str(exc), page)

    def _finish_save(self, item, result, error=None, page=1, reread=False):
        if error and reread:
            # The review data belongs to the old file: drop it so the PDF is read again.
            item["data"] = None
            self.sidebar.update_entry(item, "PENDING")
            active = self._is_active(item)
            if active:
                self.review.set_saving(False)
                self.viewer.load_pdf(item["path"], initial_page=page)
            if self.sidebar.get_item(item["path"]) is item:
                messagebox.showerror("Không thể lưu hồ sơ", f"{item['filename']}\n\n{error}\n\n"
                                     "Máy sẽ đọc lại PDF này. Hãy rà soát lại rồi xác nhận.")
            if active:
                self._process_single_file_async(item["path"])
            return
        if error:
            self.sidebar.update_entry(item, "READY")
            if self._is_active(item):
                self.review.set_saving(False)
                self.viewer.load_pdf(item["path"], initial_page=page)
            if self.sidebar.get_item(item["path"]) is item:
                messagebox.showerror("Không thể lưu hồ sơ", f"{item['filename']}\n\n{error}")
            return
        was_active = self._is_active(item)
        new_path = result["pdf_path"]
        old_name = item["filename"]
        item.update(path=new_path, filename=os.path.basename(new_path), saved_pdf=new_path, data=None)
        self.sidebar.update_entry(item, "COMPLETED")
        try:
            self.search_screen.refresh_stats()
            if not result.get("db_error"):
                self.search_screen.refresh_results()  # a listed row may show the old name
            self.lan_screen.refresh_state()
        except Exception:
            logger.exception("Could not refresh statistics after saving")
        if result.get("db_error"):
            messagebox.showwarning(
                "Đã lưu hồ sơ, lỗi cập nhật CSDL",
                f"Đã lưu {item['filename']} và sổ tổng hợp, nhưng chưa cập nhật được CSDL tra cứu:\n"
                f"{result['db_error']}\n\nVào tab Tra cứu, bấm '🔄 Quét lại từ Excel' và chọn thư mục tỉnh để cập nhật lại.",
            )
        elif not item.get("rename_only"):
            messagebox.showinfo("Đã lưu hồ sơ", (
                f"• Đổi tên PDF: {old_name} → {item['filename']}\n"
                f"• File Excel: {os.path.basename(result['excel_path'])}\n"
                f"• Sổ tổng hợp tỉnh: {os.path.basename(result['master_summary_path'])}\n"
                f"• CSDL tra cứu: {result['total_citizens']} công dân."
            ))
        if was_active:
            self.active_file_path = new_path
            self.review.clear_data(f"Đã lưu PDF {item['filename']}")
            self.viewer.load_pdf(new_path, initial_page=page)
            self._select_next_item(after=item)

    def _select_next_item(self, after=None):
        if after is not None:
            items = self.sidebar.queue_items
            index = next(i for i, item in enumerate(items) if item is after)
            for item in items[index + 1:] + items[:index]:
                if item["status"] in {"READY", "PENDING", "PROCESSING"}:
                    self.on_file_selected(item["path"])
                    return
            return
        for item in self.sidebar.queue_items:
            if item["status"] in ["READY", "PENDING"]:
                self.on_file_selected(item["path"])
                break

    def on_close(self):
        """Gracefully stops LAN server and terminates GUI."""
        with self._worker_lock:
            active_workers, active_ocr = self._active_workers, self._active_ocr
        saving = any(item["status"] == "SAVING" for item in self.sidebar.queue_items)
        if saving or active_workers > active_ocr or (not active_ocr and not self._ui_tasks.empty()):
            # Saving, folder scans and database sync change files: they must finish.
            messagebox.showwarning(
                "Đang xử lý",
                "Vui lòng đợi tác vụ nền hoàn tất rồi đóng ứng dụng để tránh gián đoạn xử lý tệp.",
            )
            return
        if active_ocr:
            if not messagebox.askyesno(
                    "Đang đọc OCR",
                    "Máy đang đọc OCR các file PDF. Đóng ứng dụng sẽ dừng việc đọc; các file chưa đọc xong "
                    "sẽ được đọc lại lần sau (không ảnh hưởng hồ sơ đã lưu).\n\nĐóng ứng dụng?"):
                return
            if self._batch_stop is not None:
                self._batch_stop.set()
            for item in self.sidebar.queue_items:
                item["cancelled"] = True  # queued OCR is skipped
            # OCR cannot stop inside a file: without this the program read on unseen for minutes,
            # keeping the PDF locked (see run).
            self.exit_now = True
        self._closing = True
        self._ocr.shutdown(wait=False)
        try:
            from src.server.lan_server import lan_server
            if lan_server.is_running:
                lan_server.stop()
        except Exception:
            logger.exception("Could not stop LAN server cleanly")
        try:
            self.viewer.close_pdf()
        except Exception:
            logger.exception("Could not close the active PDF cleanly")
        self.destroy()

    def run(self):
        """Show the window until it is closed.

        Closed while OCR was reading a PDF: the process ends at once. Nothing is being written then
        (on_close waits for saves, folder scans and database updates), and an OCR left running kept the
        program alive unseen for minutes with the PDF locked.
        """
        self.mainloop()
        if self.exit_now:
            logger.info("Closed while OCR was reading: ending the process now")
            logging.shutdown()
            os._exit(0)

    def _dispatch_to_ui(self, callback, *args, **kwargs):
        if not self._closing:
            self._ui_tasks.put((callback, args, kwargs))

    def _worker_started(self):
        with self._worker_lock:
            self._active_workers += 1

    def _worker_finished(self):
        with self._worker_lock:
            self._active_workers -= 1

    def _launch_worker(self, work, *, ocr=False):
        def run():
            try:
                work()
            finally:
                if ocr:
                    with self._worker_lock:
                        self._active_ocr -= 1
                self._worker_finished()

        self._worker_started()
        if ocr:
            with self._worker_lock:
                self._active_ocr += 1
        try:
            if ocr:
                self._ocr.submit(run)
            else:
                threading.Thread(target=run, daemon=True).start()
        except Exception:
            if ocr:
                with self._worker_lock:
                    self._active_ocr -= 1
            self._worker_finished()
            raise

    def _drain_ui_tasks(self):
        while not self._ui_tasks.empty():
            callback, args, kwargs = self._ui_tasks.get()
            try:
                callback(*args, **kwargs)
            except Exception:
                logger.exception("UI task callback failed: %r", callback)
                self._show_error_popup(
                    "Lỗi ứng dụng",
                    "Một thao tác giao diện gặp lỗi. Chi tiết đã được ghi vào file log.",
                )
        if not self._closing:
            self.after(50, self._drain_ui_tasks)

    def _report_callback_exception(self, exc_type, exc_value, exc_traceback):
        logger.error(
            "Unhandled Tkinter callback exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        self._show_error_popup(
            "Lỗi ứng dụng",
            "Ứng dụng gặp lỗi khi xử lý thao tác giao diện.\n"
            f"{exc_type.__name__}: {exc_value}\n\nChi tiết đã được ghi vào file log.",
        )

    @staticmethod
    def _show_error_popup(title: str, message: str):
        try:
            messagebox.showerror(title, message)
        except Exception:
            logger.exception("Could not display error popup")
