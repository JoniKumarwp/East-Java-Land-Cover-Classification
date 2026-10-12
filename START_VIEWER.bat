@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Extract this update into the project folder containing .venv and uts.
  pause
  exit /b 1
)
echo Starting matched map viewer at http://localhost:8502
".venv\Scripts\python.exe" -m streamlit run "%~dp0uts\deploy\app.py" --server.port 8502
pause
