/**
 * F8-B — Brain Queue Count Badge (IIFE).
 *
 * Shows Brain pending/processing run counts in the cobaia operator header.
 * Refreshes every 30s + reacts to brain.* WS events.
 *
 * WCAG: role=status + aria-label with counts for screen readers.
 * XSS: textContent only — no innerHTML with user data.
 *
 * Exposes: window.HermesCobaiaBrainQueueBadge = { mount, destroy }
 */
(function CobaiaBrainQueueBadge() {
    'use strict';

    var _container = null;
    var _refreshInterval = null;
    var _wsHandler = null;

    function _api(path) {
        return fetch((localStorage.getItem('hermes_api') || '') + path, {
            headers: { 'X-Hermes-Token': localStorage.getItem('hermes_token') || '' },
        }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
    }

    function _refresh() {
        _api('/api/brain/queue-stats').then(function (r) {
            _render(r);
        }).catch(function () {
            _renderOffline();
        });
    }

    function _render(data) {
        if (!_container) return;
        var pending = data.pending || 0;
        var processing = data.processing || 0;
        var total = pending + processing;
        var decidedToday = data.decided_today || 0;
        var state = total > 0 ? 'active' : 'idle';
        var label = 'Brain: ' + total + ' pendentes, ' + decidedToday + ' decididos hoje';

        var badge = document.createElement('div');
        badge.className = 'brain-queue-badge brain-queue-badge--' + state;
        badge.setAttribute('role', 'status');
        badge.setAttribute('aria-label', label);
        badge.setAttribute('title', label);

        var icon = document.createElement('span');
        icon.className = 'brain-queue-icon';
        icon.setAttribute('aria-hidden', 'true');
        icon.innerHTML = typeof window.icon === 'function' ? window.icon('settings') : '⚙';

        var count = document.createElement('span');
        count.className = 'brain-queue-count';
        count.textContent = String(total);

        var lbl = document.createElement('span');
        lbl.className = 'brain-queue-label';
        lbl.textContent = 'Brain';

        badge.appendChild(icon);
        badge.appendChild(count);
        badge.appendChild(lbl);

        if (total > 0) {
            var spinner = document.createElement('span');
            spinner.className = 'brain-queue-spinner';
            spinner.setAttribute('aria-hidden', 'true');
            badge.appendChild(spinner);
        }

        var today = document.createElement('span');
        today.className = 'brain-queue-today';
        today.setAttribute('aria-hidden', 'true');
        today.textContent = decidedToday + ' hoje';
        badge.appendChild(today);

        _container.innerHTML = '';
        _container.appendChild(badge);
    }

    function _renderOffline() {
        if (!_container) return;
        _container.innerHTML = '';
        var badge = document.createElement('div');
        badge.className = 'brain-queue-badge brain-queue-badge--offline';
        badge.setAttribute('role', 'status');
        badge.setAttribute('aria-label', 'Brain offline');
        badge.textContent = 'Brain —';
        _container.appendChild(badge);
    }

    function _onWS(event) {
        var msg = event.detail || {};
        var t = msg.event_type || msg.type || '';
        if (t.indexOf('brain.') === 0) {
            _refresh();
        }
    }

    function mount(container) {
        if (!container) return;
        _container = typeof container === 'string' ? document.getElementById(container) : container;
        if (!_container) return;
        _refresh();
        _refreshInterval = setInterval(_refresh, 30000);
        _wsHandler = _onWS;
        document.addEventListener('hermes-ws-event', _wsHandler);
    }

    function destroy() {
        clearInterval(_refreshInterval);
        if (_wsHandler) document.removeEventListener('hermes-ws-event', _wsHandler);
        _container = null;
        _wsHandler = null;
        _refreshInterval = null;
    }

    window.HermesCobaiaBrainQueueBadge = { mount: mount, destroy: destroy };
})();
