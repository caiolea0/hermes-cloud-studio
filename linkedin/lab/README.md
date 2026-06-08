# LinkedIn Lab

Modo descartavel pra testar fingerprint, login e flows sem tocar a conta de producao.

## Princípios

- **Conta cobaia separada** — credentials em `LINKEDIN_LAB_*` no `.env`, NUNCA prod
- **`user_data_dir` isolado** — sufixo `lab_*` (separa de `linkedin_data/profiles/`)
- **Sem proxy** — usa IP residencial nativo do PC (vide STEALTH-PATCHES recomendacao)
- **Headful sempre** — `headless=False` pra visualizar e completar challenges manualmente
- **Trace + screenshots** — todos artefatos em `artifacts/{flow}/{timestamp}/`

## Configurar

```env
LINKEDIN_LAB_EMAIL=milgrauz.exe@gmail.com
LINKEDIN_LAB_PASSWORD='>#AB-Lfk2vG@Uz&g'
LINKEDIN_LAB_ACCOUNT_TYPE=free
```

## Flows

### 1. fingerprint — captura baseline antes de qualquer LinkedIn

Visita 7 sites de fingerprint publicos (CreepJS, browserleaks, tls.peet.ws, bot.sannysoft, etc).
Dumpa fingerprint JS + screenshot + HTML.

```powershell
python -m linkedin.lab.lab_runner --flow fingerprint
# subset:
python -m linkedin.lab.lab_runner --flow fingerprint --sites creepjs,tls_peet
```

**Validacao manual apos rodar**: abrir `artifacts/fingerprint_baseline/{timestamp}/creepjs/screenshot.png`. Score >55 = bom. Lies count = 0-1 ideal. Se mostrar webdriver=true, chrome.runtime ausente em headless, etc — patch necessario antes de tocar LinkedIn.

### 2. login — primeiro login na conta cobaia

Detecta se sessao previa valida (reusa) ou faz login fresh.

```powershell
# Auto-preenche email/senha:
python -m linkedin.lab.lab_runner --flow login

# Pausa pra digitar senha manualmente (mais seguro contra detecção de typing pattern):
python -m linkedin.lab.lab_runner --flow login --manual-password
```

**Cuidado**: conta `milgrauz.exe@gmail.com` foi criada e logada via Brave. Primeiro login no Patchright pode disparar:
- Email verify (passa)
- 2FA (se ativo)
- Challenge "Are you a robot?" (resolve clicando + slider)

Aguardar 180s automaticamente se challenge detectado.

### 3. viewer — teste de profile view com warm-up

Pre-requisito: login OK. Roteiro: feed warm-up -> search -> click profile -> dwell -> screenshot.

```powershell
python -m linkedin.lab.lab_runner --flow viewer --search "designer cuiaba" --profile-index 0
```

Output: `artifacts/viewer_test/{timestamp}/` com trace.zip (abrir via `playwright show-trace`), 3 screenshots, result.json com `detection_signals` (vazio = ok).

## Ordem recomendada de execucao (primeira vez)

```powershell
# 1. Baseline fingerprint (NAO toca LinkedIn ainda)
python -m linkedin.lab.lab_runner --flow fingerprint
# Validar manualmente os artefatos em artifacts/fingerprint_baseline/

# 2. Primeiro login (espere challenge — eh esperado)
python -m linkedin.lab.lab_runner --flow login --manual-password

# 3. Aguardar 24h depois rodar viewer (session age >24h reduz scrutiny)
python -m linkedin.lab.lab_runner --flow viewer

# 4. Re-rodar fingerprint apos login pra ver se mudou:
python -m linkedin.lab.lab_runner --flow fingerprint
```

## Checklist pos-lab antes de prod

- [ ] Fingerprint baseline OK (CreepJS score >55, lies <2)
- [ ] Login passou sem challenge persistente
- [ ] Viewer flow zero `detection_signals` em 3 runs consecutivos
- [ ] li_at persiste apos restart (reuso de session_file)
- [ ] Apos 24h, viewer ainda funciona (li_at nao expirou)

Se 5/5 ok → patches stealth atuais estao saudaveis. Aplicar PATCH-008/014 antes de mover pra producao.

## Anti-padroes

- ❌ Usar lab profile pra outreach (e descartavel)
- ❌ Rodar lab e prod em paralelo no mesmo IP (LinkedIn ve 2 sessoes mesmo IP)
- ❌ Pular fingerprint baseline antes do login
- ❌ Aplicar patches stealth sem rodar lab antes
- ❌ Compartilhar `LINKEDIN_LAB_PASSWORD` ou commitar `.env`
