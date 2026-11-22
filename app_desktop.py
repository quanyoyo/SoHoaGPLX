"""
Entry point for the GPLX Desktop Application.
Usage:
    python app_desktop.py
"""
import sys
import os

# Ensure src is on Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.logger import configure_logging

logger = configure_logging()

from src.gui.app import GPLXApp
from src.config import init_digitization_structure

def main():
    app = None
    try:
        # Tự động khởi tạo cấu trúc thư mục chuẩn: So Hoa GPLX/DuLieuSoHoa_GPLS/[Tỉnh]/HOP/HoSo
        logger.info("Initializing application data folders")
        init_digitization_structure()

        app = GPLXApp()
        app.run()
        logger.info("Application closed normally")
    except Exception as exc:
        logger.critical("Application startup or event loop failed", exc_info=True)
        try:
            from tkinter import messagebox
            messagebox.showerror(
                "Lỗi ứng dụng",
                "Ứng dụng gặp lỗi nghiêm trọng và cần đóng. "
                "Thông tin chi tiết đã được ghi vào file log.\n\n%s" % exc,
            )
        except Exception:
            logger.exception("Could not display the application error dialog")
        finally:
            if app is not None:
                try:
                    app.destroy()
                except Exception:
                    logger.exception("Could not close the application after a fatal error")

if __name__ == "__main__":
    main()
