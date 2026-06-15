# Hermes - Setup GitHub Personal Access Token (PC + VM automated)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup_github_pat.ps1
# Compatible: Windows PowerShell 5.1+
#
# Security notes:
# - Token input MASCARADO (Read-Host -AsSecureString)
# - Token transit memoria apenas
# - Token append nos .env destino (.env PC + ~/.hermes/.env VM)
# - .env esta gitignored

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Hermes - Setup GitHub PAT (PC + VM) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Este script vai:" -ForegroundColor Yellow
Write-Host "  1. Solicitar GitHub PAT (input mascarado)"
Write-Host "  2. Adicionar ao .env PC + .env VM"
Write-Host "  3. Restart server.py PC + systemd gateway VM"
Write-Host "  4. Smoke validation"
Write-Host ""
Write-Host "Pre-requisitos:" -ForegroundColor Yellow
Write-Host "  - GitHub PAT gerado em github.com/settings/tokens"
Write-Host "  - Scopes: repo + workflow"
Write-Host "  - SSH para hermes-gcp funcional"
Write-Host ""

$confirm = Read-Host "Continuar? (s/n)"
if ($confirm -ne "s" -and $confirm -ne "S") {
    Write-Host "Abortado." -ForegroundColor Red
    exit 0
}

# ============================================================
# Step 1: Solicitar PAT mascarado
# ============================================================
Write-Host ""
Write-Host "=== Step 1/4: Solicitar PAT ===" -ForegroundColor Cyan
Write-Host "Cole seu PAT (digitacao NAO aparece terminal):"
$secureToken = Read-Host -AsSecureString
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
$plainToken = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)

if (-not ($plainToken.StartsWith("ghp_") -or $plainToken.StartsWith("github_pat_"))) {
    Write-Host ""
    Write-Host "ERRO: Token formato invalido." -ForegroundColor Red
    Write-Host "Esperado: ghp_xxxxxx OR github_pat_xxxxxx"
    $plainToken = $null
    exit 1
}

$tokenPreview = $plainToken.Substring(0, 8)
$okMsg = "  Token formato OK ({0}...)" -f $tokenPreview
Write-Host $okMsg -ForegroundColor Green

# ============================================================
# Step 2: Update .env PC
# ============================================================
Write-Host ""
Write-Host "=== Step 2/4: Update .env PC ===" -ForegroundColor Cyan

$envPathPC = "D:\dev-projects\main\hermes-cloud-studio\.env"

if (-not (Test-Path $envPathPC)) {
    Write-Host "ERRO: .env PC nao encontrado" -ForegroundColor Red
    $plainToken = $null
    exit 1
}

$envContent = Get-Content $envPathPC -Raw
$tokenLine = "GITHUB_PERSONAL_ACCESS_TOKEN=$plainToken"

if ($envContent -match "(?m)^GITHUB_PERSONAL_ACCESS_TOKEN=") {
    $newContent = $envContent -replace "(?m)^GITHUB_PERSONAL_ACCESS_TOKEN=.*$", $tokenLine
    [System.IO.File]::WriteAllText($envPathPC, $newContent, [System.Text.UTF8Encoding]::new($false))
    Write-Host "  PC .env: linha ATUALIZADA" -ForegroundColor Green
} else {
    if (-not $envContent.EndsWith("`n")) {
        Add-Content -Path $envPathPC -Value "" -Encoding UTF8
    }
    Add-Content -Path $envPathPC -Value "" -Encoding UTF8
    $commentLine = "# F.4.2 GitHub MCP PAT - gitignored"
    Add-Content -Path $envPathPC -Value $commentLine -Encoding UTF8
    Add-Content -Path $envPathPC -Value $tokenLine -Encoding UTF8
    Write-Host "  PC .env: linha ADICIONADA" -ForegroundColor Green
}

$verifyPC = Select-String -Path $envPathPC -Pattern "^GITHUB_PERSONAL_ACCESS_TOKEN=ghp_" -Quiet
if (-not $verifyPC) {
    $verifyPC = Select-String -Path $envPathPC -Pattern "^GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_" -Quiet
}
if ($verifyPC) {
    Write-Host "  PC verify: token presente" -ForegroundColor Green
} else {
    Write-Host "  PC verify: FALHOU" -ForegroundColor Red
    $plainToken = $null
    exit 1
}

# ============================================================
# Step 3: Update VM .env via SSH
# ============================================================
Write-Host ""
Write-Host "=== Step 3/4: Update VM .env via SSH ===" -ForegroundColor Cyan

# Build bash script com token embedded (run via SSH stdin, nao command-line)
$sshScript = @"
set -e
if grep -q '^GITHUB_PERSONAL_ACCESS_TOKEN=' ~/.hermes/.env 2>/dev/null; then
  sed -i 's|^GITHUB_PERSONAL_ACCESS_TOKEN=.*|GITHUB_PERSONAL_ACCESS_TOKEN=$plainToken|' ~/.hermes/.env
  echo "  VM .env: linha ATUALIZADA"
