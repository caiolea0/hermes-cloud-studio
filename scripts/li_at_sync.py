#!/usr/bin/env python3
"""LinkedIn li_at cookie sync — reads Chrome's cookie DB on Windows,
extracts the li_at value, and pushes it to the local Hermes server when
the value changed. Run periodically via Task Scheduler.

Requires: pywin32, cryptography (already present in this project).

Safe by design: reads YOUR real Chrome cookie (your residential session).
Never logs into LinkedIn, never touches passwords. If Chrome is closed
the DB is still readable (file is copied to a temp path first).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Optional

import httpx
import win32crypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

LOG = logging.getLogger("li_at_sync")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# All Chromium-based browsers use the same encryption format — just different paths.
BROWSERS = {
    "Chrome":  Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data",
    "Edge":    Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "Edge" / "User Data",
    "Brave":   Path(os.environ["LOCALAPPDATA"]) / "BraveSoftware" / "Brave-Browser" / "User Data",
    "Chromium": Path(os.environ["LOCALAPPDATA"]) / "Chromium" / "User Data",
    "Opera":   Path(os.environ["APPDATA"]) / "Opera Software" / "Opera Stable",
    "Vivaldi": Path(os.environ["LOCALAPPDATA"]) / "Vivaldi" / "User Data",
}

LOCAL_SERVER = os.environ.get("HERMES_LOCAL_URL", "http://localhost:55000")
STATE_FILE = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "data" / "li_at_last.json"


def _get_master_key(user_data_dir: Path) -> Optional[bytes]:
    """Read a Chromium-based browser's AES key from Local State (DPAPI-encrypted)."""
    local_state = user_data_dir / "Local State"
    if not local_state.exists():
        return None
    try:
        state = json.loads(local_state.read_text(encoding="utf-8"))
        enc_key_b64 = state["os_crypt"]["encrypted_key"]
        enc_key = base64.b64decode(enc_key_b64)[5:]  # strip "DPAPI" prefix
        _, key = win32crypt.CryptUnprotectData(enc_key, None, None, None, 0)
        return key
    except Exception as e:
        LOG.debug(f"master key read failed for {user_data_dir}: {e}")
        return None


def _decrypt_cookie_value(encrypted: bytes, key: bytes) -> Optional[str]:
    """Decrypt a single Chrome cookie value."""
    if not encrypted:
        return None
    # v10/v11 format: 3-byte prefix + 12-byte nonce + ciphertext + 16-byte tag
    if encrypted[:3] in (b"v10", b"v11"):
        nonce = encrypted[3:15]
        ciphertext_and_tag = encrypted[15:]
        try:
            plaintext = AESGCM(key).decrypt(nonce, ciphertext_and_tag, None)
            return plaintext.decode("utf-8", errors="replace")
        except Exception as e:
            LOG.warning(f"AES-GCM decrypt failed: {e}")
            return None
    # Legacy format: pure DPAPI
    try:
        _, plain = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)
        return plain.decode("utf-8", errors="replace")
    except Exception as e:
        LOG.warning(f"DPAPI decrypt failed: {e}")
        return None


def _win_share_copy(src: Path, dst: Path) -> bool:
    """Copy a file even when another process has it exclusively locked,
    using Win32 CreateFile with FILE_SHARE_* flags (works on Brave/Chrome)."""
    try:
        import win32file
        import win32con
        h = win32file.CreateFile(
            str(src),
            win32con.GENERIC_READ,
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
            None,
            win32con.OPEN_EXISTING,
            win32con.FILE_ATTRIBUTE_NORMAL,
            None,
        )
        try:
            with open(dst, "wb") as out:
                while True:
                    err, chunk = win32file.ReadFile(h, 1024 * 1024)
                    if err or not chunk:
                        break
                    out.write(chunk)
        finally:
            h.Close()
        return True
    except Exception as e:
        LOG.debug(f"win32 share-copy failed for {src}: {e}")
        return False


