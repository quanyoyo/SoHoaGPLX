"""
LAN Server module for Multi-PC Driving License Dossier Lookup.
Provides FastAPI REST API, PDF/Excel streaming, and Web Client for local network.
"""
import os
import io
import socket
import threading
import time
from typing import Optional, Dict, Any, List

import uvicorn
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
import qrcode

from src.database import DatabaseManager
from src.config import PROVINCE_CODES, get_resource_path
from src.logger import get_logger

logger = get_logger(__name__)

def get_lan_ip() -> str:
    """
    Detects the primary LAN IP address of this machine.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Dummy connect to determine outgoing interface
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = '127.0.0.1'
    finally:
        s.close()
    return ip

# Initialize FastAPI application
app = FastAPI(
    title="Hệ Thống Tra Cứu GPLX Mạng LAN",
    description="Máy chủ tra cứu hồ sơ GPLX nội bộ dùng cho mạng LAN văn phòng",
    version="1.0.0"
)

# Enable CORS for cross-origin LAN clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Opened on first use (server start or first request), not when this module is imported.
db_manager: Optional[DatabaseManager] = None
_db_lock = threading.Lock()


def get_db() -> DatabaseManager:
    global db_manager
    with _db_lock:
        if db_manager is None:
            db_manager = DatabaseManager()
        return db_manager

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
INDEX_HTML_PATH = get_resource_path(os.path.join("src", "server", "static", "index.html"))
if not os.path.exists(INDEX_HTML_PATH):
    INDEX_HTML_PATH = os.path.join(STATIC_DIR, "index.html")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serves the standalone Web Client for LAN users."""
    if os.path.exists(INDEX_HTML_PATH):
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Hệ thống Tra cứu GPLX - Mạng LAN</h1><p>Đang khởi tạo giao diện web...</p>"

@app.get("/api/status")
async def get_status():
    """Returns server status, LAN IP, and database statistics."""
    stats = get_db().get_stats()
    ip = get_lan_ip()
    return {
        "status": "online",
        "ip": ip,
        "port": getattr(app.state, "port", 8080),
        "url": f"http://{ip}:{getattr(app.state, 'port', 8080)}",
        "stats": stats,
        "message": "Máy chủ mạng LAN đang hoạt động ổn định"
    }

@app.get("/api/provinces")
async def get_provinces():
    """Returns list of provinces present in the system."""
    code_to_name = {p["code"]: p["name"] for p in PROVINCE_CODES if "code" in p}
    provinces_list = []
    # Query distinct province codes from dossiers
    with get_db().get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT province_code FROM dossiers ORDER BY province_code ASC")
        rows = cursor.fetchall()
        for r in rows:
            code = str(r[0])
            name = code_to_name.get(code, f"Tỉnh {code}")
            provinces_list.append({"code": code, "name": name})
    
    # If empty, provide default from configuration
    if not provinces_list:
        for p in PROVINCE_CODES[:15]:
            provinces_list.append({"code": p.get("code", "01"), "name": p.get("name", "Hà Nội")})

    return {"provinces": provinces_list}

@app.get("/api/search")
async def search_citizens(
    q: str = Query("", description="Từ khóa tìm kiếm (Họ tên, Số bằng, Năm sinh)"),
    province: str = Query("all", description="Mã tỉnh hoặc 'all'"),
    limit: int = Query(50, ge=1, le=200, description="Số lượng kết quả tối đa")
):
    """Searches citizens (substring match on the SQLite index)."""
    start_time = time.time()
    db = get_db()
    results = db.search(query=q, province_code=province, limit=limit)
    total_matches = db.count_search(q, province_code=province)
    # Files are fetched by dossier id; the server's own paths are not sent to clients.
    results = [
        {**{k: v for k, v in row.items() if k not in ("pdf_path", "excel_path")}, "has_excel": bool(row.get("excel_path"))}
        for row in results
    ]
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "query": q,
        "province": province,
        "total": len(results),
        "total_matches": total_matches,
        "latency_ms": elapsed_ms,
        "results": results
    }

