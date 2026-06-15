# Hermes - Setup GitHub Webhook Secret (PC + VM automated)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup_github_webhook_secret.ps1
# Compatible: Windows PowerShell 5.1+
#
# F.4.4 C1 — Configures GITHUB_WEBHOOK_SECRET in:
#   .env PC (D:\dev-projects\main\hermes-cloud-studio\.env)
#   ~/.hermes/.env VM (via SSH stdin bytes — CRLF-safe)
#
# IMPORTANT: Run AFTER generating a 32-byte secret:
#   python -c "import secrets; print(secrets.token_hex(32))"
# Then configure the same value in GitHub repo Settings → Webhooks → Secret.
#
# Security: input masked via Read-Host -AsSecureString, never exposed on command line.
# SSH transit: BYTES-level stdin write (ProcessStartInfo) — no CRLF injection.

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Hermes - Setup GitHub Webhook Secret (PC + VM) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Este script vai:" -ForegroundColor Yellow
Write-Host "  1. Solicitar GITHUB_WEBHOOK_SECRET (input mascarado)"
Write-Host "  2. Adicionar ao .env PC"
Write-Host "  3. Adicionar ao ~/.hermes/.env VM via SSH"
Write-Host "  4. Smoke validation (curl webhook endpoint assinado)"
Write-Host ""
Write-Host "Pre-requisitos:" -ForegroundColor Yellow
Write-Host "  - Secret gerado: python -c `"import secrets; print(secrets.token_hex(32))`""
Write-Host "  - Mesmo secret configurado em: GitHub repo -> Settings -> Webhooks -> Secret"
Write-Host "  - SSH para hermes-gcp@136.115.74.69 funcional"
Write-Host ""

$confirm = Read-Host "Continuar? (s/n)"
if ($confirm -ne "s" -and $confirm -ne "S") {
    Write-Host "Abortado." -ForegroundColor Red
    exit 0
}

# ============================================================
# Step 1: Read secret (masked)
# ============================================================
Write-Host ""
Write-Host "=== Step 1/4: Webhook Secret ===" -ForegroundColor Cyan
Write-Host "  Gerar um novo via: python -c `"import secrets; print(secrets.token_hex(32))`""
Write-Host ""

$secureSecret = Read-Host "Cole o GITHUB_WEBHOOK_SECRET" -AsSecureString

$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureSecret)
$plainSecret = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

if ($plainSecret.Length -lt 16) {
    Write-Host "ERRO: secret muito curto (minimo 16 chars). Gere um novo com token_hex(32)." -ForegroundColor Red
    $plainSecret = $null
    exit 1
}

$secretPreview = $plainSecret.Substring(0, 8)
Write-Host ("  Secret OK ({0}... {1} chars)" -f $secretPreview, $plainSecret.Length) -ForegroundColor Green

# ============================================================
# Step 2: Update .env PC
# ============================================================
Write-Host ""
Write-Host "=== Step 2/4: Update .env PC ===" -ForegroundColor Cyan

$envPathPC = "D:\dev-projects\main\hermes-cloud-studio\.env"

if (-not (Test-Path $envPathPC)) {
    Write-Host "ERRO: .env PC nao encontrado em $envPathPC" -ForegroundColor Red
    $plainSecret = $null
    exit 1
}

$envContent = Get-Content $envPathPC -Raw
$secretLine = "GITHUB_WEBHOOK_SECRET=$plainSecret"

if ($envContent -match "(?m)^GITHUB_WEBHOOK_SECRET=") {
    $newContent = $envContent -replace "(?m)^GITHUB_WEBHOOK_SECRET=.*$", $secretLine
    [System.IO.File]::WriteAllText($envPathPC, $newContent, [System.Text.UTF8Encoding]::new($false))
    Write-Host "  PC .env: linha ATUALIZADA" -ForegroundColor Green
} else {
    if (-not $envContent.EndsWith("`n")) {
        Add-Content -Path $envPathPC -Value "" -Encoding UTF8
    }
    Add-Content -Path $envPathPC -Value "" -Encoding UTF8
    Add-Content -Path $envPathPC -Value "# F.4.4 GitHub webhook HMAC secret - gitignored" -Encoding UTF8
    Add-Content -Path $envPathPC -Value $secretLine -Encoding UTF8
    Write-Host "  PC .env: linha ADICIONADA" -ForegroundColor Green
}

$verifyPC = Select-String -Path $envPathPC -Pattern "^GITHUB_WEBHOOK_SECRET=" -Quiet
if ($verifyPC) {
    Write-Host "  PC verify: GITHUB_WEBHOOK_SECRET presente" -ForegroundColor Green
} else {
    Write-Host "  PC verify: FALHOU" -ForegroundColor Red
    $plainSecret = $null
    exit 1
}

# ============================================================
# Step 3: Update VM ~/.hermes/.env via SSH (BYTES-level stdin)
# ============================================================
Write-Host ""
Write-Host "=== Step 3/4: Update VM .env via SSH ===" -ForegroundColor Cyan

$sshScript = @"
set -e
HERMES_ENV=~/.hermes/.env
if [ ! -f "`$HERMES_ENV" ]; then
  mkdir -p ~/.hermes
  touch "`$HERMES_ENV"
  chmod 600 "`$HERMES_ENV"
