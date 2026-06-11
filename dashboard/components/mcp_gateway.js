/* ============================================================
   Hermes Cloud Studio — MCPGateway (F.5.6f)
   ============================================================
   UI read-only pra ContextForge gateway VM :55401.

   Decisão D3 cristalizada: zero write actions (toggle/quarantine
   = RBAC F.future). Auto-refresh 60s. Backend reuse F.5.3+F.5.5
   endpoints (proxy via api/mcp_coverage.py).

   API global: window.MCPGateway.{init, refresh, destroy}.

   Endpoints consumidos:
   - GET /api/mcp/coverage/latest  (proxied to VM api :8420)
   - GET /api/mcp/gateway/health   (PC + VM api + gateway badges)

   XSS: textContent para todos campos dinâmicos (server names,
   tools, errors). NO innerHTML += em conteúdo runtime.
   Accessibility: ARIA roles + labels + live regions. Keyboard nav
   via natural focus order. WCAG 2.1 AA contrast (--accent on --bg
   ~ 8.2:1 per styles/tokens.css).
   ============================================================ */
(function () {
    "use strict";

    const REFRESH_INTERVAL_MS = 60000;
    const TIER_LABELS = {
        active: "Active",
        warning: "Warning",
        orphan: "Orphan",
        deprecated: "Deprecated",
        quarantine: "Quarantine",
        reserved: "Reserved",
    };
    const TIER_ORDER = ["active", "warning", "orphan", "deprecated", "quarantine", "reserved"];

    let _root = null;
    let _refreshTimer = null;
    let _lastFetchAt = null;
    let _initialized = false;

    function _$(sel) {
        return _root ? _root.querySelector(sel) : null;
    }

    function _setText(el, text) {
        if (el) el.textContent = text == null ? "—" : String(text);
    }

    function _setBadge(el, ok, labelOk, labelFail) {
        if (!el) return;
        el.classList.remove("badge-ok", "badge-fail", "badge-pending");
        if (ok === true) {
            el.classList.add("badge-ok");
            el.textContent = labelOk || "online";
        } else if (ok === false) {
            el.classList.add("badge-fail");
            el.textContent = labelFail || "offline";
        } else {
            el.classList.add("badge-pending");
            el.textContent = "...";
        }
    }

    function _formatTimestamp(ts) {
        if (!ts) return "—";
        try {
            const d = new Date(ts);
            return d.toLocaleString("pt-BR", {
                day: "2-digit", month: "2-digit",
                hour: "2-digit", minute: "2-digit",
            });
        } catch (e) {
            return String(ts);
        }
    }

    function _formatDuration(ms) {
        if (ms == null || ms === 0) return "—";
        if (ms < 1000) return ms + "ms";
        return (ms / 1000).toFixed(1) + "s";
    }

    function _renderTierSummary(summary) {
        if (!summary) return;
        TIER_ORDER.forEach(function (tier) {
            const el = _$('[data-mcp-tier="' + tier + '"]');
            if (el) {
                const countEl = el.querySelector(".mcp-tier-count");
                _setText(countEl, summary[tier] || 0);
            }
        });
        const totalEl = _$('[data-mcp-tier="total"] .mcp-tier-count');
        _setText(totalEl, summary.total_tools || 0);
    }

    function _renderItemsTable(items) {
        const tbody = _$("#mcp-table-body");
        if (!tbody) return;
        while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
        if (!Array.isArray(items) || items.length === 0) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");
            cell.colSpan = 8;
            cell.className = "mcp-empty-row";
            cell.textContent = "Nenhum MCP registrado ainda — gateway sem dados.";
            row.appendChild(cell);
            tbody.appendChild(row);
            return;
        }
        items.forEach(function (item) {
            const row = document.createElement("tr");
            row.setAttribute("data-mcp-tier-row", item.tier || "reserved");

            const cells = [
                { text: item.server, className: "mcp-cell-server" },
                { text: item.tool, className: "mcp-cell-tool" },
                { tier: item.tier, registry_tier: item.registry_tier, className: "mcp-cell-tier" },
                { text: item.chapter_owner || "—", className: "mcp-cell-chapter" },
                { text: String(item.calls || 0), className: "mcp-cell-calls" },
                { text: _formatDuration(item.avg_ms), className: "mcp-cell-ms" },
                { text: String(item.errors || 0), className: "mcp-cell-errors", error: (item.errors || 0) > 0 },
                { text: _formatTimestamp(item.last_call), className: "mcp-cell-last" },
            ];

            cells.forEach(function (c) {
                const td = document.createElement("td");
                td.className = c.className;
                if (c.tier != null) {
                    const badge = document.createElement("span");
                    badge.className = "mcp-tier-badge mcp-tier-" + (c.tier || "reserved");
                    badge.textContent = TIER_LABELS[c.tier] || c.tier;
                    td.appendChild(badge);
                    if (c.registry_tier && c.registry_tier !== c.tier) {
                        const drift = document.createElement("span");
                        drift.className = "mcp-drift-tag";
                        drift.title = "Registry tier: " + c.registry_tier + " (drift detected)";
                        drift.textContent = "⚠";
                        td.appendChild(drift);
                    }
                } else {
                    td.textContent = c.text;
                    if (c.error) td.classList.add("mcp-cell-error-positive");
                }
                row.appendChild(td);
            });
            tbody.appendChild(row);
        });
    }

    function _renderAuditLog(items) {
        const listEl = _$("#mcp-audit-log");
        if (!listEl) return;
        while (listEl.firstChild) listEl.removeChild(listEl.firstChild);
        const withCalls = (items || []).filter(function (i) { return i.last_call; })
            .sort(function (a, b) { return (b.last_call || "").localeCompare(a.last_call || ""); })
            .slice(0, 20);
        if (withCalls.length === 0) {
            const empty = document.createElement("div");
            empty.className = "mcp-audit-empty";
            empty.textContent = "Sem calls registrados nas últimas 24h.";
            listEl.appendChild(empty);
            return;
        }
        withCalls.forEach(function (item) {
            const entry = document.createElement("div");
            entry.className = "mcp-audit-entry";
            const time = document.createElement("span");
            time.className = "mcp-audit-time";
            time.textContent = _formatTimestamp(item.last_call);
            const server = document.createElement("span");
            server.className = "mcp-audit-server";
            server.textContent = item.server;
            const tool = document.createElement("span");
            tool.className = "mcp-audit-tool";
            tool.textContent = item.tool;
            const calls = document.createElement("span");
            calls.className = "mcp-audit-calls";
            calls.textContent = (item.calls || 0) + "×";
            entry.appendChild(time);
            entry.appendChild(server);
            entry.appendChild(tool);
            entry.appendChild(calls);
            listEl.appendChild(entry);
        });
    }

    function _renderError(message) {
        const errEl = _$("#mcp-error-banner");
        if (!errEl) return;
        if (message) {
            errEl.textContent = message;
            errEl.classList.add("active");
            errEl.setAttribute("role", "alert");
        } else {
            errEl.textContent = "";
            errEl.classList.remove("active");
        }
    }

    function _authHeaders() {
        const headers = {};
        try {
            const tok = localStorage.getItem("hermes_token") || "";
            if (tok) headers["X-Hermes-Token"] = tok;
        } catch (_) { /* ignore */ }
        return headers;
    }

    async function _fetchHealth() {
        try {
            const r = await fetch("/api/mcp/gateway/health", { headers: _authHeaders() });
            if (!r.ok) throw new Error("health HTTP " + r.status);
            return await r.json();
        } catch (e) {
            return { pc: { ok: false }, vm_api: { ok: false }, gateway: { ok: false } };
        }
    }

    async function _fetchCoverage() {
        const r = await fetch("/api/mcp/coverage/latest", { headers: _authHeaders() });
        if (!r.ok) throw new Error("coverage HTTP " + r.status);
        return await r.json();
    }

    async function refresh() {
        if (!_root) return;
        _renderError(null);
        const [health, coverage] = await Promise.all([
            _fetchHealth(),
            _fetchCoverage().catch(function (e) { return { error: String(e) }; }),
        ]);

        _setBadge(_$("#mcp-badge-pc"), health.pc && health.pc.ok, "PC :55000 OK", "PC offline");
        _setBadge(_$("#mcp-badge-vm"), health.vm_api && health.vm_api.ok, "VM API OK", "VM API offline");
        // Gateway badge: coverage data presença (total_tools > 0) é proxy reliable
        // pra "gateway config deployed + registry populated". Evita VM probe path quebrado
        // enquanto hermes_api.py LEGACY rodando em vez de hermes_api_v2 (F.future migration).
        const covOk = !!(coverage && !coverage.error && coverage.summary
            && (coverage.summary.total_tools || 0) > 0);
        _setBadge(
            _$("#mcp-badge-gateway"),
            covOk,
            "Gateway " + (coverage.source === "pc_local_db" ? "(PC DB)" : ":55401")
                + " — " + ((coverage.summary || {}).total_tools || 0) + " tools",
            "Gateway offline"
        );

        if (coverage && coverage.error) {
            _renderError("Falha ao carregar coverage: " + coverage.error);
            _renderTierSummary({});
            _renderItemsTable([]);
            _renderAuditLog([]);
            return;
        }

        _renderTierSummary((coverage && coverage.summary) || {});
        _renderItemsTable((coverage && coverage.items) || []);
        _renderAuditLog((coverage && coverage.items) || []);
        _lastFetchAt = Date.now();
        const tsEl = _$("#mcp-last-refresh");
        _setText(tsEl, "Atualizado " + new Date(_lastFetchAt).toLocaleTimeString("pt-BR"));
    }

    function init(selector) {
        _root = typeof selector === "string"
            ? document.querySelector(selector)
            : selector;
        if (!_root) {
            console.warn("[MCPGateway] root selector not found:", selector);
            return;
        }
        if (_initialized) {
            refresh();
            return;
        }
        _initialized = true;
        refresh();
        _refreshTimer = setInterval(refresh, REFRESH_INTERVAL_MS);
        const btn = _$("#mcp-refresh-btn");
        if (btn) btn.addEventListener("click", function () { refresh(); });
    }

    function destroy() {
        if (_refreshTimer) {
            clearInterval(_refreshTimer);
            _refreshTimer = null;
        }
        _initialized = false;
        _root = null;
    }

    window.MCPGateway = { init: init, refresh: refresh, destroy: destroy };
})();
