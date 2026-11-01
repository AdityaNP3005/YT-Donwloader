@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Python aplikasi belum tersedia di folder .venv.
    echo Lihat petunjuk instalasi di README.md.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" app.py
if errorlevel 1 (
    echo.
    echo Aplikasi gagal dibuka. Salin pesan kesalahan di atas untuk pemeriksaan.
    pause
    exit /b 1
)
