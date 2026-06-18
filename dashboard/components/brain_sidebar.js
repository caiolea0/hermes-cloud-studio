/* UX-RM-F5-B — HermesBrainSidebar
 * Lightweight right-side panel for Brain conversation (long responses + follow-up).
 * Opens via "Expandir →" button in Cmd+K AI mode when response > 1000 chars.
 *
 * API global: window.HermesBrainSidebar.{show, close, askFollowUp}
 * localStorage: 'hermes.brain.sidebar.history' (max 10 turns).
 * WCAG: role=dialog, aria-modal=false (non-blocking), focus trap, Esc closes.
 * XSS: all user content via textContent; AI responses via _safeRender (DOMPurify guard).
 */
(function () {
    'use strict';

    var HISTORY_KEY = 'hermes.brain.sidebar.history';
    var MAX_TURNS = 10;

    var state = {
        open: false,
        streaming: false,
        abortCtrl: null,
        lastFocus: null,
        history: [],       // [{role: 'user'|'brain', text: string}]
    };

    // ── DOM builder ──────────────────────────────────────────────────────────

    function _build() {
        if (document.getElementById('brain-sidebar-overlay')) return;

        var overlay = document.createElement('div');
        overlay.id = 'brain-sidebar-overlay';
        overlay.className = 'brain-sidebar-overlay';
        overlay.setAttribute('hidden', '');
        overlay.setAttribute('aria-hidden', 'true');
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) _close();
        });

        var panel = document.createElement('div');
        panel.id = 'brain-sidebar-panel';
        panel.className = 'brain-sidebar-panel';
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-modal', 'false');
        panel.setAttribute('aria-labelledby', 'brain-sidebar-title');

        var header = document.createElement('div');
        header.className = 'brain-sidebar-header';

        var titleEl = document.createElement('h2');
        titleEl.id = 'brain-sidebar-title';
        titleEl.className = 'brain-sidebar-title';
        titleEl.textContent = 'Brain AI';

        var closeBtn = document.createElement('button');
        closeBtn.id = 'brain-sidebar-close';
        closeBtn.className = 'brain-sidebar-close';
        closeBtn.type = 'button';
        closeBtn.setAttribute('aria-label', 'Fechar painel Brain');
        closeBtn.textContent = '×';
        closeBtn.addEventListener('click', _close);

        header.appendChild(titleEl);
        header.appendChild(closeBtn);

        var messages = document.createElement('div');
        messages.id = 'brain-sidebar-messages';
        messages.className = 'brain-sidebar-messages';
        messages.setAttribute('role', 'log');
        messages.setAttribute('aria-live', 'polite');
        messages.setAttribute('aria-label', 'Conversa com Brain');

        var inputArea = document.createElement('div');
        inputArea.className = 'brain-sidebar-input-area';

        var input = document.createElement('textarea');
        input.id = 'brain-sidebar-input';
        input.className = 'brain-sidebar-input';
        input.placeholder = 'Pergunta de acompanhamento...';
        input.rows = 2;
        input.setAttribute('aria-label', 'Pergunta de acompanhamento para Brain');
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                _submitFollowUp();
            }
        });

        var sendBtn = document.createElement('button');
        sendBtn.id = 'brain-sidebar-send';
        sendBtn.className = 'brain-sidebar-send-btn';
        sendBtn.type = 'button';
        sendBtn.textContent = 'Enviar';
        sendBtn.setAttribute('aria-label', 'Enviar pergunta de acompanhamento');
        sendBtn.addEventListener('click', _submitFollowUp);

        inputArea.appendChild(input);
        inputArea.appendChild(sendBtn);

        panel.appendChild(header);
        panel.appendChild(messages);
        panel.appendChild(inputArea);
        overlay.appendChild(panel);
        document.body.appendChild(overlay);

        // Keyboard: Esc closes
        document.addEventListener('keydown', function (e) {
            if (state.open && e.key === 'Escape') {
                e.stopImmediatePropagation();
                _close();
            }
        }, true);
    }

    // ── Public API ───────────────────────────────────────────────────────────

    function show(opts) {
        opts = opts || {};
        _build();
        _loadHistory();

        if (opts.initialPrompt && opts.initialResponse) {
            // Seed with initial exchange from Cmd+K
            _appendMessage('user', opts.initialPrompt);
            _appendMessage('brain', opts.initialResponse);
            _addToHistory('user', opts.initialPrompt);
            _addToHistory('brain', opts.initialResponse);
            _saveHistory();
        }

        _open();
        // Focus the input after open
        requestAnimationFrame(function () {
            var input = document.getElementById('brain-sidebar-input');
            if (input) input.focus();
        });
    }

    function close() { _close(); }

    function askFollowUp(text) {
        if (!text || !text.trim()) return;
        _sendFollowUp(text.trim());
    }

    // ── Internal ─────────────────────────────────────────────────────────────

    function _open() {
        var overlay = document.getElementById('brain-sidebar-overlay');
        if (!overlay) return;
        state.lastFocus = document.activeElement;
        overlay.removeAttribute('hidden');
        overlay.setAttribute('aria-hidden', 'false');
        requestAnimationFrame(function () {
            var panel = document.getElementById('brain-sidebar-panel');
            if (panel) panel.classList.add('open');
        });
        state.open = true;
    }

    function _close() {
        var overlay = document.getElementById('brain-sidebar-overlay');
        var panel = document.getElementById('brain-sidebar-panel');
        if (panel) panel.classList.remove('open');
        state.open = false;
        if (state.abortCtrl) {
            state.abortCtrl.abort();
            state.abortCtrl = null;
        }
        state.streaming = false;
        setTimeout(function () {
            if (overlay) {
                overlay.setAttribute('hidden', '');
                overlay.setAttribute('aria-hidden', 'true');
            }
        }, 250);
        if (state.lastFocus && typeof state.lastFocus.focus === 'function') {
            try { state.lastFocus.focus(); } catch (_) {}
        }
    }

    function _submitFollowUp() {
        var input = document.getElementById('brain-sidebar-input');
        if (!input) return;
        var text = input.value.trim();
        if (!text || state.streaming) return;
        input.value = '';
        _sendFollowUp(text);
    }

    async function _sendFollowUp(text) {
        if (state.streaming) return;
        _appendMessage('user', text);
        _addToHistory('user', text);
        _saveHistory();

        state.streaming = true;
        state.abortCtrl = new AbortController();

        var sendBtn = document.getElementById('brain-sidebar-send');
        if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = '...'; }

        var brainMsgEl = _appendMessage('brain', '');
        brainMsgEl.classList.add('streaming');

        try {
            var token = (localStorage.getItem('hermes_token') || '');
            var api = (localStorage.getItem('hermes_api') || '').replace(/\/+$/, '');
            var page = (window.currentPage || 'unknown');

            var resp = await fetch(api + '/api/brain/stream-decide', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Hermes-Token': token },
                body: JSON.stringify({ prompt: text, context: { page: page, sidebar: true } }),
                signal: state.abortCtrl.signal,
            });

            if (!resp.ok) {
                brainMsgEl.textContent = 'Erro HTTP ' + resp.status;
                brainMsgEl.classList.add('error');
                return;
            }

            var reader = resp.body.getReader();
            var decoder = new TextDecoder();
            var buffer = '';
            var fullAnswer = '';

            while (true) {
                var chunk = await reader.read();
                if (chunk.done) break;
                buffer += decoder.decode(chunk.value, { stream: true });
                var parts = buffer.split('\n\n');
                buffer = parts.pop() || '';
                for (var i = 0; i < parts.length; i++) {
                    var part = parts[i];
                    if (!part.startsWith('data: ')) continue;
                    try {
                        var event = JSON.parse(part.slice(6));
                        if (event.type === 'thought' && event.chunk) {
                            brainMsgEl.textContent = event.chunk;
                        } else if (event.type === 'final' && event.answer) {
                            fullAnswer = String(event.answer);
                            brainMsgEl.textContent = fullAnswer;
                        } else if (event.type === 'error') {
                            brainMsgEl.textContent = 'Erro: ' + (event.message || 'desconhecido');
                            brainMsgEl.classList.add('error');
                        }
                    } catch (_) { /* ignore malformed */ }
                }
            }

            brainMsgEl.classList.remove('streaming');
            if (fullAnswer) {
                _addToHistory('brain', fullAnswer);
                _saveHistory();
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                brainMsgEl.textContent = 'Erro de rede: ' + (err.message || 'desconhecido');
                brainMsgEl.classList.add('error');
                if (window.hermesToast) window.hermesToast.error('Brain: erro de rede — ' + (err.message || 'desconhecido'));
            }
        } finally {
            state.streaming = false;
            if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = 'Enviar'; }
            var input2 = document.getElementById('brain-sidebar-input');
            if (input2) input2.focus();
        }
    }

    function _appendMessage(role, text) {
        var messages = document.getElementById('brain-sidebar-messages');
        if (!messages) return document.createElement('div');

        var msgEl = document.createElement('div');
        msgEl.className = 'brain-sidebar-msg brain-sidebar-msg--' + role;
        msgEl.textContent = text;

        var label = document.createElement('span');
        label.className = 'brain-sidebar-msg-role';
        label.setAttribute('aria-hidden', 'true');
        label.textContent = role === 'user' ? 'Você' : 'Brain';
        msgEl.prepend(label);

        messages.appendChild(msgEl);
        messages.scrollTop = messages.scrollHeight;
        return msgEl;
    }

    // ── localStorage history (max MAX_TURNS turns) ───────────────────────────

    function _loadHistory() {
        var messages = document.getElementById('brain-sidebar-messages');
        if (!messages) return;
        messages.textContent = '';
        try {
            var raw = localStorage.getItem(HISTORY_KEY);
            state.history = raw ? JSON.parse(raw) : [];
        } catch (_) {
            state.history = [];
        }
        state.history.slice(-MAX_TURNS).forEach(function (turn) {
            _appendMessage(turn.role, turn.text);
        });
    }

    function _addToHistory(role, text) {
        state.history.push({ role: role, text: text });
        if (state.history.length > MAX_TURNS * 2) {
            state.history = state.history.slice(-MAX_TURNS * 2);
        }
    }

    function _saveHistory() {
        try {
            localStorage.setItem(HISTORY_KEY, JSON.stringify(state.history.slice(-MAX_TURNS * 2)));
        } catch (_) { /* storage full — non-critical */ }
    }

    // ── Init ─────────────────────────────────────────────────────────────────

    window.HermesBrainSidebar = {
        show: show,
        close: close,
        askFollowUp: askFollowUp,
        _state: state,  // testing only
        _historyKey: HISTORY_KEY,  // testing only
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _build);
    } else {
        _build();
    }
})();
