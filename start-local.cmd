@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Create a Python 3.12 virtual environment and install requirements-dev.txt first.
  exit /b 1
)
.venv\Scripts\python.exe -m screening.local --showcase
