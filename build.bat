@echo off
echo ==========================================
echo Tachyon Deduper - Build Script
echo ==========================================

echo [1/3] Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo [2/3] Building executable...
pyinstaller --noconsole --onefile --name "TachyonDeduper" main.py

echo [3/3] Build complete!
echo Executable is located in the 'dist' folder.
pause
