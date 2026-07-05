@echo off
title Shweta Wake Word Setup
color 0B
echo Starting Wake Word Setup Tool...
cd /d "%~dp0"
call venv\Scripts\activate.bat
python wakeword_setup.py
pause