def _dossier_file(dossier_id: int, kind: str) -> str:
    """Only files of dossiers recorded in the database are served, never an arbitrary path."""
    files = get_db().get_dossier_files(dossier_id)
    path = files and files[f"{kind}_path"]
    if not path or not os.path.isfile(path) or not path.lower().endswith(f".{'pdf' if kind == 'pdf' else 'xlsx'}"):
        detail = "Không tìm thấy tệp PDF của hồ sơ." if kind == "pdf" else "Hồ sơ chưa có tệp Excel."
        raise HTTPException(status_code=404, detail=detail)
    return path


@app.get("/api/pdf/{dossier_id}")
async def stream_pdf(dossier_id: int):
    """Streams a dossier's PDF for viewing in the browser (page jumps use #page=N)."""
    path = _dossier_file(dossier_id, "pdf")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=os.path.basename(path),
        content_disposition_type="inline",
        headers={"Accept-Ranges": "bytes"},
    )


@app.get("/api/excel/{dossier_id}")
async def download_excel(dossier_id: int):
    """Serves a dossier's companion Excel file for download."""
    path = _dossier_file(dossier_id, "excel")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=os.path.basename(path),
    )

@app.get("/api/qr")
async def get_qr_code(url: Optional[str] = None):
    """
    Generates and returns a PNG QR code pointing to the LAN access URL.
    """
    port = getattr(app.state, "port", 8080)
    target_url = url or f"http://{get_lan_ip()}:{port}"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1E293B", back_color="#FFFFFF")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    return Response(content=buf.getvalue(), media_type="image/png")


START_TIMEOUT_SECONDS = 10


class LANServerManager:
    """
    Manages the lifecycle of the LAN FastAPI server in a background thread.
    Allows easy start/stop directly from the Tkinter GUI.
    """
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.server: Optional[uvicorn.Server] = None
        self.thread: Optional[threading.Thread] = None
        self.is_running = False

    def start(self, port: Optional[int] = None) -> str:
        """Starts the server in background thread if not already running."""
        if self.is_running:
            return self.get_url()

        if port is not None:
            if not 1 <= port <= 65535:
                raise ValueError(f"Cổng {port} không hợp lệ. Cổng phải là số từ 1 đến 65535 (mặc định 8080).")
            self.port = port

        logger.info("Starting LAN server on %s:%s", self.host, self.port)
        get_db()
        app.state.port = self.port
        app.state.host = self.host

        config = uvicorn.Config(
            app=app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
            # Windowed PyInstaller builds have sys.stdout/sys.stderr=None;
            # Uvicorn's default formatter calls sys.stdout.isatty().
            log_config=None,
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        # Report running only once the port is open: a busy port ends the thread instead.
        deadline = time.monotonic() + START_TIMEOUT_SECONDS
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not server.started:
            server.should_exit = True
            thread.join(timeout=2.0)
            logger.error("LAN server could not open port %s", self.port)
            raise RuntimeError(
                f"Không mở được cổng {self.port}. Cổng này có thể đang được chương trình khác "
                "(hoặc một cửa sổ phần mềm khác) dùng. Hãy chọn cổng khác rồi bật lại."
            )
        self.server, self.thread, self.is_running = server, thread, True
        logger.info("LAN server started; access URL: %s", self.get_url())
        return self.get_url()

    def stop(self):
        """Stops the running server."""
        if self.server and self.is_running:
            logger.info("Stopping LAN server on port %s", self.port)
            self.server.should_exit = True
            self.is_running = False
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=2.0)
            self.server = None
            self.thread = None
            logger.info("LAN server stopped")

    def get_lan_ip(self) -> str:
        return get_lan_ip()

    def get_url(self) -> str:
        return f"http://{self.get_lan_ip()}:{self.port}"


# Global server manager singleton
lan_server = LANServerManager()
