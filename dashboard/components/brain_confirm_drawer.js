/* ============================================================
   Hermes Cloud Studio — BrainConfirmDrawer (F.6.4)
   ============================================================
   Side-drawer 480px right-side para Brain owner confirm pendentes.

   Decisões cristalizadas (commit d040e9b):
   D1 NÃO blocking dialog — aria-modal="false", backdrop click closes
   D3 SHOW ALL concurrent runs, sorted newest first (started_at DESC)
   D4 WS canonical brain.run_awaiting_confirm + run_confirm_resolved
   D5 forever pending — drawer só age sob comando explicit owner

   API global: window.BrainConfirmDrawer.{init, open, close, refresh, onWSEvent}

   Boot:
   - Auto-init em DOMContentLoaded (idempotent)
   - WS subscription delegate from dashboard/app.js handleWSEvent
   - Page-reload survives via GET /api/brain/runs?status=requires_confirm

   XSS: BrainConfirmCard usa textContent. Drawer container static markup index.html.
   Accessibility: role=dialog + aria-labelledby + Esc closes + focus mgmt.
   ============================================================ */
(function () {
    "use strict";

    var state = {
        initialized: false,
        pendingRuns: [],   // [{run_id, intent, action_class, confidence, summary_card, ...}]
        drawerOpen: false,
        lastFocus: null,
    };

    function _$(sel) { return document.querySelector(sel); }

    function _api() {
        return (localStorage.getItem("hermes_api") || "").replace(/\/+$/, "");
    }

    function _token() {
        return localStorage.getItem("hermes_token") || "";
    }

    function _toast(msg, tone) {
        if (window.hermesToast && typeof window.hermesToast[tone || "info"] === "function") {
            try { window.hermesToast[tone || "info"](msg); } catch (e) {}
        } else {
            console.log("[brain-confirm]", tone || "info", msg);
        }
    }

    function _renderEmpty(list) {
        list.textContent = "";
        var empty = document.createElement("div");
        empty.className = "brain-confirm-empty";
        empty.textContent = "Nenhuma decisão pendente. Brain está em IDLE.";
        list.appendChild(empty);
    }

    function _updateBadge() {
        var badge = document.getElementById("brain-confirm-badge");
        var trigger = document.getElementById("brain-confirm-trigger");
        var count = state.pendingRuns.length;
        if (badge) {
            badge.textContent = String(count);
            badge.classList.toggle("hidden", count === 0);
        }
        if (trigger) {
            trigger.setAttribute("aria-label",
                count === 0
                    ? "Brain awaiting confirm (sem pendentes)"
                    : "Brain awaiting confirm (" + count + " pendentes)");
        }
        var headerCount = document.getElementById("brain-confirm-drawer-count");
        if (headerCount) headerCount.textContent = String(count);
    }

    function _sortNewestFirst(list) {
        return list.slice().sort(function (a, b) {
            var ta = new Date(a.started_at || 0).getTime();
            var tb = new Date(b.started_at || 0).getTime();
            return tb - ta;
        });
    }

    function _renderList() {
        var list = document.getElementById("brain-confirm-list");
        if (!list) return;
        if (state.pendingRuns.length === 0) {
            _renderEmpty(list);
            return;
        }
        list.textContent = "";
        var sorted = _sortNewestFirst(state.pendingRuns);
        sorted.forEach(function (run) {
            if (!window.BrainConfirmCard) return;
            var card = window.BrainConfirmCard.render(run, { onAction: _handleAction });
            list.appendChild(card);
        });
    }

    function _handleAction(runId, action, comment, done) {
        var url = (_api() || "") + "/api/brain/confirm/" + encodeURIComponent(runId);
        fetch(url, {
            method: "POST",
            headers: {
                "X-Hermes-Token": _token(),
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ action: action, comment: comment || "" }),
        })
            .then(function (r) {
                if (r.ok) return r.json();
                if (r.status === 409) {
                    _toast("Run já resolvida em outra aba (409)", "warn");
                    state.pendingRuns = state.pendingRuns.filter(function (x) { return x.run_id !== runId; });
                    _updateBadge();
                    _renderList();
                    return null;
                }
                if (r.status === 404) {
                    _toast("Run não encontrada (404)", "error");
                    return null;
                }
                _toast("Erro HTTP " + r.status + " ao confirmar", "error");
                return null;
            })
            .then(function (data) {
                if (data && data.ok) {
                    var label = action === "approve" ? "aprovada" : (action === "deny" ? "negada" : "cancelada");
                    _toast("Run " + label + " — " + data.final_state, "success");
                }
                done && done(null);
            })
            .catch(function (err) {
                _toast("Falha de rede: " + err, "error");
                done && done(err);
            });
    }

    function _open() {
        var drawer = document.getElementById("brain-confirm-drawer");
        if (!drawer) return;
        state.lastFocus = document.activeElement;
        drawer.hidden = false;
        // double rAF so CSS transition fires
        requestAnimationFrame(function () {
            requestAnimationFrame(function () { drawer.classList.add("open"); });
        });
        state.drawerOpen = true;
        var closeBtn = document.getElementById("brain-confirm-close");
        if (closeBtn) closeBtn.focus();
    }

    function _close() {
        var drawer = document.getElementById("brain-confirm-drawer");
        if (!drawer) return;
        drawer.classList.remove("open");
        state.drawerOpen = false;
        // wait for transition before hidden
        setTimeout(function () { drawer.hidden = true; }, 220);
        if (state.lastFocus && typeof state.lastFocus.focus === "function") {
            try { state.lastFocus.focus(); } catch (e) {}
        }
    }

    function _onKeydown(e) {
        if (!state.drawerOpen) return;
        if (e.key === "Escape") { _close(); }
    }

    function _hydrateFromServer() {
        var url = (_api() || "") + "/api/brain/runs?status=requires_confirm&limit=50";
        fetch(url, { headers: { "X-Hermes-Token": _token() } })
            .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
            .then(function (data) {
                if (!data || !data.ok) return;
                state.pendingRuns = (data.runs || []).map(_normalize_run);
                _updateBadge();
                _renderList();
            })
            .catch(function (err) {
                console.warn("BrainConfirmDrawer hydrate failed:", err);
            });
    }

    function _normalize_run(row) {
        // row vem do GET /api/brain/runs (schema brain_runs)
        // OR vem do WS brain.run_awaiting_confirm (schema payload custom).
        // Normaliza pra shape unificado consumido pelo card.
        if (row.summary_card) return row;
        var fr = {};
        try { fr = row.final_result ? JSON.parse(row.final_result) : {}; } catch (e) { fr = {}; }
        var actionClass = fr.action_class || (fr.destructive ? (row.intent || "") : "");
        return {
            run_id: row.id || row.run_id,
            intent: row.intent || fr.intent || "",
            action_class: actionClass,
            confidence: row.confidence_score != null ? row.confidence_score : (fr.confidence || 0),
            confirm_reason: fr.confirm_reason || "",
            started_at: row.started_at || "",
            summary_card: {
                what: String(fr.final_answer || ("intent=" + (row.intent || ""))).slice(0, 200),
                why: fr.confirm_reason || "",
                cost: parseFloat(row.total_cost_credits || fr.cost_credits || 0) || 0,
                iterations: parseInt(fr.iterations || 0, 10) || 0,
            },
        };
    }

    function onWSEvent(event) {
        if (!event || typeof event.type !== "string") return;
        if (event.type === "brain.run_awaiting_confirm") {
            var rid = event.run_id;
            if (!rid) return;
            var exists = state.pendingRuns.some(function (r) { return r.run_id === rid; });
            if (exists) return;
            state.pendingRuns.push({
                run_id: rid,
                intent: event.intent || "",
                action_class: event.action_class || "",
                confidence: parseFloat(event.confidence) || 0,
                confirm_reason: event.confirm_reason || "",
                started_at: event.started_at || new Date().toISOString(),
                summary_card: event.summary_card || { what: "", why: event.confirm_reason || "", cost: 0, iterations: 0 },
            });
            _updateBadge();
            _renderList();
            _toast("Brain aguarda confirmação (" + (event.intent || "") + ")", "warn");
        } else if (event.type === "brain.run_confirm_resolved") {
            var rid2 = event.run_id;
            if (!rid2) return;
            state.pendingRuns = state.pendingRuns.filter(function (r) { return r.run_id !== rid2; });
            _updateBadge();
            _renderList();
        }
    }

    function _wireDOM() {
        var trigger = document.getElementById("brain-confirm-trigger");
        if (trigger && !trigger.dataset.wired) {
            trigger.dataset.wired = "1";
            trigger.addEventListener("click", function () { _open(); });
        }
        var closeBtn = document.getElementById("brain-confirm-close");
        if (closeBtn && !closeBtn.dataset.wired) {
            closeBtn.dataset.wired = "1";
            closeBtn.addEventListener("click", function () { _close(); });
        }
        var backdrop = document.getElementById("brain-confirm-backdrop");
        if (backdrop && !backdrop.dataset.wired) {
            backdrop.dataset.wired = "1";
            backdrop.addEventListener("click", function () { _close(); });
        }
        document.addEventListener("keydown", _onKeydown);
    }

    function init() {
        if (state.initialized) return;
        state.initialized = true;
        _wireDOM();
        _updateBadge();
        _hydrateFromServer();
    }

    function open() { _open(); }
    function close() { _close(); }
    function refresh() { _hydrateFromServer(); }

    /**
     * F5-B: show() — open drawer from palette AI mode or explicit click.
     * opts.source: 'palette_ai_mode' | 'explicit_click' | 'cobaia_loop' (telemetry).
     * Fires WS event brain.confirm_requested.from_palette when source=palette_ai_mode.
     */
    function show(opts) {
        opts = opts || {};
        state.lastSource = opts.source || 'direct';
        _open();

        // Telemetry: broadcast source if from palette
        if (opts.source === 'palette_ai_mode') {
            _broadcastConfirmRequested(opts);
        }
    }

    function _broadcastConfirmRequested(opts) {
        try {
            var api = (localStorage.getItem("hermes_api") || "").replace(/\/+$/, "");
            var token = localStorage.getItem("hermes_token") || "";
            // Fire-and-forget POST to WS broadcast endpoint — non-critical
            fetch(api + "/api/daemon/broadcast", {
                method: "POST",
                headers: { "X-Hermes-Token": token, "Content-Type": "application/json" },
                body: JSON.stringify({
                    event_type: "brain.confirm_requested.from_palette",
                    payload: {
                        intent: opts.intent || "",
                        confidence: typeof opts.confidence === "number" ? opts.confidence : 0,
                        source: opts.source || "palette_ai_mode",
                    },
                }),
            }).catch(function () {});
        } catch (e) {
            // telemetry non-critical — never throw
        }
    }

    window.BrainConfirmDrawer = {
        init: init,
        open: open,
        close: close,
        refresh: refresh,
        show: show,
        onWSEvent: onWSEvent,
        _state: state,  // testing only
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
