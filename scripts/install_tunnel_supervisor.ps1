# Hermes Tunnel Supervisor — installer Windows Task Scheduler
# Cria task que roda no logon do usuario, com restart automatico se cair.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)
$Bat = Join-Path $Root "scripts\tunnel_supervisor.bat"
$TaskName = "HermesTunnelSupervisor"

if (-not (Test-Path $Bat)) {
    Write-Error "tunnel_supervisor.bat nao encontrado em $Bat"
    exit 1
}

Write-Host "Removendo task antiga (se existir)..."
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# -WindowStyle Hidden adicional pra garantir zero janela visivel
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c start `"`" /B `"$Bat`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Mantem SOCKS5 :55081 + SSH reverse tunnel pra VM Hermes always-on."

Write-Host "OK. Task '$TaskName' instalada. Iniciando agora..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 5
Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State, LastRunTime
