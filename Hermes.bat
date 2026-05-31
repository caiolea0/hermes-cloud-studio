@echo off
set SCRIPT_DIR=%~dp0
if exist "%SCRIPT_DIR%app\src-tauri\target\release\hermes.exe" (
    start "" "%SCRIPT_DIR%app\src-tauri\target\release\hermes.exe"
) else if exist "%SCRIPT_DIR%app\src-tauri\target\debug\hermes.exe" (
    start "" "%SCRIPT_DIR%app\src-tauri\target\debug\hermes.exe"
) else (
    echo [Hermes] .exe nao encontrado.
    echo.
    echo Para compilar:
    echo   cd app
    echo   npm run tauri build
    echo.
    pause
)
