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
          <div class="ring" style="--val:${Number(p.score)||0};--col:var(--${scoreColor});--sz:42px" aria-label="Score ${Number(p.score)||0}">
            <b>${Number(p.score)||0}</b>
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

  // Score bands para filtro da legenda
  const SCORE_BANDS = {
    hot:    { min: 70, max: 100, label: 'Quente (≥70)',      color: 'hsl(25,80%,58%)' },
    medium: { min: 50, max: 69,  label: 'Oportunidade (50–69)', color: 'hsl(40,72%,55%)' },
    cool:   { min: 0,  max: 49,  label: 'Consolidado (<50)', color: 'hsl(215,40%,48%)' },
  };
  const _activeBands = { hot: true, medium: true, cool: true };

  function _initMap() {
    _mapInitialized = true;
    const container = document.getElementById('map-container');
    if (!container) return;

    if (typeof maplibregl === 'undefined') {
      container.innerHTML = `
        <div style="height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px">
          <i class="ti ti-map-off" style="font-size:48px;color:var(--tx4)" aria-hidden="true"></i>
          <p class="muted">Mapa não disponível</p>
          <p class="muted2" style="font-size:12px">lib MapLibre não carregada</p>
        </div>`;
      return;
    }

    try {
      if (typeof pmtiles !== 'undefined') {
        const protocol = new pmtiles.Protocol();
        maplibregl.addProtocol('pmtiles', protocol.tile.bind(protocol));
      }

      const map = new maplibregl.Map({
        container: 'map-container',
        style: '/map/style-hermes-dark.json',
        center: [-56.0, -15.6],
        zoom: 11,
        attributionControl: false,
      });

      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
      map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');

      map.on('load', () => _loadGeoLayers(map));
      map.on('error', (e) => {
        // Source errors (pmtiles não existe ainda) são esperados — não exibir ao usuário
        if (e.sourceId === 'hermes') return;
        console.warn('[map] erro MapLibre:', e.error?.message || e);
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

  async function _loadGeoLayers(map) {
    try {
      // Carrega bairros + prospects em paralelo
      const [bairros, fc] = await Promise.allSettled([
        hermesAPI.getGeoBairros(),
        hermesAPI.getGeoProspects(),
      ]);

      // ── Camada 1: Choropleth de bairros ─────────────────────────────────
      const bairrosData = bairros.status === 'fulfilled' ? bairros.value : null;
      if (bairrosData && bairrosData.features && bairrosData.features.length > 0) {
        map.addSource('bairros', { type: 'geojson', data: bairrosData });

        // Fill: cor por avg_score (calor de oportunidade)
        map.addLayer({
          id: 'bairros-fill',
          type: 'fill',
          source: 'bairros',
          paint: {
            'fill-color': [
              'interpolate', ['linear'], ['coalesce', ['get', 'avg_score'], 0],
              0,  'hsl(265,4%,9%)',
              20, 'hsl(265,5%,11%)',
              50, 'hsl(30,20%,13%)',
              70, 'hsl(25,35%,17%)',
            ],
            'fill-opacity': [
              'interpolate', ['linear'], ['coalesce', ['get', 'prospect_count'], 0],
              0, 0,
              1, 0.45,
              10, 0.65,
            ],
          },
        });

        // Border: sempre visível
        map.addLayer({
          id: 'bairros-line',
          type: 'line',
          source: 'bairros',
          paint: {
            'line-color': 'hsl(265,8%,24%)',
            'line-width': 0.5,
            'line-opacity': 0.5,
          },
        });

        // Border selecionado (feature-state highlight)
        map.addLayer({
          id: 'bairros-selected',
          type: 'line',
          source: 'bairros',
          filter: ['==', ['id'], ''],
          paint: {
            'line-color': 'hsl(265,60%,65%)',
            'line-width': 1.5,
            'line-opacity': 0.9,
          },
        });

        // Click → flyTo + modal
        let _selectedBairroId = null;
        map.on('click', 'bairros-fill', (e) => {
          const feat = e.features[0];
          if (!feat) return;
          const props = feat.properties;
          const id = props.id;

          // Highlight selected
          if (_selectedBairroId !== null) {
            map.setFilter('bairros-selected', ['==', ['id'], '']);
          }
          _selectedBairroId = id;
          map.setFilter('bairros-selected', ['==', ['get', 'id'], id]);

          // Desatura bairros não-focados
          map.setPaintProperty('bairros-fill', 'fill-opacity', [
            'case',
            ['==', ['get', 'id'], id], 0.75,
            ['interpolate', ['linear'], ['coalesce', ['get', 'prospect_count'], 0],
              0, 0, 1, 0.25, 10, 0.35],
          ]);

          // Camera: flyTo sob no-preference, jumpTo sob reduce
          const prefersReduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
          const target = { center: [e.lngLat.lng, e.lngLat.lat], zoom: 14 };
          if (prefersReduce) {
            map.jumpTo(target);
          } else {
            map.flyTo({ ...target, curve: 1.42, duration: 1600, essential: true });
          }

          _showRegionModal(props, map.project(target.center));
        });

        map.on('mouseenter', 'bairros-fill', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'bairros-fill', () => { map.getCanvas().style.cursor = ''; });
      }

      // ── Camada 2: Prospects circles (data-driven por score) ─────────────
      const fcData = fc.status === 'fulfilled' ? fc.value : null;
      if (fcData && fcData.features && fcData.features.length > 0) {
        map.addSource('prospects', { type: 'geojson', data: fcData });

        map.addLayer({
          id: 'prospects-circles',
          type: 'circle',
          source: 'prospects',
          paint: {
            // Raio cresce com zoom e com score
            'circle-radius': [
              'interpolate', ['linear'], ['zoom'],
              10, ['step', ['get', 'score'], 2.5, 50, 3.5, 70, 5],
              14, ['step', ['get', 'score'], 5,   50, 7,   70, 10],
            ],
            // Cor por score (hsl — MapLibre não aceita oklch)
            'circle-color': [
              'step', ['get', 'score'],
              'hsl(265,5%,38%)',    // < 30: cinza neutro
              30, 'hsl(215,40%,48%)', // 30–49: azul/consolidado
              50, 'hsl(40,72%,55%)',  // 50–69: âmbar/oportunidade
              70, 'hsl(25,80%,58%)',  // ≥70: coral/quente
            ],
            // Opacidade aumenta com score
            'circle-opacity': [
              'step', ['get', 'score'],
              0.5,
              30, 0.65,
              50, 0.80,
              70, 0.92,
            ],
            // Brilho (stroke) só nos mais quentes
            'circle-stroke-width': ['step', ['get', 'score'], 0, 70, 1.5],
            'circle-stroke-color': 'hsl(25,90%,78%)',
            'circle-stroke-opacity': 0.6,
          },
        });

        // Popup/tooltip on click
        map.on('click', 'prospects-circles', (e) => {
          const props = e.features[0]?.properties;
          if (!props) return;
          // Fecha modal de bairro se aberto
          _hideRegionModal();
          const stageLabel = {
            discovered: 'Descoberto', qualified: 'Qualificado',
            audited: 'Auditado', contacted: 'Contactado',
          }[props.stage] || props.stage;
          new maplibregl.Popup({ closeButton: true, closeOnClick: true, className: 'map-popup' })
            .setLngLat(e.lngLat)
            .setHTML(`
              <div style="min-width:180px">
                <div style="font-weight:600;font-size:13px;margin-bottom:4px">${_escHtml(props.name)}</div>
                <div style="font-size:11px;color:var(--tx3);margin-bottom:6px">${_escHtml(props.category || '—')}</div>
                <div style="display:flex;gap:6px;flex-wrap:wrap">
                  <span style="font-size:11px;padding:2px 7px;border-radius:5px;background:hsl(265,6%,14%);color:var(--tx2)">
                    Score ${Number(props.score) || 0}
                  </span>
                  <span style="font-size:11px;padding:2px 7px;border-radius:5px;background:hsl(265,6%,14%);color:var(--tx3)">
                    ${_escHtml(stageLabel)}
                  </span>
                </div>
              </div>`)
            .addTo(map);
        });

        map.on('mouseenter', 'prospects-circles', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'prospects-circles', () => { map.getCanvas().style.cursor = ''; });
      }

      // Inicializa legenda depois de carregar camadas
      _initLegend(map);

    } catch (err) {
      console.warn('[map] falha carregar camadas geo:', err);
    }
  }

  // ── Legenda + filtro ────────────────────────────────────────────────────────

  function _initLegend(map) {
    const legend = document.getElementById('map-legend');
    if (!legend) return;
    legend.hidden = false;
    legend.setAttribute('aria-hidden', 'false');

    legend.querySelectorAll('[data-band]').forEach(btn => {
      btn.addEventListener('click', () => {
        const band = btn.dataset.band;
        _activeBands[band] = !_activeBands[band];
        btn.classList.toggle('legend-inactive', !_activeBands[band]);
        btn.setAttribute('aria-pressed', String(_activeBands[band]));
        _updateProspectsFilter(map);
      });
    });
  }

  function _updateProspectsFilter(map) {
    if (!map.getLayer('prospects-circles')) return;
    const active = Object.entries(_activeBands)
      .filter(([, on]) => on)
      .map(([k]) => SCORE_BANDS[k]);

    if (active.length === 0) {
      map.setFilter('prospects-circles', ['==', ['get', 'score'], -1]);
      return;
    }
    if (active.length === 3) {
      map.setFilter('prospects-circles', null);
      return;
    }
    const conditions = active.map(b =>
      ['all', ['>=', ['get', 'score'], b.min], ['<=', ['get', 'score'], b.max]]
    );
    map.setFilter('prospects-circles', ['any', ...conditions]);
  }

  // ── Region modal ───────────────────────────────────────────────────────────

  function _showRegionModal(props, _screenPos) {
    const modal = document.getElementById('region-modal');
    if (!modal) return;

    const name = document.getElementById('region-modal-name');
    const stats = document.getElementById('region-modal-stats');
    if (name) name.textContent = props.name || 'Região';
    if (stats) {
      const total = Number(props.prospect_count) || 0;
      const hot   = Number(props.hot_count)     || 0;
      const med   = Number(props.medium_count)  || 0;
      const avg   = Number(props.avg_score)     || 0;
      // Valores sempre visíveis (reduced-motion: sem count-up)
      stats.innerHTML = `
        <div class="region-stat">
          <span class="region-stat-n">${total}</span>
          <span class="region-stat-l">prospects</span>
        </div>
        <div class="region-stat">
          <span class="region-stat-n hot">${hot}</span>
          <span class="region-stat-l">quentes (≥70)</span>
        </div>
        <div class="region-stat">
          <span class="region-stat-n med">${med}</span>
          <span class="region-stat-l">oportunidade</span>
        </div>
        <div class="region-stat">
          <span class="region-stat-n">${avg}</span>
          <span class="region-stat-l">score médio</span>
        </div>`;
    }

    modal.hidden = false;
    modal.setAttribute('aria-hidden', 'false');

    // Foco trap: botão de fechar
    const closeBtn = document.getElementById('region-close-btn');
    if (closeBtn) closeBtn.focus();
  }

  function _hideRegionModal() {
    const modal = document.getElementById('region-modal');
    if (!modal) return;
    modal.hidden = true;
    modal.setAttribute('aria-hidden', 'true');
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

    // Region modal close
    const regionClose = document.getElementById('region-close-btn');
    if (regionClose) regionClose.addEventListener('click', _hideRegionModal);
    const regionCta = document.getElementById('region-cta-btn');
    if (regionCta) regionCta.addEventListener('click', () => {
      hermesToast.info('Envio à esteira — disponível em UI-P3');
      _hideRegionModal();
    });

    // ⌘K
    window.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        const pal = document.getElementById('cmdpalette');
        if (pal && !pal.hidden) _closePalette();
        else _openPalette();
      }
      if (e.key === 'Escape') {
        _closePalette();
        _hideRegionModal();
      }
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
