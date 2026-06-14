/* ============================================================
   Hermes Cloud Studio — ObservabilityCosts (F.8.3 C2)
   ============================================================
   Bar chart provider/model breakdown + Line chart cost over time
   (cost over time = 30d via group_by=day backend D8 future, F.8.3
   reusa range filter direto na bar — line histórico fica F.future
   quando endpoint accept group_by=day adicional além provider/model/
   requester/server).

   Decisões F.8.3 D2: Chart.js BAR + LINE mixed.
   D6 CSV export ?format=csv server-side reuse.

   API global: window.ObservabilityCosts.{render, destroy}.

   Endpoint: GET /api/observability/costs?range=24h|7d|30d
                  &group_by=provider|model|requester|server
                  &format=json|csv
   ============================================================ */
(function () {
    "use strict";

    var ROOT_SEL = '[data-component="observability-costs"]';
    var state = {
        chart: null,
        wired: false,
        filters: { range: "24h", group_by: "provider" },
    };

    function _$(sel) { return document.querySelector(ROOT_SEL + " " + sel); }
    function _authHeaders() {
        var h = {};
        try {
            var t = localStorage.getItem("hermes_token") || "";
            if (t) h["X-Hermes-Token"] = t;
        } catch (_) {}
        return h;
    }

    function _markup() {
        return ''
            + '<div class="observability-panel-toolbar" role="group" aria-label="Costs filters">'
            + '  <label class="observability-filter-label">Range'
            + '    <select class="observability-filter-select" data-filter="range">'
            + '      <option value="24h">24h</option>'
            + '      <option value="7d">7d</option>'
            + '      <option value="30d">30d</option>'
            + '    </select>'
            + '  </label>'
            + '  <label class="observability-filter-label">Group by'
            + '    <select class="observability-filter-select" data-filter="group_by">'
            + '      <option value="provider">provider</option>'
            + '      <option value="model">model</option>'
            + '      <option value="requester">requester</option>'
            + '      <option value="server">server</option>'
            + '    </select>'
            + '  </label>'
            + '  <button type="button" class="observability-csv-btn" data-action="export-csv" aria-label="Export costs CSV">Export CSV</button>'
            + '</div>'
            + '<div class="observability-error-banner" data-role="error" aria-live="polite"></div>'
            + '<div class="observability-charts-grid">'
            + '  <div class="observability-chart-card">'
            + '    <h3 class="observability-chart-title" id="obs-costs-bar-title">Total cost por grupo (credits)</h3>'
            + '    <div class="observability-chart-canvas-wrap"><canvas data-canvas="bar" aria-labelledby="obs-costs-bar-title" role="img"></canvas></div>'
            + '  </div>'
            + '  <div class="observability-chart-card">'
            + '    <h3 class="observability-chart-title" id="obs-costs-summary-title">Resumo agregado</h3>'
            + '    <div data-role="summary" aria-labelledby="obs-costs-summary-title"></div>'
            + '  </div>'
            + '</div>';
    }

    function _ensureMarkup() {
        var host = document.querySelector(ROOT_SEL);
        if (!host) return null;
        if (!host.firstElementChild) {
            host.innerHTML = _markup();
        }
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
            var btn = e.target.closest('[data-action="export-csv"]');
            if (!btn) return;
            var qs = new URLSearchParams(Object.assign({}, state.filters, { format: "csv" }));
            window.location.assign("/api/observability/costs?" + qs.toString());
        });
    }

    function _setBanner(msg) {
        var el = _$('[data-role="error"]');
        if (!el) return;
        if (msg) {
            el.textContent = msg;
            el.classList.add("active");
        } else {
            el.textContent = "";
            el.classList.remove("active");
        }
    }

    function _renderSummary(data) {
        var el = _$('[data-role="summary"]');
        if (!el) return;
        el.textContent = "";
        var items = (data && data.items) || [];
        if (!items.length) {
            var empty = document.createElement("p");
            empty.className = "observability-empty-row";
            empty.textContent = "Sem dados de cost neste range/grupo.";
            el.appendChild(empty);
            return;
        }
        var totals = items.reduce(function (acc, r) {
            acc.calls += Number(r.call_count) || 0;
            acc.credits += Number(r.total_cost_credits) || 0;
            acc.usd += Number(r.total_cost_usd) || 0;
            acc.tokensIn += Number(r.total_tokens_in) || 0;
            acc.tokensOut += Number(r.total_tokens_out) || 0;
            acc.errors += Number(r.error_count) || 0;
            return acc;
        }, { calls: 0, credits: 0, usd: 0, tokensIn: 0, tokensOut: 0, errors: 0 });

        var rows = [
            ["Calls", totals.calls.toLocaleString("pt-BR")],
            ["Total credits", totals.credits.toFixed(4)],
            ["Total USD", "$" + totals.usd.toFixed(4)],
            ["Tokens in", totals.tokensIn.toLocaleString("pt-BR")],
            ["Tokens out", totals.tokensOut.toLocaleString("pt-BR")],
            ["Errors", String(totals.errors)],
            ["Grupos", String(items.length)],
        ];
        var dl = document.createElement("dl");
        dl.style.display = "grid";
        dl.style.gridTemplateColumns = "max-content 1fr";
        dl.style.gap = "var(--space-xs) var(--space-md)";
        rows.forEach(function (kv) {
            var dt = document.createElement("dt");
            dt.style.color = "var(--color-fg-muted)";
            dt.textContent = kv[0];
            var dd = document.createElement("dd");
            dd.style.margin = "0";
            dd.style.fontVariantNumeric = "tabular-nums";
            dd.textContent = kv[1];
            dl.appendChild(dt);
            dl.appendChild(dd);
        });
        el.appendChild(dl);
    }

    function _renderBar(data) {
        var canvas = _$('[data-canvas="bar"]');
        if (!canvas) return;
        if (state.chart) {
            try { state.chart.destroy(); } catch (_) {}
            state.chart = null;
        }
        if (typeof window.Chart === "undefined") {
            _setBanner("Chart.js vendor não carregou.");
            return;
        }
        var items = (data && data.items) || [];
        var labels = items.map(function (r) { return String(r.group_key || "—"); });
        var values = items.map(function (r) { return Number(r.total_cost_credits) || 0; });
        var ctx = canvas.getContext("2d");
        state.chart = new window.Chart(ctx, {
            type: "bar",
            data: {
                labels: labels,
                datasets: [{
                    label: "Cost (credits)",
                    data: values,
                    backgroundColor: "rgba(88,166,255,0.55)",
                    borderColor: "rgba(88,166,255,1)",
                    borderWidth: 1,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: "#8b949e" } },
                    y: { ticks: { color: "#8b949e" }, beginAtZero: true },
                },
            },
        });
    }

    async function render() {
        _ensureMarkup();
        _wireOnce();
        // sync filter UI with state
        var rangeSel = _$('[data-filter="range"]');
        var groupSel = _$('[data-filter="group_by"]');
        if (rangeSel) rangeSel.value = state.filters.range;
        if (groupSel) groupSel.value = state.filters.group_by;
        _setBanner(null);

        var qs = new URLSearchParams(Object.assign({}, state.filters, { format: "json" }));
        try {
            var r = await fetch("/api/observability/costs?" + qs.toString(), { headers: _authHeaders() });
            if (!r.ok) {
                _setBanner("Falha ao carregar costs (HTTP " + r.status + ")");
                _renderBar({ items: [] });
                _renderSummary({ items: [] });
                return;
            }
            var data = await r.json();
            _renderBar(data);
            _renderSummary(data);
        } catch (e) {
            _setBanner("Erro de rede: " + (e && e.message ? e.message : e));
        }
    }

    function destroy() {
        if (state.chart) {
            try { state.chart.destroy(); } catch (_) {}
            state.chart = null;
        }
    }

    window.ObservabilityCosts = { render: render, destroy: destroy };
})();
