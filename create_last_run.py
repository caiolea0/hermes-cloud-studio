import json
from pathlib import Path

home = Path.home() / ".hermes"
reports = sorted(home.glob("logs/night_scraper_report_*.json"), reverse=True)
if not reports:
    print("No report found")
    exit(1)

d = json.loads(reports[0].read_text(encoding="utf-8"))
out = {
    "completed_at": "2026-05-27T06:38:24Z",
    "stats": d,
    "cities": d.get("cities_completed", []),
    "total_categories": 111,
}
dest = home / "data" / "night_scraper_last_run.json"
dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Created {dest}")
