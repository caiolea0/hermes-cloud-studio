"""Centralized SQLite connection helper for LinkedIn modules.

All DB connections go through _connect() to guarantee consistent PRAGMAs.
"""
import sqlite3
from pathlib import Path


def _connect(path: Path | str, timeout: float = 30.0) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=timeout, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
