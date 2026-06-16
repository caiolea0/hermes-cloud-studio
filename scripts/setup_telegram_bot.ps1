# Hermes - Setup Telegram Bot Token + Chat ID (PC + VM automated)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup_telegram_bot.ps1
# Compatible: Windows PowerShell 5.1+
#
# Security notes:
# - Token input MASCARADO (Read-Host -AsSecureString)
# - Token memoria apenas + cleanup ASAP
# - Token append nos .env PC + VM (gitignored)
# - Smoke send confirmation Telegram message

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Hermes - Setup Telegram Bot (PC + VM) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Este script vai:" -ForegroundColor Yellow
Write-Host "  1. Solicitar TELEGRAM_BOT_TOKEN (input mascarado)"
Write-Host "  2. Solicitar TELEGRAM_CHAT_ID (input visivel - nao e secret)"
Write-Host "  3. Adicionar ao .env PC + .env VM"
Write-Host "  4. Smoke send test message Telegram"
Write-Host ""
Write-Host "Pre-requisitos:" -ForegroundColor Yellow
Write-Host "  - Bot criado via @BotFather (token format 123456789:ABCdef...)"
Write-Host "  - Owner enviou ao menos 1 mensagem ao bot (chat existe)"
Write-Host "  - chat_id obtido via getUpdates"
Write-Host "  - SSH para hermes-gcp@136.115.74.69 funcional"
Write-Host ""

$confirm = Read-Host "Continuar? (s/n)"
if ($confirm -ne "s" -and $confirm -ne "S") {
    Write-Host "Abortado." -ForegroundColor Red
    exit 0
}

# ============================================================
# Step 1: Solicitar Bot Token mascarado
# ============================================================
Write-Host ""
Write-Host "=== Step 1/4: Telegram Bot Token ===" -ForegroundColor Cyan
Write-Host "Cole token do bot (digitacao NAO aparece terminal):"
$secureToken = Read-Host -AsSecureString
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
$plainToken = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)

if (-not ($plainToken -match "^\d+:[A-Za-z0-9_-]{30,}$")) {
    Write-Host ""
    Write-Host "ERRO: Token formato invalido." -ForegroundColor Red
    Write-Host "Esperado: 123456789:ABCdefGHIjklMNOpqrSTUvwxYZabcDEF"
    $plainToken = $null
    exit 1
}

$tokenPreview = $plainToken.Substring(0, 12)
$okMsg = "  Token formato OK ({0}...)" -f $tokenPreview
Write-Host $okMsg -ForegroundColor Green

# ============================================================
# Step 2: Solicitar Chat ID (visible - not secret)
# ============================================================
Write-Host ""
Write-Host "=== Step 2/4: Telegram Chat ID ===" -ForegroundColor Cyan
Write-Host "Cole chat_id (numero grande tipo 6034756748):"
$chatIdRaw = Read-Host
# Cleanup: trim whitespace + remove leading ":" se paste acidental + strip non-digit prefix
$chatId = $chatIdRaw.Trim() -replace '^[:\s]+', '' -replace '\s+$', ''

if (-not ($chatId -match "^-?\d+$")) {
    Write-Host "ERRO: chat_id deve ser numero (positivo private OR negativo grupo)." -ForegroundColor Red
    Write-Host "  Recebido raw: '$chatIdRaw' (len=$($chatIdRaw.Length))" -ForegroundColor Yellow
    Write-Host "  Apos cleanup: '$chatId' (len=$($chatId.Length))" -ForegroundColor Yellow
    $plainToken = $null
    exit 1
}

$chatMsg = "  Chat ID OK ({0})" -f $chatId
Write-Host $chatMsg -ForegroundColor Green

# ============================================================
# Step 3: Update .env PC + VM
# ============================================================
Write-Host ""
Write-Host "=== Step 3/4: Update .env PC + VM ===" -ForegroundColor Cyan

$envPathPC = "D:\dev-projects\main\hermes-cloud-studio\.env"

if (-not (Test-Path $envPathPC)) {
    Write-Host "ERRO: .env PC nao encontrado" -ForegroundColor Red
    $plainToken = $null
    exit 1
}

# PC .env update (replace OR append both vars)
$envContent = Get-Content $envPathPC -Raw
$tokenLine = "HERMES_TELEGRAM_BOT_TOKEN=$plainToken"
$chatLine = "HERMES_TELEGRAM_CHAT_ID=$chatId"

# Token
if ($envContent -match "(?m)^HERMES_TELEGRAM_BOT_TOKEN=") {
    $envContent = $envContent -replace "(?m)^HERMES_TELEGRAM_BOT_TOKEN=.*$", $tokenLine
    Write-Host "  PC .env BOT_TOKEN: ATUALIZADA" -ForegroundColor Green
} else {
    if (-not $envContent.EndsWith("`n")) {
        $envContent += "`n"
    }
    $envContent += "`n# F.7 C4 Telegram bot Hermes - gitignored`n$tokenLine`n"
    Write-Host "  PC .env BOT_TOKEN: ADICIONADA" -ForegroundColor Green
}

