/* ============================================================
   Skill Proposals Modals (F.4.3 C1)
   ============================================================
   3 modais:
     - openAccept(proposal): confirma + POST /accept
     - openReject(proposal): textarea reason + POST /reject
     - openPath1(proposal):  prompt copy-to-clipboard + status poll

   PATH 1 D3 (PIVOT D6 honest):
     - Primary impl: modal mostra prompt pré-pronto
     - Owner copia → cola Claude Code → executa
     - Polls /api/skills/synthesis-runs/{id} every 5s até status='completed'

   Experimental WS flag HERMES_F43_WS_LISTENER (default OFF):
     - Lê /api/config no init
     - Quando ON: emit brain.workflow_trigger_request + aguarda 5s ack
     - Fallback automático para modal se ack ausente
   ============================================================ */
(function () {
    "use strict";

    var _state = {
        wsListenerEnabled: false,
        configLoaded: false,
        activeModal: null,
        pollTimer: null,
        currentRunId: null,
        previouslyFocused: null,
    };

    var WORKFLOW_SCRIPT_PATH = ".claude/workflows/hermes-skill-forge.js";

    /* ---- helpers ---------------------------------------- */

    function _escape(s) {
        if (s == null) return "";
        return String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function _authToken() {
        try { return localStorage.getItem("hermes_token") || ""; }
        catch (e) { return ""; }
    }

    function _apiFetch(url, options) {
        var opts = options || {};
        opts.headers = Object.assign({
            "Content-Type": "application/json",
            "X-Hermes-Token": _authToken(),
        }, opts.headers || {});
        return fetch(url, opts);
    }

    function _toast(msg, kind) {
        if (typeof window.toast === "function") {
            window.toast(msg, kind || "info");
        } else {
            console.log("[SkillProposalsModal]", msg);
        }
    }

    function _ensureRoot() {
        var existing = document.getElementById("sp-modal-root");
        if (existing) return existing;
        var div = document.createElement("div");
        div.id = "sp-modal-root";
        document.body.appendChild(div);
        return div;
    }

    function _focusables(panel) {
        return Array.prototype.slice.call(panel.querySelectorAll(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        ));
    }

    function _trapTab(e, panel) {
        if (e.key !== "Tab") return;
        var f = _focusables(panel);
        if (!f.length) return;
        var first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    }

    function _showModal(html, opts) {
        opts = opts || {};
        var root = _ensureRoot();
        _state.previouslyFocused = document.activeElement;
        _closeModal({ skipFocus: true });

        var wrapper = document.createElement("div");
        wrapper.className = "sp-modal";
        wrapper.setAttribute("role", "dialog");
        wrapper.setAttribute("aria-modal", "true");
        if (opts.labelledBy) wrapper.setAttribute("aria-labelledby", opts.labelledBy);
        wrapper.innerHTML = html;
        root.appendChild(wrapper);
        _state.activeModal = wrapper;

        var panel = wrapper.querySelector(".sp-modal-panel");

        /* Backdrop close */
        var backdrop = wrapper.querySelector(".sp-modal-backdrop");
        if (backdrop) backdrop.addEventListener("click", function () { _closeModal(); });

        /* Esc close + focus trap */
        wrapper.addEventListener("keydown", function (e) {
            if (e.key === "Escape") { e.preventDefault(); _closeModal(); return; }
            if (panel) _trapTab(e, panel);
        });

        /* Initial focus */
        setTimeout(function () {
            var first = panel ? panel.querySelector("[data-autofocus]") : null;
            if (first && first.focus) first.focus();
            else if (panel) {
                var f = _focusables(panel);
                if (f.length) f[0].focus();
            }
        }, 30);

        return wrapper;
    }

    function _closeModal(opts) {
        opts = opts || {};
        if (_state.pollTimer) { clearTimeout(_state.pollTimer); _state.pollTimer = null; }
        _state.currentRunId = null;
        if (_state.activeModal && _state.activeModal.parentNode) {
            _state.activeModal.parentNode.removeChild(_state.activeModal);
        }
        _state.activeModal = null;
        if (!opts.skipFocus && _state.previouslyFocused && _state.previouslyFocused.focus) {
            try { _state.previouslyFocused.focus(); } catch (e) {}
        }
        _state.previouslyFocused = null;
    }

    /* ---- /api/config preload --------------------------- */

    function _loadConfig() {
        if (_state.configLoaded) return Promise.resolve();
        return _apiFetch("/api/config")
            .then(function (r) { return r.ok ? r.json() : {}; })
            .then(function (cfg) {
                _state.wsListenerEnabled = !!(cfg && cfg.HERMES_F43_WS_LISTENER);
                _state.configLoaded = true;
            })
            .catch(function () { _state.configLoaded = true; });
    }

    /* ---- Accept modal ---------------------------------- */

    function openAccept(proposal) {
        if (!proposal) return;
        var prTemplatePreview = (
            "## Proposal " + (proposal.name || "(sem nome)") + "\n\n" +
            (proposal.description ? "**Rationale:**\n" + proposal.description + "\n\n" : "") +
            "**Status atual:** " + (proposal.status || "draft") + "\n" +
            "**Source:** " + (proposal.source_pattern || "—") + "\n\n" +
            "→ Accept dispara: lab sandbox → (se lab_passed) GitHub PR draft via mcp.github."
        );

        var html = (
            '<div class="sp-modal-backdrop" aria-hidden="true"></div>' +
            '<div class="sp-modal-panel" role="document">' +
                '<header class="sp-modal-header">' +
                    '<h3 class="sp-modal-title" id="sp-accept-title">Aceitar proposal</h3>' +
                '</header>' +
                '<div class="sp-modal-body">' +
                    '<p class="sp-section-title">Preview da ação</p>' +
                    '<pre class="sp-modal-preview">' + _escape(prTemplatePreview) + '</pre>' +
                    '<p class="sp-modal-status" id="sp-accept-status" aria-live="polite" hidden></p>' +
                '</div>' +
                '<footer class="sp-modal-footer">' +
                    '<button class="sp-btn" type="button" data-action="cancel" data-autofocus>Cancelar</button>' +
                    '<button class="sp-btn sp-btn-primary" type="button" id="sp-accept-confirm">✓ Confirmar accept</button>' +
                '</footer>' +
            '</div>'
        );

        var wrapper = _showModal(html, { labelledBy: "sp-accept-title" });
        wrapper.querySelector("[data-action='cancel']").addEventListener("click", function () { _closeModal(); });
        wrapper.querySelector("#sp-accept-confirm").addEventListener("click", function () {
            _confirmAccept(proposal.id, wrapper);
        });
    }

    function _confirmAccept(proposalId, wrapper) {
        var confirmBtn = wrapper.querySelector("#sp-accept-confirm");
        var statusEl = wrapper.querySelector("#sp-accept-status");
        confirmBtn.disabled = true;
        if (statusEl) {
            statusEl.removeAttribute("hidden");
            statusEl.textContent = "Disparando lab + PR (3-8s)…";
            statusEl.dataset.state = "running";
        }

        _apiFetch("/api/skills/proposals/" + encodeURIComponent(proposalId) + "/accept", {
            method: "POST",
            body: JSON.stringify({}),
        })
            .then(function (r) {
                return r.json().then(function (data) { return { ok: r.ok, status: r.status, data: data }; });
            })
            .then(function (res) {
                if (!res.ok) {
                    var msg = (res.data && res.data.detail) ? res.data.detail : ("http_" + res.status);
                    throw new Error(msg);
                }
                var pr = res.data.pr || {};
                var newStatus = res.data.new_status || "lab_passed";
                var lab = res.data.lab_test_result || {};
                var labOk = !!(lab && lab.status === "passed");
                var prOk = (pr.status === "ok");
                var summary;
                if (prOk) {
                    summary = "PR aberto: " + (pr.pr_url || pr.url || "(sem url)");
                } else if (!labOk) {
                    summary = "Lab " + (lab.status || "failed") + " — PR bloqueado.";
                } else {
                    summary = "Lab passou, PR " + (pr.status || "failed") + ".";
                }
                if (statusEl) {
                    statusEl.textContent = "✓ " + summary;
                    statusEl.dataset.state = "completed";
                }
                _toast("Accept ok: " + summary, prOk ? "success" : "warning");
                setTimeout(function () { _closeModal(); }, 1500);
                if (window.SkillProposalsStudio) {
                    window.SkillProposalsStudio.refreshList();
                    window.SkillProposalsStudio.selectProposal(proposalId);
                }
            })
            .catch(function (err) {
                if (statusEl) {
                    statusEl.textContent = "✗ Falha: " + err.message;
                    statusEl.dataset.state = "failed";
                }
                _toast("Accept falhou: " + err.message, "error");
                confirmBtn.disabled = false;
            });
    }

    /* ---- Reject modal ---------------------------------- */

    function openReject(proposal) {
        if (!proposal) return;
        var html = (
            '<div class="sp-modal-backdrop" aria-hidden="true"></div>' +
            '<div class="sp-modal-panel" role="document">' +
                '<header class="sp-modal-header">' +
                    '<h3 class="sp-modal-title" id="sp-reject-title">Rejeitar proposal</h3>' +
                '</header>' +
                '<div class="sp-modal-body">' +
                    '<label class="sp-modal-label">' +
                        'Motivo (opcional, máx 500 chars)' +
                        '<textarea class="sp-modal-textarea" id="sp-reject-reason" maxlength="500" placeholder="Ex: lógica conflita com skill X / unsafe permission /..." data-autofocus></textarea>' +
                    '</label>' +
                    '<p class="sp-modal-status" id="sp-reject-status" aria-live="polite" hidden></p>' +
                '</div>' +
                '<footer class="sp-modal-footer">' +
                    '<button class="sp-btn" type="button" data-action="cancel">Cancelar</button>' +
                    '<button class="sp-btn sp-btn-danger" type="button" id="sp-reject-confirm">✗ Confirmar reject</button>' +
                '</footer>' +
            '</div>'
        );
        var wrapper = _showModal(html, { labelledBy: "sp-reject-title" });
        wrapper.querySelector("[data-action='cancel']").addEventListener("click", function () { _closeModal(); });
        wrapper.querySelector("#sp-reject-confirm").addEventListener("click", function () {
            var reason = wrapper.querySelector("#sp-reject-reason").value || "";
            _confirmReject(proposal.id, reason, wrapper);
        });
    }

    function _confirmReject(proposalId, reason, wrapper) {
        var confirmBtn = wrapper.querySelector("#sp-reject-confirm");
        var statusEl = wrapper.querySelector("#sp-reject-status");
        confirmBtn.disabled = true;
        if (statusEl) {
            statusEl.removeAttribute("hidden");
            statusEl.textContent = "Persistindo decisão…";
            statusEl.dataset.state = "running";
        }
        var body = reason ? { reason: reason } : {};
        _apiFetch("/api/skills/proposals/" + encodeURIComponent(proposalId) + "/reject", {
            method: "POST",
            body: JSON.stringify(body),
        })
            .then(function (r) {
                return r.json().then(function (data) { return { ok: r.ok, status: r.status, data: data }; });
            })
            .then(function (res) {
                if (!res.ok) {
                    var msg = (res.data && res.data.detail) ? res.data.detail : ("http_" + res.status);
                    throw new Error(msg);
                }
                if (statusEl) {
                    statusEl.textContent = "✓ Rejeitado.";
                    statusEl.dataset.state = "completed";
                }
                _toast("Proposal rejeitado.", "success");
                setTimeout(function () { _closeModal(); }, 800);
                if (window.SkillProposalsStudio) {
                    window.SkillProposalsStudio.refreshList();
                }
            })
            .catch(function (err) {
                if (statusEl) {
                    statusEl.textContent = "✗ Falha: " + err.message;
                    statusEl.dataset.state = "failed";
                }
                _toast("Reject falhou: " + err.message, "error");
                confirmBtn.disabled = false;
            });
    }

    /* ---- PATH 1 modal (Run Workflow Now) ---------------- */

    function openPath1(proposal) {
        if (!proposal) return;
        _loadConfig().then(function () {
            /* First, queue the synthesis run via API to get run_id */
            _apiFetch("/api/skills/proposals/generate", {
                method: "POST",
                body: JSON.stringify({ trigger_source: "ui_button" }),
            })
                .then(function (r) {
                    return r.json().then(function (data) { return { ok: r.ok, status: r.status, data: data }; });
                })
                .then(function (res) {
                    if (!res.ok) {
                        var msg = (res.data && res.data.detail) ? res.data.detail : ("http_" + res.status);
                        throw new Error(msg);
                    }
                    var runId = (res.data && res.data.run_id) ? res.data.run_id : null;
                    _renderPath1Modal(proposal, runId);
                    /* If WS listener flag ON: try emit + 5s ack window */
                    if (_state.wsListenerEnabled && runId) {
                        _tryWsTrigger(runId, proposal);
                    } else if (runId) {
                        _startPath1Poll(runId);
                    }
                })
                .catch(function (err) {
                    _toast("Falha ao enfileirar synthesis: " + err.message, "error");
                });
        });
    }

    function _renderPath1Modal(proposal, runId) {
        var workflowArgs = {
            proposal_id: proposal.id,
            proposal_name: proposal.name,
            run_id: runId,
        };
        var promptText = (
            'Workflow({\n' +
            '  scriptPath: "' + WORKFLOW_SCRIPT_PATH + '",\n' +
            '  args: ' + JSON.stringify(workflowArgs, null, 2).split("\n").map(function (l, i) { return i ? "  " + l : l; }).join("\n") + ',\n' +
            '})'
        );

        var html = (
            '<div class="sp-modal-backdrop" aria-hidden="true"></div>' +
            '<div class="sp-modal-panel" role="document">' +
                '<header class="sp-modal-header">' +
                    '<h3 class="sp-modal-title" id="sp-path1-title">Run Workflow Now</h3>' +
                '</header>' +
                '<div class="sp-modal-body">' +
                    '<p class="sp-section-title">Como executar (PATH 1)</p>' +
                    '<ol style="margin:0;padding-left:20px;font-size:12px;line-height:1.6;color:var(--text-2,#8b8b98);">' +
                        '<li>Clique <strong>Copiar prompt</strong> abaixo.</li>' +
                        '<li>Abra Claude Code (PC) numa sessão.</li>' +
                        '<li>Cole o prompt e execute — o Workflow MCP roda local.</li>' +
                        '<li>Status atualiza automaticamente quando completar.</li>' +
                    '</ol>' +
                    '<pre class="sp-modal-preview" id="sp-path1-prompt">' + _escape(promptText) + '</pre>' +
                    '<div style="display:flex;gap:8px;align-items:center;">' +
                        '<button class="sp-btn sp-btn-primary" type="button" id="sp-path1-copy" data-autofocus aria-label="Copiar prompt para clipboard">📋 Copiar prompt</button>' +
                        '<span class="sp-copy-confirm" id="sp-path1-copy-confirm" aria-live="polite">Copiado ✓</span>' +
                    '</div>' +
                    '<p class="sp-modal-status" id="sp-path1-status" aria-live="polite">' +
                        'Aguardando synthesis_runs.status → completed…' +
                        (runId ? ' <span style="opacity:0.6;">(' + _escape(runId) + ')</span>' : '') +
                    '</p>' +
                '</div>' +
                '<footer class="sp-modal-footer">' +
                    '<button class="sp-btn" type="button" data-action="cancel">Fechar</button>' +
                '</footer>' +
            '</div>'
        );

        var wrapper = _showModal(html, { labelledBy: "sp-path1-title" });
        /* Store raw (unescaped) prompt for clipboard copy — avoids HTML entity leakage. */
        var promptEl = wrapper.querySelector("#sp-path1-prompt");
        if (promptEl) promptEl.dataset.rawPrompt = promptText;
        wrapper.querySelector("[data-action='cancel']").addEventListener("click", function () { _closeModal(); });
        wrapper.querySelector("#sp-path1-copy").addEventListener("click", function () {
            var promptEl = wrapper.querySelector("#sp-path1-prompt");
            var text = (promptEl && promptEl.dataset.rawPrompt) ? promptEl.dataset.rawPrompt : (promptEl ? promptEl.textContent : "");
            _copyToClipboard(text).then(function () {
                var confirm = wrapper.querySelector("#sp-path1-copy-confirm");
                if (confirm) {
                    confirm.classList.add("is-visible");
                    setTimeout(function () { confirm.classList.remove("is-visible"); }, 1500);
                }
            }).catch(function () {
                _toast("Falha ao copiar — selecione manualmente.", "warning");
            });
        });
    }

    function _copyToClipboard(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(text);
        }
        return new Promise(function (resolve, reject) {
            try {
                var ta = document.createElement("textarea");
                ta.value = text;
                ta.style.position = "fixed";
                ta.style.left = "-9999px";
                document.body.appendChild(ta);
                ta.select();
                var ok = document.execCommand("copy");
                document.body.removeChild(ta);
                ok ? resolve() : reject(new Error("execCommand_failed"));
            } catch (e) { reject(e); }
        });
    }

    function _startPath1Poll(runId) {
        _state.currentRunId = runId;
        _pollOnce(runId, 0);
    }

    function _pollOnce(runId, attempts) {
        if (!_state.activeModal || _state.currentRunId !== runId) return;
        if (attempts > 720) return; /* ~1h max */
        _apiFetch("/api/skills/synthesis-runs/" + encodeURIComponent(runId))
            .then(function (r) {
                if (r.status === 404) {
                    /* endpoint not present (F.4.3 C2 may expose) — fall back to list refresh */
                    return null;
                }
                return r.ok ? r.json() : null;
            })
            .then(function (data) {
                if (data && data.status) {
                    var statusEl = _state.activeModal && _state.activeModal.querySelector("#sp-path1-status");
                    if (statusEl) {
                        statusEl.textContent = "Status: " + data.status;
                        statusEl.dataset.state = data.status;
                    }
                    if (data.status === "completed" || data.status === "failed") {
                        if (window.SkillProposalsStudio) window.SkillProposalsStudio.refreshList();
                        return;
                    }
                }
                _state.pollTimer = setTimeout(function () { _pollOnce(runId, attempts + 1); }, 5000);
            })
            .catch(function () {
                _state.pollTimer = setTimeout(function () { _pollOnce(runId, attempts + 1); }, 5000);
            });
    }

    function _tryWsTrigger(runId, proposal) {
        var ackReceived = false;
        var ackHandler = function (e) {
            if (e && e.detail && e.detail.event_type === "brain.workflow_trigger_ack" &&
                e.detail.payload && e.detail.payload.run_id === runId) {
                ackReceived = true;
                document.removeEventListener("hermes-ws-event", ackHandler);
                var statusEl = _state.activeModal && _state.activeModal.querySelector("#sp-path1-status");
                if (statusEl) statusEl.textContent = "WS listener acked — workflow rodando…";
                _startPath1Poll(runId);
            }
        };
        document.addEventListener("hermes-ws-event", ackHandler);

        /* Emit via shared WS if available */
        try {
            if (window.ws && typeof window.ws.send === "function") {
                window.ws.send(JSON.stringify({
                    event_type: "brain.workflow_trigger_request",
                    payload: { run_id: runId, script: WORKFLOW_SCRIPT_PATH, args: { proposal_id: proposal.id } },
                }));
            }
        } catch (e) { /* ignore */ }

        setTimeout(function () {
            document.removeEventListener("hermes-ws-event", ackHandler);
            if (!ackReceived) {
                /* fallback to modal poll */
                _startPath1Poll(runId);
            }
        }, 5000);
    }

    /* ---- Public API ------------------------------------- */

    window.SkillProposalsModal = {
        openAccept: openAccept,
        openReject: openReject,
        openPath1: openPath1,
        close: function () { _closeModal(); },
    };

})();
