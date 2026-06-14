/* ============================================================
   Pipeline Studio — Templates Gallery (F.9.4 clone REAL)
   ============================================================
   Fetches GET /api/pipeline-studio/templates → 5 seed cards.
   F.9.4: Clone button real — POST /drafts then switchTab Builder.
   textContent XSS safe throughout.

   API: window.PipelineStudioTemplates.{init, render, destroy}
   ============================================================ */
(function () {
    "use strict";

    var _initialized = false;
    var _templates   = [];

    /* ---- DOM helpers ------------------------------------ */

    function _id(id) { return document.getElementById(id); }

    function _setText(el, text) {
        if (el) el.textContent = (text == null) ? "" : String(text);
    }

    function _getToken() {
        return localStorage.getItem("hermes_token") || "";
    }

    function _showToast(msg, type) {
        if (window.toast && typeof window.toast === "function") {
            window.toast(msg, type || "info");
        } else {
            console.log("[PipelineStudioTemplates] " + msg);
        }
    }

    /* ---- Fetch templates -------------------------------- */

    async function _fetchTemplates() {
        try {
            var resp = await fetch("/api/pipeline-studio/templates", {
                headers: { "X-Hermes-Token": _getToken() }
            });
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            var data = await resp.json();
            _templates = (data && data.templates) ? data.templates : [];
        } catch (e) {
            console.warn("[PipelineStudioTemplates] fetch failed", e);
            _templates = [];
        }
    }

    /* ---- Clone template → create draft → switch to Builder --- */

    async function _cloneTemplate(tpl, btn) {
        btn.disabled = true;
        btn.textContent = "Clonando...";
        try {
            var resp = await fetch("/api/pipeline-studio/drafts", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Hermes-Token": _getToken()
                },
                body: JSON.stringify({
                    name: tpl.name || tpl.id || "Template clone",
                    description: tpl.description || "",
                    yaml_blob: tpl.yaml_blob || "name: template\nsteps: []\n",
                    tags: ["template-derived"]
                })
            });
            if (!resp.ok) {
                var err = await resp.json().catch(function () { return {}; });
                throw new Error(err.detail || ("HTTP " + resp.status));
            }
            var newDraft = await resp.json();
            _showToast("Template clonado para Builder", "success");
            /* Switch to Builder tab and load the cloned draft */
            if (window.PipelineStudioShell && typeof window.PipelineStudioShell.switchTab === "function") {
                window.PipelineStudioShell.switchTab("builder", { draft_id: newDraft.id });
            }
        } catch (e) {
            _showToast("Erro ao clonar: " + e.message, "error");
            btn.disabled = false;
            btn.textContent = "Clonar e editar";
        }
    }

    /* ---- Render ----------------------------------------- */

    function render() {
        var panel = _id("ps-panel-templates");
        if (!panel) return;

        panel.innerHTML = "";

        if (!_templates.length) {
            var empty = document.createElement("div");
            empty.className = "ps-stub-placeholder";
            empty.textContent = "Nenhum template encontrado.";
            panel.appendChild(empty);
            return;
        }

        var header = document.createElement("div");
        header.style.cssText = "margin-bottom:16px";
        var h3 = document.createElement("h3");
        h3.style.cssText = "margin:0 0 4px;font-size:15px;font-weight:600;color:var(--text-1)";
        h3.textContent = "Templates de Pipeline";
        var sub = document.createElement("p");
        sub.style.cssText = "margin:0;font-size:12px;color:var(--text-3)";
        sub.textContent = "Clone um template como ponto de partida e edite no Builder.";
        header.appendChild(h3);
        header.appendChild(sub);
        panel.appendChild(header);

        var grid = document.createElement("div");
        grid.className = "ps-templates-grid";

        _templates.forEach(function (tpl) {
            var card = document.createElement("div");
            card.className = "ps-template-card";
            card.setAttribute("tabindex", "0");
            card.setAttribute("role", "article");
            card.setAttribute("aria-label", "Template: " + (tpl.name || "Sem nome"));

            var nameEl = document.createElement("div");
            nameEl.className = "ps-template-name";
            nameEl.textContent = tpl.name || tpl.id || "Template";

            var descEl = document.createElement("div");
            descEl.className = "ps-template-desc";
            descEl.textContent = tpl.description || "—";

            var metaEl = document.createElement("div");
            metaEl.className = "ps-template-meta";

            var stepsEl = document.createElement("span");
            stepsEl.className = "ps-template-steps-badge";
            stepsEl.textContent = (tpl.steps_count || 0) + " steps";

            var tags = (tpl.tags || []);
            var tagsEl = document.createElement("span");
            tagsEl.style.cssText = "font-size:10px;color:var(--text-3)";
            tagsEl.textContent = tags.length ? tags.join(", ") : "";

            metaEl.appendChild(stepsEl);
            metaEl.appendChild(tagsEl);

            var cloneBtn = document.createElement("button");
            cloneBtn.className = "ps-btn ps-btn-ghost ps-template-clone-btn";
            cloneBtn.type = "button";
            cloneBtn.textContent = "Clonar e editar";
            cloneBtn.setAttribute("aria-label", "Clonar template " + (tpl.name || "") + " para o Builder");

            /* D1: clone on click — race prevention via disabled during request */
            cloneBtn.addEventListener("click", function () {
                _cloneTemplate(tpl, cloneBtn);
            });

            card.appendChild(nameEl);
            card.appendChild(descEl);
            card.appendChild(metaEl);
            card.appendChild(cloneBtn);

            grid.appendChild(card);
        });

        panel.appendChild(grid);
    }

    /* ---- Init / Destroy --------------------------------- */

    async function init() {
        if (_initialized) { render(); return; }
        _initialized = true;
        await _fetchTemplates();
        render();
    }

    function destroy() {
        _initialized = false;
    }

    /* ---- Public API ------------------------------------- */

    window.PipelineStudioTemplates = { init: init, render: render, destroy: destroy };

})();
