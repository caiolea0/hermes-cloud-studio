/* ============================================================
   Hermes Cloud Studio — ObservabilityPerf (F.8.3 C2)
   ============================================================
   Live: bar per endpoint (p50/p95/p99 stacked) — current 1h rolling.
   History: line p50/p95/p99 over time (history rows).

   Decisões F.8.3 D2: line + bar mixed.

   Endpoint: GET /api/observability/perf?source=live|history
                  &range=24h|7d|30d&endpoint=
   ============================================================ */
(function () {
    "use strict";

    var ROOT_SEL = '[data-component="observability-perf"]';
    var state = {
        chart: null,
        wired: false,
        filters: { source: "live", range: "24h", endpoint: "" },
    };

    function _$(sel) { return document.querySelector(ROOT_SEL + " " + sel); }
    function _authHeaders() {
        var h = {};
        try { var t = localStorage.getItem("hermes_token") || ""; if (t) h["X-Hermes-Token"] = t; } catch (_) {}
        return h;
    }

    function _markup() {
        return ''
            + '<div class="observability-panel-toolbar" role="group" aria-label="Performance filters">'
            + '  <label class="observability-filter-label">Source'
            + '    <select class="observability-filter-select" data-filter="source">'
            + '      <option value="live">live (1h rolling)</option>'
            + '      <option value="history">history</option>'
            + '    </select>'
            + '  </label>'
            + '  <label class="observability-filter-label">Range (history)'
            + '    <select class="observability-filter-select" data-filter="range">'
            + '      <option value="24h">24h</option>'
            + '      <option value="7d">7d</option>'
            + '      <option value="30d">30d</option>'
            + '    </select>'
            + '  </label>'
            + '  <label class="observability-filter-label">Endpoint'
            + '    <input type="text" class="observability-filter-input" data-filter="endpoint" placeholder="GET /api/dashboard" />'
            + '  </label>'
            + '</div>'
            + '<div class="observability-error-banner" data-role="error" aria-live="polite"></div>'
            + '<div class="observability-charts-grid">'
            + '  <div class="observability-chart-card">'
            + '    <h3 class="observability-chart-title" id="obs-perf-title">Latência p50/p95/p99</h3>'
            + '    <div class="observability-chart-canvas-wrap"><canvas data-canvas="perf" aria-labelledby="obs-perf-title" role="img"></canvas></div>'
            + '  </div>'
            + '  <div class="observability-chart-card">'
            + '    <h3 class="observability-chart-title" id="obs-perf-table-title">Endpoints monitorados</h3>'
            + '    <div data-role="table-wrap" aria-labelledby="obs-perf-table-title"></div>'
            + '  </div>'
            + '</div>';
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
        host.addEventListener("input", function (e) {
            var inp = e.target.closest('input[data-filter="endpoint"]');
            if (!inp) return;
            state.filters.endpoint = inp.value;
            clearTimeout(state._typingTimer);
            state._typingTimer = setTimeout(render, 400);
        });
    }

    function _setBanner(msg) {
        var el = _$('[data-role="error"]');
        if (!el) return;
        if (msg) { el.textContent = msg; el.classList.add("active"); }
        else { el.textContent = ""; el.classList.remove("active"); }
    }

    function _renderTable(rows) {
        var wrap = _$('[data-role="table-wrap"]');
        if (!wrap) return;
        wrap.textContent = "";
        if (!rows || !rows.length) {
            var empty = document.createElement("p");
            empty.className = "observability-empty-row";
            empty.textContent = "Sem endpoints monitorados ainda.";
            wrap.appendChild(empty);
            return;
        }
        var tableWrap = document.createElement("div");
        tableWrap.className = "observability-table-wrap";
        var table = document.createElement("table");
        table.className = "observability-table";
        var thead = document.createElement("thead");
        var theadRow = document.createElement("tr");
        ["Endpoint", "Count", "p50 (ms)", "p95 (ms)", "p99 (ms)"].forEach(function (h) {
            var th = document.createElement("th");
            th.scope = "col";
            th.textContent = h;
            theadRow.appendChild(th);
        });
        thead.appendChild(theadRow);
        table.appendChild(thead);
        var tbody = document.createElement("tbody");
        rows.forEach(function (row) {
            var tr = document.createElement("tr");
            var ep = row.endpoint || (row.stats && row.stats.endpoint) || "—";
            var stats = row.stats || row;
            var cells = [
                ep,
                String(stats.count || 0),
                stats.p50 != null ? Number(stats.p50).toFixed(1) : "—",
                stats.p95 != null ? Number(stats.p95).toFixed(1) : "—",
                stats.p99 != null ? Number(stats.p99).toFixed(1) : "—",
            ];
            cells.forEach(function (v, i) {
                var td = document.createElement("td");
                if (i > 0) td.className = "col-num";
                td.textContent = v;
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        tableWrap.appendChild(table);
        wrap.appendChild(tableWrap);
    }

    function _renderChart(rows) {
        var canvas = _$('[data-canvas="perf"]');
        if (!canvas) return;
        if (state.chart) { try { state.chart.destroy(); } catch (_) {} state.chart = null; }
        if (typeof window.Chart === "undefined") {
            _setBanner("Chart.js vendor não carregou.");
            return;
        }
        var labels = rows.map(function (r) {
            return r.endpoint || (r.stats && r.stats.endpoint) || r.recorded_at || "—";
        });
        var p50s = rows.map(function (r) { var s = r.stats || r; return Number(s.p50) || 0; });
        var p95s = rows.map(function (r) { var s = r.stats || r; return Number(s.p95) || 0; });
        var p99s = rows.map(function (r) { var s = r.stats || r; return Number(s.p99) || 0; });
        var chartType = state.filters.source === "history" ? "line" : "bar";
        var ctx = canvas.getContext("2d");
        state.chart = new window.Chart(ctx, {
            type: chartType,
            data: {
                labels: labels,
                datasets: [
                    { label: "p50", data: p50s, backgroundColor: "rgba(63,185,80,0.55)", borderColor: "rgba(63,185,80,1)", borderWidth: 1, tension: 0.2 },
                    { label: "p95", data: p95s, backgroundColor: "rgba(210,153,34,0.55)", borderColor: "rgba(210,153,34,1)", borderWidth: 1, tension: 0.2 },
                    { label: "p99", data: p99s, backgroundColor: "rgba(248,81,73,0.55)", borderColor: "rgba(248,81,73,1)", borderWidth: 1, tension: 0.2 },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "bottom", labels: { color: "#8b949e" } } },
                scales: { x: { ticks: { color: "#8b949e", maxRotation: 35, minRotation: 0 } }, y: { ticks: { color: "#8b949e" }, beginAtZero: true } },
            },
        });
    }

    async function render() {
        _ensureMarkup();
        _wireOnce();
        var sel = _$('[data-filter="source"]'); if (sel) sel.value = state.filters.source;
        var sel2 = _$('[data-filter="range"]'); if (sel2) sel2.value = state.filters.range;
        var inp = _$('[data-filter="endpoint"]'); if (inp && document.activeElement !== inp) inp.value = state.filters.endpoint;
        _setBanner(null);

        var qsObj = { source: state.filters.source };
        if (state.filters.source === "history") qsObj.range = state.filters.range;
        if (state.filters.endpoint) qsObj.endpoint = state.filters.endpoint;
        var qs = new URLSearchParams(qsObj);
        try {
            var r = await fetch("/api/observability/perf?" + qs.toString(), { headers: _authHeaders() });
            if (!r.ok) {
                _setBanner("Falha ao carregar perf (HTTP " + r.status + ")");
                _renderChart([]); _renderTable([]);
                return;
            }
            var data = await r.json();
            var rows;
            if (data.source === "live") {
                rows = data.endpoints || (data.stats ? [{ endpoint: data.endpoint, stats: data.stats }] : []);
            } else {
                rows = data.items || [];
            }
            _renderChart(rows);
            _renderTable(rows);
        } catch (e) {
            _setBanner("Erro de rede: " + (e && e.message ? e.message : e));
        }
    }

    function destroy() {
        if (state.chart) { try { state.chart.destroy(); } catch (_) {} state.chart = null; }
        if (state._typingTimer) { clearTimeout(state._typingTimer); state._typingTimer = null; }
    }

    window.ObservabilityPerf = { render: render, destroy: destroy };
})();
