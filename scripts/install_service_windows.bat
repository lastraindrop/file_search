@echo off
REM FileCortex Windows 服务安装（NSSM）
REM 前置: 已 pip install file-cortex；nssm.exe 在 PATH 中
REM 用法: 以管理员身份运行 scripts\install_service_windows.bat <FCTX_API_TOKEN>

setlocal
if "%~1"=="" (
  echo 用法: install_service_windows.bat ^<FCTX_API_TOKEN^>
  exit /b 1
)

set TOKEN=%~1
set FCTX_EXE=%~dp0..\..\Scripts\fctx-web.exe

if not exist "%FCTX_EXE%" (
  echo 未找到 %FCTX_EXE%，请确认已安装 file-cortex 并调整路径。
  exit /b 1
)

nssm install FileCortex "%FCTX_EXE%" "--host 127.0.0.1 --port 8000"
nssm set FileCortex AppEnvironmentExtra FCTX_API_TOKEN=%TOKEN%
nssm set FileCortex AppStdout %ProgramData%\FileCortex\logs\out.log
nssm set FileCortex AppStderr %ProgramData%\FileCortex\logs\err.log
nssm set FileCortex AppDirectory %ProgramData%\FileCortex
nssm start FileCortex

echo FileCortex 服务已启动: http://127.0.0.1:8000
endlocal
