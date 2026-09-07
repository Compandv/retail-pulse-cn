@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\analyze_comments.ps1" %*
exit /b %errorlevel%
