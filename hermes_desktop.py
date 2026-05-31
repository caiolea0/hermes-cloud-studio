"""
Hermes Command Center — Desktop App
====================================
- Abre o dashboard em janela nativa
- Roda proxy SOCKS5 + túnel SSH em background
- Ícone na bandeja do sistema com status on/off
- Inicia server.py automaticamente
"""
import asyncio
import logging
import os
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

load_dotenv(BASE_DIR / ".env")

VM_USER = os.environ.get("VM_USER", "hermes-gcp")
VM_HOST = os.environ.get("VM_HOST", "")
PROXY_PORT = int(os.environ.get("PROXY_PORT", "1081"))
PROXY_USER = os.environ.get("PROXY_USER", "")
PROXY_PASS = os.environ.get("PROXY_PASS", "")
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "8500"))
DASHBOARD_URL = f"http://localhost:{DASHBOARD_PORT}"

LOG_FILE = BASE_DIR / "hermes_desktop.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("hermes-desktop")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class AppState:
    proxy_running = False
    tunnel_running = False
    server_running = False
    proxy_task = None
    tunnel_proc = None
    server_proc = None
    tray_icon = None
    window = None
    should_exit = False

state = AppState()

# ---------------------------------------------------------------------------
# SOCKS5 Proxy (async, runs in its own thread)
# ---------------------------------------------------------------------------
async def socks5_handle_client(reader, writer):
    try:
        data = await asyncio.wait_for(reader.read(256), timeout=10)
        if len(data) < 3 or data[0] != 0x05:
            writer.close()
            return

        methods = data[2: 2 + data[1]]
        if 0x02 in methods:
            writer.write(b"\x05\x02")
            await writer.drain()
            auth = await asyncio.wait_for(reader.read(256), timeout=10)
            if len(auth) < 3 or auth[0] != 0x01:
                writer.write(b"\x01\x01"); await writer.drain(); writer.close(); return
            ulen = auth[1]
            username = auth[2: 2 + ulen].decode()
            plen = auth[2 + ulen]
            password = auth[3 + ulen: 3 + ulen + plen].decode()
            if username == PROXY_USER and password == PROXY_PASS:
                writer.write(b"\x01\x00")
            else:
                writer.write(b"\x01\x01"); await writer.drain(); writer.close(); return
            await writer.drain()
        else:
            writer.write(b"\x05\x00")
            await writer.drain()

        data = await asyncio.wait_for(reader.read(256), timeout=10)
        if len(data) < 7 or data[0] != 0x05 or data[1] != 0x01:
            writer.write(b"\x05\x07\x00\x01" + b"\x00" * 6)
            await writer.drain(); writer.close(); return

        atyp = data[3]
        if atyp == 0x01:
            dst_addr = socket.inet_ntoa(data[4:8])
            dst_port = struct.unpack("!H", data[8:10])[0]
        elif atyp == 0x03:
            dlen = data[4]
            dst_addr = data[5: 5 + dlen].decode()
            dst_port = struct.unpack("!H", data[5 + dlen: 7 + dlen])[0]
        elif atyp == 0x04:
            dst_addr = socket.inet_ntop(socket.AF_INET6, data[4:20])
            dst_port = struct.unpack("!H", data[20:22])[0]
        else:
            writer.close(); return

        try:
            rr, rw = await asyncio.wait_for(asyncio.open_connection(dst_addr, dst_port), timeout=15)
        except Exception:
            writer.write(b"\x05\x05\x00\x01" + b"\x00" * 6)
            await writer.drain(); writer.close(); return

        writer.write(b"\x05\x00\x00\x01" + b"\x00" * 4 + struct.pack("!H", dst_port))
        await writer.drain()

        async def pipe(r, w):
            try:
                while True:
                    chunk = await r.read(8192)
                    if not chunk:
                        break
                    w.write(chunk)
                    await w.drain()
            except Exception:
                pass
            finally:
                try: w.close()
                except Exception: pass

        await asyncio.gather(pipe(reader, rw), pipe(rr, writer))
    except Exception:
        pass
    finally:
        try: writer.close()
        except Exception: pass


async def run_proxy_server():
    server = await asyncio.start_server(socks5_handle_client, "127.0.0.1", PROXY_PORT)
    state.proxy_running = True
    log.info(f"SOCKS5 proxy on 127.0.0.1:{PROXY_PORT}")
    update_tray_status()
    async with server:
        await server.serve_forever()


def proxy_thread_fn():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_proxy_server())
    except Exception as e:
        log.error(f"Proxy error: {e}")
    finally:
        state.proxy_running = False
        update_tray_status()

# ---------------------------------------------------------------------------
# SSH Tunnel
# ---------------------------------------------------------------------------
def start_tunnel():
    if state.tunnel_proc and state.tunnel_proc.poll() is None:
        return
    cmd = [
        "ssh", "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-R", f"127.0.0.1:{PROXY_PORT}:127.0.0.1:{PROXY_PORT}",
        "-N", f"{VM_USER}@{VM_HOST}",
    ]
    try:
        state.tunnel_proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        time.sleep(3)
        if state.tunnel_proc.poll() is None:
            state.tunnel_running = True
            log.info("SSH tunnel open")
        else:
            stderr = state.tunnel_proc.stderr.read().decode(errors="replace")
            log.error(f"SSH tunnel failed: {stderr}")
            state.tunnel_running = False
    except Exception as e:
        log.error(f"SSH tunnel error: {e}")
        state.tunnel_running = False
    update_tray_status()


