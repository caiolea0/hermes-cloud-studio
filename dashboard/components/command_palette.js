/* UX-RM-F2-B — Command Palette (Cmd+K / Ctrl+K)
 * API global: window.HermesCommandPalette.{register, open, close}
 * WCAG 2.1 AA: role=dialog, aria-modal, focus trap, live region, keyboard nav.
 * Vanilla JS — no external deps.
 */
(function () {
    'use strict';

    class HermesCommandPalette {
        constructor() {
            this._commands = [];
            this._open = false;
            this._filterText = '';
            this._selectedIndex = 0;
            this._prevFocused = null;
            this._overlay = null;
            this._dialog = null;
            this._inputEl = null;
            this._resultsEl = null;
            this._statusEl = null;
            this._buildDOM();
            this._bindGlobalShortcut();
        }

        register(command) {
            // command: {id, label, group, shortcut, action}
            this._commands.push(command);
        }

        open() {
            this._open = true;
            this._prevFocused = document.activeElement;
            this._filterText = '';
            this._selectedIndex = 0;
            this._inputEl.value = '';
            this._inputEl.setAttribute('aria-expanded', 'true');
            this._overlay.removeAttribute('hidden');
            this._overlay.setAttribute('aria-hidden', 'false');
            requestAnimationFrame(() => this._inputEl.focus());
            this._renderResults();
        }

        close() {
            this._open = false;
            this._inputEl.setAttribute('aria-expanded', 'false');
            this._overlay.setAttribute('hidden', '');
            this._overlay.setAttribute('aria-hidden', 'true');
            if (this._prevFocused && typeof this._prevFocused.focus === 'function') {
                this._prevFocused.focus();
            }
        }

        _buildDOM() {
            const overlay = document.createElement('div');
            overlay.id = 'hermes-cmd-palette-overlay';
            overlay.className = 'cmd-palette-overlay';
            overlay.setAttribute('hidden', '');
            overlay.setAttribute('aria-hidden', 'true');
            overlay.setAttribute('role', 'presentation');
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) this.close();
            });

            const dialog = document.createElement('div');
            dialog.id = 'hermes-cmd-palette';
            dialog.className = 'cmd-palette-dialog';
            dialog.setAttribute('role', 'dialog');
            dialog.setAttribute('aria-modal', 'true');
            dialog.setAttribute('aria-label', 'Command Palette');

            const inputWrap = document.createElement('div');
            inputWrap.className = 'cmd-palette-input-wrap';

            const searchIcon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            searchIcon.setAttribute('width', '16');
            searchIcon.setAttribute('height', '16');
            searchIcon.setAttribute('fill', 'none');
            searchIcon.setAttribute('stroke', 'currentColor');
            searchIcon.setAttribute('stroke-width', '2');
            searchIcon.setAttribute('viewBox', '0 0 24 24');
            searchIcon.setAttribute('aria-hidden', 'true');
            searchIcon.classList.add('cmd-palette-search-icon');
            searchIcon.innerHTML = '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>';

            const input = document.createElement('input');
            input.type = 'search';
            input.className = 'cmd-palette-input';
            input.placeholder = 'Buscar comandos, navegar paginas...';
            input.setAttribute('aria-label', 'Buscar comandos');
            input.setAttribute('role', 'combobox');
            input.setAttribute('aria-autocomplete', 'list');
            input.setAttribute('aria-expanded', 'false');
            input.setAttribute('aria-controls', 'cmd-palette-results');
            input.setAttribute('aria-activedescendant', '');
            input.autocomplete = 'off';
            input.spellcheck = false;

            input.addEventListener('input', () => {
                this._filterText = input.value;
                this._selectedIndex = 0;
                this._renderResults();
            });

            input.addEventListener('keydown', (e) => {
                if (e.key === 'ArrowDown') { e.preventDefault(); this._moveSelection(+1); }
                else if (e.key === 'ArrowUp') { e.preventDefault(); this._moveSelection(-1); }
                else if (e.key === 'Enter') { e.preventDefault(); this._executeSelected(); }
                else if (e.key === 'Tab' && !e.shiftKey) {
                    e.preventDefault();
                    const items = this._resultsEl.querySelectorAll('.cmd-palette-item');
                    if (items.length) items[0].focus();
                } else if (e.key === 'Tab' && e.shiftKey) {
                    e.preventDefault();
                    const items = this._resultsEl.querySelectorAll('.cmd-palette-item');
                    if (items.length) items[items.length - 1].focus();
                }
            });

            const status = document.createElement('div');
            status.id = 'cmd-palette-status';
            status.className = 'sr-only';
            status.setAttribute('aria-live', 'polite');
            status.setAttribute('aria-atomic', 'true');

            const results = document.createElement('div');
            results.id = 'cmd-palette-results';
            results.className = 'cmd-palette-results';
            results.setAttribute('role', 'listbox');
            results.setAttribute('aria-label', 'Comandos disponíveis');

            inputWrap.appendChild(searchIcon);
            inputWrap.appendChild(input);
            dialog.appendChild(inputWrap);
            dialog.appendChild(status);
            dialog.appendChild(results);
            overlay.appendChild(dialog);
            document.body.appendChild(overlay);

            this._overlay = overlay;
            this._dialog = dialog;
            this._inputEl = input;
            this._resultsEl = results;
            this._statusEl = status;
        }

        _bindGlobalShortcut() {
            // Cmd+K (Mac) / Ctrl+K (Windows/Linux) — capture phase to fire first
            document.addEventListener('keydown', (e) => {
                const isMac = navigator.platform ? navigator.platform.toUpperCase().includes('MAC') : false;
                const trigger = isMac ? e.metaKey : e.ctrlKey;
                if (trigger && e.key === 'k') {
                    e.preventDefault();
                    this._open ? this.close() : this.open();
                    return;
                }
                // Escape when open — capture to beat other handlers
                if (this._open && e.key === 'Escape') {
                    e.stopImmediatePropagation();
                    this.close();
                }
            }, true);
        }

        _filterCommands() {
            const q = this._filterText.toLowerCase().trim();
            if (!q) return this._commands;
            return this._commands.filter(c =>
                c.label.toLowerCase().includes(q) ||
                (c.group || '').toLowerCase().includes(q) ||
                (c.id || '').toLowerCase().includes(q)
            );
        }

        _esc(str) {
            if (!str) return '';
            const d = document.createElement('div');
            d.textContent = str;
            return d.innerHTML;
        }

        _renderResults() {
            const filtered = this._filterCommands();

            if (!filtered.length) {
                const msg = this._filterText
                    ? `Nenhum resultado para "${this._esc(this._filterText)}"`
                    : 'Digite para buscar comandos...';
                this._resultsEl.innerHTML = `<div class="cmd-palette-empty">${msg}</div>`;
                this._statusEl.textContent = this._filterText ? 'Nenhum resultado' : '';
                this._selectedIndex = 0;
                return;
            }

            // Group by group name, preserving insertion order
            const groups = {};
            const groupOrder = [];
            filtered.forEach(c => {
                const g = c.group || 'Acoes';
                if (!groups[g]) { groups[g] = []; groupOrder.push(g); }
                groups[g].push(c);
            });

            let globalIdx = 0;
            let html = '';
            groupOrder.forEach(groupName => {
                html += `<div class="cmd-palette-group-label" role="presentation">${this._esc(groupName)}</div>`;
                groups[groupName].forEach(cmd => {
                    const isSelected = globalIdx === this._selectedIndex;
                    const shortcutHtml = cmd.shortcut
                        ? `<span class="cmd-palette-shortcut" aria-hidden="true">${cmd.shortcut.split(' ').map(k => `<kbd>${this._esc(k)}</kbd>`).join(' ')}</span>`
                        : '';
                    html += `<button class="cmd-palette-item${isSelected ? ' selected' : ''}"
                        role="option"
                        aria-selected="${isSelected}"
                        id="cmd-item-${globalIdx}"
                        data-cmd-idx="${globalIdx}"
                        tabindex="${isSelected ? '0' : '-1'}">
                        <span class="cmd-palette-label">${this._esc(cmd.label)}</span>
                        ${shortcutHtml}
                    </button>`;
                    globalIdx++;
                });
            });

            this._resultsEl.innerHTML = html;
            this._statusEl.textContent = `${filtered.length} comando${filtered.length !== 1 ? 's' : ''} disponivel${filtered.length !== 1 ? 's' : ''}`;

            // Update aria-activedescendant
            const activeId = `cmd-item-${this._selectedIndex}`;
            this._inputEl.setAttribute('aria-activedescendant', activeId);

            // Bind interactions
            this._resultsEl.querySelectorAll('.cmd-palette-item').forEach(btn => {
                btn.addEventListener('click', () => {
                    this._selectedIndex = parseInt(btn.dataset.cmdIdx, 10);
                    this._executeSelected();
                });
                btn.addEventListener('keydown', (e) => {
                    if (e.key === 'ArrowDown') { e.preventDefault(); this._moveSelection(+1); }
                    else if (e.key === 'ArrowUp') { e.preventDefault(); this._moveSelection(-1); }
                    else if (e.key === 'Enter') { e.preventDefault(); this._executeSelected(); }
                    else if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); this.close(); }
                    else if (e.key === 'Tab' && !e.shiftKey) {
                        e.preventDefault();
                        const idx = parseInt(btn.dataset.cmdIdx, 10);
                        if (idx >= filtered.length - 1) this._inputEl.focus();
                        else this._moveSelection(+1);
                    } else if (e.key === 'Tab' && e.shiftKey) {
                        e.preventDefault();
                        const idx = parseInt(btn.dataset.cmdIdx, 10);
                        if (idx === 0) this._inputEl.focus();
                        else this._moveSelection(-1);
                    }
                });
            });

            // Scroll selected into view
            this._scrollSelectedIntoView();
        }

        _scrollSelectedIntoView() {
            const selected = this._resultsEl.querySelector('.cmd-palette-item.selected');
            if (selected) selected.scrollIntoView({ block: 'nearest' });
        }

        _moveSelection(delta) {
            const filtered = this._filterCommands();
            if (!filtered.length) return;
            this._selectedIndex = Math.max(0, Math.min(filtered.length - 1, this._selectedIndex + delta));
            this._renderResults();
            const selected = this._resultsEl.querySelector('.cmd-palette-item.selected');
            if (selected) selected.focus();
        }

        _executeSelected() {
            const filtered = this._filterCommands();
            if (!filtered.length) return;
            const cmd = filtered[this._selectedIndex];
            if (!cmd) return;
            this.close();
            try { cmd.action(); } catch (e) {
                console.error('[HermesCommandPalette] action error:', e);
            }
        }
    }

    window.HermesCommandPalette = new HermesCommandPalette();
})();
