/* ============================================================
   Pipeline Studio — Runs Monitor (F.9.3c REAL)
   ============================================================
   WS PRIMARY (D4): conecta /ws?token=..., escuta eventos
   pipeline.step_* + pipeline.run_complete/aborted.
   POLLING FALLBACK 5s quando WS desconectado.
   Reconnect exponential backoff 1/2/4/8s max (D4).
   Abort inline + browser confirm (D5).
   Status indicator verde/âmbar/vermelho.
   setInterval/clearInterval em destroy + visibilitychange.

   API: window.PipelineStudioRunsMonitor.{init, render, destroy}

   XSS: textContent em todos os campos dinâmicos.
   ============================================================ */
(function () {
    "use strict";

    var POLL_INTERVAL_MS  = 5000;
    var MAX_BACKOFF_MS    = 8000;

    var _ws               = null;
    var _pollTimer        = null;
    var _reconnectTimer   = null;
    var _reconnectAttempt = 0;
    var _connectionState  = "disconnected"; /* "ws_connected" | "polling" | "disconnected" */
    var _initialized      = false;

    /* run_id → {run_id, draft_id, status, steps:[]} */
    var _runs             = {};

    /* ---- DOM helpers ------------------------------------ */

    function _id(id)  { return document.getElementById(id); }

    function _setText(el, text) {
        if (el) el.textContent = (text == null) ? "" : String(text);
    }

    /* ---- Auth token ------------------------------------- */

    function _getToken() {
        return localStorage.getItem("hermes_token") || "";
    }

    /* ---- WS connection (D4 PRIMARY) -------------------- */

    function _connectWs() {
        try {
            var protocol = location.protocol === "https:" ? "wss:" : "ws:";
            var token    = _getToken();
            _ws = new WebSocket(
                protocol + "//" + location.host + "/ws?token=" + encodeURIComponent(token)
            );

            _ws.onopen = function () {
                _reconnectAttempt = 0;
                _setConnectionState("ws_connected");
                _stopPolling();
            };

            _ws.onmessage = function (e) {
                try {
                    var event = JSON.parse(e.data);
                    if (event.event_type && event.event_type.indexOf("pipeline.") === 0) {
                        _handlePipelineEvent(event);
                    }
                } catch (err) {
                    console.warn("[RunsMonitor] WS parse error", err);
                }
            };

            _ws.onclose = function () {
                _setConnectionState("polling");
                _startPolling();
                _scheduleReconnect();
            };

            _ws.onerror = function () {
                /* onclose fires after onerror — no extra action needed */
                console.warn("[RunsMonitor] WS error");
            };

        } catch (e) {
            _setConnectionState("polling");
            _startPolling();
            _scheduleReconnect();
        }
    }

    /* ---- Reconnect backoff (D4: 1/2/4/8s max) ---------- */

    function _scheduleReconnect() {
        if (_reconnectTimer) return;
        var delay = Math.min(1000 * Math.pow(2, _reconnectAttempt), MAX_BACKOFF_MS);
        _reconnectAttempt++;
        _reconnectTimer = setTimeout(function () {
            _reconnectTimer = null;
            _connectWs();
        }, delay);
    }

    /* ---- Polling fallback (D4: 5s) --------------------- */

    function _startPolling() {
        if (_pollTimer) return;
        _pollTimer = setInterval(_pollActiveRuns, POLL_INTERVAL_MS);
    }

    function _stopPolling() {
        if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
    }

    async function _pollActiveRuns() {
        var runIds = Object.keys(_runs).filter(function (id) {
            var r = _runs[id];
            return r && (r.status === "running" || r.status === "queued" || r.status === "pending");
        });
        for (var i = 0; i < runIds.length; i++) {
            var runId = runIds[i];
            try {
                var resp = await fetch("/api/pipeline-studio/runs/" + encodeURIComponent(runId), {
                    headers: { "X-Hermes-Token": _getToken() }
                });
                if (resp.ok) {
                    var data = await resp.json();
                    _runs[runId] = data;
                    render();
                }
            } catch (e) {
                console.warn("[RunsMonitor] poll " + runId + " failed", e);
            }
        }
    }

    /* ---- WS event handler ------------------------------ */

    function _handlePipelineEvent(event) {
        var payload = event.payload || {};
        var runId   = payload.run_id;
        if (!runId) return;

        if (!_runs[runId]) {
            _runs[runId] = {
                run_id:   runId,
                draft_id: payload.draft_id || null,
                status:   "running",
                steps:    []
            };
        }

        var run = _runs[runId];
        var et  = event.event_type;

        if (et === "pipeline.step_start") {
            _upsertStep(run, {
                step_idx:  payload.step_idx,
                step_name: payload.step_name || "",
                tool_invoked: payload.tool || "",
                status:    "running"
            });
        } else if (et === "pipeline.step_done") {
            _upsertStep(run, {
                step_idx:   payload.step_idx,
                step_name:  payload.step_name || "",
                status:     "completed",
                latency_ms: payload.latency_ms
            });
        } else if (et === "pipeline.step_error") {
            _upsertStep(run, {
                step_idx:  payload.step_idx,
                step_name: payload.step_name || "",
                status:    "error",
                error:     payload.error || ""
            });
        } else if (et === "pipeline.run_complete") {
            run.status = payload.status || "completed";
        } else if (et === "pipeline.run_aborted") {
            run.status = "aborted";
        }

        render();
    }

    function _upsertStep(run, stepData) {
        var existing = null;
        for (var i = 0; i < run.steps.length; i++) {
            if (run.steps[i].step_idx === stepData.step_idx) {
                existing = run.steps[i];
                break;
            }
        }
        if (existing) {
            Object.keys(stepData).forEach(function (k) { existing[k] = stepData[k]; });
        } else {
            run.steps.push(stepData);
        }
        run.steps.sort(function (a, b) { return a.step_idx - b.step_idx; });
    }

    /* ---- Connection state indicator -------------------- */

    function _setConnectionState(state) {
        _connectionState = state;
        _updateStatusIndicator();
    }

    function _updateStatusIndicator() {
        var dotEl  = _id("ps-ws-dot");
        var textEl = _id("ps-ws-text");
        if (!dotEl) return;

        var colorClass = "red";
        var label      = "Desconectado";
        if (_connectionState === "ws_connected") { colorClass = "green"; label = "WS conectado"; }
        else if (_connectionState === "polling")  { colorClass = "amber"; label = "Polling 5s"; }

        dotEl.className = "ps-ws-dot " + colorClass;
        _setText(textEl, label);
    }

    /* ---- Abort run (D5: inline + browser confirm) ------- */

    async function _abortRun(runId) {
        if (!confirm("Abortar run " + runId.slice(0, 8) + "?\nSoft abort: step atual termina, seguintes pulados.")) {
            return;
        }
        try {
            var resp = await fetch("/api/pipeline-studio/runs/" + encodeURIComponent(runId) + "/abort", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Hermes-Token": _getToken()
                },
                body: JSON.stringify({ reason: "owner_inline" })
            });
            if (resp.ok) {
                _showToast("Abort solicitado", "success");
                if (_runs[runId]) _runs[runId].status = "aborted";
                render();
            } else {
                _showToast("Erro ao abortar", "error");
            }
        } catch (e) {
            _showToast("Erro ao abortar: " + e.message, "error");
        }
    }

    /* ---- Render ----------------------------------------- */

    function render() {
        var panel = _id("ps-panel-runs-monitor");
        if (!panel) return;

        /* Build via DOM — no innerHTML with run data */
        panel.innerHTML = "";

        /* Header: status indicator */
        var header = document.createElement("div");
        header.className = "ps-runs-header";

        var wsIndicator = document.createElement("div");
        wsIndicator.className = "ps-ws-indicator";
        var dot = document.createElement("span");
        dot.id = "ps-ws-dot";
        dot.className = "ps-ws-dot";
        var wsText = document.createElement("span");
        wsText.id = "ps-ws-text";
        wsIndicator.appendChild(dot);
        wsIndicator.appendChild(wsText);

        var title = document.createElement("h3");
        title.style.cssText = "margin:0;font-size: var(--text-base);font-weight:600;color:var(--text-1)";
        title.textContent = "Execuções Ativas";

        header.appendChild(title);
        header.appendChild(wsIndicator);
        panel.appendChild(header);

        _updateStatusIndicator();

        /* Runs list */
        var runIds = Object.keys(_runs);
        if (!runIds.length) {
            var empty = document.createElement("div");
            empty.className = "ps-runs-empty";
            empty.textContent = "Nenhuma execução ainda. Execute um pipeline na aba Builder.";
            panel.appendChild(empty);
            return;
        }

        var list = document.createElement("div");
        list.className = "ps-runs-list";

        runIds.forEach(function (runId) {
            var run  = _runs[runId];
            var row  = document.createElement("div");
            row.className = "ps-run-row";
            row.dataset.runId = runId;

            /* Status badge */
            var badge = document.createElement("span");
            badge.className = "ps-run-status-badge " + (run.status || "");
            badge.textContent = run.status || "—";

            /* Run ID */
            var idEl = document.createElement("span");
            idEl.className = "ps-run-id";
            idEl.textContent = runId.slice(0, 8) + "…";
            idEl.title = runId;

            /* Progress */
            var prog = document.createElement("span");
            prog.className = "ps-run-progress";
            var done = (run.steps || []).filter(function (s) {
                return s.status === "completed" || s.status === "error" || s.status === "skipped";
            }).length;
            prog.textContent = done + "/" + (run.steps || []).length + " steps";

            row.appendChild(badge);
            row.appendChild(idEl);
            row.appendChild(prog);

            /* Abort button if running */
            if (run.status === "running" || run.status === "queued") {
                var abortBtn = document.createElement("button");
                abortBtn.className = "ps-abort-btn";
                abortBtn.type = "button";
                abortBtn.textContent = "Abortar";
                abortBtn.setAttribute("aria-label", "Abortar run " + runId.slice(0, 8));
                abortBtn.dataset.runId = runId;
                row.appendChild(abortBtn);
            }

            list.appendChild(row);
        });

        /* Event delegation for abort */
        list.addEventListener("click", function (e) {
            var btn = e.target.closest(".ps-abort-btn");
            if (btn && btn.dataset.runId) _abortRun(btn.dataset.runId);
        });

        panel.appendChild(list);
    }

    /* ---- Toast helper ----------------------------------- */

    function _showToast(msg, type) {
        if (window.toast && typeof window.toast === "function") {
            window.toast(msg, type || "info");
        }
    }

    /* ---- Track new run from Builder --------------------- */

    function trackRun(runId, draftId) {
        if (!_runs[runId]) {
            _runs[runId] = {
                run_id:   runId,
                draft_id: draftId || null,
                status:   "queued",
                steps:    []
            };
            render();
        }
    }

    /* ---- Init / Destroy --------------------------------- */

    function init() {
        if (_initialized) {
            render();
            return;
        }
        _initialized = true;
        _connectWs();
        render();
    }

    function destroy() {
        _stopPolling();
        if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
        if (_ws) { _ws.onclose = null; _ws.close(); _ws = null; }
        _initialized = false;
        _runs = {};
    }

    /* ---- Public API ------------------------------------- */

    window.PipelineStudioRunsMonitor = {
        init:     init,
        render:   render,
        destroy:  destroy,
        trackRun: trackRun,
    };

})();
