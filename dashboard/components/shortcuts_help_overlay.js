/* UX-RM-F2-B — Shortcuts Help Overlay
 * API global: window.HermesShortcutsHelp.{show, hide}
 * Triggered by '?' key (keyboard_shortcuts.js) or command palette action.
 * Depends on: window.HermesKeyboardShortcuts (optional — graceful if absent)
 */
(function () {
    'use strict';

    const _overlay = document.createElement('div');
    _overlay.id = 'hermes-shortcuts-overlay';
    _overlay.className = 'shortcuts-overlay';
    _overlay.setAttribute('hidden', '');
    _overlay.setAttribute('aria-hidden', 'true');
    _overlay.setAttribute('role', 'presentation');

    const _dialog = document.createElement('div');
    _dialog.className = 'shortcuts-dialog';
    _dialog.setAttribute('role', 'dialog');
    _dialog.setAttribute('aria-modal', 'true');
    _dialog.setAttribute('aria-labelledby', 'shortcuts-dialog-title');

    _overlay.appendChild(_dialog);
    document.body.appendChild(_overlay);

    let _prevFocused = null;
    let _keyHandler = null;
    let _clickHandler = null;

    function _esc(str) {
        if (!str) return '';
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    function show() {
        _prevFocused = document.activeElement;

        const shortcuts = window.HermesKeyboardShortcuts ? window.HermesKeyboardShortcuts.listAll() : [];

        // Group by category
        const groups = {};
        shortcuts.forEach(s => {
            const cat = s.category || 'Navegacao';
            if (!groups[cat]) groups[cat] = [];
            groups[cat].push(s);
        });

        const groupsHtml = Object.entries(groups).map(([cat, items]) => `
            <div class="shortcuts-group">
                <div class="shortcuts-group-title">${_esc(cat)}</div>
                <table class="shortcuts-table" role="presentation">
                    <tbody>
                        ${items.map(s => `
                            <tr>
                                <td class="shortcuts-label">${_esc(s.label)}</td>
                                <td class="shortcuts-kbd">
                                    ${s.combo.split(' ').map((k, i, arr) =>
                                        `<kbd>${_esc(k)}</kbd>${i < arr.length - 1 ? '<span class="shortcuts-then">then</span>' : ''}`
                                    ).join('')}
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `).join('');

        _dialog.innerHTML = `
            <div class="shortcuts-header">
                <h2 id="shortcuts-dialog-title" class="shortcuts-title">Atalhos de Teclado</h2>
                <button class="shortcuts-close" aria-label="Fechar atalhos" id="shortcuts-close-btn">
                    <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M18 6 6 18M6 6l12 12"/>
                    </svg>
                </button>
            </div>
            <div class="shortcuts-body">
                <div class="shortcuts-also">
                    <div class="shortcuts-section-title">Globais</div>
                    <table class="shortcuts-table" role="presentation">
                        <tbody>
                            <tr><td class="shortcuts-label">Command Palette</td><td class="shortcuts-kbd"><kbd>Ctrl</kbd><kbd>K</kbd></td></tr>
                            <tr><td class="shortcuts-label">Este painel</td><td class="shortcuts-kbd"><kbd>?</kbd></td></tr>
                            <tr><td class="shortcuts-label">Fechar modal</td><td class="shortcuts-kbd"><kbd>Esc</kbd></td></tr>
                        </tbody>
                    </table>
                </div>
                ${groupsHtml || '<p class="shortcuts-empty">Nenhum atalho G-prefix registrado.</p>'}
            </div>
        `;

        _overlay.removeAttribute('hidden');
        _overlay.setAttribute('aria-hidden', 'false');

        const closeBtn = document.getElementById('shortcuts-close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', hide);
            // W3 fix: single focusable element — Tab/Shift+Tab wrap to itself (WCAG 2.1 SC 2.1.2)
            closeBtn.addEventListener('keydown', (e) => {
                if (e.key === 'Tab') { e.preventDefault(); closeBtn.focus(); }
            });
            requestAnimationFrame(() => closeBtn.focus());
        }

        _keyHandler = (e) => { if (e.key === 'Escape') { e.stopImmediatePropagation(); hide(); } };
        document.addEventListener('keydown', _keyHandler, true);

        _clickHandler = (e) => { if (e.target === _overlay) hide(); };
        _overlay.addEventListener('click', _clickHandler);
    }

    function hide() {
        _overlay.setAttribute('hidden', '');
        _overlay.setAttribute('aria-hidden', 'true');
        if (_keyHandler) document.removeEventListener('keydown', _keyHandler, true);
        if (_clickHandler) _overlay.removeEventListener('click', _clickHandler);
        _keyHandler = null;
        _clickHandler = null;
        if (_prevFocused && typeof _prevFocused.focus === 'function') _prevFocused.focus();
    }

    window.HermesShortcutsHelp = { show, hide };
})();
