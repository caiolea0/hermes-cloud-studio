/**
 * F8-B — Sentry Alerts Inline Banner (IIFE).
 *
 * Shows top open error above operator KPIs. Dismissed for 1h via localStorage.
 * Critical severity overrides dismissed state and shows again.
 * Auto-refreshes every 60s + reacts to sentry.issue_new WS event.
 *
 * WCAG: role=alert + aria-live=polite.
 * XSS: escapeHtml on all user-facing strings; only safe keys rendered.
 *
 * Exposes: window.HermesCobaiaSentryBanner = { mount, destroy, dismiss }
 */
(function CobaiaSentryBanner() {
    'use strict';

    var DISMISS_KEY = 'hermes.sentry_banner.dismissed_until';
    var DISMISS_TTL = 3600000; // 1h in ms

    var _container = null;
    var _refreshInterval = null;
    var _wsHandler = null;
    var _lastItems = [];

    function _api(path) {
        return fetch((localStorage.getItem('hermes_api') || '') + path, {
            headers: { 'X-Hermes-Token': localStorage.getItem('hermes_token') || '' },
        }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
    }

    function _escapeHtml(str) {
        return String(str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function _isDismissed(severity) {
        if (severity === 'critical') return false; // always show critical
        var until = parseInt(localStorage.getItem(DISMISS_KEY) || '0', 10);
        return Date.now() < until;
    }

    function _refresh() {
        _api('/api/observability/errors?status=open&limit=5').then(function (r) {
            // Flatten items_by_category into flat list
            var items = [];
            var byCategory = r.items_by_category || {};
            Object.keys(byCategory).forEach(function (cat) {
                var catItems = (byCategory[cat] || {}).items || [];
                catItems.forEach(function (item) { items.push(item); });
            });
            // Sort by severity (critical first)
            items.sort(function (a, b) {
                var sev = { critical: 0, error: 1, warning: 2 };
                return (sev[a.severity] || 3) - (sev[b.severity] || 3);
            });
            _lastItems = items.slice(0, 3);
            _render(_lastItems);
        }).catch(function () {
            if (_container) _container.innerHTML = '';
        });
    }

    function _render(items) {
        if (!_container) return;
        if (!items || !items.length) {
            _container.innerHTML = '';
            return;
        }
        var top = items[0];
        if (_isDismissed(top.severity)) {
            _container.innerHTML = '';
            return;
        }

        var sev = top.severity || 'error';
        var count = items.length;

        var banner = document.createElement('div');
        banner.className = 'sentry-banner sentry-banner--' + sev;
        banner.setAttribute('role', 'alert');
        banner.setAttribute('aria-live', 'polite');

        var iconEl = document.createElement('span');
        iconEl.className = 'sentry-banner-icon';
        iconEl.setAttribute('aria-hidden', 'true');
        iconEl.innerHTML = typeof window.icon === 'function'
            ? window.icon(sev === 'critical' ? 'alert-octagon' : 'alert-triangle')
            : '';

        var content = document.createElement('div');
        content.className = 'sentry-banner-content';

        var strong = document.createElement('strong');
        strong.className = 'sentry-banner-title';
        strong.textContent = top.title || '(sem título)';

        var small = document.createElement('small');
        small.className = 'sentry-banner-meta';
        small.textContent = count + ' issue' + (count !== 1 ? 's' : '') + ' open';

        content.appendChild(strong);
        content.appendChild(small);

        var link = document.createElement('a');
        link.className = 'sentry-banner-link';
        link.href = '#observability';
        link.textContent = 'Ver tudo →';

        var dismissBtn = document.createElement('button');
        dismissBtn.className = 'sentry-banner-dismiss';
        dismissBtn.setAttribute('aria-label', 'Dispensar banner de alertas');
        dismissBtn.setAttribute('type', 'button');
        dismissBtn.textContent = '×';
        dismissBtn.addEventListener('click', function () { dismiss(); });

        banner.appendChild(iconEl);
        banner.appendChild(content);
        banner.appendChild(link);
        banner.appendChild(dismissBtn);

        _container.innerHTML = '';
        _container.appendChild(banner);
    }

    function dismiss() {
        localStorage.setItem(DISMISS_KEY, String(Date.now() + DISMISS_TTL));
        if (_container) _container.innerHTML = '';
    }

    function _onWS(event) {
        var msg = event.detail || {};
        var t = msg.event_type || msg.type || '';
        if (t === 'sentry.issue_new') {
            _refresh();
        }
    }

    function mount(container) {
        if (!container) return;
        _container = typeof container === 'string' ? document.getElementById(container) : container;
        if (!_container) return;
        _refresh();
        _refreshInterval = setInterval(_refresh, 60000);
        _wsHandler = _onWS;
        document.addEventListener('hermes-ws-event', _wsHandler);
    }

    function destroy() {
        clearInterval(_refreshInterval);
        if (_wsHandler) document.removeEventListener('hermes-ws-event', _wsHandler);
        _container = null;
        _wsHandler = null;
        _refreshInterval = null;
        _lastItems = [];
    }

    window.HermesCobaiaSentryBanner = { mount: mount, destroy: destroy, dismiss: dismiss };
})();
