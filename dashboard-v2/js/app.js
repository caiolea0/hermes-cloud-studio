/* Hermes 2.0 — Shell app: routing, data, surfaces.
   Dependências carregadas antes: config.js, toast.js, api.js, ws.js */
(function () {
  'use strict';

  // ── Routing (hash) ──────────────────────────────────────────────────────

  const SURFACES = ['mapa', 'esteira', 'dossier', 'comando'];
  let _currentSurface = null;
  let _mapInitialized = false;

  function _route() {
    const hash = location.hash.replace('#', '') || 'esteira';
    const surface = SURFACES.includes(hash) ? hash : 'esteira';
    _activate(surface);
  }

  function _activate(surface) {
    if (_currentSurface === surface) return;
    _currentSurface = surface;

    // Atualiza nav dock
    document.querySelectorAll('[data-surface]').forEach(el => {
      const isActive = el.dataset.surface === surface;
      el.setAttribute('aria-current', isActive ? 'page' : 'false');
      el.classList.toggle('on', isActive);
    });

    // Exibe surface correta (sempre visível — LEI reduced-motion)
    document.querySelectorAll('.surface').forEach(el => {
      const isActive = el.id === `surface-${surface}`;
      el.hidden = !isActive;
      el.setAttribute('aria-hidden', String(!isActive));
    });

    // Lazy inits
    if (surface === 'mapa' && !_mapInitialized) _initMap();
    if (surface === 'esteira') _loadEsteira();
    if (surface === 'comando') _loadComando();
  }

  // ── Auth / Login ────────────────────────────────────────────────────────

  function _checkAuth() {
    if (!hermesAPI.hasToken()) {
      _showLogin();
      return false;
    }
    return true;
  }

  function _showLogin() {
    const modal = document.getElementById('login-modal');
    if (!modal) return;
    modal.hidden = false;
    modal.setAttribute('aria-hidden', 'false');
    const input = modal.querySelector('#login-token-input');
    if (input) input.focus();
  }

  function _hideLogin() {
    const modal = document.getElementById('login-modal');
    if (!modal) return;
    modal.hidden = true;
    modal.setAttribute('aria-hidden', 'true');
  }

  // ── Metrics glance ──────────────────────────────────────────────────────

  async function _loadGlance() {
    try {
      const data = await hermesAPI.getProspects({ limit: 1 });
      const total = data?.total ?? data?.count ?? '—';
      const el = document.getElementById('glance-total');
      if (el) el.textContent = typeof total === 'number' ? total.toLocaleString('pt-BR') : total;
    } catch { /* silencioso — glance não é crítico */ }

    try {
      const sig = await hermesAPI.getMarketSignals({ limit: 1 });
      const count = sig?.total ?? sig?.count ?? '—';
      const el = document.getElementById('glance-signals');
      if (el) el.textContent = typeof count === 'number' ? count.toLocaleString('pt-BR') : count;
    } catch { /* silencioso */ }
  }

  // ── Surface: Esteira ────────────────────────────────────────────────────

  let _esteiraPage = 1;
  let _esteiraFilter = { stage: '', search: '' };
  let _esteiraLoading = false;

  async function _loadEsteira(reset = false) {
    if (_esteiraLoading) return;
    if (reset) { _esteiraPage = 1; }
    _esteiraLoading = true;

    const list = document.getElementById('esteira-list');
    if (!list) { _esteiraLoading = false; return; }

    if (reset || _esteiraPage === 1) {
      list.innerHTML = '<div class="esteira-loading muted" aria-live="polite">Carregando leads…</div>';
    }

    try {
      const data = await hermesAPI.getProspects({
        page: _esteiraPage,
        limit: 50,
        stage: _esteiraFilter.stage || undefined,
        search: _esteiraFilter.search || undefined,
      });

      const items = data?.items ?? data?.prospects ?? [];
      const total = data?.total ?? items.length;

      if (_esteiraPage === 1) {
        list.innerHTML = '';
        const countEl = document.getElementById('esteira-count');
        if (countEl) countEl.textContent = `${total.toLocaleString('pt-BR')} leads`;
      }

      if (items.length === 0 && _esteiraPage === 1) {
        list.innerHTML = '<div class="muted" style="padding:32px 0;text-align:center">Nenhum lead encontrado</div>';
        _esteiraLoading = false;
        return;
      }

      items.forEach(p => {
        const el = document.createElement('article');
        el.className = `lead-card card h${p.score >= 70 && !p.has_website ? ' hot' : ''}`;
        el.setAttribute('role', 'listitem');
        el.innerHTML = _renderLeadCard(p);
        list.appendChild(el);
      });

    } catch (err) {
      if (!_esteiraLoading) return;
      list.innerHTML = `<div class="muted" style="padding:32px 0;text-align:center">
        Erro ao carregar leads<br><span class="muted2" style="font-size:12px">${_escHtml(err.message)}</span>
      </div>`;
    } finally {
      _esteiraLoading = false;
    }
  }

  function _renderLeadCard(p) {
    const stage = {
      discovered: 'Descoberto',
      qualified: 'Qualificado',
      audited: 'Auditado',
      contacted: 'Contactado',
    }[p.stage] || p.stage;

    const scoreColor = p.score >= 70 ? 'warm' : p.score >= 50 ? 'good' : 'cool';
    const hasWebClass = p.has_website ? 'cool' : 'warm';
    const hasWebLabel = p.has_website ? 'Tem site' : 'Sem site';

    return `
      <div class="lead-inner" style="padding:16px 18px">
        <div class="row" style="gap:14px">
          <div class="ring" style="--val:${p.score};--col:var(--${scoreColor});--sz:42px" aria-label="Score ${p.score}">
            <b>${p.score}</b>
          </div>
          <div class="grow">
            <div style="font-weight:600;font-size:14px;line-height:1.3">${_escHtml(p.name || '—')}</div>
            <div class="muted" style="font-size:12px;margin-top:2px">${_escHtml(p.category || '—')}</div>
          </div>
          <div class="col" style="align-items:flex-end;gap:6px">
            <span class="tag ${scoreColor}" style="font-size:11px">${_escHtml(stage)}</span>
            <span class="tag ${hasWebClass}" style="font-size:11px">${hasWebLabel}</span>
          </div>
        </div>
        <div class="disc">
          <div class="in" style="padding-top:12px">
            <div class="row" style="gap:8px;flex-wrap:wrap">
              ${p.phone ? `<span class="muted" style="font-size:12px"><i class="ti ti-phone" aria-hidden="true"></i> ${_escHtml(p.phone)}</span>` : ''}
              ${p.city ? `<span class="muted" style="font-size:12px"><i class="ti ti-map-pin" aria-hidden="true"></i> ${_escHtml(p.city)}</span>` : ''}
            </div>
          </div>
        </div>
      </div>
    `;
  }

  // ── Surface: Comando ────────────────────────────────────────────────────

  async function _loadComando() {
    try {
      const state = await hermesAPI.getDaemonState();
      _renderDaemonState(state);
    } catch { /* daemon pode estar off */ }
  }

  function _renderDaemonState(state) {
    const el = document.getElementById('comando-daemon');
    if (!el || !state) return;
    const status = state.status || state.state || 'unknown';
    const color = { running: 'good', paused: 'warm', error: 'danger' }[status] || 'cool';
    el.innerHTML = `
      <div class="row">
        <span class="tag ${color}">${_escHtml(status)}</span>
        <span class="muted" style="font-size:13px">Daemon Hermes</span>
        <span class="spacer"></span>
        <span class="muted2" style="font-size:12px">${_escHtml(String(state.queue_size ?? '—'))} na fila</span>
      </div>
    `;
  }

  // ── Surface: Mapa ────────────────────────────────────────────────────────

  function _initMap() {
    _mapInitialized = true;
    const container = document.getElementById('map-container');
    if (!container) return;

    // MapLibre + pmtiles podem não estar disponíveis (vendor não baixado ou tiles ausentes)
    if (typeof maplibregl === 'undefined' || typeof pmtiles === 'undefined') {
      container.innerHTML = `
        <div style="height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px">
          <i class="ti ti-map-off" style="font-size:48px;color:var(--tx4)" aria-hidden="true"></i>
          <p class="muted">Mapa não disponível</p>
          <p class="muted2" style="font-size:12px">libs MapLibre/pmtiles ausentes ou tiles não carregados</p>
        </div>`;
      return;
    }

    try {
      const protocol = new pmtiles.Protocol();
      maplibregl.addProtocol('pmtiles', protocol.tile);

      const map = new maplibregl.Map({
        container: 'map-container',
        style: '/map/style-hermes-dark.json',
        center: [-56.0, -15.6],
        zoom: 11,
        attributionControl: false,
      });

      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
      map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');

      map.on('load', () => _loadGeoLayer(map));
      map.on('error', (e) => {
        console.warn('[map] erro MapLibre:', e);
      });

      window._hermesMap = map;
    } catch (err) {
      console.error('[map] falha inicializar MapLibre:', err);
      container.innerHTML = `
        <div style="height:100%;display:flex;align-items:center;justify-content:center">
          <p class="muted">Erro ao inicializar mapa: ${_escHtml(err.message)}</p>
        </div>`;
    }
  }

  async function _loadGeoLayer(map) {
    try {
      const fc = await hermesAPI.getGeoProspects();
      if (!fc || fc.features.length === 0) return;

      map.addSource('prospects', { type: 'geojson', data: fc });

      // Layer de pontos — cor por status_color (sem H3 hexes em P0)
      map.addLayer({
        id: 'prospects-circles',
        type: 'circle',
        source: 'prospects',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 3, 15, 6],
          'circle-color': [
            'match', ['get', 'status_color'],
            'warm', 'oklch(0.82 0.13 80)',
            'good', 'oklch(0.78 0.12 165)',
            'cool', 'oklch(0.66 0.11 240)',
            'oklch(0.55 0.009 265)',
          ],
          'circle-opacity': 0.85,
          'circle-stroke-width': 0.5,
          'circle-stroke-color': 'oklch(1 0 0 / 0.15)',
        },
      });

      // Tooltip on click
      map.on('click', 'prospects-circles', (e) => {
        const props = e.features[0]?.properties;
        if (!props) return;
        new maplibregl.Popup({ closeButton: false, className: 'map-popup' })
          .setLngLat(e.lngLat)
          .setHTML(`<strong>${_escHtml(props.name)}</strong><br>
            <span class="muted" style="font-size:12px">${_escHtml(props.category || '—')} · score ${props.score}</span>`)
          .addTo(map);
      });

      map.on('mouseenter', 'prospects-circles', () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', 'prospects-circles', () => { map.getCanvas().style.cursor = ''; });

    } catch (err) {
      console.warn('[map] falha carregar camada geo:', err);
    }
  }

  // ── ⌘K Palette ─────────────────────────────────────────────────────────

  function _openPalette() {
    const pal = document.getElementById('cmdpalette');
    if (!pal) return;
    pal.hidden = false;
    pal.setAttribute('aria-hidden', 'false');
    const input = pal.querySelector('#pal-input');
    if (input) { input.value = ''; input.focus(); }
  }

  function _closePalette() {
    const pal = document.getElementById('cmdpalette');
    if (!pal) return;
    pal.hidden = true;
    pal.setAttribute('aria-hidden', 'true');
  }

  // ── WS events ────────────────────────────────────────────────────────────

  document.addEventListener('hermes:ws-event', (e) => {
    const ev = e.detail;
    if (!ev || !ev.event_type) return;
    if (ev.event_type === 'daemon_state' || ev.event_type === 'daemon.connected') {
      if (_currentSurface === 'comando') _renderDaemonState(ev);
    }
  });

  // ── Utils ────────────────────────────────────────────────────────────────

  function _escHtml(str) {
    if (!str) return '';
    return String(str).replace(/[<>&"']/g, c =>
      ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#39;' }[c])
    );
  }

  // ── Boot ─────────────────────────────────────────────────────────────────

  function _boot() {
    // Login form
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
      loginForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const input = document.getElementById('login-token-input');
        const token = input?.value?.trim();
        if (!token) return;
        hermesAPI.saveToken(token);
        _hideLogin();
        _afterLogin();
      });
    }

    // Trata 401 global
    window.addEventListener('hermes:unauthorized', () => _showLogin());

    // Nav dock clicks
    document.querySelectorAll('[data-surface]').forEach(el => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        const s = el.dataset.surface;
        location.hash = s;
      });
      // Keyboard
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          el.click();
        }
      });
    });

    // Hash routing
    window.addEventListener('hashchange', _route);

    // ⌘K
    window.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        const pal = document.getElementById('cmdpalette');
        if (pal && !pal.hidden) _closePalette();
        else _openPalette();
      }
      if (e.key === 'Escape') _closePalette();
    });

    const palBtn = document.getElementById('pal-btn');
    if (palBtn) palBtn.addEventListener('click', _openPalette);

    const palClose = document.getElementById('pal-close');
    if (palClose) palClose.addEventListener('click', _closePalette);

    // Clique fora do palette fecha
    document.getElementById('cmdpalette')?.addEventListener('click', (e) => {
      if (e.target === e.currentTarget) _closePalette();
    });

    // Filtros esteira
    const stageFilter = document.getElementById('esteira-stage');
    if (stageFilter) {
      stageFilter.addEventListener('change', () => {
        _esteiraFilter.stage = stageFilter.value;
        _loadEsteira(true);
      });
    }

    const searchInput = document.getElementById('esteira-search');
    let _searchDebounce;
    if (searchInput) {
      searchInput.addEventListener('input', () => {
        clearTimeout(_searchDebounce);
        _searchDebounce = setTimeout(() => {
          _esteiraFilter.search = searchInput.value.trim();
          _loadEsteira(true);
        }, 350);
      });
    }

    // Checar auth e iniciar
    if (!_checkAuth()) return;
    _afterLogin();
  }

  function _afterLogin() {
    _loadGlance();
    hermesWS.connect();
    _route();
  }

  // Boot quando DOM pronto
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _boot);
  } else {
    _boot();
  }
})();
