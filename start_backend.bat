@echo off
echo ========================================
echo   DB-GPT Full Stack Startup
echo ========================================
echo.

cd /d %~dp0

echo Step 1: Activating conda environment (ops)...
call conda activate ops

echo.
echo Step 2: Starting frontend dev server (port 3001)...
start "Frontend Dev Server" cmd /k "cd /d %~dp0webui-react && npm run dev"

echo.
echo Step 3: Starting API server on port 7861...
echo   Backend API: http://127.0.0.1:7861
echo   Frontend:    http://127.0.0.1:3001
echo.

python -m uvicorn server.api:create_app --host 127.0.0.1 --port 7861 --app-dir . --factory

pause