# Chat ID
if ($envContent -match "(?m)^HERMES_TELEGRAM_CHAT_ID=") {
    $envContent = $envContent -replace "(?m)^HERMES_TELEGRAM_CHAT_ID=.*$", $chatLine
    Write-Host "  PC .env CHAT_ID: ATUALIZADA" -ForegroundColor Green
} else {
    $envContent += "$chatLine`n"
    Write-Host "  PC .env CHAT_ID: ADICIONADA" -ForegroundColor Green
}

[System.IO.File]::WriteAllText($envPathPC, $envContent, [System.Text.UTF8Encoding]::new($false))

$verifyPC = Select-String -Path $envPathPC -Pattern "^HERMES_TELEGRAM_BOT_TOKEN=\d" -Quiet
$verifyPCChat = Select-String -Path $envPathPC -Pattern "^HERMES_TELEGRAM_CHAT_ID=-?\d" -Quiet
if ($verifyPC -and $verifyPCChat) {
    Write-Host "  PC verify: ambas vars presentes" -ForegroundColor Green
} else {
    Write-Host "  PC verify: FALHOU" -ForegroundColor Red
    $plainToken = $null
    exit 1
}

# VM .env update via SSH bytes-level stdin (mem_mqekwse6 pattern preservado)
Write-Host ""
Write-Host "  Atualizando VM via SSH..."

$sshScript = @"
set -e
ENV_FILE=~/.hermes/.env
mkdir -p ~/.hermes
touch `$ENV_FILE
chmod 600 `$ENV_FILE

# Token
if grep -q '^HERMES_TELEGRAM_BOT_TOKEN=' `$ENV_FILE 2>/dev/null; then
  sed -i 's|^HERMES_TELEGRAM_BOT_TOKEN=.*|HERMES_TELEGRAM_BOT_TOKEN=$plainToken|' `$ENV_FILE
  echo "  VM BOT_TOKEN: ATUALIZADA"
else
  echo "" >> `$ENV_FILE
  echo "# F.7 C4 Telegram bot Hermes - gitignored" >> `$ENV_FILE
  echo "HERMES_TELEGRAM_BOT_TOKEN=$plainToken" >> `$ENV_FILE
  echo "  VM BOT_TOKEN: ADICIONADA"
fi

# Chat ID
if grep -q '^HERMES_TELEGRAM_CHAT_ID=' `$ENV_FILE 2>/dev/null; then
  sed -i 's|^HERMES_TELEGRAM_CHAT_ID=.*|HERMES_TELEGRAM_CHAT_ID=$chatId|' `$ENV_FILE
  echo "  VM CHAT_ID: ATUALIZADA"
else
  echo "HERMES_TELEGRAM_CHAT_ID=$chatId" >> `$ENV_FILE
  echo "  VM CHAT_ID: ADICIONADA"
fi

# Verify
if grep -q '^HERMES_TELEGRAM_BOT_TOKEN=' `$ENV_FILE && grep -q '^HERMES_TELEGRAM_CHAT_ID=' `$ENV_FILE; then
  echo "  VM verify: ambas vars presentes"
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
        $plainToken = $null
        exit 1
    }
} catch {
    Write-Host "  ERRO SSH: $_" -ForegroundColor Red
    $plainToken = $null
    exit 1
}

$sshScriptLF = $null
$bytes = $null

# ============================================================
# Step 4: Smoke send Telegram test message
# ============================================================
Write-Host ""
Write-Host "=== Step 4/4: Smoke Telegram send ===" -ForegroundColor Cyan

$testMsg = "Hermes Cobaia F.7 C4 setup OK | $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$apiUrl = "https://api.telegram.org/bot$plainToken/sendMessage"

try {
    $response = Invoke-RestMethod -Uri $apiUrl -Method Post -Body @{
        chat_id = $chatId
        text = $testMsg
    } -ErrorAction Stop

    if ($response.ok -eq $true) {
        Write-Host "  Smoke OK: mensagem enviada Telegram" -ForegroundColor Green
        Write-Host "  Verifica teu chat Telegram - deve mostrar:" -ForegroundColor Yellow
        Write-Host "    '$testMsg'"
    } else {
        Write-Host "  Smoke FAIL: API retornou ok=false" -ForegroundColor Red
        Write-Host "  Response: $($response | ConvertTo-Json -Compress)"
    }
} catch {
    Write-Host "  Smoke FAIL: $_" -ForegroundColor Red
}

# ============================================================
# Cleanup
# ============================================================
$plainToken = $null
$tokenLine = $null
$envContent = $null
[System.GC]::Collect()

Write-Host ""
Write-Host "=== Setup COMPLETO ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Reporte ao Claude (sessao orquestrador):" -ForegroundColor Yellow
Write-Host "  - Smoke Telegram message recebido: SIM | NAO"
Write-Host ""
Write-Host "Security:" -ForegroundColor Yellow
Write-Host "  - .env gitignored - NAO commitar"
Write-Host "  - Bot token NUNCA colar em chat publico"
Write-Host ""
