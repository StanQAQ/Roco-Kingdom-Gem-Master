@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if exist "%LocalAppData%\Programs\Python\Launcher\py.exe" set "PATH=%LocalAppData%\Programs\Python\Launcher;%PATH%"

where py >nul 2>nul
if errorlevel 1 (
    echo Python Launcher not found. Install 64-bit Python 3.12 from python.org and enable the launcher.
    pause
    exit /b 1
)

py -3.12 --version >nul 2>nul
if errorlevel 1 (
    echo Python 3.12 x64 is required to build the Windows executable.
    pause
    exit /b 1
)

echo Installing build dependencies...
py -3.12 -m pip install --upgrade pip
if errorlevel 1 goto :failed
py -3.12 -m pip install "PySide6>=6.8" PyInstaller
if errorlevel 1 goto :failed

echo Building standalone GUI executable...
py -3.12 -m PyInstaller --noconfirm --clean --onefile --windowed --name "Roco Kingdom Gem Master" --distpath dist --workpath build --specpath build --add-data "..\media:media" run_game.py
if errorlevel 1 goto :failed

if not exist "dist\Roco Kingdom Gem Master.exe" goto :failed
echo.
echo Build complete: %CD%\dist\Roco Kingdom Gem Master.exe
pause
exit /b 0

:failed
echo.
echo Build failed. Review the error above, then try again.
pause
exit /b 1
