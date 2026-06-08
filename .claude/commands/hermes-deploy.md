---
description: Sync seletivo PC→VM com SSH dry-run + rsync + restart + health check + rollback
argument-hint: "[target: linkedin|skills|daemon|scripts|all]"
---

Roda a skill `hermes-deploy`. Se houver argumento, restringe sync ao target especificado.
Sempre faz dry-run SSH antes. Sempre health-check pos-deploy. Rollback automatico se health falhar.
