@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PY=py -3"
) else (
    set "PY=python"
)
echo Checking Python installation...
%PY% --version || goto :error
%PY% -m venv .buildvenv || goto :error
call ".buildvenv\Scripts\python.exe" -m pip install --upgrade pip || goto :error
call ".buildvenv\Scripts\python.exe" -m pip install pyinstaller pyserial matplotlib PyQt6 || goto :error
call ".buildvenv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name "2B_106MH_OzoneMonitor" --hidden-import matplotlib.backends.backend_qtagg --exclude-module tkinter --exclude-module PyQt5 --exclude-module PySide6 "2B_106MH_Reader.py" || goto :error
echo.
echo BUILD SUCCESSFUL.
echo Copy dist\2B_106MH_OzoneMonitor.exe to the target Windows PC.
echo The receiving computer does NOT need Python installed.
echo.
pause
exit /b 0
:error
echo.
echo Build failed. Read the messages above for details.
pause
exit /b 1
