#!/usr/bin/env python3
"""Patch hermes_api.py on VM to support gosom scraper status."""
import sys

api_path = "/home/hermes-gcp/.hermes/scripts/hermes_api.py"
with open(api_path, "r") as f:
    content = f.read()

# 1. Add gosom file paths to scraper_status
old1 = '    checkpoint_file = HERMES_HOME / "data" / "night_scraper_checkpoint.json"\n    last_run_file = HERMES_HOME / "data" / "night_scraper_last_run.json"\n    pid_file = HERMES_HOME / "data" / "night_scraper.pid"'

new1 = '    gosom_checkpoint = HERMES_HOME / "data" / "gosom_checkpoint.json"\n    gosom_last_run = HERMES_HOME / "data" / "gosom_last_run.json"\n    checkpoint_file = HERMES_HOME / "data" / "night_scraper_checkpoint.json"\n    last_run_file = HERMES_HOME / "data" / "night_scraper_last_run.json"\n    pid_file = HERMES_HOME / "data" / "night_scraper.pid"'

if old1 not in content:
    print("SKIP: checkpoint_file block not found (maybe already patched)")
else:
    content = content.replace(old1, new1, 1)
    print("PATCHED: added gosom file paths")

# 2. Replace last_run fallback to check gosom files too
old2 = '''    # If no active checkpoint, try last run
    last_run = {}
    if not checkpoint and last_run_file.exists():
        try:
            last_run = json.loads(last_run_file.read_text(encoding="utf-8"))
        except Exception:
            pass'''

new2 = '''    # Check gosom checkpoint (active scrape)
    if not checkpoint and gosom_checkpoint.exists():
        try:
            gcp = json.loads(gosom_checkpoint.read_text(encoding="utf-8"))
            cities_done = gcp.get("stats", {}).get("cities_completed", [])
            checkpoint = {
                "city": cities_done[-1] if cities_done else "scraping...",
                "category_idx": gcp.get("cat_idx", 0),
                "stats": gcp.get("stats", {}),
                "timestamp": gcp.get("timestamp"),
            }
            running = True
        except Exception:
            pass

    # If no active checkpoint, try last run (gosom first, then legacy)
    last_run = {}
    if not checkpoint:
        for lr_file in [gosom_last_run, last_run_file]:
            if lr_file.exists():
                try:
                    last_run = json.loads(lr_file.read_text(encoding="utf-8"))
                    break
                except Exception:
                    pass'''

if old2 not in content:
    print("SKIP: last_run block not found")
else:
    content = content.replace(old2, new2, 1)
    print("PATCHED: gosom checkpoint + last_run fallback")

# 3. Update start_scraper to use gosom
old3 = '''    # Build command
    venv_python = str(HERMES_HOME / "hermes-agent" / "venv" / "bin" / "python")
    script = str(HERMES_HOME / "scripts" / "night_scraper.py")
    cmd_args = [venv_python, script]

    if config.cities and len(config.cities) == 1:
        cmd_args.extend(["--city", config.cities[0]])'''

new3 = '''    # Build command -- use gosom scraper
    script = str(HERMES_HOME / "scripts" / "gosom_scraper.py")
    cmd_args = ["python3", script]

    if config.cities:
        cmd_args.extend(["--cities", ",".join(config.cities)])
    if config.categories:
        cmd_args.extend(["--categories", ",".join(config.categories)])'''

if old3 not in content:
    print("SKIP: start_scraper build command not found")
else:
    content = content.replace(old3, new3, 1)
    print("PATCHED: start_scraper uses gosom")

# 4. Update history to include gosom reports
old4 = '    for f in sorted(log_dir.glob("night_scraper_report_*.json"), reverse=True):'
new4 = '    for f in sorted(list(log_dir.glob("night_scraper_report_*.json")) + list((HERMES_HOME / "data" / "discovery").glob("gosom_report_*.json")), key=lambda x: x.stat().st_mtime, reverse=True):'

if old4 not in content:
    print("SKIP: history glob not found")
else:
    content = content.replace(old4, new4, 1)
    print("PATCHED: history includes gosom reports")

with open(api_path, "w") as f:
    f.write(content)

print("ALL DONE")
