/**
 * F.7 C3 — Cobaia Activity Feed (IIFE component).
 *
 * Virtualized ring-buffer feed (cap 200 rows, FIFO) showing cobaia-related
 * activities. Color-coded by category. Auto-scroll to bottom; pause on hover.
 *
 * REUSE pattern: live_log_tail.js F.2.5c ring-buffer + auto-scroll.
 * XSS: textContent only — no innerHTML with activity data.
 * WCAG: feed region role, live region aria-live="polite" on insert.
 */
(function CobaiaActivityFeed() {
    'use strict';

    const MAX_ROWS = 200;
    const DOT_CLASS = {
        engagement: 'cobaia-feed-dot--engagement',
        connect:    'cobaia-feed-dot--connect',
        reply:      'cobaia-feed-dot--reply',
        error:      'cobaia-feed-dot--error',
        pause:      'cobaia-feed-dot--pause',
    };

    let _mount = null;
    let _list = null;
    let _countEl = null;
    let _searchEl = null;
    let _buffer = [];       // ring buffer full items
    let _filter = '';
    let _userScrolled = false;  // true when user scrolled away from bottom

    function _dotClass(category) {
        return DOT_CLASS[category] || 'cobaia-feed-dot--default';
    }

    function _formatTs(ts) {
        try {
            const d = new Date(ts);
            return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        } catch (_) { return ''; }
    }

    function _matchesFilter(item) {
        if (!_filter) return true;
        const q = _filter.toLowerCase();
        return (item.message || '').toLowerCase().includes(q) ||
               (item.category || '').toLowerCase().includes(q);
    }

    function _buildRow(item) {
        const row = document.createElement('div');
        row.className = 'cobaia-feed-item';

        const dot = document.createElement('span');
        dot.className = `cobaia-feed-dot ${_dotClass(item.category)}`;
        dot.setAttribute('aria-hidden', 'true');

        const msg = document.createElement('span');
        msg.className = 'cobaia-feed-msg';
        msg.textContent = item.message || '';

        const ts = document.createElement('span');
        ts.className = 'cobaia-feed-ts';
        ts.textContent = _formatTs(item.timestamp);
        ts.setAttribute('aria-label', item.timestamp || '');

        row.appendChild(dot);
        row.appendChild(msg);
        row.appendChild(ts);
        return row;
    }

    function _rerenderFiltered() {
        if (!_list) return;
        const items = _buffer.filter(_matchesFilter);
        _list.innerHTML = '';
        if (items.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'cobaia-feed-empty';
            empty.textContent = _filter ? 'Nenhum resultado para "' + _filter + '"' : 'Sem atividade ainda';
            _list.appendChild(empty);
        } else {
            items.forEach(item => _list.appendChild(_buildRow(item)));
        }
        if (_countEl) _countEl.textContent = `${items.length}/${_buffer.length}`;
        _maybeScrollBottom();
    }

    function _maybeScrollBottom() {
        if (!_list || _userScrolled) return;
        _list.scrollTop = _list.scrollHeight;
    }

    function addEvent(item) {
        // Ring buffer: FIFO evict
        _buffer.push(item);
        if (_buffer.length > MAX_ROWS) _buffer.shift();

        if (!_matchesFilter(item)) {
            if (_countEl) _countEl.textContent = `${_buffer.filter(_matchesFilter).length}/${_buffer.length}`;
            return;
        }
        if (!_list) return;

        // Remove empty placeholder if present
        const empty = _list.querySelector('.cobaia-feed-empty');
        if (empty) empty.remove();

        // Evict from DOM if oversized (beyond MAX_ROWS visible)
        const visible = _list.querySelectorAll('.cobaia-feed-item');
        if (visible.length >= MAX_ROWS) visible[0].remove();

        const row = _buildRow(item);
        _list.appendChild(row);
        if (_countEl) _countEl.textContent = `${_list.querySelectorAll('.cobaia-feed-item').length}/${_buffer.length}`;
        _maybeScrollBottom();
    }

    function clear() {
        _buffer = [];
        _rerenderFiltered();
    }

    function mount(containerId) {
        _mount = document.getElementById(containerId);
        if (!_mount) {
            console.warn('[cobaia-feed] mount point not found:', containerId);
            return;
        }
        _mount.innerHTML = `
            <div class="cobaia-feed-controls">
                <input type="search" class="cobaia-feed-search" placeholder="Filtrar atividade..."
                       aria-label="Filtrar atividade cobaia" autocomplete="off">
                <span class="cobaia-feed-count" aria-live="polite">0/0</span>
            </div>
            <div class="cobaia-feed-list" role="log" aria-label="Atividade cobaia em tempo real" aria-live="polite"></div>`;

        _searchEl = _mount.querySelector('.cobaia-feed-search');
        _list = _mount.querySelector('.cobaia-feed-list');
        _countEl = _mount.querySelector('.cobaia-feed-count');

        _searchEl.addEventListener('input', () => {
            _filter = _searchEl.value.trim();
            _rerenderFiltered();
        });

        // Pause auto-scroll when user scrolls up
        _list.addEventListener('scroll', () => {
            const atBottom = _list.scrollHeight - _list.scrollTop - _list.clientHeight < 10;
            _userScrolled = !atBottom;
        });

        // Pause auto-scroll on hover
        _list.addEventListener('mouseenter', () => { _userScrolled = true; });
        _list.addEventListener('mouseleave', () => {
            const atBottom = _list.scrollHeight - _list.scrollTop - _list.clientHeight < 10;
            if (atBottom) _userScrolled = false;
        });

        _rerenderFiltered();
    }

    window.CobaiaActivityFeed = { mount, addEvent, clear };
})();
