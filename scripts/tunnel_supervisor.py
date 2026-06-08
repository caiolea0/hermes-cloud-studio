"""Hermes Tunnel Supervisor — mantem socks5_proxy.py + SSH reverse tunnel SEMPRE UP.

Roda no PC Windows. Independente do Tauri/Hermes.exe. Idempotente.

Loop:
  1. Probe :55081 listening localmente. Se nao, spawn socks5_proxy.py
  2. Verificar SSH reverse tunnel ativo (probe via SSH na VM: ss -ltn | grep :55081)
     Se nao listening na VM, spawn `ssh -N -R ...`
  3. End-to-end check: SSH na VM e curl --socks5-hostname 127.0.0.1:55081 https://api.ipify.org
     Se NAO retornar IP residencial (i.e. retornar 136.115.74.69 da VM OU timeout), restart tudo
  4. Sleep TICK_SEC, repete

Backoff: 30s base entre restarts. Max 3 restarts/min, depois cooldown 60s.

Log: logs/tunnel_supervisor.log

Uso:
    python scripts/tunnel_supervisor.py
    python scripts/tunnel_supervisor.py --one-shot      # roda 1 ciclo e sai (pre-flight gate)
    python scripts/tunnel_supervisor.py --status        # imprime estado e sai
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# --- Config ---
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "tunnel_supervisor.log"
STATE_FILE = LOG_DIR / "tunnel_supervisor_state.json"

SOCKS5_PORT = 55081
VM_HOST = "136.115.74.69"
VM_USER = "hermes-gcp"
SSH_KEY = str(Path(os.environ.get("USERPROFILE", "")) / ".ssh" / "id_ed25519")
TICK_SEC = 30
MAX_RESTARTS_PER_MIN = 3
COOLDOWN_SEC = 60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("supervisor")


# --- State persistence ---

def save_state(state: dict):
    state["updated_at"] = datetime.utcnow().isoformat()
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning(f"save_state failed: {e}")


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# --- Health checks ---

def port_listening(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if PC has socket listening on (host, port)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def ssh_exec(cmd: str, timeout: float = 10.0) -> tuple[int, str, str]:
    """Run a command on the VM via SSH. Returns (rc, stdout, stderr)."""
    try:
        result = subprocess.run(
            [
                "ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes",
                "-i", SSH_KEY, f"{VM_USER}@{VM_HOST}", cmd,
            ],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "ssh timeout"
    except Exception as e:
        return -2, "", str(e)


def check_vm_tunnel_listening() -> bool:
    """Verify SSH reverse tunnel landed :55081 on VM (loopback)."""
    rc, out, _ = ssh_exec(f"ss -ltn '( sport = :{SOCKS5_PORT} )' | grep -q ':{SOCKS5_PORT}'")
    return rc == 0


def check_egress_residential() -> tuple[bool, str]:
    """End-to-end: VM curl via socks5 -> egress IP. Returns (is_residential, ip)."""
    rc, out, _ = ssh_exec(
        f"curl -s --max-time 8 --socks5-hostname 127.0.0.1:{SOCKS5_PORT} https://api.ipify.org"
    )
    ip = out.strip()
    if rc != 0 or not ip:
        return False, ip or "(no response)"
    is_residential = ip != VM_HOST and not ip.startswith("136.115.")
    return is_residential, ip


# --- Process management ---

def find_socks5_pid() -> int | None:
    """Look for running socks5_proxy.py process (Windows: tasklist + wmic)."""
    try:
        out = subprocess.check_output(
            ["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine", "/format:csv"],
            text=True, stderr=subprocess.DEVNULL, timeout=10,
        )
        for line in out.splitlines():
            if "socks5_proxy" in line and str(SOCKS5_PORT) in line:
                parts = line.strip().split(",")
                for p in reversed(parts):
                    if p.strip().isdigit():
                        return int(p.strip())
    except Exception:
        pass
    return None


def find_ssh_tunnel_pid() -> int | None:
    """Look for ssh.exe with -R 55081 flag."""
    try:
        out = subprocess.check_output(
            ["wmic", "process", "where", "name='ssh.exe'", "get", "ProcessId,CommandLine", "/format:csv"],
            text=True, stderr=subprocess.DEVNULL, timeout=10,
        )
        for line in out.splitlines():
            if f":{SOCKS5_PORT}:" in line and "-R" in line:
                parts = line.strip().split(",")
                for p in reversed(parts):
                    if p.strip().isdigit():
                        return int(p.strip())
    except Exception:
        pass
    return None


def spawn_socks5() -> int | None:
    """Start socks5_proxy.py in background. Returns PID."""
    script = BASE_DIR / "socks5_proxy.py"
    if not script.exists():
        log.error(f"socks5_proxy.py NAO encontrado em {script}")
        return None
    py = sys.executable
    log.info(f"spawning socks5: {py} {script} {SOCKS5_PORT}")
    try:
        proc = subprocess.Popen(
            [py, str(script), str(SOCKS5_PORT)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000,  # CREATE_NO_WINDOW
        )
        return proc.pid
    except Exception as e:
        log.error(f"spawn socks5 failed: {e}")
        return None


def spawn_ssh_tunnel() -> int | None:
    """Start SSH reverse tunnel in background. Returns PID."""
    log.info(f"spawning ssh reverse tunnel -R {SOCKS5_PORT}")
    try:
        proc = subprocess.Popen(
            [
                "ssh", "-N",
                "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3",
                "-o", "ExitOnForwardFailure=yes", "-o", "BatchMode=yes",
                "-i", SSH_KEY,
                "-R", f"127.0.0.1:{SOCKS5_PORT}:127.0.0.1:{SOCKS5_PORT}",
                f"{VM_USER}@{VM_HOST}",
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000,
        )
        return proc.pid
    except Exception as e:
        log.error(f"spawn ssh failed: {e}")
        return None


def kill_pid(pid: int):
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
        log.info(f"killed pid {pid}")
    except Exception:
        pass


# --- Tick logic ---

class Supervisor:
    def __init__(self):
        self.restart_window: list[float] = []  # timestamps of recent restarts
        self.cooldown_until: float = 0.0
        self.socks5_pid: int | None = find_socks5_pid()
        self.ssh_pid: int | None = find_ssh_tunnel_pid()

    def can_restart(self) -> bool:
        now = time.time()
        if now < self.cooldown_until:
            return False
        # prune old entries
        self.restart_window = [t for t in self.restart_window if now - t < 60]
        if len(self.restart_window) >= MAX_RESTARTS_PER_MIN:
            self.cooldown_until = now + COOLDOWN_SEC
            log.warning(f"restart cap atingido — cooldown {COOLDOWN_SEC}s")
            return False
        return True

    def restart_socks5(self):
        if not self.can_restart():
            return
        if self.socks5_pid:
            kill_pid(self.socks5_pid)
        self.socks5_pid = spawn_socks5()
        self.restart_window.append(time.time())
        time.sleep(2)

    def restart_ssh(self):
        if not self.can_restart():
            return
        if self.ssh_pid:
            kill_pid(self.ssh_pid)
        self.ssh_pid = spawn_ssh_tunnel()
        self.restart_window.append(time.time())
        time.sleep(3)

    def tick(self) -> dict:
        """One iteration. Returns state dict."""
        state = {
            "socks5_listening": port_listening("127.0.0.1", SOCKS5_PORT),
            "socks5_pid": self.socks5_pid,
            "ssh_pid": self.ssh_pid,
            "vm_tunnel_landed": False,
            "egress_residential": False,
            "egress_ip": "",
            "actions": [],
        }

        # 1. socks5 local
        if not state["socks5_listening"]:
            log.warning("socks5 :55081 NAO listening — spawning")
            state["actions"].append("spawn_socks5")
            self.restart_socks5()
            state["socks5_listening"] = port_listening("127.0.0.1", SOCKS5_PORT)
            state["socks5_pid"] = self.socks5_pid
            if not state["socks5_listening"]:
                log.error("socks5 spawn falhou")
                return state

        # 2. SSH reverse tunnel landed on VM
        state["vm_tunnel_landed"] = check_vm_tunnel_listening()
        if not state["vm_tunnel_landed"]:
            log.warning("SSH reverse :55081 NAO landed na VM — spawning")
            state["actions"].append("spawn_ssh_tunnel")
            self.restart_ssh()
            time.sleep(3)
            state["vm_tunnel_landed"] = check_vm_tunnel_listening()
            state["ssh_pid"] = self.ssh_pid
            if not state["vm_tunnel_landed"]:
                log.error("SSH tunnel spawn falhou")
                return state

        # 3. End-to-end egress check
        ok, ip = check_egress_residential()
        state["egress_residential"] = ok
        state["egress_ip"] = ip
        if not ok:
            log.warning(f"egress NAO residencial: {ip} — restart SSH")
            state["actions"].append("restart_ssh_egress_fail")
            self.restart_ssh()
            time.sleep(4)
            ok2, ip2 = check_egress_residential()
            state["egress_residential"] = ok2
            state["egress_ip"] = ip2

        return state


def cmd_status():
    sup = Supervisor()
    state = sup.tick()
    save_state(state)
    print(json.dumps(state, indent=2))
    sys.exit(0 if state.get("egress_residential") else 1)


def cmd_one_shot():
    """Pre-flight gate: garante tudo UP, returncode 0 se OK pra rodar pipeline."""
    sup = Supervisor()
    for _ in range(3):
        state = sup.tick()
        if state.get("egress_residential"):
            save_state(state)
            print(f"OK egress={state['egress_ip']}")
            return 0
        time.sleep(2)
    save_state(state)
    print(f"FAIL egress={state.get('egress_ip')} actions={state.get('actions')}", file=sys.stderr)
    return 2


def cmd_loop():
    log.info("tunnel_supervisor started (loop mode)")
    sup = Supervisor()
    while True:
        try:
            state = sup.tick()
            save_state(state)
            if state.get("egress_residential"):
                log.info(f"OK egress={state['egress_ip']}")
            else:
                log.warning(f"DEGRADED egress={state.get('egress_ip')} actions={state.get('actions')}")
        except Exception as e:
            log.exception(f"tick failed: {e}")
        time.sleep(TICK_SEC)


def main():
    p = argparse.ArgumentParser(description="Hermes tunnel supervisor")
    p.add_argument("--status", action="store_true", help="Imprime estado atual e sai")
    p.add_argument("--one-shot", action="store_true", help="Roda 1 ciclo (pre-flight gate) e sai")
    args = p.parse_args()

    if args.status:
        cmd_status()
    elif args.one_shot:
        sys.exit(cmd_one_shot())
    else:
        cmd_loop()


if __name__ == "__main__":
    main()
