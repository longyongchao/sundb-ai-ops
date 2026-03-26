@echo off
echo ========================================
echo   DB-GPT Backend Server Startup
echo ========================================
echo.

cd /d %~dp0

echo Step 1: Activating virtual environment...
call venv_dbgpt\Scripts\activate.bat

echo.
echo Step 2: Installing missing dependencies...
pip install strsimpy -q
pip install levenshtein -q
pip install rapidfuzz -q

echo.
echo Step 3: Starting API server on port 7861...
echo.

python -m uvicorn server.api:create_app --host 127.0.0.1 --port 7861 --app-dir . --factory

pause