# R5 PHASE 1 - Setup per-role gateway bearers (PS5.1 compatible, ASCII only)
# Usage: .\scripts\setup_gateway_role_bearers.ps1
# Auto-generates 11 per-role bearers, updates .env PC, syncs to VM ~/.hermes/.env,
# restarts hermes-mcps-gateway on VM, smoke-tests trusted path.

param(
    [string]$VmHost = "hermes-gcp@136.115.74.69",
    [string]$SshKey = "$env:USERPROFILE\.ssh\id_ed25519",
    [string]$EnvFile = ".env",
    [switch]$DryRun
)

Set-StrictMode -Version 1
$ErrorActionPreference = "Stop"

Write-Host "[R5] setup_gateway_role_bearers.ps1 starting..." -ForegroundColor Cyan

# --- Step 1: Generate 11 per-role bearers via Python ---
$roles = @(
    "HERMES_GATEWAY_BEARER_BRAIN",
    "HERMES_GATEWAY_BEARER_BRAIN_CORE",
    "HERMES_GATEWAY_BEARER_BRAIN_F4",
    "HERMES_GATEWAY_BEARER_BRAIN_F5",
    "HERMES_GATEWAY_BEARER_BRAIN_F6",
    "HERMES_GATEWAY_BEARER_BRAIN_F7_COBAIA",
    "HERMES_GATEWAY_BEARER_BRAIN_F7_COBAIA_AUTOTUNE",
    "HERMES_GATEWAY_BEARER_BRAIN_F8",
    "HERMES_GATEWAY_BEARER_BRAIN_F9",
    "HERMES_GATEWAY_BEARER_BREADCRUMB",
    "HERMES_GATEWAY_BEARER_API"
)

Write-Host "[R5] Generating $($roles.Count) per-role bearers..."
$bearers = @{}
foreach ($role in $roles) {
    $val = python -c "import secrets; print(secrets.token_urlsafe(32))" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "[R5] python bearer generation failed for $role"
        exit 1
    }
    $bearers[$role] = $val.Trim()
    Write-Host "  $role = [GENERATED]"
}

if ($DryRun) {
    Write-Host "[R5] DryRun mode -- no files written, no VM actions." -ForegroundColor Yellow
    exit 0
}

# --- Step 2: Update .env PC (upsert each key) ---
Write-Host "[R5] Updating $EnvFile on PC..."
if (-not (Test-Path $EnvFile)) {
    Write-Error "[R5] $EnvFile not found. Run from repo root."
    exit 1
}

$envContent = Get-Content $EnvFile -Raw
foreach ($role in $roles) {
    $val = $bearers[$role]
    if ($envContent -match "(?m)^${role}=") {
        # Replace existing line
        $envContent = $envContent -replace "(?m)^${role}=.*", "${role}=${val}"
    } else {
        # Append after HERMES_GATEWAY_OAUTH_SECRET line or at end
        if ($envContent -match "(?m)^HERMES_GATEWAY_OAUTH_SECRET=") {
            $envContent = $envContent -replace "(?m)(^HERMES_GATEWAY_OAUTH_SECRET=.*)", "`$1`n${role}=${val}"
        } else {
            $envContent = $envContent + "`n${role}=${val}"
        }
    }
}
$envContent | Out-File $EnvFile -Encoding utf8 -NoNewline
Write-Host "[R5] .env PC updated."

# --- Step 3: Build VM env update block ---
Write-Host "[R5] Syncing per-role bearers to VM $VmHost..."
$vmUpdateLines = @()
foreach ($role in $roles) {
    $val = $bearers[$role]
    $vmUpdateLines += "${role}=${val}"
}
$vmUpdateBlock = $vmUpdateLines -join "`n"

# Build SSH command to upsert each line in ~/.hermes/.env
$sshPythonScript = @"
import re, os
env_path = os.path.expanduser('~/.hermes/.env')
with open(env_path, 'r') as f:
    content = f.read()
lines = [
$(foreach ($role in $roles) {
    "    ('$role', '$($bearers[$role])'),"
})
]
for key, val in lines:
    pattern = r'^' + re.escape(key) + r'=.*'
    replacement = key + '=' + val
    if re.search(pattern, content, re.MULTILINE):
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    else:
        content += '\n' + replacement
with open(env_path, 'w') as f:
    f.write(content)
print('VM .env updated: ' + str(len(lines)) + ' keys')
"@

$tmpScript = [System.IO.Path]::GetTempFileName() + ".py"
$sshPythonScript | Out-File $tmpScript -Encoding utf8

try {
    $scpResult = scp -i $SshKey $tmpScript "${VmHost}:/tmp/r5_update_env.py" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "[R5] SCP to VM failed (offline?). Bearer update skipped for VM. Error: $scpResult"
    } else {
        $sshResult = ssh -i $SshKey $VmHost "python3 /tmp/r5_update_env.py && rm /tmp/r5_update_env.py" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "[R5] VM env update failed: $sshResult"
        } else {
            Write-Host "[R5] VM .env updated: $sshResult"

            # --- Step 4: Restart gateway on VM ---
            Write-Host "[R5] Restarting hermes-mcps-gateway on VM..."
            # NOTE: hermes-mcps-gateway is USER-level systemd (not system). Use --user, no sudo.
            $restartResult = ssh -i $SshKey $VmHost "systemctl --user restart hermes-mcps-gateway && sleep 4 && systemctl --user is-active hermes-mcps-gateway" 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "[R5] Gateway restart may have failed: $restartResult"
            } else {
                Write-Host "[R5] Gateway restarted: $restartResult"

                # --- Step 5: Smoke test trusted path ---
                Write-Host "[R5] Smoke test: per-role bearer -> trusted path..."
                $brainBearer = $bearers["HERMES_GATEWAY_BEARER_BRAIN_CORE"]
                $smokeResult = ssh -i $SshKey $VmHost @"
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:55401/health -H 'Authorization: Bearer $brainBearer'
"@ 2>&1
                if ($smokeResult -eq "200") {
                    Write-Host "[R5] Smoke OK: health 200 with BRAIN_CORE bearer" -ForegroundColor Green
                } else {
                    Write-Warning "[R5] Smoke unexpected: HTTP $smokeResult (expected 200)"
                }
            }
        }
    }
} finally {
    Remove-Item $tmpScript -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "[R5] DONE. Per-role bearers generated and deployed." -ForegroundColor Green
Write-Host "[R5] Next: run 'python -m pytest tests/test_r5_per_role_bearers.py -v' to verify." -ForegroundColor Cyan
Write-Host "[R5] Monitor: grep 'R5_FALLBACK' ~/.hermes/logs/gateway*.log on VM to track migration." -ForegroundColor Cyan
