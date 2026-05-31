# Hermes Residential Proxy Tunnel
# Roda um SOCKS5 proxy local e cria túnel reverso para a VM
# Uso: .\proxy-tunnel.ps1 [start|stop|status]

param([string]$Action = "start")

$ProxyPort = 1080
$VMUser = "hermes-gcp"
$VMHost = "136.115.74.69"

function Start-Tunnel {
    Write-Host "=== Hermes Residential Proxy ===" -ForegroundColor Cyan

    # Check if already running
    $existing = Get-Process -Name "pproxy" -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "[!] Proxy already running (PID: $($existing.Id))" -ForegroundColor Yellow
        return
    }

    # Start SOCKS5 proxy in background
    Write-Host "[1/3] Starting SOCKS5 proxy on localhost:$ProxyPort..." -ForegroundColor Green
    $proxyJob = Start-Process -FilePath "pproxy" -ArgumentList "-l socks5://127.0.0.1:$ProxyPort -v" -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2

    if ($proxyJob.HasExited) {
        Write-Host "[X] Proxy failed to start. Port $ProxyPort in use?" -ForegroundColor Red
        return
    }
    Write-Host "    Proxy running (PID: $($proxyJob.Id))" -ForegroundColor Gray

    # Open reverse SSH tunnel
    Write-Host "[2/3] Opening reverse tunnel to VM ($VMHost)..." -ForegroundColor Green
    $sshJob = Start-Process -FilePath "ssh" -ArgumentList "-o StrictHostKeyChecking=no -R 127.0.0.1:${ProxyPort}:127.0.0.1:${ProxyPort} -N ${VMUser}@${VMHost}" -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 3

    if ($sshJob.HasExited) {
        Write-Host "[X] SSH tunnel failed. Check SSH key." -ForegroundColor Red
        Stop-Process -Id $proxyJob.Id -Force -ErrorAction SilentlyContinue
        return
    }
    Write-Host "    Tunnel open (PID: $($sshJob.Id))" -ForegroundColor Gray

    # Save PIDs
    @{proxy=$proxyJob.Id; ssh=$sshJob.Id} | ConvertTo-Json | Out-File "$env:TEMP\hermes-proxy.json" -Encoding utf8

    Write-Host "[3/3] Testing..." -ForegroundColor Green
    Write-Host ""
    Write-Host "  VM scraper proxy: socks5://localhost:$ProxyPort" -ForegroundColor White
    Write-Host "  Exit IP: seu IP residencial (179.245.x.x)" -ForegroundColor White
    Write-Host ""
    Write-Host "Tunnel ativo. Feche este terminal ou rode .\proxy-tunnel.ps1 stop para parar." -ForegroundColor Cyan
}

function Stop-Tunnel {
    Write-Host "Stopping Hermes proxy..." -ForegroundColor Yellow

    if (Test-Path "$env:TEMP\hermes-proxy.json") {
        $pids = Get-Content "$env:TEMP\hermes-proxy.json" | ConvertFrom-Json
        Stop-Process -Id $pids.proxy -Force -ErrorAction SilentlyContinue
        Stop-Process -Id $pids.ssh -Force -ErrorAction SilentlyContinue
        Remove-Item "$env:TEMP\hermes-proxy.json" -Force
        Write-Host "Stopped." -ForegroundColor Green
    } else {
        # Fallback: kill by name
        Get-Process -Name "pproxy" -ErrorAction SilentlyContinue | Stop-Process -Force
        Write-Host "Cleaned up." -ForegroundColor Green
    }
}

function Get-TunnelStatus {
    $proxy = Get-Process -Name "pproxy" -ErrorAction SilentlyContinue
    $pidFile = "$env:TEMP\hermes-proxy.json"

    if ($proxy) {
        Write-Host "Proxy: RUNNING (PID: $($proxy.Id))" -ForegroundColor Green
        if (Test-Path $pidFile) {
            $pids = Get-Content $pidFile | ConvertFrom-Json
            $sshProc = Get-Process -Id $pids.ssh -ErrorAction SilentlyContinue
            if ($sshProc) {
                Write-Host "Tunnel: RUNNING (PID: $($pids.ssh))" -ForegroundColor Green
            } else {
                Write-Host "Tunnel: DOWN" -ForegroundColor Red
            }
        }
    } else {
        Write-Host "Proxy: NOT RUNNING" -ForegroundColor Red
    }
}

switch ($Action.ToLower()) {
    "start"  { Start-Tunnel }
    "stop"   { Stop-Tunnel }
    "status" { Get-TunnelStatus }
    default  { Write-Host "Usage: .\proxy-tunnel.ps1 [start|stop|status]" }
}
