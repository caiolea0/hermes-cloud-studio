---
description: Inicia fase do IMPLEMENTATION-PLAN com pré-requisitos automatizados + persistência
argument-hint: "<A|B|C|D|E>"
---

Leia `.claude/HOW-TO-START-PHASE.md` no projeto. Execute os 7 pré-requisitos em paralelo,
reporte baseline da `python scripts/validate_implementation.py --phase $1`, aguarde
confirmação do owner antes de mexer em código.

Lembre: persistência obrigatória ao longo (mark_chapter + TaskCreate + memory_save +
PLAN update + GUARDRAILS update + validation script). Anti-padrões em
`.claude/IMPLEMENTATION-PLAN.md` "Convenções desta sessão de implementação".
