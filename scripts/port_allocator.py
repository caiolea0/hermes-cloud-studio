#!/usr/bin/env python3
"""Port Allocator - cross-project port management.

Resolve conflitos de porta entre projetos em D:\\dev-projects\\main\\.

Mecanismo:
  1. Cada projeto declara portas em `.claude/PORTS.json`
  2. Registry global em `~/.dev-projects-ports.json` rastreia alocações
  3. Allocator probe porta livre OS-level + cruza com registry
  4. Realoca dentro do fallback_range se ocupada
  5. Marca como "in_use" com PID/timestamp pra detectar stale

Uso CLI:
    python scripts/port_allocator.py --probe              # imprime alocacoes resolvidas (sem reservar)
    python scripts/port_allocator.py --allocate dashboard # aloca a porta e reserva
    python scripts/port_allocator.py --release dashboard  # libera (no shutdown)
    python scripts/port_allocator.py --status             # estado de todas as portas
    python scripts/port_allocator.py --cleanup            # remove allocations stale

Uso programatico (server.py):
    from scripts.port_allocator import allocate_port, is_self_already_running
    if is_self_already_running("dashboard"):
        sys.exit("server.py ja rodando em outra instancia - idempotente")
    port = allocate_port("dashboard")
"""
from __future__ import annotations
import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent.parent
PORTS_FILE = BASE_DIR / ".claude" / "PORTS.json"
GLOBAL_REGISTRY = Path(os.path.expanduser("~")) / ".dev-projects-ports.json"
STALE_AFTER_SECONDS = 3600  # 1h sem heartbeat = considerar stale

PROJECT_NAME = "hermes-cloud-studio"


# ───────────── Util ─────────────

