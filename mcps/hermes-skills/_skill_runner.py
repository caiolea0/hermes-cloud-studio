"""Isolated subprocess execution context for skill dry-run (H2).

Called by mcps/hermes-skills/server.py via asyncio.create_subprocess_exec.
Receives YAML path + input JSON via argv[1]/argv[2].
Validates skill schema + scans banned patterns (best-effort — motivated
attacker can obfuscate; catches accidental/naive misuse).
Prints result JSON to stdout, exits.
"""
from __future__ import annotations

import json
import signal
import sys
import time

import yaml

# Best-effort banned patterns (string-level scan on re-serialized YAML).
# NOT 100% — obfuscation bypasses. Honest defense per H2 spec.
_BANNED: tuple[str, ...] = (
    "os.system(",
    "subprocess.",
    "__import__('os')",
    '__import__("os")',
    "eval(",
    "exec(",
    "sys.exit(",
)

# Mirror constants from auto_skill_runner.py (avoid import dep).
_REQUIRED_YAML_KEYS: tuple[str, ...] = ("name", "version")
_REQUIRE_EITHER: tuple[str, ...] = ("provider", "steps")


def _scan_banned(yaml_text: str) -> list[str]:
    """Return list of banned patterns found in yaml_text (empty = clean)."""
    return [pat for pat in _BANNED if pat in yaml_text]


def _validate_and_exec(skill_dict: dict, _input_data: dict) -> dict:
    """Validate skill schema + scan for banned patterns.

    Returns lab_test_result dict (status/stdout/stderr/latency_ms/exit_code/mock).
    mock=False marks this as real subprocess execution (vs inline fallback).
    """
    start = time.perf_counter()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    status = "passed"
    exit_code = 0

    # 1. Banned pattern scan on canonical re-serialized YAML.
    yaml_text = yaml.safe_dump(skill_dict)
    banned_found = _scan_banned(yaml_text)
    if banned_found:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return {
            "status": "failed",
            "stdout": "",
            "stderr": f"banned pattern(s) detected: {banned_found}",
            "latency_ms": latency_ms,
            "exit_code": 2,
            "mock": False,
        }

    # 2. Required keys present.
    missing = [k for k in _REQUIRED_YAML_KEYS if k not in skill_dict]
    if missing:
        stderr_lines.append(f"Missing required key(s): {missing}")
        status = "failed"
        exit_code = 1

    # 3. At least one of provider | steps.
    if status == "passed" and not any(k in skill_dict for k in _REQUIRE_EITHER):
        stderr_lines.append(f"At least one of {list(_REQUIRE_EITHER)} required")
        status = "failed"
        exit_code = 1

    if status == "passed":
        present = sorted(k for k in skill_dict if k in _REQUIRED_YAML_KEYS + _REQUIRE_EITHER)
        stdout_lines.append(f"Subprocess sandbox OK: keys {present}")
        stdout_lines.append(
            f"model={skill_dict.get('model')!r} "
            f"provider={skill_dict.get('provider')!r}"
        )

    latency_ms = int((time.perf_counter() - start) * 1000)
    return {
        "status": status,
        "stdout": "\n".join(stdout_lines),
        "stderr": "\n".join(stderr_lines),
        "latency_ms": latency_ms,
        "exit_code": exit_code,
        "mock": False,
    }


def _fail(msg: str, exit_code: int = 1) -> None:
    print(json.dumps({
        "status": "failed",
        "stdout": "",
        "stderr": msg,
        "latency_ms": 0,
        "exit_code": exit_code,
        "mock": False,
    }))
    sys.exit(exit_code)


if __name__ == "__main__":
    # SIGALRM hard timeout (defense beyond asyncio wait_for in caller).
    # Not available on Windows — guard gracefully.
    try:
        signal.signal(signal.SIGALRM, lambda *_: sys.exit(124))
        signal.alarm(70)  # 10s grace above asyncio 60s
    except AttributeError:
        pass  # Windows — rely on asyncio wait_for

    if len(sys.argv) < 3:
        _fail("Usage: _skill_runner.py <yaml_path> <input_json>")

    yaml_path_arg = sys.argv[1]
    try:
        input_data_arg: dict = json.loads(sys.argv[2])
    except json.JSONDecodeError as exc:
        _fail(f"input_json decode error: {exc}")

    try:
        with open(yaml_path_arg, "r", encoding="utf-8") as fh:
            raw = fh.read()
        skill = yaml.safe_load(raw)
    except Exception as exc:
        _fail(f"yaml read/parse error: {exc}")

    if not isinstance(skill, dict):
        _fail("YAML root must be a mapping (dict)")

    result = _validate_and_exec(skill, input_data_arg)
    print(json.dumps(result))
    # exit_code 2 (banned) normalizes to 1 for shell
    sys.exit(0 if result["exit_code"] == 0 else 1)
