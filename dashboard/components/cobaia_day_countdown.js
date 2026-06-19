/**
 * F8-A — Cobaia Day Countdown (IIFE component).
 *
 * Shows Day N/14 + phase label + progress bar for warmup timeline.
 * Fetches /api/linkedin/cobaia/status and auto-refreshes once per hour.
 *
 * XSS: textContent only — no innerHTML with user data.
 * WCAG: progressbar role + aria-valuenow/max, aria-label on badge.
 *
 * Exposes: window.CobaiaDayCountdown = { mount, destroy }
 */
(function CobaiaDayCountdown() {
    'use strict';

    const API = () => localStorage.getItem('hermes_api') || '';
    const TOKEN = () => localStorage.getItem('hermes_token') || '';

    const PHASE_LABELS = {
        lurking: 'Lurking',
        ramp: 'Ramp',
        normal: 'Ativo',
        paused: 'Pausado',
    };
    const TOTAL_DAYS = 14;

    let _mount = null;
    let _refreshInterval = null;

    function _apiFetch(path) {
        return fetch(API() + path, { headers: { 'X-Hermes-Token': TOKEN() } })
            .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
    }

    function _render(status) {
        if (!_mount) return;

        var started = status && status.started_at;
        var dayN = (started && status.current_day != null) ? status.current_day : 0;
        var phase = (started && status.phase) ? status.phase : null;
        var phaseLabel = phase ? (PHASE_LABELS[phase] || phase) : 'Start Warmup';
        var pct = Math.min(100, (dayN / TOTAL_DAYS) * 100).toFixed(1);
        var ariaLabel = phase
            ? 'Dia ' + dayN + ' de ' + TOTAL_DAYS + ', fase ' + phaseLabel
            : 'Warmup nao iniciado';

        var badge = document.createElement('div');
        badge.className = 'op-day-badge' + (phase ? ' op-day-badge--' + phase : ' op-day-badge--pending');
        badge.setAttribute('aria-label', ariaLabel);

        var dayNumEl = document.createElement('span');
        dayNumEl.className = 'op-day-n';
        dayNumEl.textContent = phase ? ('Dia ' + dayN + '/' + TOTAL_DAYS) : 'Aguardando';

        var phaseEl = document.createElement('span');
        phaseEl.className = 'op-day-phase';
        phaseEl.textContent = phaseLabel;

        var progress = document.createElement('div');
        progress.className = 'op-day-progress';
        progress.setAttribute('role', 'progressbar');
        progress.setAttribute('aria-valuemin', '0');
        progress.setAttribute('aria-valuenow', dayN);
        progress.setAttribute('aria-valuemax', TOTAL_DAYS);
        progress.setAttribute('aria-label', 'Progresso: ' + dayN + ' de ' + TOTAL_DAYS + ' dias');

        var fill = document.createElement('div');
        fill.className = 'op-day-progress-fill';
        fill.style.width = pct + '%';
        progress.appendChild(fill);

        badge.appendChild(dayNumEl);
        badge.appendChild(phaseEl);
        badge.appendChild(progress);

        _mount.innerHTML = '';
        _mount.appendChild(badge);
    }

    function _refresh() {
        _apiFetch('/api/linkedin/cobaia/status').then(function (s) { _render(s); }).catch(function () {});
    }

    function mount(containerId, initialStatus) {
        _mount = document.getElementById(containerId);
        if (!_mount) {
            console.warn('[cobaia-day-countdown] mount point not found:', containerId);
            return;
        }
        _render(initialStatus || null);
        if (_refreshInterval) clearInterval(_refreshInterval);
        _refreshInterval = setInterval(_refresh, 3600000); // once per hour
    }

    function destroy() {
        if (_refreshInterval) { clearInterval(_refreshInterval); _refreshInterval = null; }
        _mount = null;
    }

    window.CobaiaDayCountdown = { mount: mount, destroy: destroy };
})();
