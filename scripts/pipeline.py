"""Hermes Prospecting Pipeline — CLI wrapper.

Thin wrapper sobre core.pipeline.PipelineRunner. Logica vive em core/pipeline.py
(compartilhada com daemon/orchestrator.py).

Modos:
    python -m scripts.pipeline --mode full --city "Cuiaba"
    python -m scripts.pipeline --mode discovery --city "Cuiaba" --categories "design,marketing"
    python -m scripts.pipeline --mode audit-pending
    python -m scripts.pipeline --mode outreach-ready
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.pipeline import PipelineRunner

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
LOG_DIR = HERMES_HOME / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


async def _dispatch(args: argparse.Namespace) -> dict:
    runner = PipelineRunner.from_settings()
    categories = (
        [c.strip() for c in args.categories.split(",")] if args.categories else None
    )

    if args.mode == "full":
        result = await runner.run_full(args.city, categories)
        out = result.as_dict()
        log_path = LOG_DIR / f"pipeline_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        log_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return out
    if args.mode == "discovery":
        return await runner.discovery(args.city, categories)
    if args.mode == "audit-pending":
        return await runner.audit_pending()
    if args.mode == "outreach-ready":
        return await runner.outreach_ready()
    raise ValueError(f"Unknown mode: {args.mode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes Prospecting Pipeline (CLI)")
    parser.add_argument("--city", default="Cuiaba", help="Target city")
    parser.add_argument(
        "--mode",
        choices=["full", "discovery", "audit-pending", "outreach-ready"],
        default="full",
    )
    parser.add_argument("--categories", help="Comma-separated categories")
    args = parser.parse_args()

    result = asyncio.run(_dispatch(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
