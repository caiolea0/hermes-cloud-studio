# Hermes — Setup GitHub Personal Access Token (PC + VM automated)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup_github_pat.ps1
#
# Security notes:
# - Token input MASCARADO (Read-Host -AsSecureString — nao aparece terminal)
# - Token transit memoria apenas, NUNCA gravado em arquivo intermediario
# - Token append nos .env destino (.env PC + ~/.hermes/.env VM)
# - .env esta gitignored, NAO sera commitado
# - Smoke validation post-write
# - Memory cleanup garantido fim do script

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Hermes — Setup GitHub PAT (PC + VM) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Este script vai:" -ForegroundColor Yellow
Write-Host "  1. Solicitar seu GitHub PAT (input mascarado, nao eco terminal)"
Write-Host "  2. Adicionar GITHUB_PERSONAL_ACCESS_TOKEN ao .env PC + ~/.hermes/.env VM"
Write-Host "  3. Restart server.py PC + systemd gateway VM"
Write-Host "  4. Smoke validation: confirma PAT presence + GitHub MCP gateway dispatch"
Write-Host ""
Write-Host "Pre-requisitos:" -ForegroundColor Yellow
Write-Host "  - GitHub PAT ja gerado em github.com/settings/tokens"
Write-Host "  - Scopes necessarios: repo + workflow (Classic) OR Contents+PR RW (Fine-grained)"
Write-Host "  - SSH para hermes-gcp@136.115.74.69 funcional"
Write-Host ""

$confirm = Read-Host "Continuar? (s/n)"
if ($confirm -ne "s" -and $confirm -ne "S") {
    Write-Host "Abortado." -ForegroundColor Red
    exit 0
}

Write-Host ""
Write-Host "=== Step 1/4: Solicitar PAT (mascarado) ===" -ForegroundColor Cyan
Write-Host "Cole seu PAT (digitacao NAO aparece terminal por seguranca):"
$secureToken = Read-Host -AsSecureString
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
$plainToken = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)

# Validate format
if (-not ($plainToken.StartsWith("ghp_") -or $plainToken.StartsWith("github_pat_"))) {
    Write-Host ""
    Write-Host "ERRO: Token formato invalido." -ForegroundColor Red
    Write-Host "  Esperado: ghp_xxxxxx (Classic) OR github_pat_xxxxxx (Fine-grained)"
    Write-Host "  Recebido: $($plainToken.Substring(0, [Math]::Min(8, $plainToken.Length)))..."
    $plainToken = $null
    exit 1
}

Write-Host "  Token formato OK ($($plainToken.Substring(0, 8))...)" -ForegroundColor Green

# ============================================================
# Step 2: Update .env PC
# ============================================================
Write-Host ""
Write-Host "=== Step 2/4: Update .env PC ===" -ForegroundColor Cyan

$envPathPC = "D:\dev-projects\main\hermes-cloud-studio\.env"

if (-not (Test-Path $envPathPC)) {
    Write-Host "ERRO: .env PC nao encontrado em $envPathPC" -ForegroundColor Red
    $plainToken = $null
    exit 1
}

# Check if line already exists (replace) OR append new
$envContent = Get-Content $envPathPC -Raw
$tokenLine = "GITHUB_PERSONAL_ACCESS_TOKEN=$plainToken"

if ($envContent -match "(?m)^GITHUB_PERSONAL_ACCESS_TOKEN=") {
    # Replace existing line
    $newContent = $envContent -replace "(?m)^GITHUB_PERSONAL_ACCESS_TOKEN=.*$", $tokenLine
    [System.IO.File]::WriteAllText($envPathPC, $newContent, [System.Text.UTF8Encoding]::new($false))
    Write-Host "  PC .env: linha GITHUB_PERSONAL_ACCESS_TOKEN ATUALIZADA" -ForegroundColor Green
} else {
    # Append new block
    if (-not $envContent.EndsWith("`n")) {
        Add-Content -Path $envPathPC -Value "" -Encoding UTF8
    }
    Add-Content -Path $envPathPC -Value "" -Encoding UTF8
    Add-Content -Path $envPathPC -Value "# F.4.2 GitHub MCP PAT (gitignored, repo+workflow scopes)" -Encoding UTF8
    Add-Content -Path $envPathPC -Value $tokenLine -Encoding UTF8
    Write-Host "  PC .env: linha GITHUB_PERSONAL_ACCESS_TOKEN ADICIONADA" -ForegroundColor Green
}

