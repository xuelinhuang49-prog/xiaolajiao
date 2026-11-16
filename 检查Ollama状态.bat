@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 检查 Ollama 已安装模型：
echo.
ollama list
if errorlevel 1 (
  echo.
  echo Ollama 未启动或命令不可用，请先打开 Ollama。
  pause
  exit /b 1
)
echo.
echo 检查小辣椒模型：
ollama show xiaolajiao
if errorlevel 1 echo 未找到 xiaolajiao。请运行“安装并创建小辣椒模型.bat”。
echo.
pause
