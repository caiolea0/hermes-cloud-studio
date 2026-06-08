"""Preflight VM gate — INEGOCIAVEL antes de qualquer pipeline LinkedIn.

Garante:
1. Proxy SOCKS5 reverse PC esta UP (curl socks5 retorna)
2. Egress NAO eh datacenter VM (NAO 136.115.74.69 nem range GCP)
3. Egress eh residencial brasileiro plausivel

Se falhar, RAISE ProxyHealthError — NUNCA cai pra IP direto VM.

Uso:
    from linkedin.preflight import assert_tunnel_healthy
    assert_tunnel_healthy(proxy_url="socks5://127.0.0.1:55081")  # raises if degraded
"""
from __future__ import annotations
import os
import re
import subprocess
import logging

logger = logging.getLogger(__name__)

# IPs/ranges PROIBIDOS (datacenter = queima)
VM_HOST = "136.115.74.69"
DATACENTER_BLOCKLIST = [
    "136.115.",     # this VM
    "34.",          # GCP common range
    "35.",          # GCP common range
    "104.196.",     # GCP
    "8.8.8.",       # google DNS-like flag
    "1.1.1.",       # cloudflare warp
]


class ProxyHealthError(RuntimeError):
    """Raised when preflight gate fails. NUNCA permitir bypass."""


def _curl_via_socks5(socks_host: str, socks_port: int, timeout: int = 10) -> str:
    """Returns egress IP via socks5. Raises on failure."""
    try:
        result = subprocess.run(
            [
                "curl", "-s", "--max-time", str(timeout),
                "--socks5-hostname", f"{socks_host}:{socks_port}",
                "https://api.ipify.org",
            ],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if result.returncode != 0:
            raise ProxyHealthError(
                f"curl via socks5://{socks_host}:{socks_port} falhou rc={result.returncode}: {result.stderr.strip()[:200]}"
            )
        ip = result.stdout.strip()
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
            raise ProxyHealthError(f"resposta nao eh IPv4: {ip[:100]!r}")
        return ip
    except subprocess.TimeoutExpired:
        raise ProxyHealthError(f"curl via socks5 TIMEOUT apos {timeout}s")
    except FileNotFoundError:
        raise ProxyHealthError("curl nao disponivel no PATH")


def _is_datacenter(ip: str) -> bool:
    return any(ip.startswith(prefix) for prefix in DATACENTER_BLOCKLIST)


def assert_tunnel_healthy(
    proxy_url: str | None = None,
    require_residential: bool = True,
) -> str:
    """Gate inegociavel. Returns egress IP se OK; raise ProxyHealthError se nao.

    Args:
        proxy_url: URL socks5 tipo "socks5://127.0.0.1:55081". Se None, le LINKEDIN_PROXY do env.
        require_residential: se True, exige IP non-datacenter.

    Returns:
        egress IP string

    Raises:
        ProxyHealthError em qualquer falha.
    """
    if proxy_url is None:
        proxy_url = os.environ.get("LINKEDIN_PROXY", "").strip()

    if not proxy_url:
        raise ProxyHealthError(
            "LINKEDIN_PROXY nao configurado. Pipeline LinkedIn EXIGE proxy reverse "
            "SOCKS5 do PC residencial. Setar LINKEDIN_PROXY=socks5://127.0.0.1:55081 no .env"
        )

    m = re.match(r"^socks5(?:h)?://(?:[^@]*@)?([^:]+):(\d+)$", proxy_url)
    if not m:
        raise ProxyHealthError(f"LINKEDIN_PROXY formato invalido: {proxy_url!r} (esperado socks5://host:port)")
    host, port = m.group(1), int(m.group(2))

    logger.info(f"preflight: curl via {proxy_url}")
    ip = _curl_via_socks5(host, port)
    logger.info(f"preflight: egress IP = {ip}")

    if require_residential and _is_datacenter(ip):
        raise ProxyHealthError(
            f"egress IP {ip} esta em DATACENTER blocklist. "
            f"Proxy reverse PC NAO esta funcional ou caiu pra IP direto. "
            f"Verificar tunnel_supervisor no PC: `python scripts/tunnel_supervisor.py --status`"
        )

    if ip == VM_HOST:
        raise ProxyHealthError(
            f"egress IP eh VM host ({VM_HOST}) — proxy nao esta sendo aplicado. ABORTANDO."
        )

    return ip


def preflight_check_or_die(proxy_url: str | None = None) -> str:
    """Convenience: roda assert, loga ok, retorna IP. Sai com exit 2 se fail (pra CLI)."""
    import sys
    try:
        ip = assert_tunnel_healthy(proxy_url)
        print(f"PREFLIGHT OK: egress={ip}")
        return ip
    except ProxyHealthError as e:
        print(f"PREFLIGHT FAIL: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    # CLI: `python -m linkedin.preflight` ou `python linkedin/preflight.py`
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).parent.parent / ".env")
    preflight_check_or_die()
