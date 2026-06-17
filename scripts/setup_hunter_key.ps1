# Hermes - Setup Hunter.io API key (PC + VM automated)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup_hunter_key.ps1
# Compatible: Windows PowerShell 5.1+
#
# F.7 P5 hardening - Hunter.io email verifier (Task 6 + MCP HARD REQ)
# Free tier: 25 verifies/mo + 100 searches/mo + 15 req/min rate limit
#
# Security notes:
# - Key input MASCARADO (Read-Host -AsSecureString)
# - Key memoria apenas + cleanup ASAP
# - Key append nos .env PC + VM (gitignored)
# - Smoke /v2/account confirma quota + plan_name

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Hermes - Setup Hunter.io API key (PC + VM) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Este script vai:" -ForegroundColor Yellow
Write-Host "  1. Solicitar HUNTER_API_KEY (input mascarado)"
Write-Host "  2. Adicionar ao .env PC + .env VM"
Write-Host "  3. Smoke /v2/account confirma quota + plan_name"
Write-Host ""
Write-Host "Pre-requisitos:" -ForegroundColor Yellow
Write-Host "  - Conta criada em hunter.io (free tier OK)"
Write-Host "  - Key gerada em hunter.io Settings - API"
Write-Host "  - SSH para hermes-gcp@136.115.74.69 funcional"
Write-Host ""

$confirm = Read-Host "Continuar? (s/n)"
if ($confirm -ne "s" -and $confirm -ne "S") {
    Write-Host "Abortado." -ForegroundColor Red
    exit 0
}

# ============================================================
# Step 1: Solicitar Hunter API key mascarado
# ============================================================
Write-Host ""
Write-Host "=== Step 1/4: Hunter.io API key ===" -ForegroundColor Cyan
Write-Host "Cole key Hunter.io (digitacao NAO aparece terminal):"
$secureKey = Read-Host -AsSecureString
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
$plainKey = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)

# Hunter keys are hex 40+ chars
if (-not ($plainKey -match "^[a-f0-9]{30,}$")) {
    Write-Host ""
    Write-Host "ERRO: Key formato invalido." -ForegroundColor Red
    Write-Host "Esperado: hex lowercase 30+ chars (ex: abc123def456...)"
    $plainKey = $null
    exit 1
}

$keyPreview = $plainKey.Substring(0, 8)
$okMsg = "  Key formato OK ({0}...)" -f $keyPreview
Write-Host $okMsg -ForegroundColor Green

# ============================================================
# Step 2: Update .env PC
# ============================================================
Write-Host ""
Write-Host "=== Step 2/4: Update .env PC ===" -ForegroundColor Cyan

$envPathPC = "D:\dev-projects\main\hermes-cloud-studio\.env"

if (-not (Test-Path $envPathPC)) {
    Write-Host "ERRO: .env PC nao encontrado" -ForegroundColor Red
    $plainKey = $null
    exit 1
}

$envContent = Get-Content $envPathPC -Raw
$keyLine = "HUNTER_API_KEY=$plainKey"

if ($envContent -match "(?m)^HUNTER_API_KEY=") {
    $envContent = $envContent -replace "(?m)^HUNTER_API_KEY=.*$", $keyLine
    Write-Host "  PC .env HUNTER_API_KEY: ATUALIZADA" -ForegroundColor Green
} else {
    if (-not $envContent.EndsWith("`n")) {
        $envContent += "`n"
    }
    $envContent += "`n# F.7 P5 Hunter.io email verifier (free tier 25/mo) - gitignored`n$keyLine`n"
    Write-Host "  PC .env HUNTER_API_KEY: ADICIONADA" -ForegroundColor Green
}

[System.IO.File]::WriteAllText($envPathPC, $envContent, [System.Text.UTF8Encoding]::new($false))

$verifyPC = Select-String -Path $envPathPC -Pattern "^HUNTER_API_KEY=[a-f0-9]" -Quiet
if ($verifyPC) {
    Write-Host "  PC verify: HUNTER_API_KEY presente" -ForegroundColor Green
} else {
    Write-Host "  PC verify: FALHOU" -ForegroundColor Red
    $plainKey = $null
    exit 1
}

