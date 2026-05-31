#!/usr/bin/env python3
"""Patch hermes_api.py on VM to add audit endpoints."""
import sys

api_path = "/home/hermes-gcp/.hermes/scripts/hermes_api.py"
with open(api_path, "r") as f:
    content = f.read()

# 1. Add import for web_audit at top (after existing imports)
old_import = "from pathlib import Path"
new_import = """from pathlib import Path
import threading"""

if "import threading" not in content:
    content = content.replace(old_import, new_import, 1)
    print("PATCHED: added threading import")
else:
    print("SKIP: threading import already present")

# 2. Add audit state variable after HERMES_HOME definition
# Find a good anchor point - after the global variables
old_anchor = "app = FastAPI("
audit_state_block = """# Audit state
_audit_state = {
    "running": False,
    "total": 0,
    "done": 0,
    "results": [],
    "started_at": None,
    "finished_at": None,
    "errors": [],
}
_audit_lock = threading.Lock()

app = FastAPI("""

if "_audit_state" not in content:
    content = content.replace(old_anchor, audit_state_block, 1)
    print("PATCHED: added audit state")
else:
    print("SKIP: audit state already present")

# 3. Add audit endpoints before the hermes_status endpoint
old_hermes_status = '@app.get("/api/hermes/status")'

audit_endpoints = '''@app.post("/api/audit/start")
async def start_audit(batch_size: int = 50, stage: str = "discovered"):
    """Start batch audit of prospects in background thread."""
    global _audit_state
    with _audit_lock:
        if _audit_state["running"]:
            return {"status": "already_running", "done": _audit_state["done"], "total": _audit_state["total"]}

    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM prospects WHERE stage = ? AND (audit_summary IS NULL OR audit_summary = '') ORDER BY score DESC LIMIT ?",
            (stage, batch_size)
        ).fetchall()
        prospects = [dict(r) for r in rows]
    finally:
        db.close()

    if not prospects:
        return {"status": "nothing_to_audit", "total": 0}

    with _audit_lock:
        _audit_state = {
            "running": True,
            "total": len(prospects),
            "done": 0,
            "results": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "errors": [],
        }

    def run_audit_batch(prospect_list):
        global _audit_state
        import importlib
        sys.path.insert(0, str(HERMES_HOME / "scripts"))
        try:
            import web_audit
            importlib.reload(web_audit)
        except Exception as e:
            with _audit_lock:
                _audit_state["errors"].append(f"Import error: {e}")
                _audit_state["running"] = False
            return

        for p in prospect_list:
            try:
                result = web_audit.audit_prospect(p)
                new_stage = "qualified" if result["score"] >= 50 else "discovered"
                if result["score"] >= 70:
                    new_stage = "audited"

                db2 = get_db()
                try:
                    db2.execute(
                        "UPDATE prospects SET score=?, stage=?, audit_summary=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (result["score"], new_stage, result["audit_summary"], p["id"])
                    )
                    db2.execute(
                        "INSERT INTO activities (type, title, description, prospect_id) VALUES (?,?,?,?)",
                        ("audit", f"Auditoria: {p.get('business_name', p.get('name', '?'))}",
                         f"Score: {result['score']} | Stage: {new_stage}", p["id"])
                    )
                    db2.commit()
                finally:
                    db2.close()

                with _audit_lock:
                    _audit_state["done"] += 1
                    _audit_state["results"].append({
                        "id": p["id"],
                        "name": p.get("business_name", p.get("name")),
                        "score": result["score"],
                        "stage": new_stage,
                    })

                import time
                time.sleep(0.3)

            except Exception as e:
                with _audit_lock:
                    _audit_state["done"] += 1
                    _audit_state["errors"].append(f"{p.get('business_name', '?')}: {e}")

        with _audit_lock:
            _audit_state["running"] = False
            _audit_state["finished_at"] = datetime.now(timezone.utc).isoformat()

    t = threading.Thread(target=run_audit_batch, args=(prospects,), daemon=True)
    t.start()

    return {"status": "started", "total": len(prospects)}


@app.get("/api/audit/status")
async def audit_status():
    """Get current audit batch status."""
    with _audit_lock:
        return dict(_audit_state)


@app.post("/api/audit/prospect/{prospect_id}")
async def audit_single(prospect_id: int):
    """Audit a single prospect immediately."""
    db = get_db()
    try:
        row = db.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
        if not row:
            return {"error": "Prospect not found"}, 404
        p = dict(row)
    finally:
        db.close()

    sys.path.insert(0, str(HERMES_HOME / "scripts"))
    from web_audit import audit_prospect
    result = audit_prospect(p)

    new_stage = "qualified" if result["score"] >= 50 else "discovered"
    if result["score"] >= 70:
        new_stage = "audited"

    db = get_db()
    try:
        db.execute(
            "UPDATE prospects SET score=?, stage=?, audit_summary=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (result["score"], new_stage, result["audit_summary"], prospect_id)
        )
        db.execute(
            "INSERT INTO activities (type, title, description, prospect_id) VALUES (?,?,?,?)",
            ("audit", f"Auditoria: {p.get('business_name', p.get('name', '?'))}",
             f"Score: {result['score']} | Stage: {new_stage}", prospect_id)
        )
        db.commit()
    finally:
        db.close()

    result["new_stage"] = new_stage
    return result


''' + '@app.get("/api/hermes/status")'

if '/api/audit/start' not in content:
    content = content.replace(old_hermes_status, audit_endpoints, 1)
    print("PATCHED: added audit endpoints")
else:
    print("SKIP: audit endpoints already present")

with open(api_path, "w") as f:
    f.write(content)

print("ALL DONE")
