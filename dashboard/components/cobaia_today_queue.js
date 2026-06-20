/**
 * F8-A — Cobaia Today's Queue (IIFE component).
 *
 * Shows next warmup actions planned for today with ETA and skip action.
 * Fetches /api/linkedin/cobaia/today-queue and refreshes every 60s.
 * Subscribes to cobaia.queue_updated WS event for real-time updates.
 *
 * XSS: textContent only — no innerHTML with user data.
 * WCAG: list role, aria-label on list + buttons, role=alert on error.
 *
 * Exposes: window.CobaiaTodayQueue = { mount, destroy }
 */
(function CobaiaTodayQueue() {
    'use strict';

    const API = () => localStorage.getItem('hermes_api') || '';
    const TOKEN = () => localStorage.getItem('hermes_token') || '';

    const ACTION_ICONS = {
        view:    'eye',
        connect: 'link',
        engage:  'message-circle',
        follow:  'plus',
        message: 'inbox',
    };

    let _mount = null;
    let _refreshInterval = null;
    let _wsHandler = null;

    function _apiFetch(path) {
        return fetch(API() + path, { headers: { 'X-Hermes-Token': TOKEN() } })
            .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
    }

    function _apiPost(path) {
        return fetch(API() + path, {
            method: 'POST',
            headers: { 'X-Hermes-Token': TOKEN() },
        }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
    }

    function _formatTime(eta) {
        if (!eta) return '--:--';
        try {
            var d = new Date(eta);
            return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
        } catch (_) { return '--:--'; }
    }

    function _actionIcon(action) {
        var name = ACTION_ICONS[action];
        if (name && typeof window.icon === 'function') return window.icon(name);
        return '•'; // bullet fallback
    }

    function _renderError() {
        if (!_mount) return;
        _mount.innerHTML = '';
        var el = document.createElement('div');
        el.className = 'op-queue-error';
        el.setAttribute('role', 'alert');
        el.textContent = 'Erro ao carregar fila — tentando novamente...';
        _mount.appendChild(el);
    }

    function _renderEmpty() {
        if (!_mount) return;
        _mount.innerHTML = '';
        var empty = document.createElement('div');
        empty.className = 'op-queue-empty';
        empty.textContent = 'Nenhuma acao programada para hoje';
        _mount.appendChild(empty);
    }

    function _renderQueue(queue) {
        if (!_mount) return;
        _mount.innerHTML = '';

        if (!queue || !queue.length) {
            _renderEmpty();
            return;
        }

        var list = document.createElement('ul');
        list.className = 'op-queue-list';
        list.setAttribute('role', 'list');

        queue.forEach(function (item) {
            var li = document.createElement('li');
            li.className = 'op-queue-item';

            var timeEl = document.createElement('div');
            timeEl.className = 'op-queue-time';
            timeEl.textContent = _formatTime(item.eta);
            timeEl.setAttribute('aria-label', 'Horario: ' + _formatTime(item.eta));

            var actionWrap = document.createElement('div');
            actionWrap.className = 'op-queue-action';

            var icon = document.createElement('span');
            icon.className = 'op-queue-action-icon';
            icon.innerHTML = _actionIcon(item.action);
            icon.setAttribute('aria-hidden', 'true');

            var text = document.createElement('span');
            text.className = 'op-queue-action-text';
            text.textContent = item.description || item.action || 'Acao';

            actionWrap.appendChild(icon);
            actionWrap.appendChild(text);

            var skipBtn = document.createElement('button');
            skipBtn.className = 'op-queue-skip btn-ghost';
            skipBtn.textContent = 'Pular';
            skipBtn.setAttribute('aria-label', 'Pular: ' + (item.description || item.action || 'acao'));
            skipBtn.dataset.itemId = item.id;
            skipBtn.addEventListener('click', function () { _skipItem(item.id); });

            li.appendChild(timeEl);
            li.appendChild(actionWrap);
            li.appendChild(skipBtn);
            list.appendChild(li);
        });

        _mount.appendChild(list);
    }

    function _refresh() {
        _apiFetch('/api/linkedin/cobaia/today-queue')
            .then(function (data) { _renderQueue(data.queue || []); })
            .catch(function () { _renderError(); });
    }

    function _skipItem(id) {
        if (id == null) return;
        _apiPost('/api/linkedin/cobaia/today-queue/' + id + '/skip')
            .then(function () {
                if (window.toast) toast('Acao pulada', 'success');
                _refresh();
            })
            .catch(function (e) {
                console.warn('[cobaia-today-queue] skip failed:', e);
                if (window.toast) toast('Erro ao pular acao', 'error');
            });
    }

    function mount(containerId) {
        _mount = document.getElementById(containerId);
        if (!_mount) {
            console.warn('[cobaia-today-queue] mount point not found:', containerId);
            return;
        }
        _refresh();
        if (_refreshInterval) clearInterval(_refreshInterval);
        _refreshInterval = setInterval(_refresh, 60000);

        _wsHandler = function (e) {
            var event = e.detail || {};
            if (event.event_type === 'cobaia.queue_updated') _refresh();
        };
        document.addEventListener('hermes-ws-event', _wsHandler);
    }

    function destroy() {
        if (_refreshInterval) { clearInterval(_refreshInterval); _refreshInterval = null; }
        if (_wsHandler) { document.removeEventListener('hermes-ws-event', _wsHandler); _wsHandler = null; }
        _mount = null;
    }

    window.CobaiaTodayQueue = { mount: mount, destroy: destroy, refresh: _refresh };
})();
