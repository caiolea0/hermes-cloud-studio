@echo off
REM Hermes LinkedIn li_at sync — scheduled task wrapper
REM Runs the Python sync script. Logs to data/li_at_sync.log.

cd /d "D:\dev-projects\main\hermes-cloud-studio"
python scripts\li_at_sync.py >> "%USERPROFILE%\.hermes\data\li_at_sync.log" 2>&1
exit /b %ERRORLEVEL%
