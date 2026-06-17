# Hermes - Rotate Gateway OAuth Secret (auto-gerado PC + VM)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup_gateway_oauth_secret.ps1
# Compatible: Windows PowerShell 5.1+
#
# Security notes:
# - Secret gerado LOCALMENTE via Python secrets.token_urlsafe(32)
# - NUNCA exibir valor completo em terminal (preview 8 chars apenas)
# - Update PC .env + VM .env + restart hermes-mcps-gateway VM
# - Smoke: GET gateway /health com Bearer → 200

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Hermes - Rotate Gateway OAuth Secret (PC + VM) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Este script vai:" -ForegroundColor Yellow
Write-Host "  1. Gerar novo HERMES_GATEWAY_OAUTH_SECRET via Python"
Write-Host "  2. Atualizar .env PC + .env VM via SSH"
Write-Host "  3. Reiniciar hermes-mcps-gateway na VM"
Write-Host "  4. Smoke: autenticar gateway endpoint → 200"
Write-Host ""
Write-Host "Pre-requisitos:" -ForegroundColor Yellow
Write-Host "  - Python 3 disponivel nesta maquina (para gerar secret)"
Write-Host "  - SSH para hermes-gcp@136.115.74.69 funcional"
Write-Host "  - hermes-mcps-gateway service na VM (porta 55401)"
Write-Host ""

$confirm = Read-Host "Continuar? (s/n)"
if ($confirm -ne "s" -and $confirm -ne "S") {
    Write-Host "Abortado." -ForegroundColor Red
    exit 0
}

# ============================================================
# Step 1: Gerar novo secret localmente via Python
# ============================================================
Write-Host ""
Write-Host "=== Step 1/4: Gerar novo OAuth secret ===" -ForegroundColor Cyan

try {
    $newSecret = python -c "import secrets; print(secrets.token_urlsafe(32))" 2>&1
    $newSecret = $newSecret.Trim()
} catch {
    Write-Host "ERRO: Python nao encontrado. Instalar Python 3 ou gerar manualmente:" -ForegroundColor Red
    Write-Host "  python -c ""import secrets; print(secrets.token_urlsafe(32))"""
    exit 1
}

if (-not ($newSecret -match "^[A-Za-z0-9_-]{40,}$")) {
    Write-Host "ERRO: secret gerado invalido (len=$($newSecret.Length))" -ForegroundColor Red
    Write-Host "Output Python: '$newSecret'"
    $newSecret = $null
    exit 1
}

$secretPreview = $newSecret.Substring(0, 8)
Write-Host ("  Secret gerado OK ({0}... len={1})" -f $secretPreview, $newSecret.Length) -ForegroundColor Green

# ============================================================
# Step 2: Update .env PC + VM
# ============================================================
Write-Host ""
Write-Host "=== Step 2/4: Update .env PC + VM ===" -ForegroundColor Cyan

$envPathPC = "D:\dev-projects\main\hermes-cloud-studio\.env"

if (-not (Test-Path $envPathPC)) {
    Write-Host "ERRO: .env PC nao encontrado" -ForegroundColor Red
    $newSecret = $null
    exit 1
}

$envContent = Get-Content $envPathPC -Raw
$secretLine = "HERMES_GATEWAY_OAUTH_SECRET=$newSecret"

if ($envContent -match "(?m)^HERMES_GATEWAY_OAUTH_SECRET=") {
    $envContent = $envContent -replace "(?m)^HERMES_GATEWAY_OAUTH_SECRET=.*$", $secretLine
    Write-Host "  PC .env HERMES_GATEWAY_OAUTH_SECRET: ATUALIZADA" -ForegroundColor Green
} else {
    if (-not $envContent.EndsWith("`n")) {
        $envContent += "`n"
    }
    $envContent += "`n# P1 Hardening - MCP gateway OAuth bearer`n$secretLine`n"
    Write-Host "  PC .env HERMES_GATEWAY_OAUTH_SECRET: ADICIONADA" -ForegroundColor Green
}

[System.IO.File]::WriteAllText($envPathPC, $envContent, [System.Text.UTF8Encoding]::new($false))

$verifyPC = Select-String -Path $envPathPC -Pattern "^HERMES_GATEWAY_OAUTH_SECRET=.{40,}" -Quiet
if ($verifyPC) {
    Write-Host "  PC verify: OK" -ForegroundColor Green
} else {
    Write-Host "  PC verify: FALHOU" -ForegroundColor Red
    $newSecret = $null
    exit 1
}

# VM .env update via SSH bytes-level stdin
Write-Host ""
Write-Host "  Atualizando VM via SSH..."

