@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  ============================================
echo   助老机器人 - 方言语音交流演示
echo   正在启动本地服务 http://localhost:8001
echo   浏览器会自动打开，请稍候...
echo   (关闭本窗口即停止服务)
echo  ============================================
echo.
start "" cmd /c "timeout /t 2 >nul & start http://localhost:8001/"
py server.py
pause
