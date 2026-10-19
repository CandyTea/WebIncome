@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 请先按 README 安装本地运行环境。
  pause
  exit /b 1
)
if not exist ".local" mkdir ".local"
if not exist ".local\preview-password.txt" ".venv\Scripts\python.exe" -c "from pathlib import Path; import secrets; Path('.local/preview-password.txt').write_text(secrets.token_hex(16), encoding='ascii')"
set /p WEBINCOME_ADMIN_PASSWORD=<".local\preview-password.txt"
set WEBINCOME_PUBLIC_VIEW=1
set PYTHONIOENCODING=utf-8
echo 本地地址：http://127.0.0.1:8765
echo 管理密码：%WEBINCOME_ADMIN_PASSWORD%
echo 监测同步助手中保存的 Excel；未设置时使用默认流水表。
echo 修改并保存 Excel 后，网页会自动更新。请保持此窗口运行。
".venv\Scripts\python.exe" desktop_sync.py --mode local --console
pause
