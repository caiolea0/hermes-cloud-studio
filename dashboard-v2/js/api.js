/* Hermes 2.0 — REST client para hermes-api (VM :8800).
   Token lido do localStorage (key: hermes_token).
   401 → abre modal de login. Erros de rede → hermesToast.error().
   Endpoints: /api/prospects /api/market/signals /api/vuecra/queue /api/geo/* */
(function () {
  'use strict';

  const TOKEN_KEY = 'hermes_token';

  function _base() {
    return window.HERMES_API || 'http://100.74.227.37:8800';
  }

  function _token() {
    return localStorage.getItem(TOKEN_KEY) || '';
  }

  async function _fetch(path, opts = {}) {
    const url = _base() + path;
    const headers = {
      'X-Hermes-Token': _token(),
      'Content-Type': 'application/json',
      ...(opts.headers || {}),
    };
    try {
      const res = await fetch(url, { ...opts, headers });
      if (res.status === 401) {
        window.hermesToast && hermesToast.warn('Sessão expirada — faça login novamente');
        window.dispatchEvent(new CustomEvent('hermes:unauthorized'));
        throw Object.assign(new Error('Unauthorized'), { status: 401 });
      }
      if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw Object.assign(new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`), { status: res.status });
      }
      // 204 No Content
      if (res.status === 204) return null;
      return await res.json();
    } catch (err) {
      if (err.status) throw err; // relança erros HTTP já tratados
      // Erro de rede (offline, VPS inacessível)
      window.hermesToast && hermesToast.error('Sem conexão com o servidor Hermes');
      throw err;
    }
  }

  // ── Prospects ────────────────────────────────────────────────────────────

  async function getProspects({ page = 1, limit = 50, stage, city, search } = {}) {
    const params = new URLSearchParams({ page, limit });
    if (stage) params.set('stage', stage);
    if (city) params.set('city', city);
    if (search) params.set('search', search);
    return _fetch(`/api/prospects?${params}`);
  }

  // ── Market Signals (H2-F7) ───────────────────────────────────────────────

  async function getMarketSignals({ limit = 100, cnae } = {}) {
    const params = new URLSearchParams({ limit });
    if (cnae) params.set('cnae', cnae);
    return _fetch(`/api/market/signals?${params}`);
  }

  // ── Vuecra Queue (H2-F5) ────────────────────────────────────────────────

  async function getVuecraQueue() {
    return _fetch('/api/vuecra/queue');
  }

  // ── Geo (UI-P0 B5) ───────────────────────────────────────────────────────

  async function getGeoProspects({ minScore, stage } = {}) {
    const params = new URLSearchParams();
    if (minScore != null) params.set('min_score', minScore);
    if (stage) params.set('stage', stage);
    const qs = params.toString();
    return _fetch(`/api/geo/prospects${qs ? '?' + qs : ''}`);
  }

  async function getGeoBairros() {
    return _fetch('/api/geo/bairros');
  }

  // ── Daemon / Status ──────────────────────────────────────────────────────

  async function ping() {
    return _fetch('/api/_ping');
  }

  async function getDaemonState() {
    return _fetch('/api/daemon/state');
  }

  // ── Auth helpers ─────────────────────────────────────────────────────────

  function saveToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
  }

  function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
  }

  function hasToken() {
    return Boolean(_token());
  }

  // Expõe API global
  window.hermesAPI = {
    getProspects,
    getMarketSignals,
    getVuecraQueue,
    getGeoProspects,
    getGeoBairros,
    ping,
    getDaemonState,
    saveToken,
    clearToken,
    hasToken,
    _fetch,
  };
})();
