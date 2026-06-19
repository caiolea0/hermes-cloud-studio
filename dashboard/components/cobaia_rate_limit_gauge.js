/**
 * F8-B — LinkedIn Rate-Limit Gauge (IIFE).
 *
 * Shows 3 rate-limit buckets (views, connects, engagements) as color-coded bars.
 * Data from GET /api/linkedin/rate-limits (PC local stats).
 * Refreshes every 60s. Fail-graceful: renders "—" on error.
 *
 * WCAG: role=progressbar + aria-valuenow/aria-valuemax per bucket.
 * XSS: textContent only.
 *
 * Exposes: window.HermesCobaiaRateLimitGauge = { mount, destroy }
 */
(function CobaiaRateLimitGauge() {
    'use strict';

    var _container = null;
    var _refreshInterval = null;

    var BUCKETS = [
        { key: 'views',   label: 'Views',     icon: 'eye',
          used: 'daily_views',   limit: 'daily_views_limit' },
        { key: 'connect', label: 'Connects',  icon: 'users',
          used: 'daily_connections', limit: 'daily_connections_limit' },
        { key: 'engage',  label: 'Engage',    icon: 'message-circle',
          used: 'daily_engagements', limit: 'engagements_limit' },
    ];

    function _api(path) {
        return fetch((localStorage.getItem('hermes_api') || '') + path, {
            headers: { 'X-Hermes-Token': localStorage.getItem('hermes_token') || '' },
        }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
    }

    function _refresh() {
        _api('/api/linkedin/rate-limits').then(function (r) {
            _render(r);
        }).catch(function () {
            _renderError();
        });
    }

    function _colorClass(pct) {
        if (pct < 50) return 'green';
        if (pct < 80) return 'amber';
        return 'red';
    }

    function _render(data) {
        if (!_container) return;
        var frag = document.createDocumentFragment();

        var wrapper = document.createElement('div');
        wrapper.className = 'rl-gauge-grid';
        wrapper.setAttribute('role', 'group');
        wrapper.setAttribute('aria-label', 'LinkedIn rate limits');

        BUCKETS.forEach(function (b) {
            var used  = parseInt(data[b.used]  || 0, 10);
            var limit = parseInt(data[b.limit] || 100, 10);
            if (limit <= 0) limit = 100;
            var pct   = Math.min(100, Math.round((used / limit) * 100));
            var color = _colorClass(pct);

            var gauge = document.createElement('div');
            gauge.className = 'rl-gauge rl-gauge--' + color;

            var header = document.createElement('div');
            header.className = 'rl-gauge-header';

            var iconEl = document.createElement('span');
            iconEl.className = 'rl-gauge-icon';
            iconEl.setAttribute('aria-hidden', 'true');
            iconEl.innerHTML = typeof window.icon === 'function' ? window.icon(b.icon) : '';

            var labelEl = document.createElement('span');
            labelEl.className = 'rl-gauge-name';
            labelEl.textContent = b.label;

            header.appendChild(iconEl);
            header.appendChild(labelEl);

            var bar = document.createElement('div');
            bar.className = 'rl-gauge-bar';
            bar.setAttribute('role', 'progressbar');
            bar.setAttribute('aria-valuenow', String(used));
            bar.setAttribute('aria-valuemin', '0');
            bar.setAttribute('aria-valuemax', String(limit));
            bar.setAttribute('aria-label', b.label + ': ' + used + ' de ' + limit);

            var fill = document.createElement('div');
            fill.className = 'rl-gauge-fill';
            fill.style.width = pct + '%';
            bar.appendChild(fill);

            var numbers = document.createElement('div');
            numbers.className = 'rl-gauge-numbers';

            var usedEl = document.createElement('span');
            usedEl.textContent = String(used);
            var sep = document.createElement('span');
            sep.textContent = ' / ';
            sep.setAttribute('aria-hidden', 'true');
            var limitEl = document.createElement('span');
            limitEl.textContent = String(limit);

            numbers.appendChild(usedEl);
            numbers.appendChild(sep);
            numbers.appendChild(limitEl);

            gauge.appendChild(header);
            gauge.appendChild(bar);
            gauge.appendChild(numbers);

            wrapper.appendChild(gauge);
        });

        frag.appendChild(wrapper);
        _container.innerHTML = '';
        _container.appendChild(frag);
    }

    function _renderError() {
        if (!_container) return;
        _container.innerHTML = '';
        var wrapper = document.createElement('div');
        wrapper.className = 'rl-gauge-grid rl-gauge-grid--offline';
        BUCKETS.forEach(function (b) {
            var gauge = document.createElement('div');
            gauge.className = 'rl-gauge rl-gauge--offline';
            var lbl = document.createElement('span');
            lbl.className = 'rl-gauge-name';
            lbl.textContent = b.label + ': —';
            gauge.appendChild(lbl);
            wrapper.appendChild(gauge);
        });
        _container.appendChild(wrapper);
    }

    function mount(container) {
        if (!container) return;
        _container = typeof container === 'string' ? document.getElementById(container) : container;
        if (!_container) return;
        _refresh();
        _refreshInterval = setInterval(_refresh, 60000);
    }

    function destroy() {
        clearInterval(_refreshInterval);
        _container = null;
        _refreshInterval = null;
    }

    window.HermesCobaiaRateLimitGauge = { mount: mount, destroy: destroy };
})();