def _open_locked_sqlite(path: Path) -> Optional[sqlite3.Connection]:
    """Open a SQLite DB that may be locked by a running browser."""
    # 1. immutable URI (works for unlocked or read-share files)
    try:
        uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
        c = sqlite3.connect(uri, uri=True, timeout=2)
        c.execute("SELECT 1").fetchone()
        return c
    except Exception:
        pass
    # 2. shutil.copy fallback
    tmp = Path(tempfile.gettempdir()) / f"hermes_cookies_{path.parent.parent.name}_{path.parent.name}.db"
    try:
        shutil.copy2(path, tmp)
        return sqlite3.connect(str(tmp), timeout=2)
    except Exception:
        pass
    # 3. Win32 share-mode copy (works against Brave/Chrome exclusive lock)
    if _win_share_copy(path, tmp):
        try:
            return sqlite3.connect(str(tmp), timeout=2)
        except Exception as e:
            LOG.debug(f"sqlite open after share-copy failed: {e}")
    return None


def _try_one_db(cookies_db: Path, key: bytes, browser_name: str) -> Optional[str]:
    if not cookies_db.exists():
        return None
    conn = _open_locked_sqlite(cookies_db)
    if not conn:
        return None
    try:
        rows = conn.execute(
            "SELECT host_key, encrypted_value FROM cookies "
            "WHERE host_key LIKE '%.linkedin.com' AND name='li_at'"
        ).fetchall()
    except Exception as e:
        LOG.debug(f"query {cookies_db}: {e}")
        rows = []
    finally:
        conn.close()
    if not rows:
        return None
    rows.sort(key=lambda r: 0 if r[0].startswith(".linkedin.com") else 1)
    val = _decrypt_cookie_value(rows[0][1], key)
    if val:
        LOG.info(f"Found li_at in {browser_name} ({cookies_db.parent.parent.name}) — host={rows[0][0]}")
    return val


def read_li_at_from_chrome() -> Optional[str]:
    """Scan all Chromium-based browsers + all profiles for the LinkedIn li_at cookie."""
    for browser_name, user_data in BROWSERS.items():
        if not user_data.exists():
            continue
        key = _get_master_key(user_data)
        if not key:
            continue
        # Iterate over profile directories (Default, Profile 1, Profile 2, ...)
        for profile in user_data.iterdir():
            if not profile.is_dir():
                continue
            for candidate in [profile / "Network" / "Cookies", profile / "Cookies"]:
                val = _try_one_db(candidate, key, browser_name)
                if val:
                    return val
    LOG.warning("li_at cookie not found in any installed Chromium browser — log in to LinkedIn first")
    return None


def _read_last_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")


def push_to_hermes(li_at: str) -> bool:
    """POST the new cookie to local Hermes server. Returns True on success."""
    try:
        r = httpx.post(
            f"{LOCAL_SERVER}/api/internal/li_at_rotate",
            json={"li_at": li_at},
            timeout=15.0,
        )
        if r.status_code == 200:
            data = r.json()
            LOG.info(f"Server response: {data}")
            return data.get("ok", False)
        LOG.error(f"Server returned {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        LOG.error(f"POST failed: {e}")
        return False


def main() -> int:
    LOG.info("li_at_sync starting")
    li_at = read_li_at_from_chrome()
    if not li_at:
        LOG.error("No cookie found — exiting (will retry next run)")
        return 1
    LOG.info(f"li_at read OK (length={len(li_at)})")

    last = _read_last_state()
    if last.get("li_at") == li_at:
        LOG.info("No change since last sync — done")
        return 0

    LOG.info("Cookie changed — pushing to Hermes...")
    if push_to_hermes(li_at):
        _write_state({"li_at": li_at, "synced_at": __import__("datetime").datetime.now().isoformat()})
        LOG.info("Sync OK")
        return 0
    LOG.error("Sync failed — will retry next run")
    return 2


if __name__ == "__main__":
    sys.exit(main())
