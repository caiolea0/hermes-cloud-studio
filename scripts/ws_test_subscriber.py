"""F.2.3 — WebSocket smoke test subscriber.

Conecta no /ws do server.py local, filtra eventos por tipo, conta distintos.
Exit 0 se >=3 tipos distintos recebidos antes do timeout; exit 1 se timeout sem matches.

Uso:
    python scripts/ws_test_subscriber.py \\
        --types daemon.subsystem_status,daemon.log_event,daemon.decision \\
        --timeout 60

Auth: HERMES_AUTH_TOKEN do .env (mesmo token que dashboard usa via ?token=).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from urllib.parse import quote

# Windows cp1252 console: force utf-8 stdout/stderr pra evitar UnicodeEncodeError em emojis/setas.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import websockets
except ImportError:
    print("[ws_test_subscriber] FATAL: pip install websockets", file=sys.stderr)
    sys.exit(2)

from dotenv import load_dotenv

load_dotenv()


async def listen(url: str, wanted: set[str], timeout: float, min_distinct: int) -> int:
    deadline = time.monotonic() + timeout
    seen: dict[str, int] = {}
    print(f"[ws_test_subscriber] connecting -> {url.split('?')[0]} (token redacted)")
    print(f"[ws_test_subscriber] filtering types: {sorted(wanted)} | timeout={timeout}s | min_distinct={min_distinct}")
    try:
        async with websockets.connect(url, max_size=2**20) as ws:
            print("[ws_test_subscriber] connected, listening...")
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5.0))
                except asyncio.TimeoutError:
                    continue
                try:
                    evt = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                etype = evt.get("type")
                if not etype:
                    continue
                if etype in wanted:
                    seen[etype] = seen.get(etype, 0) + 1
                    print(f"  [{etype}] count={seen[etype]} payload_keys={sorted(evt.keys())}")
                    if len(seen) >= min_distinct:
                        print(f"[ws_test_subscriber] OK — {len(seen)} distinct types received: {seen}")
                        return 0
    except Exception as e:
        print(f"[ws_test_subscriber] connection error: {e}", file=sys.stderr)
        return 2
    print(f"[ws_test_subscriber] TIMEOUT — only {len(seen)} distinct types: {seen}", file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="F.2.3 WS broadcast smoke subscriber")
    ap.add_argument("--types", required=True, help="csv list de event types pra filtrar")
    ap.add_argument("--timeout", type=float, default=60.0, help="timeout segundos (default 60)")
    ap.add_argument("--min-distinct", type=int, default=3, help="quantos tipos distintos exigir (default 3)")
    ap.add_argument("--host", default="127.0.0.1:55000", help="host:port do server.py (default 127.0.0.1:55000)")
    ap.add_argument("--token", default=None, help="auth token (default $HERMES_AUTH_TOKEN)")
    args = ap.parse_args()

    wanted = {t.strip() for t in args.types.split(",") if t.strip()}
    if not wanted:
        print("[ws_test_subscriber] --types vazio", file=sys.stderr)
        return 2

    token = args.token or os.environ.get("HERMES_AUTH_TOKEN", "")
    if not token:
        print("[ws_test_subscriber] WARN: sem HERMES_AUTH_TOKEN — auth provavelmente vai rejeitar", file=sys.stderr)

    url = f"ws://{args.host}/ws?token={quote(token)}"
    return asyncio.run(listen(url, wanted, args.timeout, args.min_distinct))


if __name__ == "__main__":
    sys.exit(main())