# Verify
$verifyPC = Select-String -Path $envPathPC -Pattern "^GITHUB_PERSONAL_ACCESS_TOKEN=ghp_|^GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_" -Quiet
if ($verifyPC) {
    Write-Host "  PC verify: token presente .env" -ForegroundColor Green
} else {
    Write-Host "  PC verify: FALHOU — linha nao encontrada apos write" -ForegroundColor Red
    $plainToken = $null
    exit 1
}

# ============================================================
# Step 3: Update VM ~/.hermes/.env via SSH
# ============================================================
Write-Host ""
Write-Host "=== Step 3/4: Update VM ~/.hermes/.env via SSH ===" -ForegroundColor Cyan

# Use heredoc-style stdin pra evitar token no command-line ssh history
$sshCmd = @"
set -e

# Check if line exists
if grep -q '^GITHUB_PERSONAL_ACCESS_TOKEN=' ~/.hermes/.env 2>/dev/null; then
  # Replace existing
  sed -i 's|^GITHUB_PERSONAL_ACCESS_TOKEN=.*|GITHUB_PERSONAL_ACCESS_TOKEN=__TOKEN_PLACEHOLDER__|' ~/.hermes/.env
  echo "  VM .env: linha ATUALIZADA"
else
  # Append new
  echo "" >> ~/.hermes/.env
  echo "# F.4.2 GitHub MCP PAT (gitignored, repo+workflow scopes)" >> ~/.hermes/.env
  echo "GITHUB_PERSONAL_ACCESS_TOKEN=__TOKEN_PLACEHOLDER__" >> ~/.hermes/.env
  echo "  VM .env: linha ADICIONADA"
fi

# Verify
if grep -q '^GITHUB_PERSONAL_ACCESS_TOKEN=ghp_\|^GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_' ~/.hermes/.env; then
  echo "  VM verify: token presente .env"
  # Perms safety check
  chmod 600 ~/.hermes/.env
  echo "  VM perms: 600 (owner-only)"
else
  echo "  VM verify: FALHOU"
  exit 1
fi
"@

# Replace placeholder with real token AND immediately execute (token never persisted)
$sshCmdReal = $sshCmd.Replace("__TOKEN_PLACEHOLDER__", $plainToken)

try {
    $sshOutput = $sshCmdReal | ssh -o ConnectTimeout=10 -o BatchMode=yes hermes-gcp@136.115.74.69 'bash -s' 2>&1
    Write-Host $sshOutput -ForegroundColor Green
} catch {
    Write-Host "  ERRO SSH: $_" -ForegroundColor Red
    $plainToken = $null
    $sshCmdReal = $null
    exit 1
} finally {
    # Cleanup token from local memory ASAP
    $sshCmdReal = $null
}

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
Start-Process -FilePath "python" -ArgumentList "server.py" `
    -WorkingDirectory "D:\dev-projects\main\hermes-cloud-studio" `
    -WindowStyle Hidden `
    -RedirectStandardOutput "logs\server_pat.log" `
    -RedirectStandardError "logs\server_pat.err.log" | Out-Null
Start-Sleep 10

$srvCheck = Get-NetTCPConnection -LocalPort 55000 -State Listen -ErrorAction SilentlyContinue
if ($srvCheck) {
    Write-Host "  PC server: restarted PID $($srvCheck.OwningProcess)" -ForegroundColor Green
} else {
    Write-Host "  PC server: WARN DOWN — check logs\server_pat.err.log" -ForegroundColor Yellow
}

# Restart VM systemd gateway
Write-Host "  VM gateway: restarting systemd..."
$vmRestart = ssh -o ConnectTimeout=5 hermes-gcp@136.115.74.69 "systemctl --user restart hermes-mcps-gateway.service && sleep 3 && systemctl --user is-active hermes-mcps-gateway.service" 2>&1
Write-Host "  VM gateway status: $vmRestart" -ForegroundColor Green

