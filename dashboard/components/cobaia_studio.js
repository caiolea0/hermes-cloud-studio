/**
 * F.7 C3 — Cobaia Studio (master IIFE orchestrator).
 *
 * Mounts 4 sub-components, fetches initial data in parallel,
 * and fans out WS cobaia.* events to sub-components.
 *
 * Dedup: Map LRU cap 100 + 250ms debounce (REUSE F.4.3 W4 pattern).
 * WS key: uses event_type NOT type (F.4 lesson W4).
 *
 * Exposes: window.CobaiaStudio = { mount, unmount }
 */
(function CobaiaStudio() {
    'use strict';

    const API = () => localStorage.getItem('hermes_api') || '';
    const TOKEN = () => localStorage.getItem('hermes_token') || '';

    let _mounted = false;
    let _wsHandler = null;
    let _debounceTimer = null;
    const _dedup = new Map();           // delivery_id → timestamp LRU cap 100
    const DEDUP_CAP = 100;
    const DEDUP_DEBOUNCE_MS = 250;

    // ------------------------------------------------------------------ API

    function _apiFetch(path) {
        return fetch(`${API()}${path}`, {
            headers: { 'X-Hermes-Token': TOKEN() },
        }).then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            return r.json();
        });
    }

    // ------------------------------------------------------------------ Dedup

    function _isDup(eventType, deliveryId) {
        const key = `${eventType}:${deliveryId}`;
        if (_dedup.has(key)) return true;
        _dedup.set(key, Date.now());
        if (_dedup.size > DEDUP_CAP) {
            _dedup.delete(_dedup.keys().next().value);
        }
        return false;
    }

    // ------------------------------------------------------------------ WS

    function _handleCobaiaEvent(event) {
        const et = event.event_type || '';
        if (!et.startsWith('cobaia.')) return;
        const deliveryId = event.delivery_id || et;
        if (_isDup(et, deliveryId)) return;

        // Debounce rapid bursts (e.g. activity feed)
        clearTimeout(_debounceTimer);
        _debounceTimer = setTimeout(() => _dispatchCobaiaEvent(event), DEDUP_DEBOUNCE_MS);
    }

    function _dispatchCobaiaEvent(event) {
        const et = event.event_type || '';

        if (et === 'cobaia.daily_check_done' || et === 'cobaia.state_changed') {
            const state = event.data || {};
            if (window.CobaiaEmergencyStop) window.CobaiaEmergencyStop.updatePhase(state.phase);
            _refreshTimeline();
        }
        if (et === 'cobaia.auto_paused') {
            if (window.CobaiaEmergencyStop) window.CobaiaEmergencyStop.updatePhase('paused');
            if (window.toast) toast('Cobaia auto-pausada: ' + (event.data && event.data.reason || 'erros consecutivos'), 'warn');
        }
        if (et === 'cobaia.activity') {
            const item = event.data || {};
            if (window.CobaiaActivityFeed) window.CobaiaActivityFeed.addEvent({
                message: item.message || item.action || et,
                category: item.category || 'engagement',
                timestamp: item.timestamp || new Date().toISOString(),
            });
        }
        if (et === 'cobaia.metrics_updated') {
            _refreshKpis();
        }
    }

    // ------------------------------------------------------------------ Data load

    function _refreshTimeline() {
        _apiFetch('/api/linkedin/cobaia/timeline')
            .then(data => {
                if (window.CobaiaTimeline) window.CobaiaTimeline.render(data);
            })
            .catch(err => console.warn('[cobaia-studio] timeline fetch failed:', err));
    }

    function _refreshKpis() {
        _apiFetch('/api/linkedin/cobaia/metrics?days=7')
            .then(data => {
                if (window.CobaiaKpiCards) window.CobaiaKpiCards.render(data);
            })
            .catch(err => console.warn('[cobaia-studio] metrics fetch failed:', err));
    }

    function _loadAll() {
        // Parallel fetch — status + metrics + timeline
        const statusP = _apiFetch('/api/linkedin/cobaia/status').catch(() => null);
        const metricsP = _apiFetch('/api/linkedin/cobaia/metrics?days=7').catch(() => null);
        const timelineP = _apiFetch('/api/linkedin/cobaia/timeline').catch(() => null);

        Promise.all([statusP, metricsP, timelineP]).then(([status, metrics, timeline]) => {
            if (window.CobaiaEmergencyStop) {
                const phase = (status && status.phase) || null;
                window.CobaiaEmergencyStop.mount('cobaia-emergency-stop-mount', phase, _onStateChange);
            }
            if (window.CobaiaTimeline) {
                window.CobaiaTimeline.mount('cobaia-timeline-mount');
                window.CobaiaTimeline.render(timeline || { exists: false });
            }
            if (window.CobaiaKpiCards) {
                window.CobaiaKpiCards.mount('cobaia-kpi-mount');
                window.CobaiaKpiCards.render(metrics || {});
            }
            if (window.CobaiaActivityFeed) {
                window.CobaiaActivityFeed.mount('cobaia-feed-mount');
            }
            _renderHeader(status);
        });
    }

    function _onStateChange(state) {
        _renderHeader(state);
        _refreshTimeline();
        _refreshKpis();
    }

    // ------------------------------------------------------------------ Header

    function _renderHeader(status) {
        const el = document.getElementById('cobaia-header-mount');
        if (!el) return;
        if (!status) {
            el.textContent = 'Cobaia nao iniciada';
            return;
        }
        const phase = status.phase || 'lurking';
        const day = status.current_day != null ? status.current_day : '—';
        const PHASE_LABELS = { lurking: 'Lurking', ramp: 'Ramp', normal: 'Normal', paused: 'Pausado' };
        const label = PHASE_LABELS[phase] || phase;

        const badge = document.createElement('span');
        badge.className = `cobaia-phase-badge cobaia-phase-badge--${phase}`;
        badge.textContent = label;
        badge.setAttribute('aria-label', `Fase ${label}`);

        const dayEl = document.createElement('span');
        dayEl.className = 'cobaia-header-day';
        dayEl.textContent = `Dia ${day}`;

        const handleEl = document.createElement('span');
        handleEl.className = 'cobaia-header-handle';
        handleEl.textContent = status.account_handle || '';

        el.innerHTML = '';
        el.appendChild(badge);
        el.appendChild(dayEl);
        el.appendChild(handleEl);
    }

    // ------------------------------------------------------------------ Mount / Unmount

    function mount() {
        if (_mounted) return;
        _mounted = true;

        _loadAll();

        _wsHandler = (e) => _handleCobaiaEvent(e.detail || {});
        document.addEventListener('hermes-ws-event', _wsHandler);
    }

    function unmount() {
        if (!_mounted) return;
        _mounted = false;
        if (_wsHandler) {
            document.removeEventListener('hermes-ws-event', _wsHandler);
            _wsHandler = null;
        }
        clearTimeout(_debounceTimer);
        if (window.CobaiaKpiCards) window.CobaiaKpiCards.destroy();
        _dedup.clear();
    }

    window.CobaiaStudio = { mount, unmount };
})();
