---
description: Audit backend↔frontend gap. Re-rodável após cada chapter F.x.
---

Roda a skill `hermes-frontend-gap` pra atualizar `.claude/FRONTEND-GAP.md`.

Sequência (3 scripts determinísticos):

```powershell
python .claude/skills/hermes-frontend-gap/scripts/parse_routes.py
python .claude/skills/hermes-frontend-gap/scripts/grep_frontend.py
python .claude/skills/hermes-frontend-gap/scripts/rank_gaps.py
```

Outputs:
- `.claude/frontend-gap/routes.json` — inventário AST 138+ rotas (PC + VM)
- `.claude/frontend-gap/frontend-consumption.json` — mapa consumo `dashboard/app.js`
- `.claude/frontend-gap/ws-events.json` — handlers vs broadcasts
- `.claude/frontend-gap/diff-vs-known.md` — drift vs execução anterior
- `.claude/FRONTEND-GAP.md` — relatório principal (6 seções)

Quando rodar:
- Inicio fase F (estabelecer baseline)
- Após cada chapter F.2-F.9 fechar (termômetro UX)
- PR review backend sem frontend correspondente (regra GUARDRAILS §F.1)
- Owner pergunta "que botão falta no dashboard"

Sanity asserts (rank_gaps.py):
- routes total ≥ 130
- consumed ≥ 30
- elapsed < 90s

Drift detection:
- `git diff --stat` após rodar deve mostrar APENAS paths sob `.claude/`. Se aparecer outro path = drift acidental, abortar + investigar.
