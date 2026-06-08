@echo off
REM Hermes Tunnel Supervisor — Windows wrapper.
REM Mantem socks5 + ssh reverse tunnel sempre UP.
REM Adicione ao Task Scheduler: "At log on" -> rodar este .bat
REM Detalhes: SCHTASKS /Create /TN "HermesTunnelSupervisor" /TR "%~dpnx0" /SC ONLOGON /RL HIGHEST

setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"

REM Garante python no PATH
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERR] python nao encontrado no PATH
    exit /b 1
)

REM Rodar em background (start /min)
start "HermesTunnelSupervisor" /MIN python "%ROOT%\scripts\tunnel_supervisor.py"
endlocal
