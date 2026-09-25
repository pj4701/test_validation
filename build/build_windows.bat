@echo off
setlocal
cd /d "%~dp0.."

echo ============================================
echo Data Validation Hub - Windows Build
echo ============================================

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    py -3 -m venv .venv
    if errorlevel 1 goto :error
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r build\requirements-build.txt

if exist dist rmdir /s /q dist
if exist build\pyinstaller rmdir /s /q build\pyinstaller

pyinstaller --noconfirm --clean build\DataValidationHub.spec

if errorlevel 1 goto :error

echo.
echo BUILD COMPLETE
 echo EXE: dist\DataValidationHub\DataValidationHub.exe
pause
exit /b 0

:error
echo.
echo BUILD FAILED
pause
exit /b 1
