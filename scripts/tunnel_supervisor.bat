@echo off
REM Hermes Tunnel Supervisor — Windows wrapper INVISIVEL (pythonw.exe sem console).
REM Mantem socks5 + ssh reverse tunnel sempre UP.

setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"

REM Procura pythonw.exe (Python sem console) — preferencial
set "PYW="
for %%P in (pythonw.exe) do set "PYW=%%~$PATH:P"

REM Fallback: scan Python313/312/311 instalados
if not defined PYW (
    for %%V in (313 312 311 310) do (
        if exist "C:\Python%%V\pythonw.exe" set "PYW=C:\Python%%V\pythonw.exe"
    )
)

if not defined PYW (
    echo [ERR] pythonw.exe nao encontrado. Instale Python ou ajuste PATH.
    exit /b 1
)

REM Usa start sem janela visivel. pythonw nao cria console.
start "" "%PYW%" "%ROOT%\scripts\tunnel_supervisor.py"
endlocal
