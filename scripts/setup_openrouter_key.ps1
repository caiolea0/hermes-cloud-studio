# Hermes - Rotate OpenRouter API Key (PC + VM automated)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup_openrouter_key.ps1
# Compatible: Windows PowerShell 5.1+
#
# Security notes:
# - Key input MASCARADO (Read-Host -AsSecureString)
# - Key em memoria apenas + cleanup pos-uso
# - Update PC .env + VM .env (gitignored)
# - Smoke: GET https://openrouter.ai/api/v1/auth/key → 200

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Hermes - Rotate OpenRouter API Key (PC + VM) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Este script vai:" -ForegroundColor Yellow
Write-Host "  1. Solicitar nova OPENROUTER_API_KEY (input mascarado)"
Write-Host "  2. Validar formato (sk-or-v1-...)"
Write-Host "  3. Atualizar .env PC + .env VM via SSH"
Write-Host "  4. Smoke: verificar key valida via OpenRouter API"
Write-Host ""
Write-Host "Pre-requisitos:" -ForegroundColor Yellow
Write-Host "  - Acessar openrouter.ai → Settings → Keys"
Write-Host "  - Revogar key antiga (sk-or-v1-...)"
Write-Host "  - Gerar nova key"
Write-Host "  - SSH para hermes-gcp@136.115.74.69 funcional"
Write-Host ""

$confirm = Read-Host "Continuar? (s/n)"
if ($confirm -ne "s" -and $confirm -ne "S") {
    Write-Host "Abortado." -ForegroundColor Red
    exit 0
}

# ============================================================
# Step 1: Solicitar nova API Key mascarada
# ============================================================
Write-Host ""
Write-Host "=== Step 1/4: OpenRouter API Key ===" -ForegroundColor Cyan
Write-Host "Cole nova API key (digitacao NAO aparece terminal):"
$secureKey = Read-Host -AsSecureString
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
$plainKey = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)

if (-not ($plainKey -match "^sk-or-v1-[A-Za-z0-9]{40,}$")) {
    Write-Host ""
    Write-Host "ERRO: Key formato invalido." -ForegroundColor Red
    Write-Host "Esperado: sk-or-v1-<40+ chars alfanumerico>"
    $plainKey = $null
    exit 1
}

$keyPreview = $plainKey.Substring(0, 14)
Write-Host ("  Key formato OK ({0}...)" -f $keyPreview) -ForegroundColor Green

# ============================================================
# Step 2: Update .env PC
# ============================================================
Write-Host ""
Write-Host "=== Step 2/4: Update .env PC + VM ===" -ForegroundColor Cyan

$envPathPC = "D:\dev-projects\main\hermes-cloud-studio\.env"

if (-not (Test-Path $envPathPC)) {
    Write-Host "ERRO: .env PC nao encontrado" -ForegroundColor Red
    $plainKey = $null
    exit 1
}

$envContent = Get-Content $envPathPC -Raw
$keyLine = "OPENROUTER_API_KEY=$plainKey"

if ($envContent -match "(?m)^OPENROUTER_API_KEY=") {
    $envContent = $envContent -replace "(?m)^OPENROUTER_API_KEY=.*$", $keyLine
    Write-Host "  PC .env OPENROUTER_API_KEY: ATUALIZADA" -ForegroundColor Green
} else {
    if (-not $envContent.EndsWith("`n")) {
        $envContent += "`n"
    }
    $envContent += "`n# P1 Hardening — OpenRouter LLM provider`n$keyLine`n"
    Write-Host "  PC .env OPENROUTER_API_KEY: ADICIONADA" -ForegroundColor Green
}

[System.IO.File]::WriteAllText($envPathPC, $envContent, [System.Text.UTF8Encoding]::new($false))

