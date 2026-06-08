---
name: hermes-deploy
description: Sync seletivo PC→VM com SSH dry-run, rsync, restart services, health check e rollback se falhar. Use quando user diz "deploy VM", "sync VM", "/hermes-deploy", ou apos editar arquivos que rodam na VM (hermes_api_v2.py, daemon/, scripts/, linkedin/, skills/).
---

# /hermes-deploy — PC -> VM sync seguro

## Quando disparar
- Apos editar codigo que roda na VM
- User pede "deploy", "sync VM"
- Apos editar skill YAML em `skills/`

## Quando NAO disparar
- Edicao em `dashboard/`, `app/`, `server.py` (PC-only)
- Edicao em `mcps/` (local)
- Sem confirmacao explicita do user pra deploy

## Procedimento determinístico

### 1. Mapear arquivos a sincronizar
Compare mtime local vs ultimo deploy (rastrear em `.claude/.last-deploy.json`):
```
Arquivos VM-target:
- hermes_api_v2.py -> ~/hermes_api_v2.py
- daemon/ -> ~/daemon/
- scripts/ -> ~/scripts/
- linkedin/ -> ~/linkedin/  (cuidado: stealth.py, human.py, limiter.py — testar lab antes!)
- skills/ -> ~/.hermes/skills/
- gosom_scraper.py -> ~/gosom_scraper.py
- night_scraper.py -> ~/night_scraper.py
```

### 2. Dry-run SSH (sempre, antes de qualquer rsync)
```powershell
ssh hermes-gcp@136.115.74.69 "ls ~/hermes_api_v2.py && systemctl --user status hermes-api"
```

### 3. Rsync seletivo (so o que mudou)
```powershell
# Exemplo skill:
scp skills/linkedin-engagement.yaml hermes-gcp@136.115.74.69:~/.hermes/skills/
# Exemplo modulo:
rsync -avz --delete linkedin/ hermes-gcp@136.115.74.69:~/linkedin/
```

### 4. Restart service na VM
```powershell
ssh hermes-gcp@136.115.74.69 "systemctl --user restart hermes-api"
# Ou: ssh ... "pkill -f hermes_api_v2 && cd ~ && nohup python3 hermes_api_v2.py > logs/api.log 2>&1 &"
```

### 5. Health check pos-deploy
Aguardar 5s, depois:
```powershell
curl -H "X-Hermes-Token: $env:HERMES_AUTH_TOKEN" http://localhost:8500/api/hermes/status
# Validar que VM voltou
```

### 6. Rollback se health falhar
- SSH na VM, restaurar backup `~/.hermes/backups/{timestamp}/`
- Restart
- Reportar falha pro user com log

### 7. Persistir deploy log
Update `.claude/.last-deploy.json`:
```json
{"timestamp": "2026-06-07T12:34", "files": [...], "result": "ok|rollback"}
```

## Confirmacoes obrigatorias (NAO ASSUMIR)
- **stealth.py / human.py / limiter.py**: testar em lab antes (`/hermes-li-lab`). Deploy direto = risco de ban.
- **Migrations DB**: sempre pedir confirmacao + backup `~/.hermes/data/command_center.db.bak`
- **Restart com daemon running**: pausar daemon antes (`hermes-control daemon_control(pause)`)

## Anti-padroes
- Sync `linkedin/` sem teste lab
- Skipar dry-run "porque ja sei o que tem na VM"
- Restart sem health check
- Deploy quando session LI esta em campaign-running (interrompe campanha)
