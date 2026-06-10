# F.3.4 Smoke E2E Real — Evidence Summary

**Data execução:** 2026-06-09 22:16-22:18 UTC-3 (02:06-02:07 UTC)
**Run ID:** `aeb103e9c2e94d13`
**Flow:** `fingerprint` (multi-site, 7 sites)

## Triple evidence resumo

### 1. DB row lab_runs (PC hermes_local.db)

```json
{
  "id": "705d093fc3aa4b86bc8a09ead8fc624a",
  "run_id": "aeb103e9c2e94d13",
  "flow": "fingerprint",
  "started_at": 1781057784.985391,
  "completed_at": 1781057869.6344545,
  "status": "success",
  "duration_ms": 84649,
  "artifacts_path": "linkedin/lab/artifacts/aeb103e9c2e94d13",
  "compliance_score": null,
  "fingerprint_hash": null,
  "artifacts": []
}
```

✅ Status `running` → `success` transition observed.
✅ `duration_ms` = 84649 (~85s end-to-end execution).
⚠️ `compliance_score` + `fingerprint_hash` `null` (parsing gap, F.3.followup).
⚠️ `artifacts` array vazio (path mismatch backend ↔ runner, F.3.followup).

### 2. Artifact files VM disk

```
~/linkedin/lab/artifacts/fingerprint_baseline/20260610T020624Z/
├── amiunique/         (3 files)
├── bot_sannysoft/     (3 files)
├── browserleaks_canvas/  (3 files)
├── browserleaks_webgl/   (3 files)
├── creepjs/           (3 files: body.html + fingerprint.json + screenshot.png)
├── fingerprint_pro_demo/ (3 files)
├── tls_peet/          (3 files)
└── summary.json       (768 linhas, 25KB)

Total: 22 arquivos, 5.6MB.
```

✅ Multi-site fingerprint completo (7 sites + summary).
✅ Per-site: screenshot.png + fingerprint.json + body.html.
✅ summary.json agrega fingerprint cross-site.

Sample fingerprint (creepjs site):
- `userAgent`: `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ... Chrome/149.0.0.0`
- `webdriver`: `false` (✅ stealth ativo)
- `webgl.unmasked_vendor`: `Google Inc. (Google)`
- `language`: `pt-BR`
- `timezone_intl`: `America/Cuiaba`

### 3. WebSocket events

Distinct types capturados: **2** (de 6 esperados).

```
[lab.run_started]   count=1
[lab.step_progress] count=3
```

⚠️ Eventos faltantes (parsing gap F.3.1/F.3.2 integration):
- `lab.screenshot_captured`
- `lab.compliance_score`
- `lab.fingerprint_dump`
- `lab.run_completed`

## Pipeline end-to-end validado

```
PC frontend (HermesLabCockpit)
    ↓ POST /api/lab/start {flow: fingerprint}
PC backend api/lab.py
    ↓ INSERT lab_runs row (status=running)
    ↓ SSH dispatch hermes-gcp@VM
VM lab_runner (xvfb-run -a python3 -m linkedin.lab.lab_runner --flow fingerprint)
    ↓ Patchright headful (1280x1024)
    ↓ visit 7 fingerprint sites
    ↓ capture screenshot + DOM + JS fingerprint
    ↓ stdout JSON events (lab.run_started + lab.step_progress)
PC backend parse events
    ↓ WS broadcast (handlers F.3.3 frontend)
    ↓ UPDATE lab_runs (status=success, duration_ms)
VM filesystem (artifacts persisted, 22 files, 5.6MB)
```

✅ POST endpoint funciona.
✅ SSH async dispatch funciona.
✅ lab_runner executa full multi-site flow.
✅ DB transitions running→success.
✅ Artifacts persisted disk VM.
✅ WS broadcast funciona (parcial — 2 de 6 event types).
⚠️ Backend event parsing layer missing 4 event types.
⚠️ artifacts_path mismatch (DB: `linkedin/lab/artifacts/{run_id}`, runner: `linkedin/lab/artifacts/{flow_baseline}/{timestamp}/`).

## F.3.followup tracked (não-blocker F.3.4)

- **FOLLOWUP-1 — event parsing extension**: api/lab.py parse handler precisa extrair
  screenshot_captured + compliance_score + fingerprint_dump + run_completed do stdout
  JSON do lab_runner. Hoje só emite run_started + step_progress.
- **FOLLOWUP-2 — artifacts path reconciliation**: DB `artifacts_path` aponta pra
  run_id-named dir, mas lab_runner escreve em `{flow_baseline}/{timestamp}/`. Path
  sync precisa: ou backend usa convenção runner, ou runner aceita `--out-dir` flag
  com path do backend.
- **FOLLOWUP-3 — compliance_score extraction**: lab_runner summary.json hoje não
  computa overall compliance score. Adicionar agregação cross-site no runner OR
  pos-processing backend.
- **FOLLOWUP-4 — fingerprint_hash computation**: hash agregado dos fingerprints
  cross-site pra detection diff entre runs. Hash SHA256 dos fingerprints concatenados.

Todos FOLLOWUP-* não bloqueiam F.3.4 closeout — pipeline funciona end-to-end.
Endereçar como F.3.followup hotfix sessão dedicada OU início de F.4.

## Files evidence local-only (.claude/_snapshots/f34_smoke/, gitignored)

- `api_start_response.json` — POST /api/lab/start response
- `db_run_detail.json` — GET /api/lab/runs/{id} response final
- `ws_events_observed.txt` — WS subscriber output
- `vm_artifacts.txt` — VM disk artifacts listing
- `vm_summary_stats.txt` — file count + total size