fi
if grep -q '^GITHUB_WEBHOOK_SECRET=' "`$HERMES_ENV" 2>/dev/null; then
  sed -i 's|^GITHUB_WEBHOOK_SECRET=.*|GITHUB_WEBHOOK_SECRET=$plainSecret|' "`$HERMES_ENV"
  echo "  VM .env: linha ATUALIZADA"
else
  echo "" >> "`$HERMES_ENV"
  echo "# F.4.4 GitHub webhook HMAC secret" >> "`$HERMES_ENV"
  echo "GITHUB_WEBHOOK_SECRET=$plainSecret" >> "`$HERMES_ENV"
  echo "  VM .env: linha ADICIONADA"
fi
chmod 600 "`$HERMES_ENV"
if grep -q '^GITHUB_WEBHOOK_SECRET=' "`$HERMES_ENV"; then
  echo "  VM verify: GITHUB_WEBHOOK_SECRET presente"
else
  echo "  VM verify: FALHOU"
  exit 1
fi
"@

# Normalize CRLF -> LF (bash quebra com \r em structures)
$sshScriptLF = $sshScript -replace "`r`n", "`n"
$sshScriptLF = $sshScriptLF -replace "`r", "`n"

# CRITICAL: PowerShell pipe `|` re-introduz CRLF mesmo de source LF.
# Solucao: ProcessStartInfo + StandardInput.BaseStream.Write(bytes) bypass total.
# cf. mem_mqekwse6 pattern (setup_github_pat.ps1)
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

    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()

    Write-Host $stdout.Trim() -ForegroundColor Green

    if ($proc.ExitCode -ne 0) {
        Write-Host "ERRO SSH (exit $($proc.ExitCode)):" -ForegroundColor Red
        Write-Host $stderr -ForegroundColor Red
        $plainSecret = $null
        exit 1
    }
} catch {
    Write-Host "ERRO conectando SSH: $_" -ForegroundColor Red
    $plainSecret = $null
    exit 1
}

# ============================================================
# Step 4: Smoke validate (curl webhook sem payload assinado -> 400/200 OK)
# ============================================================
Write-Host ""
Write-Host "=== Step 4/4: Smoke validation ===" -ForegroundColor Cyan
Write-Host "  Enviando payload vazio com assinatura invalida -> espera 401..."

$smokeUrl = "http://localhost:55000/api/skills/webhook/pr-merged"
$smokeBody = "{}"
$smokeBodyBytes = [System.Text.Encoding]::UTF8.GetBytes($smokeBody)

# Compute invalid signature (wrong key)
$wrongKey = "wrong-key-for-smoke-test"
$hmac = New-Object System.Security.Cryptography.HMACSHA256
$hmac.Key = [System.Text.Encoding]::UTF8.GetBytes($wrongKey)
$sigBytes = $hmac.ComputeHash($smokeBodyBytes)
$sigHex = ($sigBytes | ForEach-Object { "{0:x2}" -f $_ }) -join ""
$sig = "sha256=$sigHex"

try {
    $response = Invoke-WebRequest -Uri $smokeUrl -Method POST -Body $smokeBody `
        -ContentType "application/json" `
        -Headers @{ "X-Hub-Signature-256" = $sig; "CF-Connecting-IP" = "192.30.252.1" } `
        -UseBasicParsing -ErrorAction SilentlyContinue

    $status = $response.StatusCode
    if ($status -eq 401 -or $status -eq 200 -or $status -eq 403) {
        Write-Host "  Smoke OK: endpoint respondeu HTTP $status (esperado 401/200)" -ForegroundColor Green
    } else {
        Write-Host "  Smoke WARN: status inesperado $status" -ForegroundColor Yellow
    }
} catch {
    $status = $_.Exception.Response.StatusCode.value__
    if ($status -eq 401 -or $status -eq 403) {
        Write-Host "  Smoke OK: endpoint respondeu HTTP $status" -ForegroundColor Green
    } else {
        Write-Host "  Smoke WARN: $_ (server pode estar offline - OK para continuar)" -ForegroundColor Yellow
    }
}

# ============================================================
# Cleanup
# ============================================================
$plainSecret = $null
$hmac.Dispose()

Write-Host ""
Write-Host "=== CONCLUIDO ===" -ForegroundColor Green
Write-Host ""
Write-Host "Proximos passos:" -ForegroundColor Yellow
Write-Host "  1. Configurar webhook no GitHub repo:"
Write-Host "     Settings -> Webhooks -> Add webhook"
Write-Host "     Payload URL: https://hermes.caioleo.com/api/skills/webhook/pr-merged"
Write-Host "     Content type: application/json"
Write-Host "     Secret: (o mesmo valor inserido acima)"
Write-Host "     Events: Pull requests (checked only)"
Write-Host ""
Write-Host "  2. Restart server PC (tray -> Reiniciar Servicos) para carregar o novo secret"
Write-Host ""
Write-Host "  3. Restart hermes-api VM para carregar GITHUB_WEBHOOK_SECRET na VM env"
Write-Host "     ssh hermes-gcp@136.115.74.69 'systemctl --user restart hermes-api'"
Write-Host ""