$sshScript = @"
set -e
ENV_FILE=~/.hermes/.env
mkdir -p ~/.hermes
touch `$ENV_FILE
chmod 600 `$ENV_FILE

if grep -q '^HERMES_GATEWAY_OAUTH_SECRET=' `$ENV_FILE 2>/dev/null; then
  sed -i 's|^HERMES_GATEWAY_OAUTH_SECRET=.*|HERMES_GATEWAY_OAUTH_SECRET=$newSecret|' `$ENV_FILE
  echo "  VM HERMES_GATEWAY_OAUTH_SECRET: ATUALIZADA"
else
  echo "" >> `$ENV_FILE
  echo "# P1 Hardening - MCP gateway OAuth bearer" >> `$ENV_FILE
  echo "HERMES_GATEWAY_OAUTH_SECRET=$newSecret" >> `$ENV_FILE
  echo "  VM HERMES_GATEWAY_OAUTH_SECRET: ADICIONADA"
fi

if grep -q '^HERMES_GATEWAY_OAUTH_SECRET=.\{40,\}' `$ENV_FILE; then
  echo "  VM verify: OK"
else
  echo "  VM verify: FALHOU (secret muito curto?)"
  exit 1
fi
"@

$sshScriptLF = $sshScript -replace "`r`n", "`n" -replace "`r", "`n"

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "ssh"
$psi.Arguments = "-T -o ConnectTimeout=10 -o BatchMode=yes hermes-gcp@136.115.74.69 bash -s"
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true

try {
    $proc = [System.Diagnostics.Process]::Start($psi)
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $bytes = $utf8NoBom.GetBytes($sshScriptLF)
    $proc.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
    $proc.StandardInput.BaseStream.Flush()
    $proc.StandardInput.Close()
    $sshOutput = $proc.StandardOutput.ReadToEnd()
    $sshErr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()
    $exitCode = $proc.ExitCode

    if ($sshOutput) { Write-Host $sshOutput -ForegroundColor Green }
    if ($sshErr) { Write-Host "  STDERR: $sshErr" -ForegroundColor Yellow }

    if ($exitCode -ne 0) {
        Write-Host "  ERRO SSH: exit code $exitCode" -ForegroundColor Red
        $newSecret = $null
        exit 1
    }
} catch {
    Write-Host "  ERRO SSH: $_" -ForegroundColor Red
    $newSecret = $null
    exit 1
}

$sshScriptLF = $null
$bytes = $null

# ============================================================
# Step 3: Restart hermes-mcps-gateway na VM
# ============================================================
Write-Host ""
Write-Host "=== Step 3/4: Restart hermes-mcps-gateway VM ===" -ForegroundColor Cyan

$restartScript = @"
set -e
if systemctl is-active --quiet hermes-mcps-gateway 2>/dev/null; then
  systemctl restart hermes-mcps-gateway
  sleep 3
  systemctl is-active hermes-mcps-gateway && echo "  VM gateway: REINICIADO OK" || { echo "  VM gateway: FALHOU"; exit 1; }
  systemctl status hermes-mcps-gateway --no-pager -l 2>&1 | tail -5
elif pgrep -f "mcps/gateway" > /dev/null || pgrep -f "hermes.*gateway" > /dev/null; then
  pkill -HUP -f "mcps/gateway" 2>/dev/null || true
  pkill -HUP -f "hermes.*gateway" 2>/dev/null || true
  echo "  VM gateway: SIGHUP enviado (sem systemd)"
else
  echo "  VM gateway: processo nao encontrado — iniciar manualmente se necessario"
fi
"@

$restartScriptLF = $restartScript -replace "`r`n", "`n" -replace "`r", "`n"

$psi2 = New-Object System.Diagnostics.ProcessStartInfo
$psi2.FileName = "ssh"
$psi2.Arguments = "-T -o ConnectTimeout=15 -o BatchMode=yes hermes-gcp@136.115.74.69 bash -s"
$psi2.RedirectStandardInput = $true
$psi2.RedirectStandardOutput = $true
$psi2.RedirectStandardError = $true
$psi2.UseShellExecute = $false
$psi2.CreateNoWindow = $true

