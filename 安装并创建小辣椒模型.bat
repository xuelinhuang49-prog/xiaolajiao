@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   小辣椒 Ollama 本地模型安装与创建
echo ============================================
echo.
where ollama >nul 2>nul
if errorlevel 1 (
  echo 未找到 ollama 命令。请先安装 Ollama，并重新打开此窗口。
  pause
  exit /b 1
)
echo [1/3] 检查 Ollama 服务...
ollama list >nul 2>nul
if errorlevel 1 (
  echo Ollama 似乎尚未启动。请先启动 Ollama 应用，再重新运行本脚本。
  pause
  exit /b 1
)
echo [2/3] 下载基础模型 qwen3:4b（如果已经有，会复用）...
ollama pull qwen3:4b
if errorlevel 1 (
  echo 基础模型下载失败。请检查网络后重试，或把脚本中的 qwen3:4b 换成你已安装且支持中文的模型。
  pause
  exit /b 1
)
echo [3/3] 创建角色模型 xiaolajiao...
ollama create xiaolajiao -f "小辣椒\Modelfile.txt"
if errorlevel 1 (
  echo 创建失败，请确认“小辣椒\Modelfile.txt”存在。
  pause
  exit /b 1
)
echo.
echo 创建完成！运行“启动演示.bat”，然后打开 http://localhost:8000
pause
