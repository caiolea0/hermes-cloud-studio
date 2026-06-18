/* UX-RM-F2-B — Keyboard Shortcuts (G-prefix + ? help)
 * API global: window.HermesKeyboardShortcuts.{register, listAll}
 * Pattern: g + key = navigate; ? = shortcuts help overlay
 */
(function () {
    'use strict';

    class HermesKeyboardShortcuts {
        constructor() {
            this._gPressed = false;
            this._gTimeout = null;
            this._shortcuts = new Map(); // combo -> {action, label, category}
            this._bindListener();
        }

        register(combo, action, label, category) {
            this._shortcuts.set(combo, { action, label, category: category || 'Navegacao' });
        }

        listAll() {
            return Array.from(this._shortcuts.entries()).map(([combo, data]) => ({
                combo, action: data.action, label: data.label, category: data.category
            }));
        }

        _bindListener() {
            document.addEventListener('keydown', (e) => {
                const tag = document.activeElement ? document.activeElement.tagName : '';
                const isEditable = ['INPUT', 'TEXTAREA', 'SELECT'].includes(tag) ||
                    !!(document.activeElement && document.activeElement.isContentEditable);

                // '?' key — show shortcuts help (skip when typing)
                if (!isEditable && e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                    e.preventDefault();
                    if (window.HermesShortcutsHelp) window.HermesShortcutsHelp.show();
                    return;
                }

                // g-prefix shortcuts — skip when typing or using modifier keys
                if (!isEditable && e.key === 'g' && !e.metaKey && !e.ctrlKey && !e.altKey) {
                    if (!this._gPressed) {
                        this._gPressed = true;
                        this._gTimeout = setTimeout(() => { this._gPressed = false; }, 1500);
                    }
                    return;
                }

                if (this._gPressed && !isEditable && !e.metaKey && !e.ctrlKey && !e.altKey) {
                    const combo = 'g ' + e.key;
                    clearTimeout(this._gTimeout);
                    this._gPressed = false;
                    const s = this._shortcuts.get(combo);
                    if (s) {
                        e.preventDefault();
                        try { s.action(); } catch (err) {
                            console.error('[HermesKeyboardShortcuts] action error:', err);
                        }
                    }
                }
            });
        }
    }

    window.HermesKeyboardShortcuts = new HermesKeyboardShortcuts();
})();
