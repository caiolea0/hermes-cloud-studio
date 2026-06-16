/**
 * F.7 C3 — Cobaia KPI Cards (IIFE component).
 *
 * Renders 3 KPI cards: Reply Rate, Accept Rate, View→Connect.
 * Each card: large metric + threshold color-code + 7-day sparkline (Chart.js).
 *
 * Thresholds (D3 cristalizado):
 *   reply_rate_target:       8%  (>= green, 4–8% yellow, <4% red)
 *   accept_rate_target:      20% (>= green, 10–20% yellow, <10% red)
 *   view_to_connect_target:  3%  (>= green, 1–3% yellow, <1% red)
 *
 * Chart.js vendor REUSE: loaded by index.html via /dashboard/vendor/chart.min.js
 *
 * XSS: textContent only.
 * WCAG: aria-label on each KPI card.
 */
(function CobaiaKpiCards() {
    'use strict';

    const KPI_DEFS = [
        {
            key: 'reply_rate',
            label: 'Reply Rate',
            target: 0.08,
            warn: 0.04,
            format: v => (v * 100).toFixed(1) + '%',
            desc: 'Respostas / Conexoes',
            dataKey: 'replies_received',
            denomKey: 'connects_sent',
        },
        {
            key: 'accept_rate',
            label: 'Accept Rate',
            target: 0.20,
            warn: 0.10,
            format: v => (v * 100).toFixed(1) + '%',
            desc: 'Aceites / Enviados',
            dataKey: 'connects_accepted',
            denomKey: 'connects_sent',
        },
        {
            key: 'view_to_connect',
            label: 'View→Connect',
            target: 0.03,
            warn: 0.01,
            format: v => (v * 100).toFixed(1) + '%',
            desc: 'Connects / Views',
            dataKey: 'connects_sent',
            denomKey: 'views_count',
        },
    ];

    const _charts = {};
    let _mount = null;

    function _colorClass(value, def) {
        if (value >= def.target) return 'cobaia-kpi-value--green';
        if (value >= def.warn) return 'cobaia-kpi-value--yellow';
        return 'cobaia-kpi-value--red';
    }

    function _buildSparklineData(daily, def) {
        return (daily || []).map(row => {
            const num = row[def.dataKey] || 0;
            const den = row[def.denomKey] || 0;
            return den > 0 ? num / den : 0;
        });
    }

    function _renderSparkline(canvasId, data, def) {
        const canvas = document.getElementById(canvasId);
        if (!canvas || typeof Chart === 'undefined') return;

        if (_charts[canvasId]) {
            _charts[canvasId].destroy();
            delete _charts[canvasId];
        }

        const color = data.length && data[data.length - 1] >= def.target
            ? '#3fb950'  // --color-success hex (vendor chart requires literal)
            : data.length && data[data.length - 1] >= def.warn
                ? '#d29922'  // --color-warn
                : '#f85149'; // --color-error

        _charts[canvasId] = new Chart(canvas, {
            type: 'line',
            data: {
                labels: data.map((_, i) => `D${i + 1}`),
                datasets: [{
                    data,
                    borderColor: color,
                    backgroundColor: color + '22',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    fill: true,
                    tension: 0.3,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
                scales: {
                    x: { display: false },
                    y: { display: false },
                },
                animation: { duration: 300 },
            },
        });
    }

    function render(metricsData) {
        if (!_mount) return;
        _mount.innerHTML = '';

        const grid = document.createElement('div');
        grid.className = 'cobaia-kpi-grid';

        const kpis = (metricsData && metricsData.kpis) || {};
        const daily = (metricsData && metricsData.daily) || [];

        KPI_DEFS.forEach((def, idx) => {
            const value = kpis[def.key] || 0;
            const colorClass = _colorClass(value, def);
            const canvasId = `cobaia-spark-${def.key}`;
            const ariaLabel = `${def.label}: ${def.format(value)}, alvo ${def.format(def.target)}`;

            const card = document.createElement('div');
            card.className = 'cobaia-kpi-card';
            card.setAttribute('aria-label', ariaLabel);

            const labelEl = document.createElement('div');
            labelEl.className = 'cobaia-kpi-label';
            labelEl.textContent = def.label;

            const valueEl = document.createElement('div');
            valueEl.className = `cobaia-kpi-value ${colorClass}`;
            valueEl.setAttribute('aria-live', 'polite');
            valueEl.textContent = def.format(value);

            const threshEl = document.createElement('div');
            threshEl.className = 'cobaia-kpi-threshold';
            threshEl.textContent = `Alvo: ${def.format(def.target)} · ${def.desc}`;

            const sparkWrap = document.createElement('div');
            sparkWrap.className = 'cobaia-kpi-sparkline';
            sparkWrap.setAttribute('aria-hidden', 'true');

            const canvas = document.createElement('canvas');
            canvas.id = canvasId;
            canvas.setAttribute('aria-hidden', 'true');
            sparkWrap.appendChild(canvas);

            card.appendChild(labelEl);
            card.appendChild(valueEl);
            card.appendChild(threshEl);
            card.appendChild(sparkWrap);
            grid.appendChild(card);

            // Defer sparkline render after DOM insert
            setTimeout(() => {
                _renderSparkline(canvasId, _buildSparklineData(daily, def), def);
            }, 0);
        });

        _mount.appendChild(grid);
    }

    function destroy() {
        Object.keys(_charts).forEach(id => {
            try { _charts[id].destroy(); } catch (_) {}
            delete _charts[id];
        });
    }

    function mount(containerId) {
        _mount = document.getElementById(containerId);
        if (!_mount) console.warn('[cobaia-kpi] mount point not found:', containerId);
    }

    window.CobaiaKpiCards = { mount, render, destroy };
})();
