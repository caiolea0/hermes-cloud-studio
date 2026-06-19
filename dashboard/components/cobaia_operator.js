/**
 * F8-A — Cobaia Operator Mode Orchestrator (IIFE).
 *
 * Manages the cobaia page with two view modes:
 *   'studio'   — classic Studio layout (timeline + KPIs + feed + emergency stop)
 *   'operator' — focused Operator layout (day countdown + KPI hero + today queue + live feed)
 *
 * Mode persisted in localStorage('hermes.cobaia.mode').
 * Auto-selects 'operator' when warmup_started_at is set (Day 0+), unless user has
 * an explicit preference saved.
 *
 * WS: subscribes to cobaia.* events (dedup + 250ms debounce, REUSE F.4.3 pattern).
 *
 * XSS: textContent for all dynamic data; no innerHTML with user content.
 * WCAG: role=tablist + aria-selected on toggle, h2 section titles,
 *        progressbar in CobaiaDayCountdown, role=log in CobaiaActivityFeed.
 *
 * Exposes: window.CobaiaOperator = { mount, unmount, setMode }
 */
(function CobaiaOperatorMode() {
    'use strict';

    var _STORAGE_KEY = 'hermes.cobaia.mode';

    var _container = null;
    var _mode = localStorage.getItem(_STORAGE_KEY) || 'studio';
    var _modeExplicit = !!localStorage.getItem(_STORAGE_KEY);
    var _mounted = false;
    var _wsHandler = null;
    var _debounceTimer = null;
    var _dedup = new Map();
    var DEDUP_CAP = 100;

    var PHASE_LABELS = { lurking: 'Lurking', ramp: 'Ramp', normal: 'Normal', paused: 'Pausado' };

    // ── API helper ────────────────────────────────────────────────────────────

    function _api(path) {
        return fetch((localStorage.getItem('hermes_api') || '') + path, {
            headers: { 'X-Hermes-Token': localStorage.getItem('hermes_token') || '' },
        }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
    }

    // ── Dedup helper ──────────────────────────────────────────────────────────

    function _isDup(key) {
        if (_dedup.has(key)) return true;
        _dedup.set(key, 1);
        if (_dedup.size > DEDUP_CAP) _dedup.delete(_dedup.keys().next().value);
        return false;
    }

    // ── WS event handling ─────────────────────────────────────────────────────

    function _handleWS(event) {
        var et = event.event_type || '';
        if (!et.startsWith('cobaia.')) return;
        var key = et + ':' + (event.delivery_id || et);
        if (_isDup(key)) return;
        clearTimeout(_debounceTimer);
        _debounceTimer = setTimeout(function () { _dispatch(event); }, 250);
    }

    function _dispatch(event) {
        var et = event.event_type || '';

        if (et === 'cobaia.state_changed' || et === 'cobaia.daily_check_done') {
            var state = event.data || {};
            if (window.CobaiaEmergencyStop) window.CobaiaEmergencyStop.updatePhase(state.phase);
            if (window.CobaiaDayCountdown) {
                _api('/api/linkedin/cobaia/status')
                    .then(function (s) { if (window.CobaiaDayCountdown) window.CobaiaDayCountdown.mount(_dayMountId(), s); })
                    .catch(function () {});
            }
            _api('/api/linkedin/cobaia/timeline')
                .then(function (d) { if (window.CobaiaTimeline) window.CobaiaTimeline.render(d); })
                .catch(function () {});
        }

        if (et === 'cobaia.metrics_updated') {
            _api('/api/linkedin/cobaia/metrics?days=7')
                .then(function (d) { if (window.CobaiaKpiCards) window.CobaiaKpiCards.render(d); })
                .catch(function () {});
        }

        if (et === 'cobaia.activity') {
            var item = event.data || {};
            if (window.CobaiaActivityFeed) {
                window.CobaiaActivityFeed.addEvent({
                    message: item.message || item.action || et,
                    category: item.category || 'engagement',
                    timestamp: item.timestamp || new Date().toISOString(),
                });
            }
        }

        if (et === 'cobaia.auto_paused') {
            if (window.CobaiaEmergencyStop) window.CobaiaEmergencyStop.updatePhase('paused');
            if (window.toast) toast('Cobaia auto-pausada: ' + ((event.data || {}).reason || 'erros'), 'warning');
        }
    }

    // ── Mount ID helpers (differ per mode) ───────────────────────────────────

    function _dayMountId() { return _mode === 'operator' ? 'op-day-countdown-mount' : null; }

    // ── Toggle bar HTML ───────────────────────────────────────────────────────

    function _toggleBarHTML() {
        var studioSel = _mode === 'studio' ? 'true' : 'false';
        var operSel   = _mode === 'operator' ? 'true' : 'false';
        var studioActive = _mode === 'studio' ? ' cobaia-mode-tab--active' : '';
        var operActive   = _mode === 'operator' ? ' cobaia-mode-tab--active' : '';
        return '<div class="cobaia-mode-bar">' +
            '<div class="cobaia-mode-tablist" role="tablist" aria-label="Modo de visualizacao cobaia">' +
                '<button role="tab" class="cobaia-mode-tab' + studioActive + '" data-mode="studio" aria-selected="' + studioSel + '">Studio</button>' +
                '<button role="tab" class="cobaia-mode-tab' + operActive + '" data-mode="operator" aria-selected="' + operSel + '">Operator</button>' +
            '</div>' +
        '</div>';
    }

    // ── Studio layout ─────────────────────────────────────────────────────────

    function _renderStudio() {
        if (!_container) return;
        _container.innerHTML =
            _toggleBarHTML() +
            '<section class="cobaia-section cobaia-section--header" aria-label="Status cobaia">' +
                '<div class="cobaia-header">' +
                    '<div id="op-st-header" class="cobaia-header-meta" aria-live="polite"></div>' +
                '</div>' +
                '<div id="op-st-stop"></div>' +
            '</section>' +
            '<section class="cobaia-section" aria-label="Timeline warmup 14 dias">' +
                '<h2 class="cobaia-section-title">Warmup Timeline</h2>' +
                '<div id="op-st-timeline"></div>' +
            '</section>' +
            '<section class="cobaia-section" aria-label="KPIs cobaia">' +
                '<h2 class="cobaia-section-title">KPIs — 7 dias</h2>' +
                '<div id="op-st-kpi"></div>' +
            '</section>' +
            '<section class="cobaia-section cobaia-section--feed" aria-label="Feed de atividade cobaia">' +
                '<h2 class="cobaia-section-title">Atividade em Tempo Real</h2>' +
                '<div id="op-st-feed" class="cobaia-feed-wrap"></div>' +
            '</section>';

        _bindTabs();
        _loadStudio();
    }

    function _loadStudio() {
        var statusP   = _api('/api/linkedin/cobaia/status').catch(function () { return null; });
        var metricsP  = _api('/api/linkedin/cobaia/metrics?days=7').catch(function () { return null; });
        var timelineP = _api('/api/linkedin/cobaia/timeline').catch(function () { return null; });
        Promise.all([statusP, metricsP, timelineP]).then(function (results) {
            var status   = results[0];
            var metrics  = results[1];
            var timeline = results[2];
            if (!_mounted) return; // unmounted during fetch
            if (window.CobaiaEmergencyStop) {
                window.CobaiaEmergencyStop.mount('op-st-stop', status && status.phase, _onStateChange);
            }
            if (window.CobaiaTimeline) {
                window.CobaiaTimeline.mount('op-st-timeline');
                window.CobaiaTimeline.render(timeline || { exists: false });
            }
            if (window.CobaiaKpiCards) {
                window.CobaiaKpiCards.mount('op-st-kpi');
                window.CobaiaKpiCards.render(metrics || {});
            }
            if (window.CobaiaActivityFeed) window.CobaiaActivityFeed.mount('op-st-feed');
            _renderStudioHeader(status);
        });
    }

    function _renderStudioHeader(status) {
        var el = document.getElementById('op-st-header');
        if (!el) return;
        if (!status) { el.textContent = 'Cobaia nao iniciada'; return; }
        var badge = document.createElement('span');
        badge.className = 'cobaia-phase-badge cobaia-phase-badge--' + (status.phase || 'lurking');
        badge.textContent = PHASE_LABELS[status.phase] || status.phase || 'Desconhecido';
        badge.setAttribute('aria-label', 'Fase ' + (PHASE_LABELS[status.phase] || status.phase));
        var dayEl = document.createElement('span');
        dayEl.className = 'cobaia-header-day';
        dayEl.textContent = 'Dia ' + (status.current_day != null ? status.current_day : '—');
        el.innerHTML = '';
        el.appendChild(badge);
        el.appendChild(dayEl);
    }

    function _onStateChange(state) {
        _renderStudioHeader(state);
        _api('/api/linkedin/cobaia/timeline').then(function (d) {
            if (window.CobaiaTimeline) window.CobaiaTimeline.render(d);
        }).catch(function () {});
        _api('/api/linkedin/cobaia/metrics?days=7').then(function (d) {
            if (window.CobaiaKpiCards) window.CobaiaKpiCards.render(d);
        }).catch(function () {});
    }

    // ── Operator layout ───────────────────────────────────────────────────────

    // ── Inline panic confirmation HTML ────────────────────────────────────────

    function _panicInlineHTML() {
        return '<div class="op-panic-inline" id="op-panic-inline" data-state="idle">' +
            '<button class="btn btn-danger op-panic-trigger" type="button" ' +
                    'aria-label="Acionar parada de emergência da cobaia" ' +
                    'style="min-height:44px;min-width:44px;">' +
                '🚨 Panic Stop' +
            '</button>' +
            '<div class="op-panic-confirm" id="op-panic-confirm" hidden ' +
                 'role="alertdialog" aria-modal="false" ' +
                 'aria-label="Confirmação de parada de emergência" ' +
                 'aria-describedby="op-panic-desc">' +
                '<strong>Confirmar parada?</strong>' +
                '<p id="op-panic-desc">Cobaia warmup será pausado imediatamente.</p>' +
                '<div class="op-panic-confirm-actions">' +
                    '<button class="btn btn-danger op-panic-exec" id="op-panic-exec" type="button" ' +
                            'style="min-height:44px;">' +
                        'Sim, parar' +
                    '</button>' +
                    '<button class="btn btn-ghost op-panic-cancel" type="button" ' +
                            'style="min-height:44px;">' +
                        'Cancelar' +
                    '</button>' +
                '</div>' +
            '</div>' +
        '</div>';
    }

    function _bindPanicInline() {
        var wrap = document.getElementById('op-panic-inline');
        if (!wrap) return;
        var trigger = wrap.querySelector('.op-panic-trigger');
        var confirm = document.getElementById('op-panic-confirm');
        var execBtn = document.getElementById('op-panic-exec');
        var cancelBtn = wrap.querySelector('.op-panic-cancel');

        function _show() {
            if (trigger) trigger.hidden = true;
            if (confirm) { confirm.hidden = false; }
            if (execBtn) execBtn.focus();
        }
        function _hide() {
            if (trigger) trigger.hidden = false;
            if (confirm) confirm.hidden = true;
            if (trigger) trigger.focus();
        }
        function _execute() {
            _hide();
            _api('/api/linkedin/cobaia/panic').then(function () {
                if (window.toast) toast('Cobaia pausada — emergência executada', 'error');
            }).catch(function (e) {
                if (window.toast) toast('Erro ao pausar cobaia: ' + e.message, 'error');
            });
        }
        if (trigger) trigger.addEventListener('click', _show);
        if (execBtn) execBtn.addEventListener('click', _execute);
        if (cancelBtn) cancelBtn.addEventListener('click', _hide);

        // Esc closes confirm
        wrap.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && confirm && !confirm.hidden) { e.stopPropagation(); _hide(); }
        });
    }

    function _renderOperator() {
        if (!_container) return;
        _container.innerHTML =
            _toggleBarHTML() +
            '<div class="cobaia-operator-grid" role="region" aria-label="Cobaia Operator Mode">' +
                // Sentry banner above everything
                '<div class="op-sentry-banner-wrap" id="op-sentry-banner-mount"></div>' +
                '<header class="op-header">' +
                    '<div class="op-header-left">' +
                        '<div id="op-day-countdown-mount" class="op-header-countdown"></div>' +
                        '<div id="op-brain-badge-mount" class="op-brain-badge-mount"></div>' +
                    '</div>' +
                    '<div id="op-status-badge-mount" class="op-header-status" aria-live="polite"></div>' +
                    '<div class="op-header-actions">' +
                        _panicInlineHTML() +
                    '</div>' +
                '</header>' +
                '<section class="op-kpis-hero" aria-label="KPIs principais cobaia">' +
                    '<h2 class="op-panel-title">KPIs Cobaia</h2>' +
                    '<div id="op-kpi-mount"></div>' +
                '</section>' +
                '<section class="op-rl-gauge-section" aria-label="LinkedIn rate limits">' +
                    '<h2 class="op-panel-title">Rate Limits LinkedIn</h2>' +
                    '<div id="op-rl-gauge-mount"></div>' +
                '</section>' +
                '<div class="op-main-grid">' +
                    '<section class="op-queue-panel" aria-label="Proximas acoes de hoje">' +
                        '<h2 class="op-panel-title">Fila de Hoje</h2>' +
                        '<div id="op-queue-mount"></div>' +
                    '</section>' +
                    '<section class="op-feed-panel" aria-label="Atividade cobaia em tempo real">' +
                        '<h2 class="op-panel-title">Atividade Live</h2>' +
                        '<div id="op-feed-mount-op" class="cobaia-feed-wrap"></div>' +
                    '</section>' +
                '</div>' +
                '<section class="op-timeline-section" aria-label="Timeline warmup 14 dias">' +
                    '<h2 class="op-panel-title">Timeline Warmup</h2>' +
                    '<div id="op-timeline-mount-op"></div>' +
                '</section>' +
            '</div>';

        _bindTabs();
        _bindPanicInline();
        _loadOperator();
    }

    function _loadOperator() {
        var statusP   = _api('/api/linkedin/cobaia/status').catch(function () { return null; });
        var metricsP  = _api('/api/linkedin/cobaia/metrics?days=7').catch(function () { return null; });
        var timelineP = _api('/api/linkedin/cobaia/timeline').catch(function () { return null; });
        Promise.all([statusP, metricsP, timelineP]).then(function (results) {
            var status   = results[0];
            var metrics  = results[1];
            var timeline = results[2];
            if (!_mounted) return; // unmounted during fetch

            if (window.CobaiaDayCountdown) {
                window.CobaiaDayCountdown.mount('op-day-countdown-mount', status);
            }
            _renderOperatorStatusBadge(status);

            // F8-B: brain queue badge
            if (window.HermesCobaiaBrainQueueBadge) {
                window.HermesCobaiaBrainQueueBadge.mount('op-brain-badge-mount');
            }
            // F8-B: sentry banner
            if (window.HermesCobaiaSentryBanner) {
                window.HermesCobaiaSentryBanner.mount('op-sentry-banner-mount');
            }
            // F8-B: rate-limit gauge
            if (window.HermesCobaiaRateLimitGauge) {
                window.HermesCobaiaRateLimitGauge.mount('op-rl-gauge-mount');
            }

            if (window.CobaiaKpiCards) {
                window.CobaiaKpiCards.mount('op-kpi-mount');
                window.CobaiaKpiCards.render(metrics || {});
            }
            if (window.CobaiaTodayQueue) window.CobaiaTodayQueue.mount('op-queue-mount');
            if (window.CobaiaActivityFeed) window.CobaiaActivityFeed.mount('op-feed-mount-op');
            if (window.CobaiaTimeline) {
                window.CobaiaTimeline.mount('op-timeline-mount-op');
                window.CobaiaTimeline.render(timeline || { exists: false });
            }
        });
    }

    function _renderOperatorStatusBadge(status) {
        var el = document.getElementById('op-status-badge-mount');
        if (!el) return;
        el.innerHTML = '';
        if (!status || !status.phase) return;
        var badge = document.createElement('span');
        badge.className = 'cobaia-status-badge cobaia-status-badge--' + status.phase;
        badge.textContent = PHASE_LABELS[status.phase] || status.phase;
        badge.setAttribute('aria-label', 'Estado: ' + (PHASE_LABELS[status.phase] || status.phase));
        el.appendChild(badge);
    }

    // ── Mode toggle binding ───────────────────────────────────────────────────

    function _bindTabs() {
        if (!_container) return;
        _container.querySelectorAll('[role="tab"]').forEach(function (tab) {
            tab.addEventListener('click', function () { setMode(tab.dataset.mode); });
            tab.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setMode(tab.dataset.mode); }
            });
        });
    }

    // ── Render current mode ───────────────────────────────────────────────────

    function _renderMode() {
        if (_mode === 'operator') _renderOperator();
        else _renderStudio();
    }

    // ── Auto-mode detection (warmup active → prefer operator) ─────────────────

    function _checkAutoMode() {
        if (_modeExplicit) return; // user has explicit preference
        _api('/api/linkedin/cobaia/status').then(function (status) {
            if (!_mounted) return;
            if (status && status.started_at && _mode !== 'operator') {
                _mode = 'operator';
                _renderMode(); // re-render in operator mode
            }
        }).catch(function () {});
    }

    // ── Public API ────────────────────────────────────────────────────────────

    function setMode(mode) {
        if (mode !== 'studio' && mode !== 'operator') return;
        _mode = mode;
        _modeExplicit = true;
        localStorage.setItem(_STORAGE_KEY, mode);
        if (_container) _renderMode();
    }

    function mount(container) {
        if (!container) return;
        _container = container;
        _mounted = true;
        _renderMode();
        _checkAutoMode();
        _wsHandler = function (e) { _handleWS(e.detail || {}); };
        document.addEventListener('hermes-ws-event', _wsHandler);
    }

    function unmount() {
        _mounted = false;
        if (_wsHandler) {
            document.removeEventListener('hermes-ws-event', _wsHandler);
            _wsHandler = null;
        }
        clearTimeout(_debounceTimer);
        if (window.CobaiaKpiCards) window.CobaiaKpiCards.destroy();
        if (window.CobaiaTodayQueue) window.CobaiaTodayQueue.destroy();
        if (window.CobaiaDayCountdown) window.CobaiaDayCountdown.destroy();
        // F8-B new components
        if (window.HermesCobaiaBrainQueueBadge) window.HermesCobaiaBrainQueueBadge.destroy();
        if (window.HermesCobaiaSentryBanner) window.HermesCobaiaSentryBanner.destroy();
        if (window.HermesCobaiaRateLimitGauge) window.HermesCobaiaRateLimitGauge.destroy();
        _dedup.clear();
        _container = null;
    }

    window.CobaiaOperator = { mount: mount, unmount: unmount, setMode: setMode };
})();
