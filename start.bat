@echo off
echo.
echo  ☁️  Cloud Cost Panic Button
echo  Starting server at http://localhost:8000
echo.
cd /d "%~dp0"
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
