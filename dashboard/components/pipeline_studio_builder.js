/* ============================================================
   Pipeline Studio — Builder (F.9.3b REAL)
   ============================================================
   Builder vertical form: name + description + steps list
   + YAML preview side panel (50/50 split, D1+D3).
   Debounce 300ms para YAML preview (D3).
   Integra PipelineStudioStepPickerModal para add step (D2).

   API: window.PipelineStudioBuilder.{init, render, destroy}

   XSS: NUNCA innerHTML com input do owner.
        textContent para todos os campos dinâmicos.
        YAML preview: textContent no <code> (safe).

   D2 — steps cache sessionStorage 60s (step picker lê de lá).
   D3 — YAML side panel atualizado debounced 300ms.
   ============================================================ */
(function () {
    "use strict";

    /* ---- State ------------------------------------------ */

    var _initialized = false;
    var _draft = {
        name: "",
        description: "",
        steps: []
    };
    var _debounceTimer = null;
    var _lastSavedId = null;

    /* ---- DOM helpers ------------------------------------ */

    function _id(id) { return document.getElementById(id); }

    function _setText(el, text) {
        if (el) el.textContent = (text == null) ? "" : String(text);
    }

    function _esc(str) {
        return String(str == null ? "" : str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    /* ---- YAML renderer ---------------------------------- */

    function _renderYaml(draft) {
        var lines = [];
        lines.push("name: " + (draft.name || ""));
        if (draft.description) lines.push("description: " + draft.description);
        lines.push("steps:");
        if (!draft.steps.length) {
            lines.push("  # Adicione steps usando o botão abaixo");
        } else {
            draft.steps.forEach(function (s, i) {
                lines.push("  - name: " + (s.name || ("step_" + i)));
                lines.push("    tool: " + (s.tool || ""));
                if (s.args && Object.keys(s.args).length) {
                    lines.push("    args:");
                    Object.keys(s.args).forEach(function (k) {
                        lines.push("      " + k + ": " + JSON.stringify(s.args[k]));
                    });
                }
                if (s.continue_on_error) lines.push("    continue_on_error: true");
            });
        }
        return lines.join("\n");
    }

    /* ---- Debounced preview update (D3 300ms) ------------ */

    function _schedulePreviewUpdate() {
        clearTimeout(_debounceTimer);
        _debounceTimer = setTimeout(function () {
            var codeEl = _id("ps-yaml-code");
            if (codeEl) {
                codeEl.textContent = _renderYaml(_draft);  /* textContent = XSS safe */
            }
        }, 300);
    }

    /* ---- Steps rendering -------------------------------- */

    function _renderStepsList() {
        var listEl = _id("ps-steps-list");
        if (!listEl) return;
        if (!_draft.steps.length) {
            listEl.innerHTML = '<div class="ps-steps-empty">Nenhum step adicionado. Clique em "+ Adicionar step".</div>';
            return;
        }
        /* Build via DOM — NO innerHTML with user data */
        listEl.innerHTML = "";
        _draft.steps.forEach(function (step, idx) {
            var row = document.createElement("div");
            row.className = "ps-step-row";
            row.setAttribute("data-step-idx", String(idx));

            var idxEl = document.createElement("span");
            idxEl.className = "ps-step-idx";
            idxEl.textContent = String(idx + 1);

            var nameEl = document.createElement("span");
            nameEl.className = "ps-step-name";
            nameEl.textContent = step.name || ("step_" + idx);

            var toolEl = document.createElement("span");
            toolEl.className = "ps-step-tool";
            toolEl.textContent = step.tool || "—";
            toolEl.title = step.tool || "";

            var removeBtn = document.createElement("button");
            removeBtn.className = "ps-step-remove";
            removeBtn.type = "button";
            removeBtn.textContent = "×";
            removeBtn.setAttribute("aria-label", "Remover step " + (idx + 1));
            removeBtn.dataset.stepIdx = String(idx);

            row.appendChild(idxEl);
            row.appendChild(nameEl);
            row.appendChild(toolEl);
            row.appendChild(removeBtn);
            listEl.appendChild(row);
        });
    }

    /* ---- Step remove via event delegation --------------- */

    function _onStepsListClick(e) {
        var btn = e.target.closest(".ps-step-remove");
        if (!btn) return;
        var idx = parseInt(btn.dataset.stepIdx, 10);
        if (isNaN(idx)) return;
        _draft.steps.splice(idx, 1);
        _renderStepsList();
        _schedulePreviewUpdate();
    }

    /* ---- Step picker callback --------------------------- */

    function _onStepSelected(toolInfo) {
        /* toolInfo: {id, tool_name, mcp_server, description} from step picker */
        var stepName = toolInfo.tool_name || toolInfo.id || ("step_" + _draft.steps.length);
        _draft.steps.push({
            name: stepName,
            tool: toolInfo.id,
            args: {}
        });
        _renderStepsList();
        _schedulePreviewUpdate();
    }

    /* ---- Form event handlers ---------------------------- */

    function _onNameInput(e) {
        _draft.name = e.target.value;
        _schedulePreviewUpdate();
    }

    function _onDescInput(e) {
        _draft.description = e.target.value;
        _schedulePreviewUpdate();
    }

    function _onAddStepClick() {
        if (window.PipelineStudioStepPickerModal &&
            typeof window.PipelineStudioStepPickerModal.open === "function") {
            window.PipelineStudioStepPickerModal.open(_onStepSelected);
        }
    }

    /* ---- Save draft ------------------------------------- */

    async function _saveDraft() {
        var savBtn = _id("ps-save-draft-btn");
        if (!_draft.name.trim()) {
            _showToast("Nome obrigatório para salvar", "error");
            return;
        }
        var yamlBlob = _renderYaml(_draft);
        var token = localStorage.getItem("hermes_token") || "";
        try {
            var method = _lastSavedId ? "PUT" : "POST";
            var url = _lastSavedId
                ? "/api/pipeline-studio/drafts/" + encodeURIComponent(_lastSavedId)
                : "/api/pipeline-studio/drafts";
            var resp = await fetch(url, {
                method: method,
                headers: {
                    "Content-Type": "application/json",
                    "X-Hermes-Token": token
                },
                body: JSON.stringify({
                    name: _draft.name,
                    description: _draft.description || "",
                    yaml_blob: yamlBlob,
                    tags: []
                })
            });
            if (!resp.ok) {
                var err = await resp.json().catch(function () { return {}; });
                throw new Error(err.detail || ("HTTP " + resp.status));
            }
            var data = await resp.json();
            if (!_lastSavedId && data.id) _lastSavedId = data.id;
            _showToast("Draft salvo (v" + (data.version || 1) + ")", "success");
            /* Invalidate step picker cache on draft save */
            try { sessionStorage.removeItem("pipeline_studio_steps_v1"); } catch (e2) {}
        } catch (e) {
            _showToast("Erro ao salvar: " + e.message, "error");
        }
    }

    /* ---- Execute draft ---------------------------------- */

    async function _executeDraft() {
        if (!_lastSavedId) {
            _showToast("Salve o draft primeiro", "error");
            return;
        }
        var token = localStorage.getItem("hermes_token") || "";
        try {
            var resp = await fetch(
                "/api/pipeline-studio/drafts/" + encodeURIComponent(_lastSavedId) + "/execute",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-Hermes-Token": token
                    },
                    body: JSON.stringify({ variables: {}, ab_group: null })
                }
            );
            if (!resp.ok) {
                var err = await resp.json().catch(function () { return {}; });
                throw new Error(err.detail || ("HTTP " + resp.status));
            }
            var data = await resp.json();
            _showToast("Run iniciado: " + (data.run_id || "").slice(0, 8), "success");
            /* Notify monitor + switch tab */
            if (window.PipelineStudioRunsMonitor && data.run_id) {
                window.PipelineStudioRunsMonitor.trackRun(data.run_id, _lastSavedId);
            }
            if (window.PipelineStudioShell) {
                window.PipelineStudioShell.switchTab("runs-monitor");
            }
        } catch (e) {
            _showToast("Erro ao executar: " + e.message, "error");
        }
    }

    /* ---- Copy YAML -------------------------------------- */

    function _copyYaml() {
        var yaml = _renderYaml(_draft);
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(yaml).then(function () {
                _showToast("YAML copiado", "success");
            }).catch(function () {
                _showToast("Falha ao copiar", "error");
            });
        } else {
            _showToast("Clipboard API indisponível", "error");
        }
    }

    /* ---- Toast helper (delegates to global if available) */

    function _showToast(msg, type) {
        if (window.toast && typeof window.toast === "function") {
            window.toast(msg, type || "info");
        } else {
            console.log("[Builder] " + msg);
        }
    }

    /* ---- Render ----------------------------------------- */

    function render() {
        var panel = _id("ps-panel-builder");
        if (!panel) return;

        panel.innerHTML = [
            '<div class="ps-builder-split">',
            '  <!-- LEFT: form -->',
            '  <div class="ps-builder-form">',
            '    <div>',
            '      <div class="ps-field-label">Nome do pipeline</div>',
            '      <input class="ps-input" id="ps-draft-name" type="text"',
            '             maxlength="200" placeholder="Ex: outreach cobaia semanal"',
            '             aria-label="Nome do pipeline" autocomplete="off">',
            '    </div>',
            '    <div>',
            '      <div class="ps-field-label">Descrição (opcional)</div>',
            '      <textarea class="ps-textarea" id="ps-draft-desc"',
            '                maxlength="500" placeholder="Descreva o objetivo deste pipeline..."',
            '                rows="3" aria-label="Descrição do pipeline"></textarea>',
            '    </div>',
            '    <div>',
            '      <div class="ps-field-label">Steps</div>',
            '      <div class="ps-steps-list" id="ps-steps-list" role="list"',
            '           aria-label="Lista de steps do pipeline"></div>',
            '    </div>',
            '    <div class="ps-btn-row">',
            '      <button class="ps-btn ps-btn-ghost" id="ps-add-step-btn" type="button"',
            '              aria-label="Adicionar step ao pipeline">+ Adicionar step</button>',
            '    </div>',
            '    <div class="ps-btn-row" style="margin-top:8px">',
            '      <button class="ps-btn ps-btn-ghost" id="ps-save-draft-btn" type="button"',
            '              aria-label="Salvar draft do pipeline">Salvar Draft</button>',
            '      <button class="ps-btn ps-btn-success" id="ps-execute-btn" type="button"',
            '              aria-label="Executar pipeline">▶ Executar</button>',
            '    </div>',
            '  </div>',
            '  <!-- RIGHT: YAML preview -->',
            '  <div class="ps-yaml-panel">',
            '    <div class="ps-yaml-header">',
            '      <span class="ps-yaml-title">YAML Preview</span>',
            '      <button class="ps-btn ps-btn-ghost" id="ps-copy-yaml-btn" type="button"',
            '              style="padding:4px 10px;font-size: var(--text-xxs)"',
            '              aria-label="Copiar YAML para clipboard">Copiar</button>',
            '    </div>',
            '    <pre class="ps-yaml-pre"><code id="ps-yaml-code"></code></pre>',
            '  </div>',
            '</div>'
        ].join("\n");

        /* Restore form values from _draft state */
        var nameInput = _id("ps-draft-name");
        var descInput = _id("ps-draft-desc");
        if (nameInput) nameInput.value = _draft.name;
        if (descInput) descInput.value = _draft.description;

        _renderStepsList();
        _schedulePreviewUpdate();

        /* Wire events */
        if (nameInput) nameInput.addEventListener("input", _onNameInput);
        if (descInput) descInput.addEventListener("input", _onDescInput);

        var stepsListEl = _id("ps-steps-list");
        if (stepsListEl) stepsListEl.addEventListener("click", _onStepsListClick);

        var addBtn = _id("ps-add-step-btn");
        if (addBtn) addBtn.addEventListener("click", _onAddStepClick);

        var saveBtn = _id("ps-save-draft-btn");
        if (saveBtn) saveBtn.addEventListener("click", _saveDraft);

        var execBtn = _id("ps-execute-btn");
        if (execBtn) execBtn.addEventListener("click", _executeDraft);

        var copyBtn = _id("ps-copy-yaml-btn");
        if (copyBtn) copyBtn.addEventListener("click", _copyYaml);
    }

    /* ---- Init / Destroy --------------------------------- */

    function init() {
        if (_initialized) {
            /* Re-entry: re-render (preserves _draft state) */
            render();
            return;
        }
        _initialized = true;
        render();
    }

    function destroy() {
        clearTimeout(_debounceTimer);
        _initialized = false;
        /* Preserve _draft state across tab switches */
    }

    /* ---- loadDraft (F.9.4 D2) — clone redirect from Templates ---------- */

    async function loadDraft(draftId) {
        /* D2: FULL state reset before load — never merge stale draft data */
        _draft = { name: "", description: "", steps: [] };
        _lastSavedId = null;

        var token = localStorage.getItem("hermes_token") || "";
        try {
            var resp = await fetch(
                "/api/pipeline-studio/drafts/" + encodeURIComponent(draftId),
                { headers: { "X-Hermes-Token": token } }
            );
            if (!resp.ok) {
                _showToast("Erro ao carregar draft", "error");
                return;
            }
            var draft = await resp.json();
            _lastSavedId = draft.id;
            _draft.name = draft.name || "";
            _draft.description = draft.description || "";

            /* Parse yaml_blob → steps array */
            var yamlBlob = draft.yaml_blob || "";
            var parsedSteps = _parseYamlSteps(yamlBlob);
            _draft.steps = parsedSteps;
        } catch (e) {
            _showToast("Erro ao carregar draft: " + e.message, "error");
            return;
        }

        render();
    }

    /* ---- Minimal YAML step parser (name + tool keys only) -------------- */

    function _parseYamlSteps(yamlBlob) {
        /* Lightweight parse: extract steps array without external lib.
           Handles the YAML rendered by _renderYaml (known format).
           Falls back to [] on any parse error. */
        try {
            var steps = [];
            var lines = yamlBlob.split("\n");
            var inSteps = false;
            var currentStep = null;
            for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                if (/^steps:/.test(line)) { inSteps = true; continue; }
                if (!inSteps) continue;
                /* New step entry */
                var nameMatch = /^\s+-\s+name:\s+(.+)$/.exec(line);
                if (nameMatch) {
                    if (currentStep) steps.push(currentStep);
                    currentStep = { name: nameMatch[1].trim(), tool: "", args: {} };
                    continue;
                }
                var toolMatch = /^\s+tool:\s+(.+)$/.exec(line);
                if (toolMatch && currentStep) {
                    currentStep.tool = toolMatch[1].trim();
                }
            }
            if (currentStep) steps.push(currentStep);
            return steps;
        } catch (e) {
            return [];
        }
    }

    window.PipelineStudioBuilder = { init: init, render: render, destroy: destroy, loadDraft: loadDraft };

})();
