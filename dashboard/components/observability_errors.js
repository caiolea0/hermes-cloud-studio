/* ============================================================
   Hermes Cloud Studio — ObservabilityErrors (F.8.3 C2 + C3)
   ============================================================
   Table errors_inbox HYBRID Sentry MCP + local categories aggregate.
   Bar chart errors per category.
   "Resolve" button → ObservabilityResolveModal.open(errorRow).

   Decisões F.8.3 D2 (bar chart category) + D4 (resolve modal C3).

   Endpoint: GET /api/observability/errors?range=24h|7d|30d
                  &status=open|resolved|wontfix
                  &category=&offset=&limit=
   ============================================================ */
(function () {
    "use strict";

    var ROOT_SEL = '[data-component="observability-errors"]';
    var state = {
        chart: null,
        wired: false,
        filters: { range: "24h", status: "open" },
        lastData: null,
    };

    function _$(sel) { return document.querySelector(ROOT_SEL + " " + sel); }
    function _authHeaders() {
        var h = {};
        try { var t = localStorage.getItem("hermes_token") || ""; if (t) h["X-Hermes-Token"] = t; } catch (_) {}
        return h;
    }
    function _escape(s) {
        return String(s == null ? "" : s);
    }

    function _markup() {
        return ''
            + '<div class="observability-panel-toolbar" role="group" aria-label="Errors filters">'
            + '  <label class="observability-filter-label">Range'
            + '    <select class="observability-filter-select" data-filter="range">'
            + '      <option value="24h">24h</option>'
            + '      <option value="7d">7d</option>'
            + '      <option value="30d">30d</option>'
            + '    </select>'
            + '  </label>'
            + '  <label class="observability-filter-label">Status'
            + '    <select class="observability-filter-select" data-filter="status">'
            + '      <option value="open">open</option>'
            + '      <option value="resolved">resolved</option>'
            + '      <option value="wontfix">wontfix</option>'
            + '    </select>'
            + '  </label>'
            + '  <span class="observability-filter-label" data-role="sentry-flag">—</span>'
            + '</div>'
            + '<div class="observability-error-banner" data-role="error" aria-live="polite"></div>'
            + '<div class="observability-charts-grid">'
            + '  <div class="observability-chart-card">'
            + '    <h3 class="observability-chart-title" id="obs-errors-bar-title">Erros por categoria</h3>'
            + '    <div class="observability-chart-canvas-wrap"><canvas data-canvas="errors-bar" aria-labelledby="obs-errors-bar-title" role="img"></canvas></div>'
            + '  </div>'
            + '  <div class="observability-chart-card">'
            + '    <h3 class="observability-chart-title">Total agregado</h3>'
            + '    <div data-role="summary"></div>'
            + '  </div>'
            + '</div>'
            + '<section aria-labelledby="obs-errors-list-title">'
            + '  <h3 id="obs-errors-list-title" class="observability-chart-title" style="margin: var(--space-md) 0 var(--space-sm);">Lista de erros</h3>'
            + '  <div data-role="list-wrap"></div>'
            + '</section>';
    }

    function _ensureMarkup() {
        var host = document.querySelector(ROOT_SEL);
        if (!host) return null;
        if (!host.firstElementChild) host.innerHTML = _markup();
        return host;
    }

    function _wireOnce() {
        if (state.wired) return;
        var host = document.querySelector(ROOT_SEL);
        if (!host) return;
        state.wired = true;
        host.addEventListener("change", function (e) {
            var sel = e.target.closest("[data-filter]");
            if (!sel) return;
            state.filters[sel.dataset.filter] = sel.value;
            render();
        });
        host.addEventListener("click", function (e) {
            var btn = e.target.closest("[data-resolve-id]");
            if (!btn) return;
            var id = btn.getAttribute("data-resolve-id");
            var title = btn.getAttribute("data-resolve-title") || "(sem título)";
            if (window.ObservabilityResolveModal && typeof window.ObservabilityResolveModal.open === "function") {
                window.ObservabilityResolveModal.open({ id: id, title: title });
            }
        });
    }

    function _setBanner(msg) {
        var el = _$('[data-role="error"]');
        if (!el) return;
        if (msg) { el.textContent = msg; el.classList.add("active"); }
        else { el.textContent = ""; el.classList.remove("active"); }
    }

    function _renderSummary(data) {
        var el = _$('[data-role="summary"]');
        if (!el) return;
        el.textContent = "";
        var cats = (data && data.items_by_category) || {};
        var keys = Object.keys(cats);
        var dl = document.createElement("dl");
        dl.style.display = "grid";
        dl.style.gridTemplateColumns = "max-content 1fr";
        dl.style.gap = "var(--space-xs) var(--space-md)";
        var rows = [["Total open", String(data.total_count || 0)],
                    ["Period", String(data.period || "")],
                    ["Status filter", String(data.status_filter || "")],
                    ["Sentry available", data.sentry_available ? "sim" : "não"]];
        keys.forEach(function (k) { rows.push(["• " + k, String((cats[k] && cats[k].total) || 0)]); });
        rows.forEach(function (kv) {
            var dt = document.createElement("dt"); dt.style.color = "var(--color-fg-muted)"; dt.textContent = kv[0];
            var dd = document.createElement("dd"); dd.style.margin = "0"; dd.style.fontVariantNumeric = "tabular-nums"; dd.textContent = kv[1];
            dl.appendChild(dt); dl.appendChild(dd);
        });
        el.appendChild(dl);
        var flag = _$('[data-role="sentry-flag"]');
        if (flag) {
            flag.textContent = "Sentry MCP: " + (data.sentry_available ? "online" : "fallback local-only");
            flag.style.color = data.sentry_available ? "var(--color-success)" : "var(--color-warn)";
        }
    }

    function _renderChart(data) {
        var canvas = _$('[data-canvas="errors-bar"]');
        if (!canvas) return;
        if (state.chart) { try { state.chart.destroy(); } catch (_) {} state.chart = null; }
        if (typeof window.Chart === "undefined") return;
        var cats = (data && data.items_by_category) || {};
        var keys = Object.keys(cats);
        var values = keys.map(function (k) { return cats[k] && cats[k].total ? Number(cats[k].total) : 0; });
        var ctx = canvas.getContext("2d");
        state.chart = new window.Chart(ctx, {
            type: "bar",
            data: { labels: keys, datasets: [{ label: "Erros (count)", data: values, backgroundColor: "rgba(248,81,73,0.55)", borderColor: "rgba(248,81,73,1)", borderWidth: 1 }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: "#8b949e" } }, y: { ticks: { color: "#8b949e" }, beginAtZero: true } } },
        });
    }

    function _renderList(data) {
        var wrap = _$('[data-role="list-wrap"]');
        if (!wrap) return;
        wrap.textContent = "";
        var cats = (data && data.items_by_category) || {};
        var allItems = [];
        Object.keys(cats).forEach(function (k) {
            (cats[k].items || []).forEach(function (it) {
                allItems.push(Object.assign({ _category: k }, it));
            });
        });
        if (!allItems.length) {
            var empty = document.createElement("p");
            empty.className = "observability-empty-row";
            empty.textContent = "Sem erros (" + state.filters.status + ") no range " + state.filters.range + ".";
            wrap.appendChild(empty);
            return;
        }
        var tableWrap = document.createElement("div");
        tableWrap.className = "observability-table-wrap";
        var table = document.createElement("table");
        table.className = "observability-table";
        var thead = document.createElement("thead");
        var theadRow = document.createElement("tr");
        ["Categoria", "Severidade", "Source", "Título", "Criado em", "Ação"].forEach(function (h) {
            var th = document.createElement("th"); th.scope = "col"; th.textContent = h; theadRow.appendChild(th);
        });
        thead.appendChild(theadRow); table.appendChild(thead);
        var tbody = document.createElement("tbody");
        allItems.forEach(function (it) {
            var tr = document.createElement("tr");
            var localId = it.local_id != null ? String(it.local_id) : "";
            var title = it.title || it.message || "(sem título)";
            var sev = (it.severity || "warning").toLowerCase();

            var tdCat = document.createElement("td"); tdCat.textContent = _escape(it._category); tr.appendChild(tdCat);
            var tdSev = document.createElement("td");
            var badge = document.createElement("span");
            badge.className = "observability-severity-badge observability-severity-" + sev;
            badge.textContent = sev;
            tdSev.appendChild(badge); tr.appendChild(tdSev);
            var tdSrc = document.createElement("td"); tdSrc.textContent = _escape(it.source || "—"); tr.appendChild(tdSrc);
            var tdTitle = document.createElement("td"); tdTitle.textContent = _escape(title); tdTitle.style.maxWidth = "360px"; tr.appendChild(tdTitle);
            var tdCreated = document.createElement("td"); tdCreated.textContent = _escape(it.created_at || "—"); tr.appendChild(tdCreated);

            var tdAct = document.createElement("td");
            if (localId && state.filters.status === "open") {
                var btn = document.createElement("button");
                btn.type = "button";
                btn.className = "observability-resolve-btn";
                btn.setAttribute("data-resolve-id", localId);
                btn.setAttribute("data-resolve-title", title);
                btn.textContent = "Resolver";
                tdAct.appendChild(btn);
            } else if (localId) {
                tdAct.textContent = it.resolved_at || "—";
            } else {
                tdAct.textContent = "Sentry-only";
            }
            tr.appendChild(tdAct);
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        tableWrap.appendChild(table);
        wrap.appendChild(tableWrap);
    }

    async function render() {
        _ensureMarkup();
        _wireOnce();
        var rangeSel = _$('[data-filter="range"]'); if (rangeSel) rangeSel.value = state.filters.range;
        var statusSel = _$('[data-filter="status"]'); if (statusSel) statusSel.value = state.filters.status;
        _setBanner(null);

        var qs = new URLSearchParams(state.filters);
        try {
            var r = await fetch("/api/observability/errors?" + qs.toString(), { headers: _authHeaders() });
            if (!r.ok) {
                _setBanner("Falha ao carregar errors (HTTP " + r.status + ")");
                _renderChart({}); _renderSummary({}); _renderList({});
                return;
            }
            var data = await r.json();
            state.lastData = data;
            _renderChart(data);
            _renderSummary(data);
            _renderList(data);
        } catch (e) {
            _setBanner("Erro de rede: " + (e && e.message ? e.message : e));
        }
    }

    function destroy() {
        if (state.chart) { try { state.chart.destroy(); } catch (_) {} state.chart = null; }
    }

    window.ObservabilityErrors = { render: render, destroy: destroy };
})();
