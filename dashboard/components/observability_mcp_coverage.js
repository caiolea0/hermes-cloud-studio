/* ============================================================
   Hermes Cloud Studio — ObservabilityMcpCoverage (F.8.4)
   ============================================================
   5ª tab da página Observability: resumo + heatmap Phase×Server
   + sparklines top 10 (Chart.js REUSE F.8.3 vendor) + tabela completa.

   Decisões F.8.4 (cristalizadas commit 4e1b183):
   D1 Heatmap CUSTOM CSS GRID (NÃO Chart.js matrix)
   D2 Audit data JSON FILE LOCAL (.claude/audits/mcp-coverage/*.json)
   D3 Sparkline TOP 10 MCPs 6 meses (Chart.js line miniatura)

   API: window.ObservabilityMcpCoverage.{render, destroy}

   XSS: escHtml() para todo valor dinâmico + DOMPurify.sanitize() final.
   Memory: _destroyCharts() antes de toda re-render (chart.destroy()).

   Backend: GET /api/observability/mcp-coverage-history?months=6
   ============================================================ */
(function () {
    "use strict";

    var ROOT_SEL = '[data-component="observability-mcp-coverage"]';
    var PHASES = ["F.4", "F.5", "F.6", "F.7", "F.8", "F.9"];

    /* Tier quality: lower index = worse (orphan < active) for worst-cell logic */
    var TIER_QUALITY = {
        quarantine: 0,
        deprecated: 1,
        orphan: 2,
        warning: 3,
        reserved: 4,
        active: 5,
    };

    var _sparkCharts = [];
    var _state = { wired: false, data: null };

    /* ---- Helpers ---- */

    function escHtml(s) {
        return String(s == null ? "" : s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function _apiBase() {
        try { return (localStorage.getItem("hermes_api") || "").replace(/\/$/, ""); } catch (_) { return ""; }
    }

    function _authHeaders() {
        var h = {};
        try { var t = localStorage.getItem("hermes_token") || ""; if (t) h["X-Hermes-Token"] = t; } catch (_) {}
        return h;
    }

    /* Destroy all sparkline Chart.js instances (memory leak prevention). */
    function _destroyCharts() {
        _sparkCharts.forEach(function (c) { try { c.destroy(); } catch (_) {} });
        _sparkCharts = [];
    }

    /* Extract major phase string: "F.5.2" → "F.5", "F.9" → "F.9". */
    function _majorPhase(chapterOwner) {
        if (!chapterOwner) return "";
        var parts = String(chapterOwner).split(".");
        return parts.slice(0, 2).join(".");
    }

    /* Return worst-quality tier from an array of tier strings. */
    function _worstTier(tiers) {
        var worst = null;
        var worstScore = Infinity;
        tiers.forEach(function (t) {
            var score = (TIER_QUALITY[t] !== undefined) ? TIER_QUALITY[t] : 99;
            if (score < worstScore) { worstScore = score; worst = t; }
        });
        return worst || "reserved";
    }

    /* Build {server → {phase → worst_tier}} from items array. */
    function _buildHeatmap(items) {
        var map = {};
        items.forEach(function (item) {
            var server = item.server || "unknown";
            var phase = _majorPhase(item.chapter_owner);
            if (!map[server]) map[server] = {};
            if (!map[server][phase]) map[server][phase] = [];
            map[server][phase].push(item.tier || "reserved");
        });
        var result = {};
        Object.keys(map).forEach(function (server) {
            result[server] = {};
            Object.keys(map[server]).forEach(function (phase) {
                result[server][phase] = _worstTier(map[server][phase]);
            });
        });
        return result;
    }

    /* ---- Render: summary cards ---- */

    function _renderSummary(summary, period) {
        var by = summary.by_tier || {};
        var periodStr = (period && period.start) ? period.start.slice(0, 7) : "";
        return '<div class="mcp-coverage-summary-row" role="list" aria-label="Resumo MCP ' + escHtml(periodStr) + '">'
            + _card("Total Tools", summary.total_tools || 0, "")
            + _card("Active", by.active || 0, (by.active > 0) ? "is-success" : "")
            + _card("Orphan", by.orphan || 0, (by.orphan > 0) ? "is-warning" : "")
            + _card("Drift", summary.drift_count || 0, (summary.drift_count > 0) ? "is-warning" : "")
            + _card("Reserved", by.reserved || 0, "")
            + '</div>';
    }

    function _card(label, value, cls) {
        return '<div class="mcp-coverage-card' + (cls ? ' ' + cls : '') + '" role="listitem">'
            + '<div class="mcp-coverage-card-value">' + escHtml(String(value)) + '</div>'
            + '<div class="mcp-coverage-card-label">' + escHtml(label) + '</div>'
            + '</div>';
    }

    /* ---- Render: heatmap CSS grid (D1) ---- */

    function _renderHeatmap(items) {
        var heatmap = _buildHeatmap(items);
        var servers = Object.keys(heatmap).sort();

        /* Header row */
        var headerCells = '<div class="heatmap-header-cell" role="columnheader"></div>';
        PHASES.forEach(function (ph) {
            headerCells += '<div class="heatmap-header-cell" role="columnheader">' + escHtml(ph) + '</div>';
        });

        /* Data rows */
        var dataRows = "";
        servers.forEach(function (server) {
            dataRows += '<div class="heatmap-row" role="row">';
            dataRows += '<div class="heatmap-label-cell" role="rowheader" title="' + escHtml(server) + '">' + escHtml(server) + '</div>';
            PHASES.forEach(function (ph) {
                var tier = (heatmap[server] && heatmap[server][ph]) ? heatmap[server][ph] : "none";
                var label = escHtml(server + " · " + ph + " · " + tier);
                dataRows += '<div class="heatmap-cell" data-tier="' + escHtml(tier)
                    + '" role="gridcell" tabindex="-1" title="' + label + '" aria-label="' + label + '"></div>';
            });
            dataRows += '</div>';
        });

        return '<section class="mcp-coverage-heatmap" role="grid" aria-label="MCP coverage matrix por server e fase">'
            + '<div class="heatmap-header-row" role="row">' + headerCells + '</div>'
            + dataRows
            + '</section>';
    }

    /* ---- Render: sparklines (D3) ---- */

    function _renderSparklines(history, topN) {
        topN = topN || 10;
        if (!history || !history.length) {
            return '<div class="mcp-coverage-empty">Sem histórico ainda. Cron audit mensal dia 15.</div>';
        }

        /* Aggregate total calls per server across all months */
        var totals = {};
        history.forEach(function (month) {
            (month.items || []).forEach(function (item) {
                var key = item.server || "?";
                totals[key] = (totals[key] || 0) + (item.calls || 0);
            });
        });

        var top = Object.keys(totals)
            .sort(function (a, b) { return totals[b] - totals[a]; })
            .slice(0, topN);

        if (!top.length) {
            return '<div class="mcp-coverage-empty">Sem dados de calls registrados.</div>';
        }

        var rows = top.map(function (server, i) {
            return '<div class="sparkline-row">'
                + '<div class="sparkline-label" title="' + escHtml(server) + '">' + escHtml(server) + '</div>'
                + '<canvas class="sparkline-canvas" width="200" height="36"'
                + ' id="obs-spark-' + i + '" aria-label="' + escHtml(server) + ' calls trend"></canvas>'
                + '<div class="sparkline-total">' + escHtml(String(totals[server])) + '</div>'
                + '</div>';
        }).join("");

        return '<div class="mcp-coverage-sparklines" id="obs-sparklines-host">' + rows + '</div>';
    }

    /* Wire Chart.js after DOM is ready (called post innerHTML) */
    function _wireSparkCharts(history, topN) {
        topN = topN || 10;
        _destroyCharts();
        if (typeof Chart === "undefined" || !history || !history.length) return;

        /* Build monthly call series per server */
        var monthLabels = [];
        var seriesByServer = {};

        history.forEach(function (monthData, mi) {
            var label = (monthData.period && monthData.period.start)
                ? monthData.period.start.slice(0, 7)
                : ("M" + (mi + 1));
            monthLabels.push(label);

            (monthData.items || []).forEach(function (item) {
                var key = item.server || "?";
                if (!seriesByServer[key]) seriesByServer[key] = [];
                seriesByServer[key][mi] = (seriesByServer[key][mi] || 0) + (item.calls || 0);
            });
        });

        /* Fill missing months with 0 */
        var n = history.length;
        Object.keys(seriesByServer).forEach(function (key) {
            for (var i = 0; i < n; i++) {
                if (seriesByServer[key][i] === undefined) seriesByServer[key][i] = 0;
            }
        });

        /* Top N by total */
        var totals = {};
        Object.keys(seriesByServer).forEach(function (k) {
            totals[k] = seriesByServer[k].reduce(function (s, v) { return s + v; }, 0);
        });
        var top = Object.keys(totals)
            .sort(function (a, b) { return totals[b] - totals[a]; })
            .slice(0, topN);

        top.forEach(function (server, i) {
            var canvas = document.getElementById("obs-spark-" + i);
            if (!canvas) return;
            var ctx = canvas.getContext("2d");
            var chart = new Chart(ctx, {
                type: "line",
                data: {
                    labels: monthLabels,
                    datasets: [{
                        data: seriesByServer[server] || [],
                        borderColor: "rgba(88, 166, 255, 0.85)",
                        backgroundColor: "rgba(88, 166, 255, 0.12)",
                        borderWidth: 1.5,
                        pointRadius: 2,
                        fill: true,
                        tension: 0.3,
                    }],
                },
                options: {
                    responsive: false,
                    animation: false,
                    plugins: { legend: { display: false }, tooltip: { enabled: false } },
                    scales: { x: { display: false }, y: { display: false, min: 0 } },
                },
            });
            _sparkCharts.push(chart);
        });
    }

    /* ---- Render: full tools table ---- */

    function _renderTable(items) {
        if (!items || !items.length) {
            return '<div class="mcp-coverage-empty">Nenhum tool registrado.</div>';
        }

        var rows = items.map(function (item) {
            var driftBadge = item.drift
                ? '<span class="mcp-coverage-badge is-warning">drift</span>'
                : "";
            return '<tr>'
                + '<td>' + escHtml(item.server || "") + '</td>'
                + '<td>' + escHtml(item.tool || "") + '</td>'
                + '<td><span class="mcp-coverage-tier-badge" data-tier="' + escHtml(item.tier || "") + '">'
                + escHtml(item.tier || "") + '</span></td>'
                + '<td>' + escHtml(item.chapter_owner || "—") + '</td>'
                + '<td>' + escHtml(String(item.calls || 0)) + '</td>'
                + '<td>' + driftBadge + '</td>'
                + '</tr>';
        }).join("");

        return '<div class="mcp-coverage-table-wrap">'
            + '<table class="mcp-coverage-table" aria-label="Todos os MCP tools">'
            + '<thead><tr>'
            + '<th scope="col">Server</th>'
            + '<th scope="col">Tool</th>'
            + '<th scope="col">Tier</th>'
            + '<th scope="col">Chapter</th>'
            + '<th scope="col">Calls 30d</th>'
            + '<th scope="col">Drift</th>'
            + '</tr></thead>'
            + '<tbody>' + rows + '</tbody>'
            + '</table>'
            + '</div>';
    }

    /* ---- Main render orchestrator ---- */

    function _renderAll(responseData) {
        var host = document.querySelector(ROOT_SEL);
        if (!host) return;

        var latest = responseData.latest;
        var history = responseData.history || [];

        if (!latest) {
            host.innerHTML = '<div class="mcp-coverage-empty">Sem dados de audit MCP ainda. '
                + 'Cron registrado: dia 15 de cada mês 10h Cuiabá.</div>';
            return;
        }

        var periodStr = (latest.period && latest.period.start)
            ? latest.period.start.slice(0, 7) : "";
        var itemCount = (latest.items || []).length;

        var html = "";

        /* Section 1: Summary cards */
        html += '<section class="mcp-coverage-section">'
            + '<h3 class="mcp-coverage-section-title">Resumo — ' + escHtml(periodStr) + '</h3>'
            + _renderSummary(latest.summary || {}, latest.period)
            + '</section>';

        /* Section 2: Heatmap Phase × Server */
        html += '<section class="mcp-coverage-section">'
            + '<h3 class="mcp-coverage-section-title">Coverage por Server × Fase</h3>'
            + _renderHeatmap(latest.items || [])
            + '</section>';

        /* Section 3: Sparklines top 10 (6 months) */
        html += '<section class="mcp-coverage-section">'
            + '<h3 class="mcp-coverage-section-title">Top MCPs por Calls (6 meses)</h3>'
            + _renderSparklines(history, 10)
            + '</section>';

        /* Section 4: Full tools table */
        html += '<section class="mcp-coverage-section">'
            + '<h3 class="mcp-coverage-section-title">Todos os Tools (' + escHtml(String(itemCount)) + ')</h3>'
            + _renderTable(latest.items || [])
            + '</section>';

        /* DOMPurify defense-in-depth (imported as vendor in index.html) */
        host.innerHTML = (typeof DOMPurify !== "undefined")
            ? DOMPurify.sanitize(html)
            : html;

        /* Wire Chart.js sparklines after DOM update */
        _wireSparkCharts(history, 10);
    }

    /* ---- Public API ---- */

    function render() {
        var host = document.querySelector(ROOT_SEL);
        if (!host) return;

        var base = _apiBase();
        var url = (base || "") + "/api/observability/mcp-coverage-history?months=6";

        fetch(url, { headers: _authHeaders() })
            .then(function (r) {
                if (!r.ok) throw new Error("HTTP " + r.status);
                return r.json();
            })
            .then(function (data) {
                _state.data = data;
                _renderAll(data);
            })
            .catch(function (err) {
                var host2 = document.querySelector(ROOT_SEL);
                if (host2) {
                    host2.innerHTML = '<div class="mcp-coverage-empty">Erro ao carregar MCP Coverage: '
                        + escHtml(String(err)) + '</div>';
                }
            });
    }

    function destroy() {
        _destroyCharts();
    }

    window.ObservabilityMcpCoverage = {
        render: render,
        destroy: destroy,
        _state: _state,
    };
})();
