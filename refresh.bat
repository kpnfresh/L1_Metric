@echo off
title KPN Fresh Dashboard — Daily Refresh
color 0A

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   KPN Fresh Dashboard — Daily Refresh   ║
echo  ╚══════════════════════════════════════════╝
echo.

:: ── CONFIG: update these paths if needed ──────────────────────────────────
set DB=D:\Reports\sales.duckdb
set SCRIPT=%~dp0build_dashboard.py
set OUT=%~dp0index.html

:: ──────────────────────────────────────────────────────────────────────────

echo  Source DB : %DB%
echo  Script    : %SCRIPT%
echo  Output    : %OUT%
echo.

:: Check DB exists
if not exist "%DB%" (
    echo  ❌  ERROR: sales.duckdb not found at %DB%
    echo      Please update the DB= path in this .bat file.
    pause
    exit /b 1
)

:: Run the pipeline
echo  ⏳  Building dashboard...
echo.
python "%SCRIPT%" --db "%DB%" --out "%OUT%"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  ❌  Build failed. Check error above.
    pause
    exit /b 1
)

echo.
echo  ✅  Dashboard rebuilt successfully!
echo.
echo  Next steps:
echo    1. Open index.html in your browser to verify
echo    2. Push index.html + *.parquet to GitHub for GitHub Pages
echo.

:: Ask to open in browser
set /p OPEN="  Open index.html in browser now? (Y/N): "
if /i "%OPEN%"=="Y" (
    start "" "%OUT%"
)

echo.
pause