def stop_tunnel():
    if state.tunnel_proc and state.tunnel_proc.poll() is None:
        state.tunnel_proc.terminate()
        state.tunnel_proc.wait(timeout=5)
    state.tunnel_running = False
    update_tray_status()


def tunnel_watchdog():
    """Restarts tunnel if it drops."""
    while not state.should_exit:
        if state.tunnel_proc and state.tunnel_proc.poll() is not None:
            log.warning("Tunnel dropped, reconnecting...")
            state.tunnel_running = False
            update_tray_status()
            time.sleep(5)
            start_tunnel()
        time.sleep(10)

# ---------------------------------------------------------------------------
# Dashboard Server (server.py)
# ---------------------------------------------------------------------------
def start_dashboard_server():
    server_py = BASE_DIR / "server.py"
    if not server_py.exists():
        log.error("server.py not found")
        return
    if is_port_in_use(DASHBOARD_PORT):
        state.server_running = True
        log.info(f"Dashboard server already on port {DASHBOARD_PORT}")
        return
    try:
        state.server_proc = subprocess.Popen(
            [sys.executable, str(server_py)],
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=open(BASE_DIR / "server_err.log", "a"),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        time.sleep(3)
        state.server_running = state.server_proc.poll() is None
        if state.server_running:
            log.info("Dashboard server started")
        else:
            log.error("Dashboard server failed to start")
    except Exception as e:
        log.error(f"Server error: {e}")


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0

# ---------------------------------------------------------------------------
# Tray Icon
# ---------------------------------------------------------------------------
def create_tray_icon():
    import pystray
    from PIL import Image, ImageDraw

    def make_icon(color):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([4, 4, 60, 60], fill=color, outline=(255, 255, 255, 200), width=3)
        d.text((20, 16), "H", fill=(255, 255, 255))
        return img

    state._icon_green = make_icon((46, 204, 113))
    state._icon_yellow = make_icon((241, 196, 15))
    state._icon_red = make_icon((231, 76, 60))

    def on_show_dashboard(icon, item):
        if state.window:
            try:
                state.window.show()
            except Exception:
                pass

    def on_toggle_tunnel(icon, item):
        if state.tunnel_running:
            stop_tunnel()
        else:
            threading.Thread(target=start_tunnel, daemon=True).start()

    def on_quit(icon, item):
        state.should_exit = True
        stop_tunnel()
        if state.server_proc:
            state.server_proc.terminate()
        icon.stop()
        if state.window:
            state.window.destroy()
        os._exit(0)

    def get_tunnel_text(item):
        return "Tunnel: ON — Desligar" if state.tunnel_running else "Tunnel: OFF — Ligar"

    menu = pystray.Menu(
        pystray.MenuItem("Abrir Dashboard", on_show_dashboard, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(get_tunnel_text, on_toggle_tunnel),
        pystray.MenuItem(lambda item: f"Proxy: {'ON' if state.proxy_running else 'OFF'}", None, enabled=False),
        pystray.MenuItem(lambda item: f"Server: {'ON' if state.server_running else 'OFF'}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Sair", on_quit),
    )

    state.tray_icon = pystray.Icon("hermes", state._icon_red, "Hermes — Iniciando...", menu)
    state.tray_icon.run_detached()


def update_tray_status():
    if not state.tray_icon:
        return
    try:
        if state.proxy_running and state.tunnel_running:
            state.tray_icon.icon = state._icon_green
            state.tray_icon.title = "Hermes — Proxy Residencial ATIVO"
        elif state.proxy_running:
            state.tray_icon.icon = state._icon_yellow
            state.tray_icon.title = "Hermes — Proxy ON, Tunnel OFF"
        else:
            state.tray_icon.icon = state._icon_red
            state.tray_icon.title = "Hermes — OFFLINE"
    except Exception:
        pass

# ---------------------------------------------------------------------------
# WebView Window
# ---------------------------------------------------------------------------
def create_window():
    import webview

    class HermesAPI:
        def get_status(self):
            return {
                "proxy": state.proxy_running,
                "tunnel": state.tunnel_running,
                "server": state.server_running,
            }

        def toggle_tunnel(self):
            if state.tunnel_running:
                stop_tunnel()
            else:
                threading.Thread(target=start_tunnel, daemon=True).start()
            return self.get_status()

    api = HermesAPI()

    state.window = webview.create_window(
        "Hermes Command Center",
        DASHBOARD_URL,
        width=1400,
        height=900,
        min_size=(800, 600),
        js_api=api,
        confirm_close=False,
    )

    def on_closed():
        state.window = None

    state.window.events.closed += on_closed
    webview.start(debug=False)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    log.info("=== Hermes Desktop starting ===")

    # 1. System tray
    create_tray_icon()
    time.sleep(1)

    # 2. SOCKS5 proxy
    proxy_t = threading.Thread(target=proxy_thread_fn, daemon=True)
    proxy_t.start()
    time.sleep(1)

    # 3. SSH tunnel
    tunnel_t = threading.Thread(target=start_tunnel, daemon=True)
    tunnel_t.start()

    # 4. Tunnel watchdog
    watchdog_t = threading.Thread(target=tunnel_watchdog, daemon=True)
    watchdog_t.start()

    # 5. Dashboard server
    start_dashboard_server()
    time.sleep(2)

    # 6. WebView window (blocks main thread)
    log.info("Opening dashboard window...")
    create_window()

    # Window closed — cleanup
    log.info("Window closed, shutting down...")
    state.should_exit = True
    stop_tunnel()
    if state.server_proc:
        state.server_proc.terminate()
    if state.tray_icon:
        state.tray_icon.stop()


if __name__ == "__main__":
    main()
