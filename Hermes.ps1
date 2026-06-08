# Hermes Dev Launcher - Smart Build & Run
# Only rebuilds when Rust source changed. Instant launch otherwise.
# Frontend always live from disk (server.py serves dashboard/ directly).

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$appDir = Join-Path $root "app"
$tauriDir = Join-Path $appDir "src-tauri"
$exe = Join-Path $tauriDir "target\release\hermes.exe"

# Kill any existing instance first (clean slate)
$existing = Get-Process -Name "hermes" -ErrorAction SilentlyContinue
if ($existing) {
    $existing | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 600
}

# Detect Rust source changes vs exe timestamp
$needRebuild = $true
if (Test-Path $exe) {
    $exeTime = (Get-Item $exe).LastWriteTime

    $newestRS = Get-ChildItem -Path (Join-Path $tauriDir "src") -Recurse -Include "*.rs" -File |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1

    $cargoToml = Join-Path $tauriDir "Cargo.toml"
    $tauriConf = Join-Path $tauriDir "tauri.conf.json"

    $cargoTime = [datetime]::MinValue
    if (Test-Path $cargoToml) { $cargoTime = (Get-Item $cargoToml).LastWriteTime }

    $confTime = [datetime]::MinValue
    if (Test-Path $tauriConf) { $confTime = (Get-Item $tauriConf).LastWriteTime }

    $rustChanged = $false
    if ($newestRS -and ($newestRS.LastWriteTime -gt $exeTime)) { $rustChanged = $true }
    if ($cargoTime -gt $exeTime) { $rustChanged = $true }
    if ($confTime -gt $exeTime) { $rustChanged = $true }

    if (-not $rustChanged) { $needRebuild = $false }
}

# Build only when needed
if ($needRebuild) {
    Set-Location $appDir
    cargo build --release --manifest-path src-tauri\Cargo.toml
    if ($LASTEXITCODE -ne 0) {
        [System.Windows.Forms.MessageBox]::Show("Hermes build failed. Check logs.", "Hermes Launcher") | Out-Null
        exit 1
    }
}

# Verify exe exists
if (-not (Test-Path $exe)) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show("hermes.exe not found at:`n$exe`n`nRun cargo build inside app/ first.", "Hermes Launcher") | Out-Null
    exit 1
}

# Launch
Start-Process -FilePath $exe
