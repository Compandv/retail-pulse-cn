@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_daily.ps1" %*
set "update_exit=%errorlevel%"
echo.
echo Update finished. Logs are saved in work\logs.
if /i "%~1"=="-SkipOpen" goto done
pause
:done
exit /b %update_exit%
