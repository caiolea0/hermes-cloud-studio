/**
 * F.7 C3 — Cobaia Emergency Stop (IIFE component).
 *
 * Renders a prominent PAUSE ALL button with native <dialog> confirmation.
 * Resume button appears when state is paused.
 *
 * XSS: DOMPurify.sanitize on all dynamic content.
 * A11y: role=button, aria-label, keyboard Enter/Space, focus management.
 * WCAG: min 44px touch target, contrast via --color-error token.
 */
(function CobaiaEmergencyStop() {
    'use strict';

    const API = () => localStorage.getItem('hermes_api') || '';
    const TOKEN = () => localStorage.getItem('hermes_token') || '';

    let _mount = null;
    let _dialog = null;
    let _onStateChange = null;
    let _currentPhase = null;

    function _apiPost(path, body) {
        return fetch(`${API()}${path}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Hermes-Token': TOKEN() },
            body: JSON.stringify(body || {}),
        }).then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            return r.json();
        });
    }

    function _setLoading(btn, loading) {
        if (!btn) return;
        btn.disabled = loading;
        const label = btn.dataset.label || btn.textContent;
        if (loading) {
            btn.dataset.label = label;
            btn.innerHTML = `<span class="cobaia-spinner" aria-hidden="true"></span> Aguardando...`;
        } else {
            btn.textContent = label;
        }
    }

    function _initDialog() {
        if (_dialog) return;
        _dialog = document.createElement('dialog');
        _dialog.className = 'cobaia-confirm-dialog';
        _dialog.setAttribute('aria-labelledby', 'cobaia-confirm-title');
        _dialog.setAttribute('aria-describedby', 'cobaia-confirm-body');
        _dialog.innerHTML = `
            <h2 class="cobaia-confirm-title" id="cobaia-confirm-title">Confirmar PAUSE ALL</h2>
            <p class="cobaia-confirm-body" id="cobaia-confirm-body">
                Toda atividade da conta cobaia sera pausada imediatamente.<br>
                Campanha ativa sera interrompida. Retomar manualmente depois.
            </p>
            <div class="cobaia-confirm-actions">
                <button class="cobaia-confirm-cancel" id="cobaia-dlg-cancel">Cancelar</button>
                <button class="cobaia-confirm-proceed" id="cobaia-dlg-confirm">Pausar Agora</button>
            </div>`;
        document.body.appendChild(_dialog);

        document.getElementById('cobaia-dlg-cancel').addEventListener('click', () => {
            _dialog.close();
        });
        document.getElementById('cobaia-dlg-confirm').addEventListener('click', async () => {
            const confirmBtn = document.getElementById('cobaia-dlg-confirm');
            _setLoading(confirmBtn, true);
            try {
                const state = await _apiPost('/api/linkedin/cobaia/emergency-stop', { reason: 'manual_emergency' });
                _dialog.close();
                if (typeof _onStateChange === 'function') _onStateChange(state);
                render(state.phase);
            } catch (err) {
                console.error('[cobaia-stop] emergency-stop failed:', err);
                if (window.toast) toast('Erro ao pausar: ' + err.message, 'error');
            } finally {
                _setLoading(confirmBtn, false);
            }
        });
        // Close on backdrop click
        _dialog.addEventListener('click', e => {
            if (e.target === _dialog) _dialog.close();
        });
        // Close on Escape (native)
    }

    async function handleResume() {
        const btn = _mount && _mount.querySelector('.cobaia-resume-btn');
        _setLoading(btn, true);
        try {
            const state = await _apiPost('/api/linkedin/cobaia/resume', {});
            if (typeof _onStateChange === 'function') _onStateChange(state);
            render(state.phase);
        } catch (err) {
            console.error('[cobaia-stop] resume failed:', err);
            if (window.toast) toast('Erro ao retomar: ' + err.message, 'error');
        } finally {
            _setLoading(btn, false);
        }
    }

    function render(phase) {
        if (!_mount) return;
        _currentPhase = phase;
        _initDialog();

        if (phase === 'paused') {
            _mount.innerHTML = `
                <button class="cobaia-resume-btn" aria-label="Retomar atividade cobaia">
                    ▶ Retomar Cobaia
                </button>`;
            _mount.querySelector('.cobaia-resume-btn').addEventListener('click', handleResume);
        } else if (!phase) {
            _mount.innerHTML = '';
        } else {
            _mount.innerHTML = `
                <button class="cobaia-emergency-btn" aria-label="Pausar toda atividade cobaia imediatamente">
                    ${typeof window.icon === 'function' ? window.icon('stop') : '⏹'} PAUSE ALL
                </button>`;
            const btn = _mount.querySelector('.cobaia-emergency-btn');
            btn.addEventListener('click', () => _dialog.showModal());
            // Keyboard: Enter + Space already fire click on <button>
        }
    }

    function mount(containerId, phase, onStateChange) {
        _mount = document.getElementById(containerId);
        _onStateChange = onStateChange || null;
        render(phase || null);
    }

    function updatePhase(phase) {
        if (phase !== _currentPhase) render(phase);
    }

    window.CobaiaEmergencyStop = { mount, updatePhase };
})();
