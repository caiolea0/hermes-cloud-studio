/* UX-RM-F2-B — Command Palette (Cmd+K / Ctrl+K)
 * UX-RM-F5-A — AI Mode (/ prefix or ?ask prefix → Brain SSE streaming)
 * UX-RM-F5-B — Citation pills + multimodal paste + Expand sidebar + confirm flow
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
            // AI mode state (UX-RM-F5-A)
            this._aiMode = false;
            this._aiBarEl = null;
            this._aiResponseEl = null;
            this._aiStopBtnEl = null;
            this._aiStreaming = false;
            this._aiAbortCtrl = null;
            this._aiFinalAnswer = null;
            this._lastToolPillEl = null;
            // F5-B additions
            this._pendingImage = null;       // Blob from clipboard paste
            this._pendingImageUrl = null;    // ObjectURL for preview
            this._lastPrompt = '';           // for sidebar "Expand →"
            this._citationsRowEl = null;     // citation pills container
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
            this._aiMode = false;
            this._updateAIModeUI(false);
            // F5-B: reset image state on open
            this._clearPendingImage();
            this._citationsRowEl = null;
            requestAnimationFrame(() => this._inputEl.focus());
            this._renderResults();
        }

        close() {
            this._stopAIStream();
            this._open = false;
            this._aiMode = false;
            this._inputEl.setAttribute('aria-expanded', 'false');
            this._overlay.setAttribute('hidden', '');
            this._overlay.setAttribute('aria-hidden', 'true');
            this._clearPendingImage();
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
                this._handleInputChange(input.value);
            });

            input.addEventListener('keydown', (e) => {
                if (e.key === 'ArrowDown') { e.preventDefault(); if (!this._aiMode) this._moveSelection(+1); }
                else if (e.key === 'ArrowUp') { e.preventDefault(); if (!this._aiMode) this._moveSelection(-1); }
                else if (e.key === 'Enter') {
                    e.preventDefault();
                    if (this._aiMode) {
                        if (this._aiFinalAnswer !== null && this._aiFinalAnswer !== undefined && this._aiFinalAnswer.trim()) {
                            // Copy final answer to clipboard (W6: guard empty answer)
                            navigator.clipboard.writeText(this._aiFinalAnswer).catch(() => {});
                            if (window.hermesToast) window.hermesToast.success('Resposta copiada');
                            this.close();
                        } else if (!this._aiStreaming) {
                            this._submitAIQuery();
                        }
                    } else {
                        this._executeSelected();
                    }
                } else if (e.key === 'Tab' && !e.shiftKey) {
                    if (this._aiMode) {
                        // W4: Tab cycles to Stop btn when streaming (keyboard accessible)
                        if (this._aiStreaming && this._aiStopBtnEl) {
                            e.preventDefault();
                            this._aiStopBtnEl.focus();
                        }
                        return;
                    }
                    e.preventDefault();
                    const items = this._resultsEl.querySelectorAll('.cmd-palette-item');
                    if (items.length) items[0].focus();
                } else if (e.key === 'Tab' && e.shiftKey) {
                    if (this._aiMode) return;
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

            // AI bar — shown when AI mode active (UX-RM-F5-A)
            const aiBar = document.createElement('div');
            aiBar.className = 'cmd-ai-bar';
            aiBar.setAttribute('hidden', '');
            aiBar.setAttribute('aria-hidden', 'true');

            const aiBadge = document.createElement('span');
            aiBadge.className = 'cmd-ai-badge';
            aiBadge.textContent = 'Brain AI';
            aiBadge.setAttribute('aria-label', 'Modo Brain AI ativo');

            const aiHint = document.createElement('span');
            aiHint.className = 'cmd-ai-hint';
            aiHint.textContent = 'Enter para enviar · Esc para cancelar';

            const aiStopBtn = document.createElement('button');
            aiStopBtn.className = 'cmd-ai-stop-btn';
            aiStopBtn.setAttribute('hidden', '');
            aiStopBtn.setAttribute('type', 'button');
            aiStopBtn.setAttribute('aria-label', 'Parar stream do Brain');
            aiStopBtn.textContent = '■ Parar';
            aiStopBtn.addEventListener('click', () => this._stopAIStream());

            aiBar.appendChild(aiBadge);
            aiBar.appendChild(aiHint);
            aiBar.appendChild(aiStopBtn);

            // AI response area — role=log, aria-live for screen readers (UX-RM-F5-A)
            const aiResponse = document.createElement('div');
            aiResponse.id = 'cmd-ai-response';
            aiResponse.className = 'cmd-ai-response';
            aiResponse.setAttribute('role', 'log');
            aiResponse.setAttribute('aria-live', 'polite');
            aiResponse.setAttribute('aria-label', 'Resposta do Brain');
            aiResponse.setAttribute('hidden', '');

            const results = document.createElement('div');
            results.id = 'cmd-palette-results';
            results.className = 'cmd-palette-results';
            results.setAttribute('role', 'listbox');
            results.setAttribute('aria-label', 'Comandos disponíveis');

            inputWrap.appendChild(searchIcon);
            inputWrap.appendChild(input);
            dialog.appendChild(inputWrap);
            dialog.appendChild(aiBar);
            dialog.appendChild(aiResponse);
            dialog.appendChild(status);
            dialog.appendChild(results);
            overlay.appendChild(dialog);
            document.body.appendChild(overlay);

            this._overlay = overlay;
            this._dialog = dialog;
            this._inputEl = input;
            this._resultsEl = results;
            this._statusEl = status;
            this._aiBarEl = aiBar;
            this._aiResponseEl = aiResponse;
            this._aiStopBtnEl = aiStopBtn;

            // F5-B: paste handler for images
            input.addEventListener('paste', async (e) => {
                const items = (e.clipboardData || {}).items || [];
                for (const item of items) {
                    if (item.type && item.type.startsWith('image/')) {
                        e.preventDefault();
                        const blob = item.getAsFile();
                        if (blob) await this._handleImagePaste(blob);
                        break;
                    }
                }
            });
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

        // ── AI mode (UX-RM-F5-A) ─────────────────────────────────────────────

        _handleInputChange(value) {
            const wasAiMode = this._aiMode;
            // "/ text" or "?ask text" → AI mode
            this._aiMode = value.startsWith('/') || value.startsWith('?ask ');

            if (this._aiMode !== wasAiMode) {
                this._updateAIModeUI(this._aiMode);
            }

            if (this._aiMode) {
                if (!this._aiStreaming) {
                    this._renderAIHint();
                }
            } else {
                this._filterText = value;
                this._selectedIndex = 0;
                this._renderResults();
            }
        }

        _updateAIModeUI(aiMode) {
            if (aiMode) {
                this._resultsEl.setAttribute('hidden', '');
                this._aiBarEl.removeAttribute('hidden');
                this._aiBarEl.setAttribute('aria-hidden', 'false');
                this._aiResponseEl.removeAttribute('hidden');
                this._inputEl.placeholder = 'Sua pergunta para o Brain... (Enter para enviar)';
                this._dialog.classList.add('cmd-palette-ai-mode');
            } else {
                this._resultsEl.removeAttribute('hidden');
                this._aiBarEl.setAttribute('hidden', '');
                this._aiBarEl.setAttribute('aria-hidden', 'true');
                if (!this._aiStreaming) {
                    this._aiResponseEl.setAttribute('hidden', '');
                    this._aiResponseEl.innerHTML = '';
                }
                this._inputEl.placeholder = 'Buscar comandos, navegar paginas...';
                this._dialog.classList.remove('cmd-palette-ai-mode');
                this._aiFinalAnswer = null;
            }
        }

        _renderAIHint() {
            const promptText = this._extractPrompt(this._inputEl.value);
            if (!promptText) {
                this._aiResponseEl.innerHTML =
                    '<div class="ai-hint-text" aria-label="Dica: escreva sua pergunta após a barra">Digite sua pergunta após <kbd>/</kbd> e pressione <kbd>Enter</kbd></div>';
            }
        }

        _extractPrompt(rawValue) {
            if (rawValue.startsWith('?ask ')) return rawValue.slice(5).trim();
            if (rawValue.startsWith('/')) return rawValue.slice(1).trim();
            return '';
        }

        async _submitAIQuery() {
            if (this._aiStreaming) return;
            const promptText = this._extractPrompt(this._inputEl.value);
            if (!promptText && !this._pendingImage) return;

            this._aiStreaming = true;
            this._aiFinalAnswer = null;
            this._lastToolPillEl = null;
            this._citationsRowEl = null;
            this._lastPrompt = promptText || 'Analyze this image';
            this._aiAbortCtrl = new AbortController();
            this._showStopBtn(true);
            this._aiResponseEl.innerHTML = '';
            this._aiResponseEl.removeAttribute('hidden');
            this._statusEl.textContent = 'Brain processando...';

            const thinkingEl = this._appendThinkingBlock();

            // F5-B: read image_b64 if pending image (client 5MB guard)
            let image_b64 = null;
            if (this._pendingImage) {
                try {
                    image_b64 = await this._blobToBase64(this._pendingImage);
                    if (image_b64 && image_b64.length > 5 * 1024 * 1024 * (4 / 3)) {
                        this._appendErrorBlock('Imagem muito grande (máx 5MB)');
                        this._aiStreaming = false;
                        this._showStopBtn(false);
                        if (thinkingEl.parentNode) thinkingEl.remove();
                        return;
                    }
                } catch (_) {
                    image_b64 = null;
                }
            }

            try {
                const token = (typeof localStorage !== 'undefined' && localStorage.getItem('hermes_token')) || '';
                const page = (typeof window !== 'undefined' && window.currentPage) || 'unknown';

                const bodyPayload = { prompt: promptText || 'Analyze this image', context: { page } };
                if (image_b64) bodyPayload.image_b64 = image_b64;

                const resp = await fetch('/api/brain/stream-decide', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Hermes-Token': token,
                    },
                    body: JSON.stringify(bodyPayload),
                    signal: this._aiAbortCtrl.signal,
                });

                if (!resp.ok) {
                    if (thinkingEl.parentNode) thinkingEl.remove();
                    const errText = resp.status === 429
                        ? 'Limite de queries atingido. Aguarde 60 segundos.'
                        : `Erro HTTP ${resp.status}`;
                    this._appendErrorBlock(errText);
                    return;
                }

                const reader = resp.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const parts = buffer.split('\n\n');
                    buffer = parts.pop() || '';
                    for (const part of parts) {
                        if (part.startsWith('data: ')) {
                            try {
                                const event = JSON.parse(part.slice(6));
                                this._appendAIEvent(event, thinkingEl);
                            } catch (_) { /* ignore malformed chunk */ }
                        }
                    }
                }
            } catch (err) {
                if (err.name !== 'AbortError') {
                    if (thinkingEl.parentNode) thinkingEl.remove();
                    this._appendErrorBlock(err.message || 'Erro de rede desconhecido');
                }
            } finally {
                this._aiStreaming = false;
                this._showStopBtn(false);
                if (thinkingEl.parentNode) thinkingEl.remove();
                // W5: stream closed without final event → show feedback
                if (!this._aiFinalAnswer && !this._aiResponseEl.querySelector('.ai-error-banner')) {
                    this._appendErrorBlock('Stream encerrado sem resposta');
                }
                this._statusEl.textContent = 'Resposta do Brain recebida';
            }
        }

        _stopAIStream() {
            if (this._aiAbortCtrl) {
                this._aiAbortCtrl.abort();
                this._aiAbortCtrl = null;
            }
            this._aiStreaming = false;
            this._showStopBtn(false);
        }

        _showStopBtn(visible) {
            if (visible) {
                this._aiStopBtnEl.removeAttribute('hidden');
            } else {
                this._aiStopBtnEl.setAttribute('hidden', '');
            }
        }

        _appendThinkingBlock() {
            const el = document.createElement('div');
            el.className = 'ai-thinking-indicator';
            el.setAttribute('aria-label', 'Brain processando');
            el.setAttribute('aria-busy', 'true');
            el.innerHTML =
                '<span class="ai-thinking-dots" aria-hidden="true"><span></span><span></span><span></span></span>' +
                '<span>Brain pensando...</span>';
            this._aiResponseEl.appendChild(el);
            return el;
        }

        _appendErrorBlock(msg) {
            const el = document.createElement('div');
            el.className = 'ai-error-banner';
            el.setAttribute('role', 'alert');
            el.textContent = `Erro: ${msg}`;
            this._aiResponseEl.appendChild(el);
        }

        _appendAIEvent(event, thinkingEl) {
            const type = event.type;

            if (type === 'thought') {
                if (thinkingEl && thinkingEl.parentNode) thinkingEl.remove();

                let thoughtEl = this._aiResponseEl.querySelector('.ai-thought-current');
                if (!thoughtEl) {
                    thoughtEl = document.createElement('div');
                    thoughtEl.className = 'ai-thought-block ai-thought-current';
                    thoughtEl.setAttribute('aria-label', 'Brain pensando');
                    this._aiResponseEl.appendChild(thoughtEl);
                }
                // Append chunk (safe: textContent)
                thoughtEl.textContent += (thoughtEl.textContent ? ' ' : '') + (event.chunk || '');

            } else if (type === 'tool_call') {
                const thoughtEl = this._aiResponseEl.querySelector('.ai-thought-current');
                if (thoughtEl) thoughtEl.classList.remove('ai-thought-current');

                const pill = document.createElement('div');
                pill.className = 'ai-tool-pill';
                pill.setAttribute('aria-label', `Ferramenta: ${this._esc(event.tool || '')}`);
                const toolName = this._esc(event.tool || '');
                pill.innerHTML =
                    '<span class="ai-tool-icon" aria-hidden="true">&#128295;</span>' +
                    `<span class="ai-tool-name">${toolName}</span>` +
                    '<span class="ai-tool-status" aria-live="polite">chamando...</span>';
                this._aiResponseEl.appendChild(pill);
                this._lastToolPillEl = pill;

            } else if (type === 'tool_result') {
                if (this._lastToolPillEl) {
                    const statusEl = this._lastToolPillEl.querySelector('.ai-tool-status');
                    if (statusEl) {
                        statusEl.textContent = event.ok ? '✓ ok' : '✗ erro';
                        this._lastToolPillEl.classList.add(event.ok ? 'ai-tool-ok' : 'ai-tool-err');
                    }
                }
                this._lastToolPillEl = null;

            } else if (type === 'citation') {
                // F5-B: citation pill — clickable source reference
                const row = this._getOrCreateCitationsRow();
                const pill = document.createElement('button');
                pill.className = 'ai-citation-pill';
                pill.type = 'button';
                pill.dataset.sourceType = event.source_type || '';
                pill.dataset.sourceId = event.source_id || '';
                pill.dataset.sourceUrl = event.source_url || '#';
                pill.setAttribute('aria-label', `Fonte: ${this._esc(event.source_type || '')}:${this._esc(event.source_id || '')}`);

                const iconSpan = document.createElement('span');
                iconSpan.setAttribute('aria-hidden', 'true');
                iconSpan.className = 'citation-icon';
                iconSpan.innerHTML = this._citationIcon(event.source_type || '');

                const labelSpan = document.createElement('span');
                labelSpan.className = 'citation-label';
                labelSpan.textContent = event.source_id || event.source_type || '';

                const confSpan = document.createElement('span');
                confSpan.className = 'citation-confidence';
                const confPct = Number.isFinite(event.confidence) ? Math.round(event.confidence * 100) : 80;
                confSpan.textContent = confPct + '%';

                pill.appendChild(iconSpan);
                pill.appendChild(labelSpan);
                pill.appendChild(confSpan);

                // Tooltip popover for snippet (ARIA role=tooltip on hover)
                if (event.snippet) {
                    pill.title = event.snippet;
                    const tooltip = document.createElement('div');
                    tooltip.className = 'citation-tooltip';
                    tooltip.setAttribute('role', 'tooltip');
                    tooltip.textContent = String(event.snippet).slice(0, 200);
                    pill.appendChild(tooltip);
                }

                pill.addEventListener('click', () => {
                    this.close();
                    const url = String(event.source_url || '#');
                    if (url.startsWith('#')) {
                        // Navigate to internal page via hash routing
                        const page = url.slice(1);
                        if (typeof window.navigate === 'function') {
                            window.navigate(page);
                        } else {
                            window.location.hash = page;
                        }
                    } else {
                        window.open(url, '_blank', 'noopener,noreferrer');
                    }
                });

                pill.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        pill.click();
                    }
                });

                row.appendChild(pill);

            } else if (type === 'final') {
                if (thinkingEl && thinkingEl.parentNode) thinkingEl.remove();

                const thoughtEl = this._aiResponseEl.querySelector('.ai-thought-current');
                if (thoughtEl) thoughtEl.classList.remove('ai-thought-current');

                const finalEl = document.createElement('div');
                finalEl.className = 'ai-final-answer';

                const conf = typeof event.confidence === 'number' ? Math.round(event.confidence * 100) : 0;
                const badgeClass = conf >= 70 ? 'ai-conf-high' : conf >= 40 ? 'ai-conf-med' : 'ai-conf-low';
                const answerText = event.answer ? this._esc(String(event.answer)) : '(sem resposta)';
                // BLOCKER-FIX: coerce to integer — prevents XSS if backend sends non-numeric value
                const iters = Number.isFinite(event.iterations) ? Math.round(event.iterations) : 0;
                const isMaxIter = event.status === 'max_iterations_reached';
                const rawAnswer = String(event.answer || '');

                finalEl.innerHTML =
                    `<div class="ai-final-text">${answerText}</div>` +
                    '<div class="ai-final-meta">' +
                    `<span class="ai-conf-badge ${badgeClass}" aria-label="Confiança ${conf}%">${conf}%</span>` +
                    `<span class="ai-iter-info" aria-hidden="true">${iters} iter</span>` +
                    (isMaxIter ? '<span class="ai-warn-badge" aria-label="Máximo de iterações atingido">max iter</span>' : '') +
                    '</div>';
                finalEl.setAttribute('tabindex', '-1');

                // F5-B: "Expandir →" button when response > 1000 chars
                if (rawAnswer.length > 1000) {
                    const expandBtn = document.createElement('button');
                    expandBtn.className = 'ai-expand-btn';
                    expandBtn.type = 'button';
                    expandBtn.textContent = 'Expandir →';
                    expandBtn.setAttribute('aria-label', 'Expandir resposta no painel lateral');
                    expandBtn.addEventListener('click', async () => {
                        this.close();
                        // UX-RM-F7-A: lazy-load brain_sidebar if not yet loaded
                        if (!window.HermesBrainSidebar && window.loadComponent) {
                            try { await window.loadComponent('brain_sidebar'); }
                            catch (e) {
                                if (window.hermesToast) window.hermesToast.error('Falha ao carregar painel lateral');
                                return;
                            }
                        }
                        if (window.HermesBrainSidebar) {
                            window.HermesBrainSidebar.show({
                                initialPrompt: this._lastPrompt || '',
                                initialResponse: rawAnswer,
                            });
                        }
                    });
                    finalEl.appendChild(expandBtn);
                }

                const copyHint = document.createElement('div');
                copyHint.className = 'ai-copy-hint';
                copyHint.setAttribute('aria-label', 'Pressione Enter para copiar a resposta');
                copyHint.textContent = 'Enter para copiar resposta';

                this._aiResponseEl.appendChild(finalEl);
                this._aiResponseEl.appendChild(copyHint);

                this._aiFinalAnswer = rawAnswer;
                finalEl.focus();

                // F5-B: requires_confirm — close palette + open BrainConfirmDrawer
                if (event.requires_confirm && window.BrainConfirmDrawer) {
                    setTimeout(() => {
                        this.close();
                        if (typeof window.BrainConfirmDrawer.show === 'function') {
                            window.BrainConfirmDrawer.show({
                                intent: event.intent || '',
                                preview: rawAnswer,
                                confidence: typeof event.confidence === 'number' ? event.confidence : 0,
                                source: 'palette_ai_mode',
                            });
                        } else {
                            window.BrainConfirmDrawer.open();
                        }
                    }, 600);
                }

            } else if (type === 'error') {
                if (thinkingEl && thinkingEl.parentNode) thinkingEl.remove();
                this._appendErrorBlock(event.message || 'Erro desconhecido');
            }
        }

        // ── Command mode (original methods) ──────────────────────────────────

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

        // ── F5-B helpers ─────────────────────────────────────────────────────

        async _handleImagePaste(blob) {
            // Client-side 5MB guard
            if (blob.size > 5 * 1024 * 1024) {
                if (window.hermesToast) window.hermesToast.error('Imagem muito grande (máx 5MB)');
                return;
            }
            this._clearPendingImage();
            this._pendingImage = blob;
            this._pendingImageUrl = URL.createObjectURL(blob);
            this._showImagePreview(this._pendingImageUrl);

            // Auto-enter AI mode with "Analyze this image" prompt
            this._aiMode = true;
            this._inputEl.value = '/ Analyze this image';
            this._updateAIModeUI(true);
            this._renderAIHint();
            this._inputEl.focus();
        }

        _showImagePreview(objectUrl) {
            // Remove existing preview
            const existing = this._dialog.querySelector('.ai-image-pill');
            if (existing) existing.remove();

            const pill = document.createElement('div');
            pill.className = 'ai-image-pill';
            pill.setAttribute('role', 'img');
            pill.setAttribute('aria-label', 'Imagem colada — pronta para análise');

            const img = document.createElement('img');
            img.src = objectUrl;
            img.alt = 'Imagem para análise pelo Brain';
            img.className = 'ai-image-preview';

            const removeBtn = document.createElement('button');
            removeBtn.className = 'ai-image-remove';
            removeBtn.type = 'button';
            removeBtn.setAttribute('aria-label', 'Remover imagem');
            removeBtn.textContent = '×';
            removeBtn.addEventListener('click', () => {
                this._clearPendingImage();
                pill.remove();
                this._aiMode = false;
                this._inputEl.value = '';
                this._updateAIModeUI(false);
                this._renderResults();
                this._inputEl.focus();
            });

            pill.appendChild(img);
            pill.appendChild(removeBtn);

            // Insert before the input wrap
            const inputWrap = this._dialog.querySelector('.cmd-palette-input-wrap');
            if (inputWrap) {
                this._dialog.insertBefore(pill, inputWrap);
            } else {
                this._dialog.prepend(pill);
            }
        }

        _clearPendingImage() {
            if (this._pendingImageUrl) {
                try { URL.revokeObjectURL(this._pendingImageUrl); } catch (_) {}
                this._pendingImageUrl = null;
            }
            this._pendingImage = null;
        }

        _blobToBase64(blob) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => {
                    const result = reader.result;
                    if (typeof result === 'string') {
                        // Strip data URL prefix (data:image/png;base64,...)
                        const idx = result.indexOf(',');
                        resolve(idx >= 0 ? result.slice(idx + 1) : result);
                    } else {
                        reject(new Error('FileReader result not string'));
                    }
                };
                reader.onerror = () => reject(reader.error);
                reader.readAsDataURL(blob);
            });
        }

        _getOrCreateCitationsRow() {
            if (this._citationsRowEl && this._citationsRowEl.parentNode) {
                return this._citationsRowEl;
            }
            const row = document.createElement('div');
            row.className = 'ai-citations-row';
            row.setAttribute('aria-label', 'Fontes citadas pelo Brain');
            row.setAttribute('role', 'group');
            this._aiResponseEl.appendChild(row);
            this._citationsRowEl = row;
            return row;
        }

        _citationIcon(sourceType) {
            const icons = {
                skill:       'code',
                memory:      'layers',
                log:         'clipboard',
                tool_result: 'wrench',
                doc:         'file-text',
            };
            const name = icons[sourceType] || 'link';
            return typeof window.icon === 'function' ? window.icon(name, {size: 14}) : name;
        }
    }

    window.HermesCommandPalette = new HermesCommandPalette();
})();
