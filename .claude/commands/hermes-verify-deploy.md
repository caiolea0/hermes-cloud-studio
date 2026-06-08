---
description: Verifica VM apos deploy (SSH + services + endpoints + DB + logs + LI session)
---

Invoca subagent `vm-deploy-verifier`. Executa 7 checks sequenciais e reporta:
DEPLOY OK | DEPLOY DEGRADED | DEPLOY FAILED.
Se FAILED, sugere rollback (nao executa sem confirmacao).
