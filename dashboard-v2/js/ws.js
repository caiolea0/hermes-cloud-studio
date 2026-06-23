/* Hermes 2.0 — WebSocket client para /ws?token= (VM hermes-api).
   Reconexão exponencial (3s → 30s). Status badge no #ws-badge.
   Emite CustomEvent 'hermes:ws-event' no document com detail = payload. */
(function () {
  'use strict';

  const TOKEN_KEY = 'hermes_token';
  let _ws = null;
  let _retryMs = 3000;
  let _retryTimer = null;
  let _intentionalClose = false;

  function _wsUrl() {
    const base = (window.HERMES_API || 'http://100.74.227.37:8800')
      .replace(/^http/, 'ws');
    const token = localStorage.getItem(TOKEN_KEY) || '';
    return `${base}/ws?token=${encodeURIComponent(token)}`;
  }

  function _setBadge(state) {
    const badge = document.getElementById('ws-badge');
    if (!badge) return;
    const states = {
      connected: { text: 'ao vivo', cls: 'good' },
      connecting: { text: 'conectando…', cls: 'warm' },
      disconnected: { text: 'desconectado', cls: 'danger' },
    };
    const s = states[state] || states.disconnected;
    badge.textContent = s.text;
    badge.className = `ws-badge ws-${state}`;
    badge.setAttribute('aria-label', `WebSocket: ${s.text}`);
  }

  function connect() {
    if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) return;
    _intentionalClose = false;
    _setBadge('connecting');

    const url = _wsUrl();
    try {
      _ws = new WebSocket(url);
    } catch (e) {
      console.warn('[ws] falha criar WebSocket:', e);
      _scheduleRetry();
      return;
    }

    _ws.onopen = () => {
      console.info('[ws] conectado');
      _setBadge('connected');
      _retryMs = 3000;
    };

    _ws.onmessage = (ev) => {
      let data;
      try { data = JSON.parse(ev.data); } catch { return; }
      document.dispatchEvent(new CustomEvent('hermes:ws-event', { detail: data }));
    };

    _ws.onclose = (ev) => {
      _setBadge('disconnected');
      if (!_intentionalClose) {
        console.info('[ws] fechado (%d), reconectando em %dms', ev.code, _retryMs);
        _scheduleRetry();
      }
    };

    _ws.onerror = () => {
      // onerror sempre precede onclose; deixa onclose lidar com retry
    };
  }

  function _scheduleRetry() {
    clearTimeout(_retryTimer);
    _retryTimer = setTimeout(() => {
      _retryMs = Math.min(_retryMs * 1.5, 30000);
      connect();
    }, _retryMs);
  }

  function disconnect() {
    _intentionalClose = true;
    clearTimeout(_retryTimer);
    if (_ws) { _ws.close(); _ws = null; }
    _setBadge('disconnected');
  }

  function isConnected() {
    return _ws && _ws.readyState === WebSocket.OPEN;
  }

  window.hermesWS = { connect, disconnect, isConnected };
})();