# ============================================================
# Step 3: Update .env VM via SSH bytes-level stdin
# ============================================================
Write-Host ""
Write-Host "=== Step 3/4: Update .env VM ===" -ForegroundColor Cyan
Write-Host "  Atualizando VM via SSH..."

$sshScript = @"
set -e
ENV_FILE=~/.hermes/.env
mkdir -p ~/.hermes
touch `$ENV_FILE
chmod 600 `$ENV_FILE

if grep -q '^HUNTER_API_KEY=' `$ENV_FILE 2>/dev/null; then
  sed -i 's|^HUNTER_API_KEY=.*|HUNTER_API_KEY=$plainKey|' `$ENV_FILE
  echo "  VM HUNTER_API_KEY: ATUALIZADA"
else
  echo "" >> `$ENV_FILE
  echo "# F.7 P5 Hunter.io email verifier - gitignored" >> `$ENV_FILE
  echo "HUNTER_API_KEY=$plainKey" >> `$ENV_FILE
  echo "  VM HUNTER_API_KEY: ADICIONADA"
fi

if grep -q '^HUNTER_API_KEY=' `$ENV_FILE; then
  echo "  VM verify: HUNTER_API_KEY presente"
  echo "  VM perms: chmod 600 owner-only"
else
  echo "  VM verify: FALHOU"
  exit 1
fi
"@

$sshScriptLF = $sshScript -replace "`r`n", "`n"
$sshScriptLF = $sshScriptLF -replace "`r", "`n"

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
        $plainKey = $null
        exit 1
    }
} catch {
    Write-Host "  ERRO SSH: $_" -ForegroundColor Red
    $plainKey = $null
    exit 1
}

$sshScriptLF = $null
$bytes = $null

# ============================================================
# Step 4: Smoke /v2/account confirma quota
# ============================================================
Write-Host ""
Write-Host "=== Step 4/4: Smoke Hunter.io /v2/account ===" -ForegroundColor Cyan

$apiUrl = "https://api.hunter.io/v2/account?api_key=$plainKey"

try {
    $response = Invoke-RestMethod -Uri $apiUrl -Method Get -ErrorAction Stop

    if ($response.data) {
        $planName = $response.data.plan_name
        $calls = $response.data.calls
        Write-Host "  Smoke OK: Hunter.io API responde 200" -ForegroundColor Green
        Write-Host "  Plan: $planName" -ForegroundColor Yellow
        if ($calls.used) {
            Write-Host "  Calls used: $($calls.used)" -ForegroundColor Yellow
        }
        if ($calls.available) {
            Write-Host "  Calls available: $($calls.available)" -ForegroundColor Yellow
        }
        Write-Host ""
        Write-Host "  Resetar mensal automatico (free tier 25 verifies/mo)" -ForegroundColor Cyan
    } else {
        Write-Host "  Smoke FAIL: response sem campo data" -ForegroundColor Red
    }
} catch {
    Write-Host "  Smoke FAIL: $_" -ForegroundColor Red
    Write-Host "  Verifique key valida em https://hunter.io/api-keys" -ForegroundColor Yellow
}

# ============================================================
# Cleanup
# ============================================================
$plainKey = $null
$keyLine = $null
$envContent = $null
[System.GC]::Collect()

Write-Host ""
Write-Host "=== Setup COMPLETO ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Endpoints disponiveis:" -ForegroundColor Yellow
Write-Host "  POST /api/cobaia/verify-email   {email}"
Write-Host "  GET  /api/cobaia/hunter-usage"
Write-Host ""
Write-Host "Reporte ao Claude (sessao orquestrador):" -ForegroundColor Yellow
Write-Host "  - Smoke Hunter API /v2/account 200: SIM | NAO"
Write-Host "  - plan_name + calls usage anotados"
Write-Host ""
Write-Host "Security:" -ForegroundColor Yellow
Write-Host "  - .env gitignored - NAO commitar"
Write-Host "  - Hunter key NUNCA colar em chat publico"
Write-Host ""
