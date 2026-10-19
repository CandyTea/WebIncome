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
echo 本地地址：http://127.0.0.1:8765
echo 管理密码：%WEBINCOME_ADMIN_PASSWORD%
echo 正在监测：全部流水表(1).xlsx
echo 修改并保存 Excel 后，网页会自动更新。请保持此窗口运行。
".venv\Scripts\python.exe" app.py --port 8765 --watch "%~dp0全部流水表(1).xlsx"
pause
