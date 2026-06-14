/* ============================================================
   Pipeline Studio — Templates Gallery (F.9.3c REAL)
   ============================================================
   Fetches GET /api/pipeline-studio/templates → 5 seed cards.
   Clone button stub (F.9.4 enhance — disabled with tooltip).
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
        sub.textContent = "Selecione um template como ponto de partida. Clone (F.9.4) disponível em breve.";
        header.appendChild(h3);
        header.appendChild(sub);
        panel.appendChild(header);

        var grid = document.createElement("div");
        grid.className = "ps-templates-grid";

        _templates.forEach(function (tpl) {
            var card = document.createElement("div");
            card.className = "ps-template-card";
            card.setAttribute("tabindex", "0");
            card.setAttribute("role", "button");
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
            cloneBtn.className = "ps-btn ps-btn-ghost";
            cloneBtn.type = "button";
            cloneBtn.style.cssText = "margin-top:10px;width:100%;justify-content:center;opacity:0.5";
            cloneBtn.textContent = "Clonar e editar (F.9.4)";
            cloneBtn.disabled = true;
            cloneBtn.title = "Funcionalidade clone-and-modify disponível em F.9.4";
            cloneBtn.setAttribute("aria-disabled", "true");

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
