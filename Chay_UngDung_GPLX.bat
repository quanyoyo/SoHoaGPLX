@echo off
chcp 65001 >nul
title HỆ THỐNG SỐ HÓA, ĐỔI TÊN & TRA CỨU HỒ SƠ GPLX
color 0B

echo =======================================================================
echo          HỆ THỐNG SỐ HÓA, ĐỔI TÊN & TRA CỨU HỒ SƠ GIẤY PHÉP LÁI XE
echo                     (DÀNH CHO Ổ CỨNG DI ĐỘNG SSD / USB)
echo =======================================================================
echo.
echo [*] Đang kiểm tra môi trường và khởi chạy ứng dụng...

cd /d "%~dp0"

REM Ưu tiên môi trường ảo của dự án (.venv)
set "PY=%~dp0.venv\Scripts\python.exe"
if exist "%PY%" goto run_app
set "PY=python"
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] KHÔNG TÌM THẤY PYTHON TRÊN MÁY TÍNH NÀY!
    echo     Vui lòng đảm bảo Python 3.10+ đã được cài đặt hoặc copy thư mục Python_Portable.
    pause
    exit /b 1
)

:run_app
REM Khởi chạy ứng dụng Desktop
start "" "%PY%" app_desktop.py

echo [*] Ứng dụng đã được khởi chạy thành công!
timeout /t 3 >nul
exit /b 0
