---
name: hermes-li-lab
description: Testar flow LinkedIn em modo lab seguro (Patchright headful, perfil descartavel, sem tocar conta real). Captura trace + screenshots + classifica deteccao. Use ANTES de aplicar patches stealth/human/limiter em producao. Trigger: "testar flow X", "rodar lab", "/hermes-li-lab".
---

# /hermes-li-lab — Lab mode anti-deteccao

## Princípio
**Nunca testar mudancas anti-deteccao na conta real.** Lab = perfil Chrome novo + IP residencial diferente + observacao isolada.

## Quando disparar
- Antes de aplicar patches do `STEALTH-PATCHES.md`
- Antes de modificar `stealth.py`, `human.py`, ou rate limites
- Quando suspeitar de novo padrao de deteccao

## Setup lab

### Pre-requisitos
- Patchright instalado
- Conta LinkedIn cobaia (NAO a do Caio) — recomendado: criar conta com email descartavel, IP diferente
- Residential SOCKS5 separado do prod

### Estrutura sugerida `linkedin/lab/`
```
linkedin/lab/
  __init__.py
  lab_runner.py       # entrypoint
  flows/
    test_viewer.py    # testa profile view
    test_engage.py    # testa comment
    test_connect.py   # testa invite
  artifacts/          # traces, screenshots, fingerprints
```

## Procedimento

### 1. Snapshot pre-teste
- `git status` linkedin/ — ja commitou patches a testar?
- Lista patches aplicados desde ultimo lab run

### 2. Rodar flow isolado
```python
# Exemplo lab_runner.py uso:
python -m linkedin.lab.lab_runner --flow viewer --profile lab_alpha --trace
```

Lab runner deve:
- Usar perfil user-data-dir NOVO em `~/.lab-profiles/{profile}/`
- Carregar stealth patches + human + limiter atuais
- Habilitar trace Playwright (zip em `artifacts/{timestamp}.zip`)
- Screenshot a cada acao
- Logar fingerprint resultante (canvas hash, WebGL renderer, etc)

### 3. Classificacao deteccao (manual + automatico)
Apos run, verificar:
- [ ] Pagina carregou sem CAPTCHA
- [ ] Sem `unusual activity` banner
- [ ] Sem redirect pra `/checkpoint/`
- [ ] Sem email verify
- [ ] Comportamento esperado (visualizou perfil, comentario apareceu, etc)
- [ ] Fingerprint diferente entre runs (anti-replay)

### 4. Comparar com baseline
Salvar resultado em `linkedin/lab/baselines/{flow}.json`:
```json
{"date": "2026-06-07", "patches_active": [...], "result": "pass|fail", "detection_signals": [...]}
```

Se PASS por 3 runs consecutivos com perfis diferentes -> patch e safe pra producao.

### 5. Deploy producao
Apos PASS triplo: chamar `/hermes-deploy` com confirmacao explicita.

## Sinais de FALHA imediata
- `/checkpoint/challenge` no URL
- `<title>Security Verification</title>`
- Captcha visivel
- Email verify modal
- 999 status code (rate-limit hard)
- Reset de cookies LI

## Output do lab run

```
LI LAB RUN — {timestamp}
Flow: {viewer|engage|connect}
Profile: lab_{name}
Patches ativos: [PATCH-001, PATCH-003, ...]

Resultado: PASS|FAIL|INCONCLUSIVE
Detection signals: {lista}
Fingerprint: canvas={hash}, webgl={renderer}, audio={hash}
Trace artifact: artifacts/{timestamp}.zip

Proximo passo: {repeat|fix patch X|deploy}
```

## Anti-padroes
- Lab com perfil ja "queimado" (deteccao previa) — sempre profile novo
- Lab com IP de prod
- Testar 1 vez so e considerar safe
- Pular fingerprint compare entre runs