$verifyPC = Select-String -Path $envPathPC -Pattern "^OPENROUTER_API_KEY=sk-or-v1-" -Quiet
if ($verifyPC) {
    Write-Host "  PC verify: OK" -ForegroundColor Green
} else {
    Write-Host "  PC verify: FALHOU" -ForegroundColor Red
    $plainKey = $null
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

if grep -q '^OPENROUTER_API_KEY=' `$ENV_FILE 2>/dev/null; then
  sed -i 's|^OPENROUTER_API_KEY=.*|OPENROUTER_API_KEY=$plainKey|' `$ENV_FILE
  echo "  VM OPENROUTER_API_KEY: ATUALIZADA"
else
  echo "" >> `$ENV_FILE
  echo "# P1 Hardening — OpenRouter LLM provider" >> `$ENV_FILE
  echo "OPENROUTER_API_KEY=$plainKey" >> `$ENV_FILE
  echo "  VM OPENROUTER_API_KEY: ADICIONADA"
fi

if grep -q '^OPENROUTER_API_KEY=sk-or-v1-' `$ENV_FILE; then
  echo "  VM verify: OK"
else
  echo "  VM verify: FALHOU"
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
# Step 3: Restart hermes_api_v2 na VM (recarregar env)
# ============================================================
Write-Host ""
Write-Host "=== Step 3/4: Restart VM API (reload env) ===" -ForegroundColor Cyan
Write-Host "  Reiniciando hermes_api_v2 na VM..."

$restartScript = @"
set -e
if systemctl is-active --quiet hermes-api 2>/dev/null; then
  systemctl restart hermes-api
  sleep 2
  systemctl is-active hermes-api && echo "  VM hermes-api: REINICIADO OK" || echo "  VM hermes-api: FALHOU"
elif pgrep -f "hermes_api_v2.py" > /dev/null; then
  pkill -HUP -f "hermes_api_v2.py" 2>/dev/null || true
  echo "  VM hermes-api: SIGHUP enviado (sem systemd)"
else
  echo "  VM hermes-api: processo nao encontrado (OK se parado)"
fi
"@

$restartScriptLF = $restartScript -replace "`r`n", "`n" -replace "`r", "`n"

$psi2 = New-Object System.Diagnostics.ProcessStartInfo
$psi2.FileName = "ssh"
$psi2.Arguments = "-T -o ConnectTimeout=10 -o BatchMode=yes hermes-gcp@136.115.74.69 bash -s"
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

    if ($out2) { Write-Host $out2 -ForegroundColor Green }
    if ($err2) { Write-Host "  STDERR: $err2" -ForegroundColor Yellow }
} catch {
    Write-Host "  AVISO restart SSH: $_ (nao bloqueia P1)" -ForegroundColor Yellow
}

# ============================================================
# Step 4: Smoke — verificar key valida via OpenRouter API
# ============================================================
Write-Host ""
Write-Host "=== Step 4/4: Smoke OpenRouter auth/key ===" -ForegroundColor Cyan

try {
    $headers = @{ "Authorization" = "Bearer $plainKey" }
    $response = Invoke-RestMethod -Uri "https://openrouter.ai/api/v1/auth/key" `
        -Method Get -Headers $headers -ErrorAction Stop

    if ($response.data) {
        $label = if ($response.data.label) { $response.data.label } else { "(sem label)" }
        $usage = if ($response.data.usage -ne $null) { $response.data.usage } else { "N/A" }
        Write-Host "  Smoke OK: key valida" -ForegroundColor Green
        Write-Host "  Label: $label | Usage: $usage" -ForegroundColor Cyan
    } else {
        Write-Host "  Smoke WARN: resposta sem .data (key pode ser valida)" -ForegroundColor Yellow
        Write-Host "  Response: $($response | ConvertTo-Json -Compress)"
    }
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    Write-Host "  Smoke FAIL (HTTP $statusCode): $_" -ForegroundColor Red
    Write-Host "  ACAO: verificar key rotacionada corretamente no openrouter.ai" -ForegroundColor Yellow
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
Write-Host "Reporte ao Claude (sessao orquestrador):" -ForegroundColor Yellow
Write-Host "  - Smoke OpenRouter key valida: SIM | NAO"
Write-Host "  - VM hermes-api reiniciado: SIM | NAO"
Write-Host ""
Write-Host "Security:" -ForegroundColor Yellow
Write-Host "  - .env gitignored - NAO commitar"
Write-Host "  - Key NUNCA colar em chat publico"
Write-Host ""
