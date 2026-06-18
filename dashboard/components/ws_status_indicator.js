/* ============================================================
   Hermes Cloud Studio — WS Status Indicator (UX-RM-F7-A)
   ============================================================
   Enhances existing #status-dot / #status-text no topbar.
   API global: window.HermesWSStatus.setState(state, attempt?)
   States: 'connecting' | 'connected' | 'reconnecting' | 'disconnected'
   WCAG 2.1 AA: role=status, aria-live=polite, aria-atomic=false.
   ============================================================ */
(function () {
    'use strict';

    var _state = 'connecting';
    var _attempt = 0;

    var STATE_CFG = {
        connecting:   { dotClass: '',         text: 'Conectando...',  title: 'WebSocket: conectando' },
        connected:    { dotClass: '',         text: 'Online',         title: 'WebSocket: conectado' },
        reconnecting: { dotClass: 'amber',    text: '',               title: 'WebSocket: reconectando' },
        disconnected: { dotClass: 'offline',  text: 'Desconectado',   title: 'WebSocket: desconectado' },
    };

    function _render(state, attempt) {
        var dot = document.getElementById('status-dot');
        var txt = document.getElementById('status-text');
        var container = document.getElementById('hermes-status');
        if (!dot || !txt) return;

        var cfg = STATE_CFG[state] || STATE_CFG.connecting;
        dot.className = 'status-dot' + (cfg.dotClass ? ' ' + cfg.dotClass : '');

        if (state === 'reconnecting') {
            txt.textContent = attempt > 0
                ? 'Reconectando (' + attempt + ')...'
                : 'Reconectando...';
        } else {
            txt.textContent = cfg.text;
        }

        if (container) {
            container.title = cfg.title + (state === 'reconnecting' && attempt > 0
                ? ' — tentativa ' + attempt
                : '');
        }
    }

    function setState(state, attempt) {
        _state = state;
        _attempt = (typeof attempt === 'number' && attempt >= 0) ? attempt : 0;
        _render(_state, _attempt);
    }

    function _ensureARIA() {
        var container = document.getElementById('hermes-status');
        if (container && !container.getAttribute('role')) {
            container.setAttribute('role', 'status');
            container.setAttribute('aria-live', 'polite');
            container.setAttribute('aria-atomic', 'false');
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _ensureARIA);
    } else {
        _ensureARIA();
    }

    window.HermesWSStatus = { setState: setState };
})();
