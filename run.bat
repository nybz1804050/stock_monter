@echo off
rem 一键启动浏览器行情看板（默认 127.0.0.1:8000）
cd /d %~dp0
python app.py --open
pause
