/**
 * F.7 C1 — Cobaia Warmup Status Card (IIFE component).
 *
 * Mounts on the linkedin page: shows current warmup phase, day counter,
 * today caps, PAUSE ALL button, and subscribes to cobaia.* WS events.
 *
 * Design tokens: --bg, --accent, --lime, --green, --red, --r (from styles.css).
 * XSS: all user data rendered via textContent or DOMPurify.sanitize.
 */
(function CobaiaStatusCard() {
    'use strict';

    const API_URL = () => localStorage.getItem('hermes_api') || '';
    const TOKEN = () => localStorage.getItem('hermes_token') || '';

    const PHASE_LABELS = {
        lurking: 'Lurking',
        ramp: 'Ramp',
        normal: 'Normal',
        paused: 'Pausado',
    };
    const PHASE_COLORS = {
        lurking: 'var(--accent)',
        ramp: 'var(--lime)',
        normal: 'var(--green)',
        paused: 'var(--red)',
    };

    let _state = null;
    let _mountPoint = null;

    // --- Render ---

    function renderCard(state) {
        if (!_mountPoint) return;
        if (!state || !state.exists) {
            _mountPoint.innerHTML = `
                <div class="cobaia-card glass">
                    <div class="cobaia-card__header">
                        <span class="cobaia-card__title">Cobaia Warmup</span>
                        <span class="cobaia-card__status cobaia-status--inactive">Inativo</span>
                    </div>
                    <p class="cobaia-card__empty">Warmup nao iniciado. Use o botao abaixo para comecar.</p>
                    <button class="btn btn--primary cobaia-btn-start" aria-label="Iniciar warmup cobaia">
                        Iniciar Warmup
                    </button>
                </div>`;
            _mountPoint.querySelector('.cobaia-btn-start').addEventListener('click', handleStartWarmup);
            return;
        }

        const phase = state.phase || 'lurking';
        const day = state.current_day || 0;
        const totalDays = 14;
        const caps = state.caps_today || {};
        const metrics = state.today_metrics || {};
        const phaseColor = PHASE_COLORS[phase] || 'var(--accent)';
        const phaseLabel = PHASE_LABELS[phase] || phase;
        const withinHours = state.within_working_hours;
        const hoursOk = withinHours ? '&#x2705;' : '&#x274C;';

        const viewsRemain = Math.max(0, (caps.views || 0) - (metrics.views_count || 0));
        const connectsRemain = Math.max(0, (caps.connects || 0) - (metrics.connects_sent || 0));
        const engagementsRemain = Math.max(0, (caps.engagements || 0) - (metrics.engagements_count || 0));

        _mountPoint.innerHTML = `
            <div class="cobaia-card glass">
                <div class="cobaia-card__header">
                    <span class="cobaia-card__title">Cobaia Warmup</span>
                    <span class="cobaia-card__status cobaia-status--${phase}"
                          style="background:${phaseColor}20;color:${phaseColor};border:1px solid ${phaseColor}40">
                        ${DOMPurify.sanitize(phaseLabel)}
                    </span>
                </div>
                <div class="cobaia-card__body">
                    <div class="cobaia-day-progress">
                        <span class="cobaia-day-label">Dia ${day} de ${totalDays}</span>
                        <div class="cobaia-day-bar" role="progressbar"
                             aria-valuenow="${day}" aria-valuemin="0" aria-valuemax="${totalDays}"
                             aria-label="Progresso warmup dia ${day} de ${totalDays}">
                            <div class="cobaia-day-bar__fill"
                                 style="width:${Math.min(100, (day / totalDays) * 100).toFixed(1)}%;
                                        background:${phaseColor}"></div>
                        </div>
                    </div>
                    <div class="cobaia-caps" aria-label="Caps de acoes hoje">
                        <span class="cobaia-cap">Views: <b>${metrics.views_count || 0}/${caps.views || 0}</b></span>
                        <span class="cobaia-cap">Connects: <b>${metrics.connects_sent || 0}/${caps.connects || 0}</b></span>
                        <span class="cobaia-cap">Engagements: <b>${metrics.engagements_count || 0}/${caps.engagements || 0}</b></span>
                    </div>
                    <div class="cobaia-hours">
                        Horario de trabalho: ${hoursOk}
                        <small style="opacity:.6">${DOMPurify.sanitize(state.hours_reason || '')}</small>
                    </div>
                    ${state.pause_reason ? `<p class="cobaia-pause-reason">Motivo pause: ${DOMPurify.sanitize(state.pause_reason)}</p>` : ''}
                </div>
                <div class="cobaia-card__actions">
                    ${phase !== 'paused'
                        ? `<button class="btn cobaia-btn-pause" style="background:var(--red)20;color:var(--red);border:1px solid var(--red)40"
                               aria-label="Pausar toda atividade cobaia">PAUSE ALL</button>`
                        : `<button class="btn cobaia-btn-resume btn--primary"
                               aria-label="Retomar atividade cobaia">Retomar</button>`
                    }
                </div>
            </div>`;

        const pauseBtn = _mountPoint.querySelector('.cobaia-btn-pause');
        const resumeBtn = _mountPoint.querySelector('.cobaia-btn-resume');
        if (pauseBtn) pauseBtn.addEventListener('click', handlePause);
        if (resumeBtn) resumeBtn.addEventListener('click', handleResume);
    }

    // --- API calls ---

    async function apiPost(path, body) {
        const r = await fetch(`${API_URL()}${path}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Hermes-Token': TOKEN(),
            },
            body: JSON.stringify(body || {}),
        });
        if (!r.ok) throw new Error(`${path} HTTP ${r.status}`);
        return r.json();
    }

    async function apiGet(path) {
        const r = await fetch(`${API_URL()}${path}`, {
            headers: { 'X-Hermes-Token': TOKEN() },
        });
        if (!r.ok) throw new Error(`${path} HTTP ${r.status}`);
        return r.json();
    }

    async function loadStatus() {
        try {
            _state = await apiGet('/api/linkedin/cobaia/status');
            renderCard(_state);
        } catch (e) {
            console.error('[cobaia] status load failed:', e);
        }
    }

    async function handleStartWarmup() {
        try {
            _state = await apiPost('/api/linkedin/cobaia/start-warmup', {});
            renderCard(_state);
        } catch (e) {
            console.error('[cobaia] start-warmup failed:', e);
            if (window.showToast) showToast('Erro ao iniciar warmup: ' + e.message, 'error');
        }
    }

    async function handlePause() {
        try {
            _state = await apiPost('/api/linkedin/cobaia/pause', { reason: 'manual_pause' });
            renderCard(_state);
        } catch (e) {
            console.error('[cobaia] pause failed:', e);
        }
    }

    async function handleResume() {
        try {
            _state = await apiPost('/api/linkedin/cobaia/resume', {});
            renderCard(_state);
        } catch (e) {
            console.error('[cobaia] resume failed:', e);
        }
    }

    // --- WS event handler ---

    function handleWSEvent(event) {
        const type = event.type || event.event_type;
        if (!type || !type.startsWith('cobaia.')) return;
        if (event.account_handle !== undefined || event.phase !== undefined) {
            _state = { ..._state, ...event, exists: true };
            renderCard(_state);
        }
        if (type === 'cobaia.auto_paused' && window.showToast) {
            showToast('Cobaia AUTO-PAUSADO: ' + (event.reason || ''), 'error');
        }
    }

    // --- Mount ---

    function mount(containerId) {
        _mountPoint = document.getElementById(containerId);
        if (!_mountPoint) {
            console.warn('[cobaia] mount point not found:', containerId);
            return;
        }
        loadStatus();
        // Register WS subscriber
        if (window._wsEventHandlers) {
            window._wsEventHandlers.push(handleWSEvent);
        } else {
            window.addEventListener('hermes-ws-event', (e) => handleWSEvent(e.detail || {}));
        }
    }

    // --- CSS injection ---

    (function injectStyles() {
        const id = 'cobaia-card-styles';
        if (document.getElementById(id)) return;
        const style = document.createElement('style');
        style.id = id;
        style.textContent = `
.cobaia-card{padding:var(--r);border-radius:var(--r);background:var(--bg-2,#13131a);border:1px solid #ffffff10}
.cobaia-card__header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.cobaia-card__title{font-weight:600;font-size:.95rem;color:var(--fg)}
.cobaia-card__status{padding:2px 10px;border-radius:20px;font-size:.75rem;font-weight:600}
.cobaia-card__empty{color:var(--fg-muted,#888);font-size:.85rem;margin-bottom:12px}
.cobaia-day-progress{margin-bottom:10px}
.cobaia-day-label{font-size:.8rem;color:var(--fg-muted,#888);display:block;margin-bottom:4px}
.cobaia-day-bar{height:6px;border-radius:3px;background:#ffffff10;overflow:hidden}
.cobaia-day-bar__fill{height:100%;border-radius:3px;transition:width .4s ease}
.cobaia-caps{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px}
.cobaia-cap{font-size:.8rem;color:var(--fg-muted,#888)}
.cobaia-cap b{color:var(--fg,#fff)}
.cobaia-hours{font-size:.78rem;color:var(--fg-muted,#888);margin-bottom:10px}
.cobaia-pause-reason{font-size:.78rem;color:var(--red);margin-bottom:8px}
.cobaia-card__actions{display:flex;gap:8px;flex-wrap:wrap}
.cobaia-btn-pause,.cobaia-btn-resume,.cobaia-btn-start{padding:6px 16px;border-radius:8px;font-size:.85rem;font-weight:600;cursor:pointer;border:none}
        `;
        document.head.appendChild(style);
    })();

    // Expose globally for mount
    window.CobaiaStatusCard = { mount, loadStatus, handleWSEvent };
})();
