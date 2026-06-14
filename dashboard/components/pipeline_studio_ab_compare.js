/* ============================================================
   Pipeline Studio — A/B Compare (F.9.4c NEW)
   ============================================================
   Chart.js 2x2 grid comparing ab_group=A vs ab_group=B metrics.
   REUSE chart.min.js vendor from F.8.3 (no duplicate download).

   D5: vertical bar charts side-by-side (pattern F.8.3).
   D6: 4 metrics only — latency p50 + p95 + total cost + success rate.
       reply_rate OMIT (F.7 future).
   D3: aggregate from GET /api/pipeline-studio/runs (no mcp_calls join).
   D4: limit 50 default, 100/200 selector.

   Memory leak: destroyCharts() BEFORE each new render.
   XSS: textContent only for owner-sourced values.
   ARIA: aria-label per canvas.

   API: window.PipelineStudioAbCompare.{init, render, destroy}
   ============================================================ */
(function () {
    "use strict";

    var _charts = { p50: null, p95: null, cost: null, success: null };
    var _state = {
        initialized: false,
        currentDraftId: null,
        currentLimit: 50,
        drafts: [],
    };

    function _getToken() {
        return localStorage.getItem("hermes_token") || "";
    }

    function _id(id) { return document.getElementById(id); }

    /* ---- Destroy all charts (memory leak prevention) ---- */

    function _destroyCharts() {
        Object.keys(_charts).forEach(function (k) {
            if (_charts[k]) {
                try { _charts[k].destroy(); } catch (e) {}
                _charts[k] = null;
            }
        });
    }

    /* ---- One bar chart: Group A vs Group B -------------- */

    function _makeBarChart(canvasId, label, valueA, valueB) {
        var ctx = _id(canvasId);
        if (!ctx) return null;
        var context = ctx.getContext("2d");
        if (!context) return null;

        return new Chart(context, {
            type: "bar",
            data: {
                labels: ["Grupo A", "Grupo B"],
                datasets: [{
                    label: label,
                    data: [valueA, valueB],
                    backgroundColor: [
                        "rgba(16, 185, 129, 0.75)",  /* --green */
                        "rgba(124, 58, 237, 0.75)"   /* --accent */
                    ],
                    borderColor: [
                        "rgba(16, 185, 129, 1)",
                        "rgba(124, 58, 237, 1)"
                    ],
                    borderWidth: 1,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { mode: "index" }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: "rgba(255,255,255,0.06)" },
                        ticks: { color: "rgba(255,255,255,0.5)", font: { size: 11 } }
                    },
                    x: {
                        grid: { display: false },
                        ticks: { color: "rgba(255,255,255,0.7)", font: { size: 12 } }
                    }
                }
            }
        });
    }

    /* ---- Render 4 charts from metrics data -------------- */

    function _renderCharts(metricsA, metricsB) {
        _destroyCharts();

        var a = metricsA || {};
        var b = metricsB || {};

        _charts.p50 = _makeBarChart(
            "ab-chart-p50",
            "Latência p50 (ms)",
            Number(a.p50_latency_ms) || 0,
            Number(b.p50_latency_ms) || 0
        );
        _charts.p95 = _makeBarChart(
            "ab-chart-p95",
            "Latência p95 (ms)",
            Number(a.p95_latency_ms) || 0,
            Number(b.p95_latency_ms) || 0
        );
        _charts.cost = _makeBarChart(
            "ab-chart-cost",
            "Custo total (créditos)",
            Number(a.total_cost_credits) || 0,
            Number(b.total_cost_credits) || 0
        );
        _charts.success = _makeBarChart(
            "ab-chart-success",
            "Taxa de sucesso (%)",
            Number(a.success_rate) || 0,
            Number(b.success_rate) || 0
        );
    }

    /* ---- Empty state ------------------------------------ */

    function _showEmpty(msg) {
        _destroyCharts();
        var grid = document.querySelector(".ab-charts-grid");
        if (!grid) return;
        grid.innerHTML = "";
        var el = document.createElement("div");
        el.className = "ab-empty-state";
        el.textContent = msg || "Nenhum dado A/B. Execute pipelines com ab_group=A e ab_group=B para comparar.";
        grid.appendChild(el);
    }

    /* ---- Populate draft selector ------------------------ */

    async function _loadDrafts() {
        try {
            var resp = await fetch("/api/pipeline-studio/drafts?limit=100", {
                headers: { "X-Hermes-Token": _getToken() }
            });
            if (!resp.ok) return;
            var data = await resp.json();
            _state.drafts = (data && data.items) ? data.items : [];
        } catch (e) {
            _state.drafts = [];
        }
        var sel = _id("ab-draft-select");
        if (!sel) return;
        /* Clear options beyond first placeholder */
        while (sel.options.length > 1) sel.remove(1);
        _state.drafts.forEach(function (d) {
            var opt = document.createElement("option");
            opt.value = d.id;
            /* textContent safe — no innerHTML with user data */
            opt.textContent = d.name;
            sel.appendChild(opt);
        });
    }

    /* ---- Fetch metrics + render ------------------------- */

    async function _loadAndRender() {
        var params = new URLSearchParams({ limit: _state.currentLimit });
        if (_state.currentDraftId) params.set("draft_id", _state.currentDraftId);

        var grid = document.querySelector(".ab-charts-grid");
        if (grid) {
            /* Restore canvas structure before new render (destroyCharts cleared it) */
            _buildChartsGrid(grid);
        }

        try {
            var resp = await fetch(
                "/api/pipeline-studio/runs?" + params.toString(),
                { headers: { "X-Hermes-Token": _getToken() } }
            );
            if (!resp.ok) {
                _showEmpty("Erro ao carregar métricas A/B.");
                return;
            }
            var data = await resp.json();
            var metrics = data.metrics || {};
            var a = metrics["A"];
            var b = metrics["B"];
            if (!a && !b) {
                _showEmpty();
                return;
            }
            _renderCharts(a, b);
        } catch (e) {
            _showEmpty("Erro ao buscar métricas: " + e.message);
        }
    }

    /* ---- Build canvas grid structure -------------------- */

    function _buildChartsGrid(grid) {
        grid.innerHTML = [
            '<div class="ab-chart-card">',
            '  <h3 class="ab-chart-title">Latência p50 (ms)</h3>',
            '  <div class="ab-chart-canvas-wrap">',
            '    <canvas id="ab-chart-p50" aria-label="Latência mediana p50 Grupo A vs B" role="img"></canvas>',
            '  </div>',
            '</div>',
            '<div class="ab-chart-card">',
            '  <h3 class="ab-chart-title">Latência p95 (ms)</h3>',
            '  <div class="ab-chart-canvas-wrap">',
            '    <canvas id="ab-chart-p95" aria-label="Latência p95 Grupo A vs B" role="img"></canvas>',
            '  </div>',
            '</div>',
            '<div class="ab-chart-card">',
            '  <h3 class="ab-chart-title">Custo total (créditos)</h3>',
            '  <div class="ab-chart-canvas-wrap">',
            '    <canvas id="ab-chart-cost" aria-label="Custo total créditos Grupo A vs B" role="img"></canvas>',
            '  </div>',
            '</div>',
            '<div class="ab-chart-card">',
            '  <h3 class="ab-chart-title">Taxa de sucesso (%)</h3>',
            '  <div class="ab-chart-canvas-wrap">',
            '    <canvas id="ab-chart-success" aria-label="Taxa de sucesso Grupo A vs B" role="img"></canvas>',
            '  </div>',
            '</div>',
        ].join("\n");
    }

    /* ---- Render (full panel) ---------------------------- */

    async function render() {
        var panel = _id("ps-panel-ab-compare");
        if (!panel) return;

        /* Build markup only on first render (wiring handled in init) */
        if (!panel.querySelector(".ab-filters-bar")) {
            panel.innerHTML = [
                '<div class="ab-filters-bar" role="group" aria-label="Filtros A/B Compare">',
                '  <label class="ab-filter-label">Draft',
                '    <select class="ab-filter-select" id="ab-draft-select" aria-label="Selecionar draft">',
                '      <option value="">Todos os drafts A/B</option>',
                '    </select>',
                '  </label>',
                '  <label class="ab-filter-label">Últimos runs',
                '    <select class="ab-filter-select" id="ab-limit-select" aria-label="Quantidade de runs">',
                '      <option value="50">50 runs</option>',
                '      <option value="100">100 runs</option>',
                '      <option value="200">200 runs</option>',
                '    </select>',
                '  </label>',
                '</div>',
                '<div class="ab-charts-grid"></div>',
            ].join("\n");

            /* Wire events once after DOM created */
            var draftSel = _id("ab-draft-select");
            var limitSel = _id("ab-limit-select");
            if (draftSel) {
                draftSel.addEventListener("change", function () {
                    _state.currentDraftId = draftSel.value || null;
                    _loadAndRender();
                });
            }
            if (limitSel) {
                limitSel.addEventListener("change", function () {
                    _state.currentLimit = parseInt(limitSel.value, 10) || 50;
                    _loadAndRender();
                });
            }
        }

        /* Populate drafts (always refresh) */
        await _loadDrafts();

        /* Build charts grid and load data */
        var grid = panel.querySelector(".ab-charts-grid");
        if (grid) _buildChartsGrid(grid);
        await _loadAndRender();
    }

    /* ---- Init / Destroy --------------------------------- */

    function init() {
        if (_state.initialized) {
            render();
            return;
        }
        _state.initialized = true;
        render();
    }

    function destroy() {
        _destroyCharts();
        _state.initialized = false;
    }

    /* ---- Public API ------------------------------------- */

    window.PipelineStudioAbCompare = { init: init, render: render, destroy: destroy };

})();