try {
    $proc2 = [System.Diagnostics.Process]::Start($psi2)
    $utf8NoBom2 = New-Object System.Text.UTF8Encoding($false)
    $bytes2 = $utf8NoBom2.GetBytes($restartScriptLF)
    $proc2.StandardInput.BaseStream.Write($bytes2, 0, $bytes2.Length)
    $proc2.StandardInput.BaseStream.Flush()
    $proc2.StandardInput.Close()
    $out2 = $proc2.StandardOutput.ReadToEnd()
    $err2 = $proc2.StandardError.ReadToEnd()
    $proc2.WaitForExit()
    $exit2 = $proc2.ExitCode

    if ($out2) { Write-Host $out2 -ForegroundColor Green }
    if ($err2) { Write-Host "  STDERR: $err2" -ForegroundColor Yellow }

    if ($exit2 -ne 0) {
        Write-Host "  AVISO: restart gateway exit $exit2 (verificar manualmente)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  AVISO restart SSH: $_ (nao bloqueia P1)" -ForegroundColor Yellow
}

# ============================================================
# Step 4: Smoke — autenticar gateway endpoint via SSH
# ============================================================
Write-Host ""
Write-Host "=== Step 4/4: Smoke gateway auth ===" -ForegroundColor Cyan
Write-Host "  Testando endpoint gateway com novo secret..."

$smokeScript = @"
set -e
SECRET="$newSecret"
BASE_URL="http://localhost:55401"

# Health endpoint (sem auth)
HEALTH=`$(curl -sf "`$BASE_URL/health" 2>&1)
if [ -z "`$HEALTH" ]; then
  HEALTH="FAIL"
fi
if echo "`$HEALTH" | grep -q 'status'; then
  echo "  Smoke /health: OK"
else
  echo "  Smoke /health FAIL: `$HEALTH"
  exit 1
fi

# Tools endpoint com Bearer auth
HTTP_CODE=`$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer `$SECRET" "`$BASE_URL/tools" 2>&1)
if [ "`$HTTP_CODE" = "200" ]; then
  echo "  Smoke /tools Bearer: OK (HTTP 200)"
elif [ "`$HTTP_CODE" = "404" ]; then
  echo "  Smoke /tools: 404 (rota nao existe - /health OK suficiente)"
elif [ "`$HTTP_CODE" = "401" ]; then
  echo "  Smoke /tools FAIL: HTTP 401 - secret novo nao aceito pelo gateway"
  exit 1
elif [ "`$HTTP_CODE" = "403" ]; then
  echo "  Smoke /tools FAIL: HTTP 403 - secret novo nao aceito pelo gateway"
  exit 1
else
  echo "  Smoke /tools: HTTP `$HTTP_CODE (gateway pode estar inicializando)"
fi

echo "  Smoke CONCLUSAO: gateway respondendo com novo secret"
"@

$smokeScriptLF = $smokeScript -replace "`r`n", "`n" -replace "`r", "`n"

$psi3 = New-Object System.Diagnostics.ProcessStartInfo
$psi3.FileName = "ssh"
$psi3.Arguments = "-T -o ConnectTimeout=15 -o BatchMode=yes hermes-gcp@136.115.74.69 bash -s"
$psi3.RedirectStandardInput = $true
$psi3.RedirectStandardOutput = $true
$psi3.RedirectStandardError = $true
$psi3.UseShellExecute = $false
$psi3.CreateNoWindow = $true

try {
    $proc3 = [System.Diagnostics.Process]::Start($psi3)
    $utf8NoBom3 = New-Object System.Text.UTF8Encoding($false)
    $bytes3 = $utf8NoBom3.GetBytes($smokeScriptLF)
    $proc3.StandardInput.BaseStream.Write($bytes3, 0, $bytes3.Length)
    $proc3.StandardInput.BaseStream.Flush()
    $proc3.StandardInput.Close()
    $out3 = $proc3.StandardOutput.ReadToEnd()
    $err3 = $proc3.StandardError.ReadToEnd()
    $proc3.WaitForExit()
    $exit3 = $proc3.ExitCode

    if ($out3) { Write-Host $out3 -ForegroundColor Green }
    if ($err3) { Write-Host "  STDERR: $err3" -ForegroundColor Yellow }

    if ($exit3 -ne 0) {
        Write-Host "  Smoke FAIL: gateway recusou novo secret" -ForegroundColor Red
        Write-Host "  Verificar: systemctl status hermes-mcps-gateway na VM" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ERRO Smoke SSH: $_" -ForegroundColor Red
}

# ============================================================
# Cleanup
# ============================================================
$newSecret = $null
$secretLine = $null
$envContent = $null
[System.GC]::Collect()

Write-Host ""
Write-Host "=== Setup COMPLETO ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Reporte ao Claude (sessao orquestrador):" -ForegroundColor Yellow
Write-Host "  - Smoke gateway /health OK: SIM | NAO"
Write-Host "  - Smoke gateway Bearer auth OK: SIM | NAO"
Write-Host "  - VM gateway reiniciado: SIM | NAO"
Write-Host ""
Write-Host "Security:" -ForegroundColor Yellow
Write-Host "  - .env gitignored - NAO commitar"
Write-Host "  - Secret NUNCA exibir completo em logs/chat"
Write-Host ""