else
  echo "" >> ~/.hermes/.env
  echo "# F.4.2 GitHub MCP PAT - gitignored" >> ~/.hermes/.env
  echo "GITHUB_PERSONAL_ACCESS_TOKEN=$plainToken" >> ~/.hermes/.env
  echo "  VM .env: linha ADICIONADA"
fi
chmod 600 ~/.hermes/.env
if grep -q '^GITHUB_PERSONAL_ACCESS_TOKEN=ghp_' ~/.hermes/.env || grep -q '^GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_' ~/.hermes/.env; then
  echo "  VM verify: token presente"
  echo "  VM perms: 600 owner-only"
else
  echo "  VM verify: FALHOU"
  exit 1
fi
"@

# Normalize CRLF -> LF (bash quebra com \r em if/fi structures)
$sshScriptLF = $sshScript -replace "`r`n", "`n"
$sshScriptLF = $sshScriptLF -replace "`r", "`n"

# CRITICAL: PowerShell pipe `|` re-introduz CRLF mesmo de source LF.
# Solucao: ProcessStartInfo + StandardInput.BaseStream.Write(bytes) bypass total.
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
        $sshScript = $null
        $sshScriptLF = $null
        $bytes = $null
        exit 1
    }
} catch {
    Write-Host "  ERRO SSH: $_" -ForegroundColor Red
    $plainToken = $null
    $sshScript = $null
    $sshScriptLF = $null
    $bytes = $null
    exit 1
}

$sshScriptLF = $null
$bytes = $null

# Cleanup token from intermediate var
$sshScript = $null

# ============================================================
# Step 4: Restart services + smoke
# ============================================================
Write-Host ""
Write-Host "=== Step 4/4: Restart services + smoke ===" -ForegroundColor Cyan

# Restart PC server
$srv = Get-NetTCPConnection -LocalPort 55000 -State Listen -ErrorAction SilentlyContinue
if ($srv) {
    $serverPid = $srv.OwningProcess
    Write-Host "  PC server: killing PID $serverPid..."
    Stop-Process -Id $serverPid -Force -ErrorAction SilentlyContinue
    Start-Sleep 4
}

Set-Location D:\dev-projects\main\hermes-cloud-studio

if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}

Start-Process -FilePath "python" -ArgumentList "server.py" `
    -WorkingDirectory "D:\dev-projects\main\hermes-cloud-studio" `
    -WindowStyle Hidden `
    -RedirectStandardOutput "logs\server_pat.log" `
    -RedirectStandardError "logs\server_pat.err.log" | Out-Null
Start-Sleep 10

$srvCheck = Get-NetTCPConnection -LocalPort 55000 -State Listen -ErrorAction SilentlyContinue
if ($srvCheck) {
    $pcMsg = "  PC server: restarted PID {0}" -f $srvCheck.OwningProcess
    Write-Host $pcMsg -ForegroundColor Green
} else {
    Write-Host "  PC server: WARN DOWN - check logs\server_pat.err.log" -ForegroundColor Yellow
}

# Restart VM systemd gateway (PS 5.1 sem && - separar comandos)
Write-Host "  VM gateway: restarting..."
$vmRestart1 = ssh -o ConnectTimeout=5 hermes-gcp@136.115.74.69 "systemctl --user restart hermes-mcps-gateway.service" 2>&1
Start-Sleep 4
$vmStatus = ssh -o ConnectTimeout=5 hermes-gcp@136.115.74.69 "systemctl --user is-active hermes-mcps-gateway.service" 2>&1
Write-Host "  VM gateway status: $vmStatus" -ForegroundColor Green

# ============================================================
# Smoke validation
# ============================================================
Write-Host ""
Write-Host "=== Smoke validation ===" -ForegroundColor Cyan

# 1. PC server health (server.py expoe / e /docs, nao /health)
try {
    $pcResp = Invoke-WebRequest -Uri "http://localhost:55000/docs" -UseBasicParsing -ErrorAction Stop
    $pcStatus = "  PC :55000 /docs: {0}" -f $pcResp.StatusCode
    Write-Host $pcStatus
} catch {
    Write-Host "  PC :55000: DOWN" -ForegroundColor Yellow
}

# 2. VM gateway health
$vmHealth = ssh -o ConnectTimeout=5 hermes-gcp@136.115.74.69 'curl -s -o /dev/null -w "%{http_code}" http://localhost:55401/health' 2>&1
Write-Host "  VM :55401 gateway: $vmHealth"