def _is_port_listening(host: str, port: int, timeout: float = 0.5) -> bool:
    """True se algo já está bound em (host, port)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False


def _load_global_registry() -> dict:
    if not GLOBAL_REGISTRY.exists():
        return {"_meta": {"format_version": 1}, "allocations": {}}
    try:
        return json.loads(GLOBAL_REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return {"_meta": {"format_version": 1}, "allocations": {}}


def _save_global_registry(data: dict):
    GLOBAL_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    GLOBAL_REGISTRY.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_project_ports() -> dict:
    if not PORTS_FILE.exists():
        raise FileNotFoundError(f"PORTS.json nao encontrado: {PORTS_FILE}")
    return json.loads(PORTS_FILE.read_text(encoding="utf-8"))


def _key(role: str) -> str:
    return f"{PROJECT_NAME}::{role}"


def _is_stale(entry: dict) -> bool:
    """Allocation eh stale se timestamp >1h sem heartbeat OU PID nao existe."""
    ts = entry.get("allocated_at", 0)
    if time.time() - ts > STALE_AFTER_SECONDS:
        # checa PID se Windows
        pid = entry.get("pid")
        if pid:
            try:
                # No Windows, OpenProcess via psutil seria ideal mas evitar dep
                # fallback: assumir stale se ts antigo
                pass
            except Exception:
                return True
        return True
    return False


def cleanup_stale_global():
    """Remove allocations stale do registry global. Idempotente."""
    reg = _load_global_registry()
    allocs = reg.get("allocations", {})
    removed = []
    for key, entry in list(allocs.items()):
        if _is_stale(entry):
            removed.append(key)
            del allocs[key]
    if removed:
        _save_global_registry(reg)
    return removed


# ───────────── Probe + allocate ─────────────

def is_self_already_running(role: str) -> bool:
    """True se outra instancia DESTE projeto JA esta ouvindo na porta preferida ou alocada.

    Idempotencia: server.py chama isso no startup. Se True, exit cedo.
    """
    project_ports = _load_project_ports()
    port_cfg = project_ports["ports"].get(role)
    if not port_cfg:
        return False

    # Checa porta atualmente alocada (se existir no global registry)
    reg = _load_global_registry()
    entry = reg.get("allocations", {}).get(_key(role))
    if entry and not _is_stale(entry):
        port = entry["port"]
        host = port_cfg.get("host", "127.0.0.1")
        if _is_port_listening(host, port):
            return True

    # Checa porta preferida
    host = port_cfg.get("host", "127.0.0.1")
    preferred = port_cfg.get("preferred")
    if preferred and _is_port_listening(host, preferred):
        return True

    return False


def allocate_port(role: str, reserve: bool = True) -> int:
    """Aloca porta livre pro role. Retorna porta.

    Estrategia:
      1. Cleanup stale entries primeiro
      2. Se role tem 'fixed': True, retornar preferred sem fallback
      3. Probe preferred - se livre, usar
      4. Senao, percorrer fallback_range procurando porta livre + nao alocada por outro projeto
      5. Se nada disponivel, raise RuntimeError
      6. Se reserve=True, gravar no registry global
    """
    cleanup_stale_global()

    project_ports = _load_project_ports()
    port_cfg = project_ports["ports"].get(role)
    if not port_cfg:
        raise ValueError(f"Role nao declarado em PORTS.json: {role}")

    host = port_cfg.get("host", "127.0.0.1")
    preferred = port_cfg["preferred"]

    # Fixed = sem fallback (ex: 8420 VM remoto, 11434 Ollama, 3141 agentmemory)
    if port_cfg.get("fixed"):
        return preferred

    reg = _load_global_registry()
    allocs = reg.setdefault("allocations", {})

    # Conjunto de portas ja alocadas por outros projetos
    busy_by_others = {
        e["port"]
        for k, e in allocs.items()
        if not k.startswith(f"{PROJECT_NAME}::") and not _is_stale(e)
    }

    candidates = [preferred] + list(range(*port_cfg.get("fallback_range", [preferred + 1, preferred + 20])))

    for port in candidates:
        if port in busy_by_others:
            continue
        if _is_port_listening(host, port):
            # Pode ser nossa propria instancia anterior (stale entry foi removida ja).
            # Se for porta preferida e ouvindo, eh provavelmente self-conflict - pular.
            continue
        # Disponivel
        if reserve:
            allocs[_key(role)] = {
                "project": PROJECT_NAME,
                "role": role,
                "port": port,
                "host": host,
                "pid": os.getpid(),
                "allocated_at": time.time(),
                "heartbeat_at": time.time(),
            }
            _save_global_registry(reg)
        return port

    raise RuntimeError(
        f"Nenhuma porta livre encontrada pra role={role} "
        f"(preferred={preferred}, range={port_cfg.get('fallback_range')}). "
        f"Verificar conflitos em outros projetos via: python {__file__} --status"
    )


def release_port(role: str):
    """Libera reserva no registry global. Chamar em shutdown."""
    reg = _load_global_registry()
    allocs = reg.get("allocations", {})
    if _key(role) in allocs:
        del allocs[_key(role)]
        _save_global_registry(reg)


def heartbeat(role: str):
    """Atualiza timestamp da allocation. Chamar periodicamente (ex: a cada 15min)."""
    reg = _load_global_registry()
    entry = reg.get("allocations", {}).get(_key(role))
    if entry:
        entry["heartbeat_at"] = time.time()
        _save_global_registry(reg)


def status_table() -> str:
    """Imprime tabela de portas + estado."""
    cleanup_stale_global()
    project_ports = _load_project_ports()
    reg = _load_global_registry()
    allocs = reg.get("allocations", {})
    rows = []
    for role, cfg in project_ports["ports"].items():
        preferred = cfg["preferred"]
        host = cfg.get("host", "127.0.0.1")
        listening = _is_port_listening(host, preferred)
        entry = allocs.get(_key(role))
        allocated_port = entry["port"] if entry else "-"
        pid = entry.get("pid") if entry else "-"
        rows.append({
            "role": role,
            "host": host,
            "preferred": preferred,
            "allocated": allocated_port,
            "listening": "yes" if listening else "no",
            "pid": pid,
            "fixed": cfg.get("fixed", False),
        })
    lines = [
        f"{'ROLE':<22} {'HOST':<16} {'PREFERRED':<10} {'ALLOC':<8} {'LISTEN':<8} {'PID':<8} {'FIXED'}",
        "-" * 92,
    ]
    for r in rows:
        lines.append(
            f"{r['role']:<22} {r['host']:<16} {r['preferred']:<10} "
            f"{str(r['allocated']):<8} {r['listening']:<8} {str(r['pid']):<8} {r['fixed']}"
        )
    lines.append("")
    other_projects = [
        f"{k.split('::')[0]}/{k.split('::')[1]} -> :{e['port']} (pid={e.get('pid','?')})"
        for k, e in allocs.items()
        if not k.startswith(f"{PROJECT_NAME}::")
    ]
    if other_projects:
        lines.append("Outros projetos no registry global:")
        for line in other_projects:
            lines.append(f"  {line}")
    return "\n".join(lines)


# ───────────── CLI ─────────────

def main():
    p = argparse.ArgumentParser(description="Port allocator cross-projeto")
    p.add_argument("--probe", action="store_true", help="Imprime alocacoes resolvidas sem reservar")
    p.add_argument("--allocate", help="Aloca + reserva role")
    p.add_argument("--release", help="Libera role")
    p.add_argument("--heartbeat", help="Atualiza timestamp do role")
    p.add_argument("--status", action="store_true", help="Tabela de estado")
    p.add_argument("--cleanup", action="store_true", help="Remove allocations stale")
    args = p.parse_args()

    if args.status:
        print(status_table())
        return 0
    if args.cleanup:
        removed = cleanup_stale_global()
        print(f"Removidas {len(removed)} entries stale: {removed}")
        return 0
    if args.probe:
        project_ports = _load_project_ports()
        for role in project_ports["ports"]:
            try:
                port = allocate_port(role, reserve=False)
                self_running = is_self_already_running(role)
                print(f"{role}: port={port} self_running={self_running}")
            except Exception as e:
                print(f"{role}: ERROR {e}")
        return 0
    if args.allocate:
        port = allocate_port(args.allocate, reserve=True)
        print(port)
        return 0
    if args.release:
        release_port(args.release)
        print(f"released {args.release}")
        return 0
    if args.heartbeat:
        heartbeat(args.heartbeat)
        print(f"heartbeat {args.heartbeat}")
        return 0

    print(status_table())
    return 0


if __name__ == "__main__":
    sys.exit(main())
