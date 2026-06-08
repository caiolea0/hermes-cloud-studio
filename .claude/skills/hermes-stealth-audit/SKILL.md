---
name: hermes-stealth-audit
description: Auditoria pontual dos modulos anti-deteccao LinkedIn (stealth.py, human.py, limiter.py, cooldown.py) cruzando com tecnicas atuais de deteccao. Versao leve da skill — pra varredura DEEP usar workflow linkedin-anti-detection-sweep. Trigger: "audit stealth", "checar anti-deteccao", "/hermes-stealth-check".
---

# /hermes-stealth-audit — Auditoria leve anti-deteccao

## Diferenca vs workflow
| | Skill `/hermes-stealth-audit` | Workflow `linkedin-anti-detection-sweep` |
|---|---|---|
| Custo | ~5-10k tokens | 120-200k tokens |
| Tempo | 2-5 min | 15-30 min |
| Profundidade | Checklist + 3-5 highlights | Pesquisa cross-source + 10-15 patches verificados |
| Quando | Check rapido pre-deploy | Sweep completo trimestral |

## Quando disparar
- Pre-deploy de mudanca em `linkedin/`
- Suspeita de regressao stealth
- Apos atualizar Patchright/Playwright

## Procedimento

### 1. Inventario rapido
```
linkedin/
  stealth.py    -> 11 patches JS
  human.py      -> mouse, typing, reading, overshoot
  limiter.py    -> rate, warm-up, working hours, cooldown
  cooldown.py   -> probe /feed via SOCKS5
  account_detector.py
```

### 2. Checklist por arquivo

#### `stealth.py` — 11 patches
- [ ] webdriver=false aplicado em context, nao so page
- [ ] window.chrome com loadTimes() retornando valores realistas
- [ ] navigator.plugins lista realista (3+ plugins comuns)
- [ ] languages=`['pt-BR', 'pt', 'en-US', 'en']` consistente com timezone
- [ ] platform=`Win32` (NAO `MacIntel` se UA Windows)
- [ ] hardwareConcurrency e deviceMemory NAO sao 0 nem improvaveis
- [ ] WebGL vendor/renderer = combinacao real (GTX 1660 + NVIDIA OK)
- [ ] Canvas noise determinístico por sessao (nao random a cada call)
- [ ] WebRTC IP leak: RTCPeerConnection retorna `[]` candidates
- [ ] Function.prototype.toString masking aplicado aos overrides
- [ ] Patches aplicados em `add_init_script` (nao `evaluate` runtime)

#### `human.py`
- [ ] Bezier mouse: 3+ control points, jitter gaussiano
- [ ] Typing: bigram timing (alguns pares mais rapidos que outros)
- [ ] Click offset gaussiano do centro do elemento (nao centro morto)
- [ ] Reading sim: distribuicao real 35/30/20/15
- [ ] Overshoot 10-15% (nao 0%, nao 50%)
- [ ] Idle entre acoes: variancia, nao constante

#### `limiter.py`
- [ ] Warm-up: ramp suave (nao step function)
- [ ] Working hours respeitado (America/Cuiaba)
- [ ] Cooldown 30min entre campaigns enforced
- [ ] Break apos N acoes — N varia (nao sempre 25)
- [ ] WAL mode em SQLite
- [ ] Sem possibilidade de burlar via reset DB

#### `cooldown.py`
- [ ] Probe via SOCKS5 (nao IP do PC)
- [ ] Cache TTLs corretos: ok=5min, cooldown=30min, challenge=10min
- [ ] Estado persiste em disco (sobrevive restart)

### 3. Smoke checks adicionais
- [ ] User-Agent UA-CH headers consistentes com `platform`
- [ ] Viewport realista (1920x1080, 1366x768, etc — nao 800x600)
- [ ] Timezone JS = America/Cuiaba se proxy BR
- [ ] Locale `pt-BR` consistente em headers e navigator

### 4. Output esperado

```
STEALTH AUDIT — {timestamp}

stealth.py        : OK 9/11 — PATCH-X falta, PATCH-Y deprecated
human.py          : OK 4/6 — overshoot fora da faixa, idle constante
limiter.py        : OK 5/5
cooldown.py       : OK 3/3

ACOES sugeridas:
1. {priority} {action}
2. ...

Recomendado: rodar workflow linkedin-anti-detection-sweep antes de novo deploy
```

## Quando escalar pro workflow
- Skill aponta >5 acoes
- Apos campanha bloqueada
- Pre-deploy em mudancas grandes
- Quarterly review
