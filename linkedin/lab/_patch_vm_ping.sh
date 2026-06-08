#!/bin/bash
# Patch VM hermes_api.py: add /api/_ping endpoint + bypass auth_middleware
# Re-runnable (idempotente — checa se já tem antes de inserir).

set -e
TARGET=/home/hermes-gcp/.hermes/scripts/hermes_api.py

if grep -q "/api/_ping" "$TARGET"; then
    echo "ALREADY patched (endpoint /api/_ping presente)"
    exit 0
fi

# Backup
cp "$TARGET" "$TARGET.bak.$(date +%s)"

# Insert /api/_ping endpoint just before 'if __name__ == "__main__":'
# Plus bypass auth_middleware for /api/_ping
python3 <<'PYEOF'
import re
path = "/home/hermes-gcp/.hermes/scripts/hermes_api.py"
content = open(path).read()

# 1. Patch auth_middleware (add /api/_ping bypass)
old_mw = """@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):"""
new_mw = """@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # /api/_ping eh probe leve do PC server.py — sem auth pra evitar timeout
    if request.url.path == "/api/_ping":
        return await call_next(request)
    if request.url.path.startswith("/api/"):"""

if old_mw in content:
    content = content.replace(old_mw, new_mw)
    print("[patch] middleware bypass added")
else:
    print("[patch] WARN: middleware pattern nao encontrado — manual review")

# 2. Insert /api/_ping endpoint before "if __name__"
ping_code = '''

@app.get("/api/_ping")
async def vm_ping():
    """Probe leve (~5ms). PC server.py usa pra detectar VM viva sem timeout em /api/dashboard."""
    import time as _t
    return {"ok": True, "ts": _t.time(), "service": "hermes_api"}


'''

if 'if __name__ == "__main__":' in content:
    content = content.replace('if __name__ == "__main__":', ping_code + 'if __name__ == "__main__":')
    print("[patch] /api/_ping endpoint added")
else:
    content += ping_code
    print("[patch] WARN: __main__ nao encontrado — append at end")

open(path, "w").write(content)
print("[patch] file written")
PYEOF

echo "OK — restart hermes_api"
pkill -f hermes_api.py 2>/dev/null || true
sleep 2

# Restart com mesmo wrapper xvfb-run que estava rodando
nohup /bin/sh /usr/bin/xvfb-run --auto-servernum \
    --server-args='-screen 0 1920x1080x24 -ac +extension GLX +render -noreset' \
    /home/hermes-gcp/.hermes/hermes-agent/venv/bin/python3 \
    /home/hermes-gcp/.hermes/scripts/hermes_api.py \
    > /home/hermes-gcp/.hermes/logs/hermes_api_restart.log 2>&1 &
sleep 5

# Verify
ss -ltn | grep ':8420' && echo "PORT LISTENING"
echo '---ping test:---'
curl -s --max-time 3 http://localhost:8420/api/_ping && echo
