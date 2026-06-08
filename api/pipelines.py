"""Hermes Cloud Studio — Pipeline templates + executions (MERGED-011)."""
from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException

from config import settings
from core.ai import call_ai
from core.models import PipelineExecuteRequest, PipelineTemplateCreate, PipelineTemplateUpdate
from core.state import VM_API_URL, get_db, spawn

router = APIRouter()


@router.get("/api/pipelines")
async def list_pipelines():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM pipeline_templates ORDER BY updated_at DESC").fetchall()
        templates = []
        for r in rows:
            t = dict(r)
            t["targets_config"] = json.loads(t["targets_config"]) if t["targets_config"] else {}
            t["schedule_config"] = json.loads(t["schedule_config"]) if t["schedule_config"] else {}
            exec_row = conn.execute(
                "SELECT * FROM pipeline_executions WHERE template_id = ? ORDER BY created_at DESC LIMIT 1",
                (t["id"],)
            ).fetchone()
            t["last_execution"] = dict(exec_row) if exec_row else None
            templates.append(t)
        return {"pipelines": templates}
    finally:
        conn.close()


@router.post("/api/pipelines")
async def create_pipeline(body: PipelineTemplateCreate):
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO pipeline_templates (name, type, description, prompt, targets_config, schedule_config)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (body.name, body.type, body.description, body.prompt,
             json.dumps(body.targets_config) if body.targets_config else None,
             json.dumps(body.schedule_config) if body.schedule_config else None)
        )
        conn.commit()
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        row = conn.execute("SELECT * FROM pipeline_templates WHERE id = ?", (pid,)).fetchone()
        result = dict(row)
        result["targets_config"] = json.loads(result["targets_config"]) if result["targets_config"] else {}
        result["schedule_config"] = json.loads(result["schedule_config"]) if result["schedule_config"] else {}
        return result
    finally:
        conn.close()


@router.get("/api/pipelines/{pipeline_id}")
async def get_pipeline(pipeline_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM pipeline_templates WHERE id = ?", (pipeline_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Pipeline not found")
        t = dict(row)
        t["targets_config"] = json.loads(t["targets_config"]) if t["targets_config"] else {}
        t["schedule_config"] = json.loads(t["schedule_config"]) if t["schedule_config"] else {}
        execs = conn.execute(
            "SELECT * FROM pipeline_executions WHERE template_id = ? ORDER BY created_at DESC LIMIT 10",
            (pipeline_id,)
        ).fetchall()
        t["executions"] = [dict(e) for e in execs]
        return t
    finally:
        conn.close()


