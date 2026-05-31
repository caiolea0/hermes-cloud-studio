#!/usr/bin/env python3
"""Patch hermes_api.py on VM to add outreach generation endpoint."""
import sys

api_path = "/home/hermes-gcp/.hermes/scripts/hermes_api.py"
with open(api_path, "r") as f:
    content = f.read()

# Add outreach endpoint before hermes_status
old = '@app.get("/api/hermes/status")'

new_block = '''@app.post("/api/prospects/{prospect_id}/outreach")
async def generate_prospect_outreach(prospect_id: int):
    """Generate outreach message for a prospect."""
    db = get_db()
    try:
        row = db.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
        if not row:
            return {"error": "Prospect not found"}, 404
        p = dict(row)
    finally:
        db.close()

    sys.path.insert(0, str(HERMES_HOME / "scripts"))
    from outreach_generator import generate_outreach
    result = generate_outreach(p)

    db = get_db()
    try:
        db.execute(
            "UPDATE prospects SET outreach_message=?, outreach_status='ready', stage='outreach', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (result.get("whatsapp_message", ""), prospect_id)
        )
        db.execute(
            "INSERT INTO activities (type, title, description, prospect_id) VALUES (?,?,?,?)",
            ("outreach", "Proposta gerada: " + p.get("business_name", p.get("name", "?")),
             "Servicos: " + ", ".join(result.get("recommended_services", [])[:3]), prospect_id)
        )
        db.commit()
    finally:
        db.close()

    return result


''' + '@app.get("/api/hermes/status")'

if '/api/prospects/{prospect_id}/outreach' not in content:
    content = content.replace(old, new_block, 1)
    print("PATCHED: added outreach endpoint")
else:
    print("SKIP: outreach endpoint already present")

with open(api_path, "w") as f:
    f.write(content)

print("ALL DONE")