# 3. PC PAT presence (leitura direta .env, encoding-safe)
$pcPatLine = Select-String -Path $envPathPC -Pattern "^GITHUB_PERSONAL_ACCESS_TOKEN=(ghp_|github_pat_)" -Quiet
if ($pcPatLine) {
    Write-Host "  PC PAT presence: present" -ForegroundColor Green
} else {
    Write-Host "  PC PAT presence: missing" -ForegroundColor Red
}

# VM PAT check
$vmPatScript = "grep -c '^GITHUB_PERSONAL_ACCESS_TOKEN=ghp_' ~/.hermes/.env 2>/dev/null || grep -c '^GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_' ~/.hermes/.env 2>/dev/null || echo 0"
$vmPat = ssh hermes-gcp@136.115.74.69 $vmPatScript 2>&1
Write-Host "  VM PAT presence count: $vmPat (>=1 = OK)"

# 4. GitHub MCP smoke via gateway dispatch (100% VM-side - secret esta na VM nao no PC)
Write-Host ""
Write-Host "  Smoke GitHub MCP via gateway..."

# Bash script remoto que: extrai secret VM + faz dispatch curl + retorna response
$smokeBash = @"
set -e
SECRET=`$(grep -E '^HERMES_GATEWAY_OAUTH_SECRET=' ~/.hermes/.env | cut -d= -f2-)
if [ -z "`$SECRET" ]; then
  echo "ERRO: HERMES_GATEWAY_OAUTH_SECRET nao encontrado no .env VM"
  exit 1
fi
curl -s -X POST http://localhost:55401/dispatch/github/search_repositories \
  -H "Authorization: Bearer `$SECRET" \
  -H "Content-Type: application/json" \
  -d '{"args": {"query": "owner:caiolea0", "per_page": 3}}'
"@

$smokeBashLF = $smokeBash -replace "`r`n", "`n" -replace "`r", "`n"

$psi2 = New-Object System.Diagnostics.ProcessStartInfo
$psi2.FileName = "ssh"
$psi2.Arguments = "-T -o ConnectTimeout=10 hermes-gcp@136.115.74.69 bash -s"
$psi2.RedirectStandardInput = $true
$psi2.RedirectStandardOutput = $true
$psi2.RedirectStandardError = $true
$psi2.UseShellExecute = $false
$psi2.CreateNoWindow = $true

$proc2 = [System.Diagnostics.Process]::Start($psi2)
$utf8NoBom2 = New-Object System.Text.UTF8Encoding($false)
$bytes2 = $utf8NoBom2.GetBytes($smokeBashLF)
$proc2.StandardInput.BaseStream.Write($bytes2, 0, $bytes2.Length)
$proc2.StandardInput.BaseStream.Flush()
$proc2.StandardInput.Close()
$ghSmoke = $proc2.StandardOutput.ReadToEnd()
$ghErr = $proc2.StandardError.ReadToEnd()
$proc2.WaitForExit()

if ($ghErr) { Write-Host "  STDERR: $ghErr" -ForegroundColor Yellow }

$ghLen = [Math]::Min(400, $ghSmoke.Length)
if ($ghLen -gt 0) {
    $ghSmokeShort = $ghSmoke.Substring(0, $ghLen)
    Write-Host "  Response preview: $ghSmokeShort..." -ForegroundColor Gray
}

if ($ghSmoke -match '"ok":\s*true' -or $ghSmoke -match '"items"' -or $ghSmoke -match '"total_count"') {
    Write-Host "  GitHub MCP: FUNCIONAL OK" -ForegroundColor Green
} elseif ($ghSmoke -match '401|unauthorized|Bad credentials') {
    Write-Host "  GitHub MCP: AUTH FAIL - check PAT scopes (repo+workflow)" -ForegroundColor Red
} elseif ($ghSmoke -match '404|not found') {
    Write-Host "  GitHub MCP: 404 tool name diferente OR endpoint - gateway OK" -ForegroundColor Yellow
} else {
    Write-Host "  GitHub MCP: WARN response inesperado - validar manual" -ForegroundColor Yellow
}

$smokeBash = $null
$smokeBashLF = $null
$bytes2 = $null

# ============================================================
# Cleanup
# ============================================================
$plainToken = $null
$tokenLine = $null
$envContent = $null
$newContent = $null
$ghSmoke = $null
[System.GC]::Collect()

Write-Host ""
Write-Host "=== Setup COMPLETO ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Reporte ao Claude (sessao orquestrador) o output dos checks:" -ForegroundColor Yellow
Write-Host "  - PC PAT presence"
Write-Host "  - VM PAT presence count"
Write-Host "  - GitHub MCP status final"
Write-Host ""
Write-Host "Security:" -ForegroundColor Yellow
Write-Host "  - .env gitignored linha 2 - NAO commitar"
Write-Host "  - Mesma decisao owner formal NIM key (nao rotacionar)"
Write-Host ""
