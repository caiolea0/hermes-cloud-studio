# Hermes LinkedIn Sync — Extension

Captura em tempo real o cookie `li_at` do LinkedIn e envia pra VM Hermes.

## Por que essa extension existe?

O script `scripts/li_at_sync.py` lê o cookie direto do SQLite do Chrome/Brave, mas Brave (e Chrome 100+) usa **lock exclusivo** no arquivo enquanto está aberto. Sem admin, é impossível ler.

A extension contorna o lock totalmente: usa `chrome.cookies` API que dá acesso direto, sem precisar tocar no SQLite. Funciona com Brave/Chrome abertos.

## Como instalar (Chrome, Brave, Edge, ou qualquer Chromium)

1. Abra `chrome://extensions/` (Brave: `brave://extensions/`, Edge: `edge://extensions/`)
2. Liga o **Modo desenvolvedor** (toggle canto superior direito)
3. Click **Carregar sem compactação**
4. Selecione `D:\dev-projects\main\hermes-cloud-studio\extension\`
5. Extension instalada — ícone roxo "H" aparece na barra

## Como funciona

- **Ao instalar**: roda sync inicial (captura cookie atual, envia se diferente do último)
- **Real-time**: ouve `chrome.cookies.onChanged` — quando LinkedIn rotaciona o `li_at`, envia em segundos
- **Safety net**: alarm a cada 30 min re-checa (caso algum evento seja perdido)
- **Manual**: click no ícone → "Sincronizar agora"

## Popup status

Mostra:
- ✅/❌ Cookie capturado
- Última sync (timestamp + trigger: install/change/alarm/popup)
- Status: rotacionado / sem mudança / erro

## Endpoint

POSTa pra `http://localhost:55000/api/internal/li_at_rotate` com `{li_at: "..."}`.
Server local forward pra VM com token `HERMES_VM_AUTH_TOKEN` (header `X-Hermes-Token`).

## Combinado com Task Scheduler

A extension cuida do **real-time**. O cron diário às 03:00 (Task Scheduler) é o **failsafe**:
- Se a extension foi removida/desabilitada → cron pega
- Se o Brave foi fechado e ficou semanas offline → cron pega o cookie do Chrome/Edge ao reabrir

## Permissões pedidas

- `cookies` — ler `li_at`
- `storage` — guardar último cookie sincronizado pra não fazer POST duplicado
- `alarms` — agendar safety-net 30 min
- `host_permissions` linkedin.com e localhost:55000

Tudo zero-tracking, zero-fingerprint, código auditável (`background.js` ~50 linhas).
