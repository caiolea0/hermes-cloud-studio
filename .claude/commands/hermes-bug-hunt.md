---
description: Code-review focado em bugs conhecidos Hermes (5 loops race, auth gaps, time import, SQL inj, cleanup)
---

Roda a skill `hermes-bug-hunt` nas 5 dimensoes obrigatorias.
Output: relatorio priorizado salvo em `.claude/BUG-HUNT-{date}.md`.
Cria task TaskCreate por bug Critical.