@router.patch("/api/pipelines/{pipeline_id}")
async def update_pipeline(pipeline_id: int, body: PipelineTemplateUpdate):
    conn = get_db()
    try:
        existing = conn.execute("SELECT * FROM pipeline_templates WHERE id = ?", (pipeline_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Pipeline not found")
        updates = []
        params = []
        for field in ["name", "description", "prompt", "is_active"]:
            val = getattr(body, field, None)
            if val is not None:
                updates.append(f"{field} = ?")
                params.append(val)
        if body.targets_config is not None:
            updates.append("targets_config = ?")
            params.append(json.dumps(body.targets_config))
        if body.schedule_config is not None:
            updates.append("schedule_config = ?")
            params.append(json.dumps(body.schedule_config))
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(pipeline_id)
            conn.execute(f"UPDATE pipeline_templates SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        row = conn.execute("SELECT * FROM pipeline_templates WHERE id = ?", (pipeline_id,)).fetchone()
        result = dict(row)
        result["targets_config"] = json.loads(result["targets_config"]) if result["targets_config"] else {}
        result["schedule_config"] = json.loads(result["schedule_config"]) if result["schedule_config"] else {}
        return result
    finally:
        conn.close()


@router.delete("/api/pipelines/{pipeline_id}")
async def delete_pipeline(pipeline_id: int):
    conn = get_db()
    try:
        conn.execute("DELETE FROM pipeline_executions WHERE template_id = ?", (pipeline_id,))
        conn.execute("DELETE FROM pipeline_templates WHERE id = ?", (pipeline_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/api/pipelines/{pipeline_id}/execute")
async def execute_pipeline(pipeline_id: int, body: PipelineExecuteRequest = None):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM pipeline_templates WHERE id = ?", (pipeline_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Pipeline not found")
        template = dict(row)
        targets = json.loads(template["targets_config"]) if template["targets_config"] else {}
        prompt = (body.override_prompt if body and body.override_prompt else template["prompt"]) or ""

        conn.execute(
            """INSERT INTO pipeline_executions (template_id, status, started_at)
               VALUES (?, 'running', CURRENT_TIMESTAMP)""",
            (pipeline_id,)
        )
        conn.commit()
        exec_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute(
            "UPDATE pipeline_templates SET last_run_at = CURRENT_TIMESTAMP, total_runs = total_runs + 1 WHERE id = ?",
            (pipeline_id,)
        )
        conn.commit()
    finally:
        conn.close()

    spawn(_run_pipeline_async(pipeline_id, exec_id, template, targets, prompt))

    return {"execution_id": exec_id, "status": "running", "pipeline_id": pipeline_id}


async def _run_pipeline_async(pipeline_id: int, exec_id: int, template: dict, targets: dict, prompt: str):
    """Run pipeline in background, updating execution record as it progresses."""
    log_entries = []
    current_phase = {"name": "init", "step": 0, "total_steps": 0}

    def add_log(msg: str, level: str = "info", phase: str = None, step: int = None, total: int = None, detail: dict = None):
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "msg": msg, "level": level}
        if phase:
            current_phase["name"] = phase
            entry["phase"] = phase
        else:
            entry["phase"] = current_phase["name"]
        if step is not None:
            current_phase["step"] = step
            entry["step"] = step
        if total is not None:
            current_phase["total_steps"] = total
            entry["total_steps"] = total
        if detail:
            entry["detail"] = detail
        log_entries.append(entry)
        conn = get_db()
        try:
            progress = 0
            if current_phase["total_steps"] > 0:
                progress = int((current_phase["step"] / current_phase["total_steps"]) * 100)
            conn.execute(
                "UPDATE pipeline_executions SET log = ?, progress = ?, processed_items = ? WHERE id = ?",
                (json.dumps(log_entries), progress, current_phase["step"], exec_id)
            )
            conn.commit()
        finally:
            conn.close()

    try:
        pipeline_type = template.get("type", "custom")
        add_log(f"Pipeline '{template['name']}' iniciado", phase="starting",
                detail={"type": pipeline_type, "template_id": pipeline_id})

        if pipeline_type == "linkedin_viewer":
            await _execute_linkedin_viewer(exec_id, targets, prompt, add_log)
        elif pipeline_type == "scraper":
            add_log("Conectando ao Hermes VM...", phase="connecting")
            add_log("Enviando configuracao de scraping...", phase="dispatching")
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(f"{VM_API_URL}/api/scraper/start", json=targets)
                if r.status_code == 200:
                    add_log("Scraper iniciado com sucesso no Hermes", phase="running", detail={"vm_response": r.status_code})
                else:
                    add_log(f"Falha ao iniciar scraper: HTTP {r.status_code}", level="error", phase="error")
        elif pipeline_type == "audit":
            add_log("Iniciando auditoria em batch...", phase="connecting")
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(f"{VM_API_URL}/api/audit/batch", json=targets)
                add_log(f"Auditoria batch: HTTP {r.status_code}", phase="running")
        elif pipeline_type == "outreach":
            add_log("Gerando mensagens de outreach...", phase="connecting")
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(f"{VM_API_URL}/api/outreach/batch", json=targets)
                add_log(f"Outreach batch: HTTP {r.status_code}", phase="running")
        else:
            add_log("Analisando demanda com Agent Zero...", phase="analyzing")
            add_log(f"Prompt: {prompt[:200]}", level="debug")
            try:
                ai_result = await call_ai(prompt, timeout=300)
                output = ai_result["response"]
                provider = ai_result["provider"]
                add_log(f"AI respondeu ({provider}): {output[:500]}", phase="completed")
            except Exception as e:
                add_log(f"Erro AI: {e}", level="error", phase="error")

        conn = get_db()
        try:
            conn.execute(
                "UPDATE pipeline_executions SET status = 'completed', completed_at = CURRENT_TIMESTAMP, progress = 100, log = ? WHERE id = ?",
                (json.dumps(log_entries), exec_id)
            )
            conn.commit()
        finally:
            conn.close()
        add_log("Pipeline concluido com sucesso", phase="done")

    except Exception as e:
        add_log(f"Pipeline falhou: {e}", level="error", phase="failed")
        conn = get_db()
        try:
            conn.execute(
                "UPDATE pipeline_executions SET status = 'failed', completed_at = CURRENT_TIMESTAMP, log = ? WHERE id = ?",
                (json.dumps(log_entries), exec_id)
            )
            conn.commit()
        finally:
            conn.close()


async def _execute_linkedin_viewer(exec_id: int, targets: dict, prompt: str, add_log):
    """Execute LinkedIn profile viewer pipeline via Hermes VM."""
    roles = targets.get("roles", ["tech recruiter", "project manager", "SMB owner"])
    max_profiles = targets.get("max_profiles", 500)
    location = targets.get("location", "Brazil")

    add_log("Preparando plano de execucao...", phase="planning",
            detail={"roles": roles, "location": location, "max_profiles": max_profiles})

    conn = get_db()
    try:
        conn.execute(
            "UPDATE pipeline_executions SET total_items = ? WHERE id = ?",
            (max_profiles, exec_id)
        )
        conn.commit()
    finally:
        conn.close()

    add_log(f"Alvos: {', '.join(roles)}", phase="planning", step=1, total=5)
    add_log(f"Regiao: {location} | Limite: {max_profiles} perfis", phase="planning")

    add_log("Conectando ao Hermes VM...", phase="connecting", step=2, total=5)

    # --- Try real LinkedIn viewer (Patchright anti-detection) ---
    result_data = None
    try:
        from linkedin import LinkedInViewer, LinkedInConfig
        li_config = LinkedInConfig(
            account_email=settings.linkedin_email,
            account_type=settings.linkedin_account_type,
            proxy_server=settings.linkedin_proxy,
            proxy_username=settings.linkedin_proxy_user,
            proxy_password=settings.linkedin_proxy_pass,
            headless=True,
        )
        li_config.targets = {"roles": roles, "location": location, "max_profiles": max_profiles}

        viewer = LinkedInViewer(li_config)
        viewer.set_log_callback(lambda msg, **kw: add_log(msg, **kw))

        add_log("LinkedIn Viewer real ativo — Patchright anti-deteccao", phase="authenticating", step=3, total=5)
        result_data = await viewer.start()
        add_log(f"Viewer real concluiu: {result_data.get('profiles_visited', 0)} perfis", phase="monitoring", step=5, total=5)

    except ImportError:
        add_log("LinkedIn module nao instalado — pip install patchright | usando simulacao", level="warn",
                phase="dispatched", step=3, total=5)
    except Exception as e:
        add_log(f"Viewer real falhou: {str(e)[:100]} — fallback simulacao", level="warn",
                phase="dispatched", step=3, total=5)

    # --- Fallback: try VM ---
    if not result_data:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                add_log("Tentando via Hermes VM...", phase="authenticating", step=3, total=5)
                r = await client.post(
                    f"{VM_API_URL}/api/pipeline/execute",
                    json={"type": "linkedin_viewer", "config": {
                        "roles": roles, "max_profiles": max_profiles,
                        "location": location, "prompt": prompt,
                    }}
                )
                if r.status_code == 200:
                    result_data = r.json()
                    add_log("VM executou com sucesso", phase="searching", step=4, total=5)
                else:
                    add_log(f"VM HTTP {r.status_code}", level="warn", phase="dispatched", step=4, total=5)
        except Exception:
            add_log("VM inacessivel — modo simulacao", level="warn", phase="offline", step=4, total=5)

    # --- Fallback: simulation ---
    if not result_data or "profiles" not in result_data:
        add_log("Gerando resultados de demonstracao...", phase="processing")
        first_names = ["Ana", "Bruno", "Carlos", "Diana", "Eduardo", "Fernanda", "Gabriel", "Helena",
                       "Igor", "Julia", "Lucas", "Mariana", "Nicolas", "Olivia", "Pedro", "Rafaela",
                       "Samuel", "Tatiana", "Victor", "Amanda", "Diego", "Camila", "Thiago", "Larissa",
                       "Felipe", "Bianca", "Ricardo", "Patricia", "Matheus", "Vanessa"]
        last_names = ["Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Almeida",
                      "Nascimento", "Lima", "Araujo", "Pereira", "Barbosa", "Ribeiro", "Carvalho",
                      "Gomes", "Martins", "Rocha", "Costa", "Freitas", "Moreira"]
        titles_by_role = {
            "tech recruiter": ["Tech Recruiter", "IT Recruiter Senior", "Talent Acquisition Tech",
                               "Recrutador de TI", "Head of Tech Recruiting", "Tech Sourcer"],
            "project manager": ["Project Manager", "Gerente de Projetos", "PM Senior", "Scrum Master",
                                "Delivery Manager", "Program Manager", "Tech Lead PM"],
            "SMB owner": ["CEO", "Fundador", "Diretor", "Socio-Diretor", "Owner",
                          "Managing Director", "Co-Founder & CTO"],
        }
        companies = ["Nubank", "iFood", "Stone", "TOTVS", "Movile", "Loggi", "QuintoAndar",
                     "Loft", "Creditas", "Gympass", "Wildlife", "PagSeguro", "Locaweb", "VTEX",
                     "RD Station", "Hotmart", "CI&T", "Accenture Brasil", "ThoughtWorks",
                     "Stefanini", "Wipro", "TCS Brasil", "Capgemini", "BairesDev",
                     "Mercado Livre", "Itau", "Bradesco", "XP Inc", "BTG Pactual", "Ambev Tech"]
        cities = ["Sao Paulo", "Rio de Janeiro", "Curitiba", "Belo Horizonte", "Porto Alegre",
                  "Florianopolis", "Brasilia", "Campinas", "Recife", "Salvador"]

        num_profiles = min(random.randint(80, 200), max_profiles)
        profiles = []
        by_role = {}
        for i in range(num_profiles):
            role = random.choice(roles)
            by_role[role] = by_role.get(role, 0) + 1
            fname = random.choice(first_names)
            lname = random.choice(last_names)
            name = f"{fname} {lname}"
            slug = f"{fname.lower()}-{lname.lower()}-{random.randint(1000,9999)}"
            title = random.choice(titles_by_role.get(role, ["Professional"]))
            company = random.choice(companies)
            city = random.choice(cities)
            profiles.append({
                "name": f"[SIM] {name}",
                "title": title,
                "company": company,
                "city": city,
                "role_match": role,
                "url": f"https://linkedin.com/in/{slug}",
                "visited": True,
                "visited_at": datetime.now(timezone.utc).isoformat(),
                "simulated": True,
            })

            if (i + 1) % 25 == 0:
                add_log(f"Visitados {i + 1}/{num_profiles} perfis...", phase="visiting",
                        step=4, total=5)
                conn = get_db()
                try:
                    conn.execute(
                        "UPDATE pipeline_executions SET processed_items = ?, progress = ? WHERE id = ?",
                        (i + 1, int(((i + 1) / num_profiles) * 100), exec_id)
                    )
                    conn.commit()
                finally:
                    conn.close()
                await asyncio.sleep(0.1)

        result_data = {
            "type": "linkedin_viewer",
            "simulated": True,
            "profiles_visited": num_profiles,
            "profiles_found": num_profiles + random.randint(50, 200),
            "by_role": by_role,
            "by_city": {},
            "profiles": profiles,
        }
        for p in profiles:
            c = p["city"]
            result_data["by_city"][c] = result_data["by_city"].get(c, 0) + 1

        add_log(f"Concluido: {num_profiles} perfis visitados", phase="monitoring", step=5, total=5,
                detail={"profiles_visited": num_profiles, "by_role": by_role})

    conn = get_db()
    try:
        conn.execute(
            "UPDATE pipeline_executions SET result = ?, processed_items = ?, progress = 100 WHERE id = ?",
            (json.dumps(result_data), result_data.get("profiles_visited", 0), exec_id)
        )
        conn.commit()
    finally:
        conn.close()

    return result_data


# --- Pipeline executions (status / list) ---

@router.get("/api/pipelines/{pipeline_id}/executions")
async def list_executions(pipeline_id: int, limit: int = 20):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM pipeline_executions WHERE template_id = ? ORDER BY created_at DESC LIMIT ?",
            (pipeline_id, limit)
        ).fetchall()
        execs = []
        for r in rows:
            e = dict(r)
            e["log"] = json.loads(e["log"]) if e["log"] else []
            e["result"] = json.loads(e["result"]) if e.get("result") else None
            execs.append(e)
        return {"executions": execs}
    finally:
        conn.close()


@router.get("/api/pipeline-executions/active")
async def get_active_executions():
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT e.*, t.name as pipeline_name, t.type as pipeline_type
               FROM pipeline_executions e
               JOIN pipeline_templates t ON e.template_id = t.id
               WHERE e.status IN ('pending', 'running')
               ORDER BY e.created_at DESC"""
        ).fetchall()
        recent = conn.execute(
            """SELECT e.*, t.name as pipeline_name, t.type as pipeline_type
               FROM pipeline_executions e
               JOIN pipeline_templates t ON e.template_id = t.id
               WHERE e.status IN ('completed', 'failed')
               ORDER BY e.completed_at DESC LIMIT 5"""
        ).fetchall()
        def parse_exec(r):
            e = dict(r)
            e["log"] = json.loads(e["log"]) if e["log"] else []
            e["result"] = json.loads(e["result"]) if e.get("result") else None
            return e
        return {
            "active": [parse_exec(r) for r in rows],
            "recent": [parse_exec(r) for r in recent],
        }
    finally:
        conn.close()


@router.get("/api/pipeline-executions/{exec_id}")
async def get_execution(exec_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM pipeline_executions WHERE id = ?", (exec_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Execution not found")
        e = dict(row)
        e["log"] = json.loads(e["log"]) if e["log"] else []
        e["result"] = json.loads(e["result"]) if e.get("result") else None
        return e
    finally:
        conn.close()
