@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 请先按 README 安装本地运行环境。
  pause
  exit /b 1
)
if not exist ".local\remote-sync.txt" (
  echo 请先创建 .local\remote-sync.txt，写入以下三行：
  echo url=http://你的网站地址:端口
  echo token=服务器上的同步令牌
  echo watch=全部流水表^(1^).xlsx
  pause
  exit /b 1
)
echo 正在监测本地 Excel 并推送到远程网站。请保持此窗口运行。
echo 按 Ctrl+C 停止。
".venv\Scripts\python.exe" remote_sync.py --config ".local\remote-sync.txt"
pause