# ============================================================
# Smoke validation
# ============================================================
Write-Host ""
Write-Host "=== Smoke validation ===" -ForegroundColor Cyan

# 1. PC server health
$pcHealth = (Invoke-WebRequest -Uri "http://localhost:55000/health" -UseBasicParsing -ErrorAction SilentlyContinue).StatusCode
Write-Host "  PC :55000 health: $pcHealth"

# 2. VM gateway health
$vmHealth = ssh -o ConnectTimeout=5 hermes-gcp@136.115.74.69 "curl -s -o /dev/null -w '%{http_code}' http://localhost:55401/health" 2>&1
Write-Host "  VM :55401 gateway: $vmHealth"

# 3. PAT presence verify (boolean check sem logar value)
$patPresent = python -c "import os; from dotenv import load_dotenv; load_dotenv(); k = os.getenv('GITHUB_PERSONAL_ACCESS_TOKEN', ''); print('present' if (k.startswith('ghp_') or k.startswith('github_pat_')) else 'missing')"
Write-Host "  PC PAT presence: $patPresent"

$vmPat = ssh hermes-gcp@136.115.74.69 "grep -c '^GITHUB_PERSONAL_ACCESS_TOKEN=ghp_\|^GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_' ~/.hermes/.env" 2>&1
Write-Host "  VM PAT presence: $vmPat (1 = OK)"

# 4. GitHub MCP smoke via gateway dispatch (read-only — list_repos test)
Write-Host ""
Write-Host "  Smoke GitHub MCP via gateway (list_repos read-only)..."
$secret = (Get-Content D:\dev-projects\main\hermes-cloud-studio\.env | Select-String "^HERMES_GATEWAY_OAUTH_SECRET=").ToString().Split("=", 2)[1]
$ghSmoke = ssh hermes-gcp@136.115.74.69 "curl -s -X POST http://localhost:55401/dispatch/github/search_repositories -H 'Authorization: Bearer $secret' -H 'Content-Type: application/json' -d '{\""args\"": {\""query\"": \""owner:caiolea0\"", \""per_page\"": 3}}'" 2>&1
$ghSmokeShort = $ghSmoke.Substring(0, [Math]::Min(300, $ghSmoke.Length))
Write-Host "  Response: $ghSmokeShort..." -ForegroundColor Gray

if ($ghSmoke -match '"ok":\s*true' -or $ghSmoke -match '"items"') {
    Write-Host "  GitHub MCP: FUNCIONAL ✓" -ForegroundColor Green
} elseif ($ghSmoke -match "401|unauthorized") {
    Write-Host "  GitHub MCP: AUTH FAIL — check PAT scopes (repo+workflow)" -ForegroundColor Red
} elseif ($ghSmoke -match "404|tool not found") {
    Write-Host "  GitHub MCP: 404 — tool name diferente, mas gateway dispatch OK" -ForegroundColor Yellow
} else {
    Write-Host "  GitHub MCP: WARN — response inesperado, validar manual" -ForegroundColor Yellow
}

# ============================================================
# Cleanup
# ============================================================
$plainToken = $null
$sshCmd = $null
$sshOutput = $null
$tokenLine = $null
$envContent = $null
$newContent = $null
[System.GC]::Collect()

Write-Host ""
Write-Host "=== Setup COMPLETO ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Proximos passos:" -ForegroundColor Yellow
Write-Host "  1. Cola mensagem CONTINUACAO F.4.2 na sessao dedicada"
Write-Host "  2. Owner Claude re-valida Step 0 (PAT presence + baselines)"
Write-Host "  3. Procede Commits F.4.2 com PAT funcional"
Write-Host ""
Write-Host "Security reminder:" -ForegroundColor Yellow
Write-Host "  - .env esta .gitignored (linha 2) — NAO commitar"
Write-Host "  - Mesmo padrao NVIDIA NIM key (owner decisao formal nao rotacionar)"
Write-Host "  - F.future: rotate manual mensal best practice"
Write-Host ""
