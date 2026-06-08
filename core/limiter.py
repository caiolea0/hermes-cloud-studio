"""Hermes Cloud Studio — slowapi rate-limiter compartilhado (MERGED-020).

Singleton Limiter pra evitar duplicacao em routers. server.py wirea o handler
de excecao + app.state.limiter no bootstrap.

Endpoints aplicam via decorator:
    from core.limiter import limiter

    @router.post("/api/server/restart-local")
    @limiter.limit("2/hour")
    async def server_restart_local(request: Request):
        ...

NOTA: o param `request: Request` na assinatura eh obrigatorio (slowapi le ele
pra key + rate counter). Endpoints com decorador mas sem Request explodem em
runtime com erro pouco claro — sempre adicionar.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Loopback bind: get_remote_address sempre retorna 127.0.0.1 nesse setup.
# Como o risco real eh DoS via loop curl/programatico no proprio host,
# rate-limit global por endpoint (key fixo) tambem faria sentido. Por ora
# get_remote_address eh suficiente — se extension/Tauri rodarem em host
# diferente, IPs distintos contam separado (defensivo).
limiter = Limiter(key_func=get_remote_address)
