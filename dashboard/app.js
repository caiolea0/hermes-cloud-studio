/* ============================================================
   GLOBAL STATE
   ============================================================ */
const VM_API = localStorage.getItem('hermes_api') || '';
let currentPage = 'dashboard';
let currentProspect = null;
let prospectsOffset = 0;
let prospectsTotal = 0;
let tasksOffset = 0;
let tasksTotal = 0;
let proposalProspects = [];
let dashboardInterval = null;
let scraperInterval = null;
let scraperRunning = false;
let claudeHistory = JSON.parse(localStorage.getItem('claude_history') || '[]');
let sentProposals = JSON.parse(localStorage.getItem('hermes_sent_proposals') || '[]');
let bulkSelected = new Set();

/* ============================================================
   UTILITY FUNCTIONS
   ============================================================ */
function escapeHtml(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

function _ensurePageH1(pageId, title) {
    const page = document.getElementById('page-' + pageId);
    if (!page) return;
    let h1 = page.querySelector(':scope > h1.page-h1');
    if (!h1) {
        h1 = document.createElement('h1');
        h1.className = 'page-h1';
        page.insertBefore(h1, page.firstChild);
    }
    h1.textContent = title;
}

/* ============================================================
   MERGED-019 — XSS sanitization (DOMPurify)
   Allowlist restritivo pra markdown render do Claude (renderMarkdownTerminal).
   Bloqueia <script>, on*=, javascript: URLs, etc. mesmo se algum bug em
   formatInline/renderMarkdownTerminal escapar mal um payload.
   ============================================================ */
const CLAUDE_ALLOWED_TAGS = [
    'div', 'span', 'p', 'br', 'hr',
    'strong', 'em', 'b', 'i', 'u', 'code', 'pre',
    'svg', 'use', 'a',
    'ul', 'ol', 'li',
];
const CLAUDE_ALLOWED_ATTR = ['style', 'class', 'href', 'use'];

function sanitizeClaudeHtml(html) {
    if (typeof DOMPurify === 'undefined') {
        console.warn('DOMPurify ausente; sanitization bypassed (fail-open dev only)');
        return html;
    }
    return DOMPurify.sanitize(html, {
        ALLOWED_TAGS: CLAUDE_ALLOWED_TAGS,
        ALLOWED_ATTR: CLAUDE_ALLOWED_ATTR,
        ALLOW_DATA_ATTR: false,
    });
}

function formatDate(dateStr) {
    if (!dateStr) return '--';
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' });
    } catch { return dateStr; }
}

function formatTime(dateStr) {
    if (!dateStr) return '';
    try {
        const d = new Date(dateStr);
        return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    } catch { return ''; }
}

function now() {
    return new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function scoreClass(score) {
    const s = Number(score) || 0;
    if (s >= 70) return 'score-high';
    if (s >= 40) return 'score-med';
    return 'score-low';
}

function stageBadge(stage) {
    const map = { 'new': 'badge-ghost', 'qualified': 'badge-lime', 'audited': 'badge-blue', 'outreach': 'badge-green', 'converted': 'badge-accent' };
    const cls = map[stage] || 'badge-ghost';
    return `<span class="badge ${cls}">${escapeHtml(stage || 'new')}</span>`;
}

function photoUrl(ref) {
    if (!ref) return '';
    if (ref.startsWith('http') && ref.includes('googleusercontent.com')) {
        return ref.replace(/=w\d+-h\d+.*$/, '=w400-h400-k-no');
    }
    return `${VM_API}/api/photos/${encodeURIComponent(ref)}?maxHeight=400`;
}

function starsHtml(rating) {
    const r = Number(rating) || 0;
    let h = '';
    for (let i = 1; i <= 5; i++) {
        h += `<svg class="${i <= r ? 'filled' : 'empty'}"><use href="#i-star"/></svg>`;
    }
    return h;
}

/* ============================================================
   RIPPLE EFFECT & ANIMATION HELPERS
   ============================================================ */
function addRipple(e) {
    const target = e.currentTarget;
    if (!target.classList.contains('ripple-host')) target.classList.add('ripple-host');
    const r = document.createElement('span');
    r.className = 'ripple';
    const rect = target.getBoundingClientRect();
    r.style.left = (e.clientX - rect.left) + 'px';
    r.style.top = (e.clientY - rect.top) + 'px';
    target.appendChild(r);
    setTimeout(() => r.remove(), 500);
}

function animateGridChildren(containerSelector) {
    const el = document.querySelector(containerSelector);
    if (!el) return;
    el.classList.remove('stagger-children');
    void el.offsetWidth;
    el.classList.add('stagger-children');
}

document.addEventListener('click', function(e) {
    const btn = e.target.closest('.btn, .wq-action-btn, .nav-item');
    if (btn) addRipple(e);
});

// UX-RM-F7-B: backdrop-click-to-dismiss via data-dismiss-fn (replaces inline onclick on overlay divs)
document.addEventListener('click', function(e) {
    const overlay = e.target.closest('[data-dismiss-fn]');
    if (!overlay || e.target !== overlay) return;
    const fn = overlay.dataset.dismissFn;
    if (fn && typeof window[fn] === 'function') window[fn]();
});

/* ============================================================
   API HELPER
   ============================================================ */
async function api(path, options = {}) {
    const url = VM_API + path;
    const token = localStorage.getItem('hermes_token') || '';
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['X-Hermes-Token'] = token;
    try {
        const resp = await fetch(url, { ...options, headers: { ...headers, ...(options.headers || {}) } });
        if (resp.status === 401) {
            localStorage.removeItem('hermes_token');
            showLoginScreen();
            throw new Error('Token invalido — faca login novamente');
        }
        if (!resp.ok) {
            const txt = await resp.text().catch(() => '');
            throw new Error(`HTTP ${resp.status}: ${txt}`);
        }
        const ct = resp.headers.get('content-type') || '';
        if (ct.includes('json')) return await resp.json();
        return await resp.text();
    } catch (err) {
        console.error('API error:', path, err);
        throw err;
    }
}

function showLoginScreen() {
    const existing = document.getElementById('login-overlay');
    if (existing) return;
    const overlay = document.createElement('div');
    overlay.id = 'login-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:99999;background:var(--bg);display:flex;align-items:center;justify-content:center;';
    overlay.innerHTML = `
        <div style="background:var(--s2);border:1px solid var(--border);border-radius:var(--r);padding:40px;width:380px;text-align:center;">
            <div style="font-size:32px;margin-bottom:8px;">H</div>
            <h2 style="font-size:18px;font-weight:600;margin-bottom:4px;">Hermes Command Center</h2>
            <p style="color:var(--text-2);font-size:12px;margin-bottom:24px;">Insira o token de acesso</p>
            <input id="login-token" type="password" placeholder="Token de acesso"
                style="width:100%;padding:10px 14px;background:var(--s3);border:1px solid var(--border);border-radius:var(--r-sm);color:var(--text);font-size:13px;margin-bottom:16px;">
            <button id="login-btn" style="width:100%;padding:10px;background:var(--accent);color:white;border-radius:var(--r-sm);font-weight:600;font-size:13px;cursor:pointer;">
                Entrar
            </button>
            <p id="login-error" style="color:var(--red);font-size:11px;margin-top:12px;display:none;"></p>
        </div>
    `;
    document.body.appendChild(overlay);
    const input = document.getElementById('login-token');
    const btn = document.getElementById('login-btn');
    const errEl = document.getElementById('login-error');
    async function tryLogin() {
        const token = input.value.trim();
        if (!token) { errEl.textContent = 'Token obrigatorio'; errEl.style.display = 'block'; return; }
        try {
            const resp = await fetch(VM_API + '/api/dashboard', { headers: { 'X-Hermes-Token': token } });
            if (resp.ok) {
                localStorage.setItem('hermes_token', token);
                overlay.remove();
                loadDashboard();
            } else {
                errEl.textContent = 'Token invalido';
                errEl.style.display = 'block';
            }
        } catch (e) {
            errEl.textContent = 'Erro de conexao';
            errEl.style.display = 'block';
        }
    }
    btn.addEventListener('click', tryLogin);
    input.addEventListener('keydown', e => { if (e.key === 'Enter') tryLogin(); });
    input.focus();
}

/**
 * Auto-bootstrap de token: zero manual entry.
 * Estrategia (em ordem):
 *   1. Tauri context -> IPC `get_auth_tokens` le .env diretamente
 *   2. Browser local (loopback) -> fetch /api/_bootstrap retorna tokens (server-side)
 *   3. Cloudflare tunnel ou remoto -> mostra login modal manual
 */
async function tryAutoBootstrap() {
    // Tauri context
    if (window.__TAURI__ || window.__TAURI_INTERNALS__) {
        try {
            const invoke = (window.__TAURI__ && window.__TAURI__.core?.invoke) || (window.__TAURI_INTERNALS__?.invoke);
            if (invoke) {
                const tokens = await invoke('get_auth_tokens');
                if (tokens?.auth_token) {
                    localStorage.setItem('hermes_token', tokens.auth_token);
                    if (tokens.internal_token) localStorage.setItem('hermes_internal_token', tokens.internal_token);
                    console.log('[hermes] auto-bootstrap via Tauri IPC OK');
                    return true;
                }
            }
        } catch (e) {
            console.warn('[hermes] Tauri IPC bootstrap falhou:', e);
        }
    }
    // Loopback fetch fallback
    const host = window.location.hostname;
    if (host === 'localhost' || host === '127.0.0.1' || host === '::1') {
        try {
            const r = await fetch(VM_API + '/api/_bootstrap');
            if (r.ok) {
                const tokens = await r.json();
                if (tokens?.auth_token) {
                    localStorage.setItem('hermes_token', tokens.auth_token);
                    if (tokens.internal_token) localStorage.setItem('hermes_internal_token', tokens.internal_token);
                    console.log('[hermes] auto-bootstrap via /api/_bootstrap OK');
                    return true;
                }
            }
        } catch (e) {
            console.warn('[hermes] /api/_bootstrap falhou:', e);
        }
    }
    return false;
}

async function checkAuth() {
    let token = localStorage.getItem('hermes_token') || '';
    const startPage = () => {
        if (window.HermesBreadcrumbs) window.HermesBreadcrumbs.mount('breadcrumb-mount');
        _restoreNavGroups();
        const hash = window.location.hash.replace('#', '') || 'control';
        navigate(hash);
        // UX-RM-F2-B — register commands + wire filters (defer scripts may already be loaded)
        _registerHermesCommands();
        _wireFilterPersistence();
        // UX-RM-F3-A — first-run onboarding wizard
        _checkOnboarding();
        // UX-RM-F7-A — lazy Ctrl+K handler (antes do command_palette.js carregar)
        _registerLazyKeyHandlers();
    };

    if (!token) {
        // Tenta auto-bootstrap (Tauri IPC ou loopback fetch)
        const ok = await tryAutoBootstrap();
        if (ok) {
            token = localStorage.getItem('hermes_token') || '';
        }
    }

    if (!token) {
        // Sem token e auto-bootstrap falhou (ex: dashboard via Cloudflare tunnel remoto)
        fetch(VM_API + '/api/dashboard').then(r => {
            if (r.status === 401) showLoginScreen();
            else startPage();
        }).catch(() => startPage());
        return;
    }

    // Token presente — validar com 1 request. Se 401, tentar re-bootstrap antes de mostrar login.
    try {
        const r = await fetch(VM_API + '/api/dashboard', { headers: { 'X-Hermes-Token': token } });
        if (r.status === 401) {
            localStorage.removeItem('hermes_token');
            const refreshed = await tryAutoBootstrap();
            if (refreshed) {
                startPage();
            } else {
                showLoginScreen();
            }
        } else {
            startPage();
        }
    } catch (e) {
        startPage();  // offline ou erro de rede — deixa app rodar com token salvo
    }
}

/* ============================================================
   TOAST SYSTEM
   ============================================================
   F.2.4 — delega pra window.toast.* (components/toast.js) quando disponível.
   Fallback preserva 100% comportamento legacy pra callers existentes (~30+ chamadas
   espalhadas usando 'success'|'error'|'info'). 'warn' adicionado em F.2.4 (novo path).
   F.2.future cleanup: remover wrapper + migrar callers diretos pra window.toast.*
   após Mission Control v2 (F.2.5a) e telas restantes adotarem padrão novo.
   ============================================================ */
function toast(msg, type = 'info') {
    if (window.hermesToast && typeof window.hermesToast[type] === 'function') {
        return window.hermesToast[type](msg);
    }
    const c = document.getElementById('toast-container');
    if (!c) return;
    const icons = { success: '#i-check', error: '#i-x', info: '#i-lightbulb' };
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.innerHTML = `<svg><use href="${icons[type] || icons.info}"/></svg><span>${escapeHtml(msg)}</span>`;
    c.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateY(8px)'; setTimeout(() => el.remove(), 300); }, 4000);
}

/* ============================================================
   F.2.5b — User preferences helpers + badge counter + sound notification
   ============================================================
   - getUserPref(key, default): sync read de cache localStorage 'hermes_user_prefs'
     (canonical = HermesPrefPanel cache, atualizado via fetch on open/init).
   - setUserPref(key, value): patch local + PUT idempotente via debounce
     (HermesPrefPanel já gerencia debounce quando aberto; chamada externa flush imediato).
   - Web Audio API beep sintetizado em error (660Hz, 150ms, volume 0.3, ADSR envelope):
     * Lazy init AudioContext após primeiro user gesture (browser autoplay policy)
     * SOMENTE toast.error toca beep (success/warn/info silent — anti-fadiga)
     * Zero binary no repo (substitui notification.mp3 vendor — arquitetura strictly cleaner)
   - Badge counter document.title text-safe:
     * Increment em hermesToast.error()
     * Clear via window.clearHermesErrorBadge() (chamado por click no error tile / PrefPanel)
   ============================================================ */
const ORIGINAL_DOC_TITLE = document.title || 'Hermes Command Center';
let _hermesErrorsUnread = 0;
let _audioCtx = null;
let _audioGestureBound = false;

function getUserPref(key, fallback) {
    try {
        const raw = localStorage.getItem('hermes_user_prefs');
        if (!raw) return fallback;
        const parsed = JSON.parse(raw);
        const data = parsed && parsed.data ? parsed.data : parsed;
        if (data && Object.prototype.hasOwnProperty.call(data, key)) {
            const v = data[key];
            return v === undefined ? fallback : v;
        }
    } catch { /* noop */ }
    return fallback;
}

function setUserPref(key, value) {
    try {
        const raw = localStorage.getItem('hermes_user_prefs');
        const parsed = raw ? JSON.parse(raw) : { version: 0, data: {} };
        const data = parsed.data && typeof parsed.data === 'object' ? parsed.data : {};
        data[key] = value;
        parsed.data = data;
        localStorage.setItem('hermes_user_prefs', JSON.stringify(parsed));
    } catch { /* noop */ }
    // Best-effort PUT em background (last-wins; HermesPrefPanel cuida do flush principal)
    const base = (typeof VM_API !== 'undefined' && VM_API) || localStorage.getItem('hermes_api') || '';
    const token = localStorage.getItem('hermes_token') || '';
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['X-Hermes-Token'] = token;
    fetch(base + '/api/user-prefs', {
        method: 'PUT',
        headers,
        body: JSON.stringify({ [key]: value }),
    }).catch(() => { /* offline OK, localStorage já patched */ });
}

function _ensureAudioCtx() {
    if (_audioCtx) return _audioCtx;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    try { _audioCtx = new Ctx(); } catch { return null; }
    return _audioCtx;
}

function _bindAudioGesture() {
    if (_audioGestureBound) return;
    _audioGestureBound = true;
    const handler = () => {
        const ctx = _ensureAudioCtx();
        if (ctx && ctx.state === 'suspended') {
            ctx.resume().catch(() => { /* noop */ });
        }
    };
    document.addEventListener('click', handler, { once: false, passive: true });
    document.addEventListener('keydown', handler, { once: false, passive: true });
}

function playErrorBeep() {
    const ctx = _ensureAudioCtx();
    if (!ctx) return;
    if (ctx.state === 'suspended') {
        // Ainda sem user gesture confirmado — silent skip.
        ctx.resume().catch(() => { /* noop */ });
        return;
    }
    try {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain).connect(ctx.destination);
        osc.type = 'sine';
        osc.frequency.value = 660; // Hz médio, não estridente
        const now = ctx.currentTime;
        const duration = 0.15;
        gain.gain.setValueAtTime(0, now);
        gain.gain.linearRampToValueAtTime(0.3, now + 0.01); // attack rápido
        gain.gain.exponentialRampToValueAtTime(0.001, now + duration); // decay suave (evita click)
        osc.start(now);
        osc.stop(now + duration);
    } catch { /* noop */ }
}

function updateBadgeTitle() {
    const enabled = getUserPref('badge_counter_unread_errors', true);
    if (!enabled || _hermesErrorsUnread <= 0) {
        document.title = ORIGINAL_DOC_TITLE;
        return;
    }
    // document.title é string text-safe — sem innerHTML, sem sanitize concern.
    document.title = `(${_hermesErrorsUnread}) ${ORIGINAL_DOC_TITLE}`;
}

function clearHermesErrorBadge() {
    _hermesErrorsUnread = 0;
    updateBadgeTitle();
}
window.clearHermesErrorBadge = clearHermesErrorBadge;
window.getUserPref = getUserPref;
window.setUserPref = setUserPref;
window.playErrorBeep = playErrorBeep;
window.updateBadgeTitle = updateBadgeTitle;

function _installErrorHook() {
    if (!window.hermesToast || typeof window.hermesToast.error !== 'function') return false;
    if (window.hermesToast.__f25b_hooked) return true;
    const originalError = window.hermesToast.error.bind(window.hermesToast);
    window.hermesToast.error = function (msg, opts) {
        _hermesErrorsUnread++;
        updateBadgeTitle();
        if (getUserPref('sound_notifications', false)) {
            playErrorBeep();
        }
        return originalError(msg, opts);
    };
    window.hermesToast.__f25b_hooked = true;
    return true;
}

// Bind audio gesture imediato + tenta hookar error toast assim que carregar
_bindAudioGesture();
(function _hookWhenReady() {
    if (_installErrorHook()) return;
    let tries = 0;
    const id = setInterval(() => {
        if (_installErrorHook() || ++tries >= 50) clearInterval(id); // 5s max
    }, 100);
})();

/* ============================================================
   UX-RM-F2-A — NAV GROUP HELPERS
   ============================================================ */
const _PAGE_TO_GROUP = {
    control: 'operations', cobaia: 'operations', 'pipeline-studio': 'operations', tasks: 'operations',
    prospects: 'outreach', proposals: 'outreach', audit: 'outreach', linkedin: 'outreach',
    skills: 'intelligence', 'skill-proposals': 'intelligence', lab: 'intelligence', memory: 'intelligence',
    claude: 'devtools', 'mcp-gateway': 'devtools',
};

function toggleNavGroup(groupId) {
    const grp = document.querySelector(`.nav-group[data-group="${groupId}"]`);
    if (!grp) return;
    const expanded = grp.getAttribute('aria-expanded') === 'true';
    _setNavGroupExpanded(grp, !expanded);
    try {
        const saved = JSON.parse(localStorage.getItem('hermes.nav.expanded_groups') || '{}');
        saved[groupId] = !expanded;
        localStorage.setItem('hermes.nav.expanded_groups', JSON.stringify(saved));
    } catch (e) {}
}

function _setNavGroupExpanded(grpEl, expanded) {
    grpEl.setAttribute('aria-expanded', String(expanded));
    const toggle = grpEl.querySelector('.nav-group-toggle');
    if (toggle) toggle.setAttribute('aria-expanded', String(expanded));
    const items = grpEl.querySelector('.nav-group-items');
    if (items) {
        if (expanded) items.removeAttribute('hidden');
        else items.setAttribute('hidden', '');
    }
}

function _expandNavGroup(groupId) {
    const grp = document.querySelector(`.nav-group[data-group="${groupId}"]`);
    if (!grp || grp.getAttribute('aria-expanded') === 'true') return;
    _setNavGroupExpanded(grp, true);
    try {
        const saved = JSON.parse(localStorage.getItem('hermes.nav.expanded_groups') || '{}');
        saved[groupId] = true;
        localStorage.setItem('hermes.nav.expanded_groups', JSON.stringify(saved));
    } catch (e) {}
}

function _restoreNavGroups() {
    try {
        const saved = JSON.parse(localStorage.getItem('hermes.nav.expanded_groups') || '{}');
        Object.keys(saved).forEach(groupId => {
            const grp = document.querySelector(`.nav-group[data-group="${groupId}"]`);
            if (grp) _setNavGroupExpanded(grp, !!saved[groupId]);
        });
    } catch (e) {}
}

/* ============================================================
   NAVIGATION
   ============================================================ */
function navigate(page) {
    // F.9.5: legacy #pipeline → Pipeline Studio visual builder (soft cutover)
    if (page === 'pipeline') page = 'pipeline-studio';
    currentPage = page;
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('[data-page]').forEach(n => {
        n.classList.remove('active');
        n.removeAttribute('aria-current');
    });

    const pageEl = document.getElementById(`page-${page}`);
    const navEl = document.querySelector(`[data-page="${page}"]`);
    if (pageEl) {
        pageEl.classList.add('active');
        pageEl.style.animation = 'none';
        void pageEl.offsetWidth;
        pageEl.style.animation = 'fade-in 0.25s var(--ease) both';
    }
    if (navEl) {
        navEl.classList.add('active');
        navEl.setAttribute('aria-current', 'page');
        const groupId = _PAGE_TO_GROUP[page] || null;
        if (groupId) _expandNavGroup(groupId);
        if (window.HermesBreadcrumbs) window.HermesBreadcrumbs.update(groupId, page);
    }

    const titles = {
        control: 'Mission Control',
        dashboard: 'Dashboard',
        prospects: 'Prospects',
        proposals: 'Centro de Propostas',
        audit: 'Auditoria Digital',
        pipeline: 'Pipeline',
        tasks: 'Fila do Dia',
        skills: 'Hermes Skills',
        linkedin: 'LinkedIn Automation',
        memory: 'Memoria do Agente',
        missions: 'Missoes da Semana',
        claude: 'AI Terminal',
        lab: 'Lab Cockpit',
        'mcp-gateway': 'MCP Gateway',
        observability: 'Observability',
        'pipeline-studio': 'Pipeline Studio',
        'skill-proposals': 'Skill Proposals',
        cobaia: 'Cobaia Live Ops',
    };
    if (page === 'cobaia') {
        // F8-A — CobaiaOperator replaces CobaiaStudio (dynamic layout with mode toggle)
        if (window.CobaiaOperator) {
            var _opContainer = document.getElementById('cobaia-page-container');
            if (_opContainer) window.CobaiaOperator.mount(_opContainer);
        } else if (window.CobaiaStudio) {
            window.CobaiaStudio.mount(); // fallback if operator not loaded
        }
    } else {
        if (window.CobaiaOperator) window.CobaiaOperator.unmount();
        else if (window.CobaiaStudio) window.CobaiaStudio.unmount();
    }
    if (page === 'linkedin') {
        loadLinkedInPage();
        _liStartLiveTickers();
        // F.7 C1 — mount cobaia warmup status card
        if (window.CobaiaStatusCard && document.getElementById('cobaia-status-card-mount')) {
            window.CobaiaStatusCard.mount('cobaia-status-card-mount');
        }
    } else if (typeof _liStopLiveTickers === 'function') {
        _liStopLiveTickers();
    }
    document.getElementById('topbar-title').textContent = titles[page] || page;
    _ensurePageH1(page, titles[page] || page);
    window.location.hash = page;

    clearInterval(dashboardInterval);
    clearInterval(scraperInterval);
    if (auditPollingInterval) { clearInterval(auditPollingInterval); auditPollingInterval = null; }

    if (page === 'control') {
        loadMissionControl();
    } else if (page === 'dashboard') {
        loadDashboard();
        dashboardInterval = setInterval(loadDashboard, 30000);
        refreshScraperStatus();
        scraperInterval = setInterval(refreshScraperStatus, 10000);
    } else if (page === 'prospects') {
        loadFilters();
        loadProspects();
    } else if (page === 'proposals') {
        loadProposalFilters();
        loadProposals();
    } else if (page === 'audit') {
        loadAuditPage();
    } else if (page === 'pipeline') {
        loadPipeline();
    } else if (page === 'tasks') {
        loadWorkQueue();
    } else if (page === 'skills') {
        loadSkills();
    } else if (page === 'memory') {
        loadMemory();
    } else if (page === 'missions') {
        loadMissions();
    } else if (page === 'claude') {
        renderClaudeHistory();
    } else if (page === 'lab') {
        // F.3.3 — Lab Cockpit init (idempotent: re-entry no-op).
        // UX-RM-F7-A: lazy-load lab suite on first navigate to lab.
        if (!window.HermesLabCockpit && window.loadComponent) {
            window.loadComponent('lab_gauge').then(function () {
                return window.loadComponent('lab_fingerprint_diff');
            }).then(function () {
                return window.loadComponent('lab_cockpit');
            }).then(function () {
                if (window.HermesLabCockpit && typeof window.HermesLabCockpit.init === 'function') {
                    try { window.HermesLabCockpit.init('[data-component="lab-cockpit"]'); }
                    catch (e) { console.warn('HermesLabCockpit init failed', e); }
                }
            }).catch(function (e) {
                if (window.hermesToast) window.hermesToast.error('Falha ao carregar Lab Cockpit');
            });
        } else if (window.HermesLabCockpit && typeof window.HermesLabCockpit.init === 'function') {
            try { window.HermesLabCockpit.init('[data-component="lab-cockpit"]'); }
            catch (e) { console.warn('HermesLabCockpit init failed', e); }
        }
    } else if (page === 'mcp-gateway') {
        // F.5.6f — MCP Gateway read-only init (idempotent: re-entry refresh).
        if (window.MCPGateway && typeof window.MCPGateway.init === 'function') {
            try { window.MCPGateway.init('[data-component="mcp-gateway"]'); }
            catch (e) { console.warn('MCPGateway init failed', e); }
        }
    } else if (page === 'observability') {
        // F.8.3 — Observability shell init (idempotent: re-entry refresh).
        if (window.ObservabilityShell && typeof window.ObservabilityShell.init === 'function') {
            try { window.ObservabilityShell.init('[data-component="observability-shell"]'); }
            catch (e) { console.warn('ObservabilityShell init failed', e); }
        }
    } else if (page === 'pipeline-studio') {
        // F.9.3 — Pipeline Studio shell init (idempotent: re-entry refresh).
        if (window.PipelineStudioShell && typeof window.PipelineStudioShell.init === 'function') {
            try { window.PipelineStudioShell.init('[data-component="pipeline-studio-shell"]'); }
            catch (e) { console.warn('PipelineStudioShell init failed', e); }
        }
    } else if (page === 'skill-proposals') {
        // F.4.3 — Skill Proposals Studio init (idempotent: re-entry refresh).
        // UX-RM-F7-A: lazy-load studio + modal on first navigate to skill-proposals.
        if (!window.SkillProposalsStudio && window.loadComponent) {
            window.loadComponent('skill_proposals_studio').then(function () {
                return window.loadComponent('skill_proposals_modal');
            }).then(function () {
                if (window.SkillProposalsStudio && typeof window.SkillProposalsStudio.init === 'function') {
                    try { window.SkillProposalsStudio.init('[data-component="skill-proposals-studio"]'); }
                    catch (e) { console.warn('SkillProposalsStudio init failed', e); }
                }
            }).catch(function (e) {
                if (window.hermesToast) window.hermesToast.error('Falha ao carregar Skill Proposals Studio');
            });
        } else if (window.SkillProposalsStudio && typeof window.SkillProposalsStudio.init === 'function') {
            try { window.SkillProposalsStudio.init('[data-component="skill-proposals-studio"]'); }
            catch (e) { console.warn('SkillProposalsStudio init failed', e); }
        }
    }
}

function refreshCurrentPage() {
    navigate(currentPage);
    toast('Pagina atualizada', 'success');
}

/* ============================================================
   SERVER CONTROL MENU (header dot dropdown)
   ============================================================ */
function toggleServerMenu(ev) {
    ev?.stopPropagation();
    const menu = document.getElementById('server-menu');
    if (!menu) return;
    if (menu.style.display === 'none' || !menu.style.display) {
        menu.style.display = 'block';
        _refreshServerMenuStatus();
    } else {
        menu.style.display = 'none';
    }
}

// close on outside click
document.addEventListener('click', (e) => {
    const menu = document.getElementById('server-menu');
    const trigger = document.getElementById('hermes-status');
    if (!menu || menu.style.display === 'none') return;
    if (menu.contains(e.target) || trigger?.contains(e.target)) return;
    menu.style.display = 'none';
});

async function _refreshServerMenuStatus() {
    // Local server — if we're running, by definition local is up
    const localDot = document.getElementById('server-menu-dot');
    const localTxt = document.getElementById('server-menu-status');
    if (localDot) localDot.style.background = 'var(--green)';
    if (localTxt) localTxt.textContent = 'Local online — porta 55000';

    // VM check via api() helper (inclui X-Hermes-Token automaticamente)
    const vmDot = document.getElementById('server-menu-vm-dot');
    const vmTxt = document.getElementById('server-menu-vm-status');
    try {
        const data = await api('/api/hermes/status');
        const vmOk = !!data?.vm_reachable;
        if (vmDot) vmDot.style.background = vmOk ? 'var(--green)' : '#ef4444';
        if (vmTxt) vmTxt.textContent = vmOk ? 'VM online — porta 8420' : 'VM offline';
    } catch {
        if (vmDot) vmDot.style.background = '#f59e0b';
        if (vmTxt) vmTxt.textContent = 'VM: status indisponível';
    }

    // Tunnel supervisor status (auto-discover)
    const tunDot = document.getElementById('server-menu-tunnel-dot');
    const tunTxt = document.getElementById('server-menu-tunnel-status');
    if (tunDot || tunTxt) {
        try {
            const t = await api('/api/tunnel/status');
            const ok = !!t?.healthy;
            if (tunDot) tunDot.style.background = ok ? 'var(--green)' : '#ef4444';
            if (tunTxt) tunTxt.textContent = ok
                ? `Tunnel OK — egress ${t.egress_ip || '?'}`
                : `Tunnel ${t?.last_action || 'down'}`;
        } catch {
            if (tunDot) tunDot.style.background = '#f59e0b';
            if (tunTxt) tunTxt.textContent = 'Tunnel: indisponível';
        }
    }
}

async function tunnelControl(action) {
    const labels = { start: 'Iniciar Tunnel', stop: 'Parar Tunnel', restart: 'Reiniciar Tunnel' };
    const label = labels[action] || action;
    if (action !== 'start' && !confirm(`Confirmar: ${label}?`)) return;
    toast(`${label} — executando...`, 'info');
    try {
        const r = await api('/api/tunnel/control', {
            method: 'POST',
            body: JSON.stringify({ action }),
        });
        toast(`${label} — ${JSON.stringify(r.result).slice(0, 80)}`, 'success');
        setTimeout(_refreshServerMenuStatus, 1500);
    } catch (e) {
        toast(`${label} falhou: ${e.message}`, 'error');
    }
}

async function serverAction(action) {
    const labels = {
        'restart-local': 'Reiniciar servidor local',
        'restart-vm':    'Reiniciar Hermes VM',
        'restart-all':   'Reiniciar tudo (local + VM)',
        'shutdown-local':'Desligar servidor local',
    };
    const label = labels[action] || action;
    if (!confirm(`Confirmar: ${label}?`)) return;
    toast(`${label} — executando...`, 'info');
    try {
        const r = await api(`/api/server/${action}`, { method: 'POST' });
        if (r.ok) {
            toast(`${label} — ${r.note || 'enviado'}`, 'success');
        } else {
            toast(`Falha: ${r.error || 'erro desconhecido'}`, 'error');
        }
    } catch (e) {
        // Restart kills connection mid-flight → expected
        if (action.includes('restart') || action.includes('shutdown')) {
            toast(`${label} — comando enviado (conexão caiu como esperado)`, 'info');
        } else {
            toast(`Erro: ${e.message || e}`, 'error');
        }
    }
    document.getElementById('server-menu').style.display = 'none';
    // Re-check status after a few seconds
    if (action.includes('restart')) {
        setTimeout(_refreshServerMenuStatus, 8000);
    }
}

/* ============================================================
   DASHBOARD
   ============================================================ */
async function loadDashboard() {
    try {
        const data = await api('/api/dashboard');
        document.getElementById('stat-total').textContent = data.total_prospects ?? '--';
        document.getElementById('stat-qualified').textContent = data.qualified ?? data.by_stage?.qualified ?? '--';
        document.getElementById('stat-audited').textContent = data.audited ?? data.by_stage?.audited ?? '--';
        document.getElementById('stat-outreach').textContent = data.outreach ?? data.by_stage?.outreach ?? '--';
        document.getElementById('stat-total-sub').textContent = `Ultimos 7 dias`;
        document.getElementById('stat-qual-sub').textContent = `Prontos para auditoria`;
        document.getElementById('stat-audit-sub').textContent = `Verificados`;
        document.getElementById('stat-outreach-sub').textContent = `Mensagens enviadas`;

        if (data.by_stage) {
            document.getElementById('funnel-new').textContent = data.by_stage.new ?? 0;
            document.getElementById('funnel-qualified').textContent = data.by_stage.qualified ?? 0;
            document.getElementById('funnel-audited').textContent = data.by_stage.audited ?? 0;
            document.getElementById('funnel-outreach').textContent = data.by_stage.outreach ?? 0;
            document.getElementById('funnel-converted').textContent = data.by_stage.converted ?? 0;
        }

        document.getElementById('status-dot').className = 'status-dot';
        document.getElementById('status-text').textContent = 'Online';

        animateGridChildren('#page-dashboard .grid-stats');
        animateGridChildren('#page-dashboard .funnel');
    } catch (e) {
        document.getElementById('status-dot').className = 'status-dot offline';
        document.getElementById('status-text').textContent = 'Offline';
    }

    loadDashboardActivities();
    loadDashboardTopProspects();
    loadDashboardTasks();
    loadDashAuditMonitor();
    refreshHermesLive();
    loadAIStatus();
}

async function loadAIStatus() {
    try {
        const s = await api('/api/hermes/status');
        const setDot = (id, on) => {
            const el = document.getElementById(id);
            if (el) el.style.background = on ? 'var(--green)' : 'var(--red)';
        };
        setDot('ai-az-dot', s.agent_zero?.online);
        setDot('ai-ollama-dot', s.ollama?.online);
        setDot('ai-mem-dot', s.agentmemory?.online);
        setDot('ai-vm-dot', s.vm_reachable);

        const azInfo = document.getElementById('ai-az-info');
        if (azInfo) azInfo.textContent = s.agent_zero?.online ? 'v1.18 Online' : 'Offline';

        const olInfo = document.getElementById('ai-ollama-info');
        if (olInfo) olInfo.textContent = s.ollama?.online ? `${s.ollama.models?.length ?? 0} modelos` : 'Offline';

        const memInfo = document.getElementById('ai-mem-info');
        if (memInfo) memInfo.textContent = s.agentmemory?.online ? 'Conectado' : 'Offline';

        const vmInfo = document.getElementById('ai-vm-info');
        if (vmInfo) vmInfo.textContent = s.vm_reachable ? `${s.total_synced ?? 0} prospects` : 'Offline';
    } catch (e) {
        console.warn('AI status check failed:', e);
    }
}

async function loadDashAuditMonitor() {
    try {
        const [dashData, auditData] = await Promise.all([
            api('/api/dashboard'),
            api('/api/audit/status')
        ]);
        const stages = dashData.by_stage || {};
        const pending = (stages.discovered || 0) + (stages.new || 0);
        const audited = (stages.audited || 0) + (stages.qualified || 0);

        document.getElementById('dash-audit-pending').textContent = pending.toLocaleString();
        document.getElementById('dash-audit-done').textContent = audited.toLocaleString();

        const highData = await api('/api/prospects?min_score=70&limit=1&offset=0');
        document.getElementById('dash-audit-high').textContent = highData.total?.toLocaleString() || '0';

        const dot = document.getElementById('dash-audit-dot');
        const label = document.getElementById('dash-audit-label');
        if (auditData.running) {
            dot.className = 'status-dot running';
            label.textContent = `Auditando ${auditData.done}/${auditData.total}`;
        } else if (auditData.finished_at) {
            dot.style.background = 'var(--blue)';
            label.textContent = `Ultimo: ${auditData.done} auditados`;
        } else {
            dot.style.background = 'var(--text-3)';
            label.textContent = 'Idle';
        }
    } catch { /* silent */ }
}

async function loadDashboardActivities() {
    try {
        const data = await api('/api/activities?limit=15');
        const items = data.activities || data.items || data || [];
        const c = document.getElementById('dash-activities');
        if (!items.length) { c.innerHTML = '<div class="empty-state"><svg><use href="#i-clock"/></svg><span>Nenhuma atividade recente</span></div>'; return; }
        c.innerHTML = items.map(a => {
            const icon = a.type === 'scraper' ? '#i-search' : a.type === 'audit' ? '#i-check-square' : a.type === 'outreach' ? '#i-send' : '#i-clock';
            return `<div class="list-row" style="cursor:default;padding:8px 12px">
                <svg style="width:16px;height:16px;stroke:var(--text-3);flex-shrink:0"><use href="${icon}"/></svg>
                <div style="flex:1;min-width:0"><div style="font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(a.description || a.message || a.title || '--')}</div><div style="font-size:10px;color:var(--text-3)">${formatDate(a.created_at || a.timestamp)} ${formatTime(a.created_at || a.timestamp)}</div></div>
            </div>`;
        }).join('');
    } catch { document.getElementById('dash-activities').innerHTML = '<div class="empty-state"><svg><use href="#i-clock"/></svg><span>Erro ao carregar atividades</span></div>'; }
}

async function loadDashboardTopProspects() {
    try {
        const data = await api('/api/prospects?limit=10&min_score=60');
        const items = data.prospects || data.items || data || [];
        const c = document.getElementById('dash-top-prospects');
        if (!items.length) { c.innerHTML = '<div class="empty-state"><svg><use href="#i-users"/></svg><span>Nenhum prospect com score alto</span></div>'; return; }
        c.innerHTML = items.map(p => `<button type="button" class="list-row" style="padding:8px 12px" onclick="openProspectPanel('${p.id}')" aria-label="Abrir ${escapeHtml(p.name || p.business_name)}">
            <div class="photo-thumb">${p.photo_ref ? `<img src="${photoUrl(p.photo_ref)}" onerror="this.parentElement.innerHTML='<svg><use href=\\'#i-store\\'/></svg>'">` : `<svg><use href="#i-store"/></svg>`}</div>
            <div style="flex:1;min-width:0"><div style="font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(p.name || p.business_name)}</div><div style="font-size:10px;color:var(--text-3)">${escapeHtml(p.category || '')} - ${escapeHtml(p.city || '')}</div></div>
            <span class="score-badge ${scoreClass(p.score)}">${p.score ?? '--'}</span>
        </button>`).join('');
    } catch { document.getElementById('dash-top-prospects').innerHTML = '<div class="empty-state"><svg><use href="#i-users"/></svg><span>Erro ao carregar</span></div>'; }
}

async function loadDashboardTasks() {
    try {
        const data = await api('/api/tasks?limit=5&status=pending');
        const items = data.tasks || data.items || data || [];
        const c = document.getElementById('dash-tasks');
        document.getElementById('dash-task-count').textContent = items.length;
        if (!items.length) { c.innerHTML = '<div class="empty-state" style="padding:24px"><svg><use href="#i-check-square"/></svg><span>Nenhuma tarefa pendente</span></div>'; return; }
        c.innerHTML = items.map(t => `<div class="list-row" style="padding:8px 12px;cursor:default">
            <svg style="width:14px;height:14px;stroke:var(--amber);flex-shrink:0"><use href="#i-clock"/></svg>
            <div style="flex:1;min-width:0"><div style="font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(t.title)}</div></div>
        </div>`).join('');
    } catch { /* silent */ }
}

/* ============================================================
   HERMES LIVE MONITOR
   ============================================================ */
let hlPollInterval = null;
let hlLastLogCount = 0;

const PHASE_TO_STEP = {
    starting: 0, planning: 0, init: 0,
    connecting: 1, authenticating: 1, dispatching: 1,
    running: 2, searching: 2, processing: 2, executing: 2, analyzing: 2,
    monitoring: 3, dispatched: 3, queued: 3,
    done: 4, completed: 4, failed: 4, error: 4, timeout: 4, offline: 3,
};

const PHASE_COLORS = {
    info: { bg: 'rgba(124,58,237,0.15)', color: 'var(--accent-l)' },
    warn: { bg: 'rgba(251,191,36,0.15)', color: 'var(--amber)' },
    error: { bg: 'rgba(251,113,133,0.15)', color: 'var(--pink)' },
    debug: { bg: 'rgba(255,255,255,0.06)', color: 'var(--text-3)' },
};

async function refreshHermesLive() {
    try {
        const data = await api('/api/pipeline-executions/active');
        const active = data.active || [];
        const recent = data.recent || [];
        const container = document.getElementById('hermes-live');
        const pulse = document.getElementById('hl-pulse');
        const statusText = document.getElementById('hl-status-text');
        const countEl = document.getElementById('hl-exec-count');
        const stepsEl = document.getElementById('hl-steps');
        const activeExecs = document.getElementById('hl-active-execs');
        const feed = document.getElementById('hl-feed');

        if (active.length > 0) {
            container.classList.remove('idle');
            pulse.classList.remove('idle');
            statusText.textContent = `${active.length} pipeline${active.length > 1 ? 's' : ''} ativo${active.length > 1 ? 's' : ''}`;
            countEl.textContent = '';
            stepsEl.style.display = 'flex';

            const mainExec = active[0];
            const logs = mainExec.log || [];
            const lastLog = logs.length ? logs[logs.length - 1] : null;
            const currentPhase = lastLog?.phase || 'init';
            const stepIdx = PHASE_TO_STEP[currentPhase] ?? 0;

            updateStepViz(stepIdx, mainExec.status === 'failed');

            activeExecs.innerHTML = active.map(ex => {
                const pct = ex.progress || 0;
                const typeIcon = PIPELINE_TYPE_META[ex.pipeline_type]?.icon || '#i-zap';
                const typeColor = PIPELINE_TYPE_META[ex.pipeline_type]?.color || 'var(--accent-l)';
                return `<div class="hl-exec-card running">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                        <div style="display:flex;align-items:center;gap:8px">
                            <svg style="width:14px;height:14px;stroke:${typeColor}"><use href="${typeIcon}"/></svg>
                            <span style="font-size:12px;font-weight:600;color:var(--text-1)">${escapeHtml(ex.pipeline_name || 'Pipeline #' + ex.id)}</span>
                        </div>
                        <span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:var(--r-xs);background:rgba(209,254,23,0.12);color:var(--lime)">${ex.status}</span>
                    </div>
                    <div style="display:flex;gap:16px;font-size:11px;color:var(--text-3);margin-bottom:8px">
                        <span>${ex.processed_items || 0}/${ex.total_items || '?'} itens</span>
                        <span>${pct}%</span>
                        <span>${ex.started_at ? new Date(ex.started_at).toLocaleTimeString() : '--'}</span>
                    </div>
                    <div style="height:3px;background:var(--s3);border-radius:2px;overflow:hidden">
                        <div style="height:100%;width:${pct}%;background:linear-gradient(90deg,var(--accent),var(--lime));border-radius:2px;transition:width 0.5s var(--ease)"></div>
                    </div>
                </div>`;
            }).join('');

            const allLogs = [];
            active.forEach(ex => {
                (ex.log || []).forEach(l => { l._pipeline = ex.pipeline_name; allLogs.push(l); });
            });
            allLogs.sort((a, b) => new Date(a.ts) - new Date(b.ts));

            if (allLogs.length !== hlLastLogCount) {
                hlLastLogCount = allLogs.length;
                feed.innerHTML = allLogs.slice(-30).map(renderFeedLine).join('');
                feed.scrollTop = feed.scrollHeight;
            }

            if (!hlPollInterval) {
                hlPollInterval = setInterval(refreshHermesLive, 2000);
            }
        } else {
            container.classList.add('idle');
            pulse.classList.add('idle');
            stepsEl.style.display = 'none';

            if (hlPollInterval) {
                clearInterval(hlPollInterval);
                hlPollInterval = null;
            }

            if (recent.length > 0) {
                statusText.textContent = `Ultimo: ${recent[0].pipeline_name || 'Pipeline'}`;
                countEl.textContent = `${recent[0].status} ${recent[0].completed_at ? timeAgo(recent[0].completed_at) : ''}`;

                activeExecs.innerHTML = recent.slice(0, 2).map(ex => {
                    const statusColor = ex.status === 'completed' ? 'var(--green)' : 'var(--pink)';
                    const typeIcon = PIPELINE_TYPE_META[ex.pipeline_type]?.icon || '#i-zap';
                    return `<div class="hl-exec-card">
                        <div style="display:flex;justify-content:space-between;align-items:center">
                            <div style="display:flex;align-items:center;gap:8px">
                                <svg style="width:14px;height:14px;stroke:${statusColor}"><use href="${typeIcon}"/></svg>
                                <span style="font-size:12px;font-weight:500;color:var(--text-2)">${escapeHtml(ex.pipeline_name || '')}</span>
                            </div>
                            <div style="display:flex;align-items:center;gap:8px">
                                <span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:var(--r-xs);background:${ex.status === 'completed' ? 'rgba(52,211,153,0.12)' : 'rgba(251,113,133,0.12)'};color:${statusColor}">${ex.status}</span>
                                <span style="font-size:10px;color:var(--text-3)">${ex.completed_at ? new Date(ex.completed_at).toLocaleTimeString() : ''}</span>
                            </div>
                        </div>
                    </div>`;
                }).join('');

                const lastLogs = recent[0].log || [];
                feed.innerHTML = lastLogs.slice(-15).map(renderFeedLine).join('');
            } else {
                statusText.textContent = 'Nenhuma atividade';
                countEl.textContent = '';
                activeExecs.innerHTML = '';
                feed.innerHTML = '<div class="hl-feed-line" style="color:var(--text-3)"><span class="hl-feed-time">--:--</span><span>Hermes aguardando comandos...</span></div>';
            }
        }
    } catch { /* silent */ }
}

function renderFeedLine(l) {
    const ts = l.ts ? new Date(l.ts).toLocaleTimeString('pt-BR', {hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '--:--';
    const colors = PHASE_COLORS[l.level] || PHASE_COLORS.info;
    const phase = l.phase || '';
    const phaseTag = phase ? `<span class="hl-feed-phase" style="background:${colors.bg};color:${colors.color}">${phase}</span>` : '';
    const msgColor = l.level === 'error' ? 'var(--pink)' : l.level === 'warn' ? 'var(--amber)' : 'var(--text-2)';
    return `<div class="hl-feed-line">
        <span class="hl-feed-time">${ts}</span>
        ${phaseTag}
        <span style="color:${msgColor}">${escapeHtml(l.msg)}</span>
    </div>`;
}

function updateStepViz(activeIdx, isFailed) {
    const steps = ['planning', 'connecting', 'executing', 'monitoring', 'done'];
    const connectors = ['hl-c1', 'hl-c2', 'hl-c3', 'hl-c4'];

    steps.forEach((s, i) => {
        const el = document.getElementById(`hl-s-${s}`);
        if (!el) return;
        el.classList.remove('active', 'done', 'error');
        if (i < activeIdx) el.classList.add('done');
        else if (i === activeIdx) el.classList.add(isFailed ? 'error' : 'active');
    });

    connectors.forEach((c, i) => {
        const el = document.getElementById(c);
        if (!el) return;
        el.classList.remove('done', 'active');
        if (i < activeIdx) el.classList.add('done');
        else if (i === activeIdx) el.classList.add('active');
    });
}

function timeAgo(dateStr) {
    if (!dateStr) return '';
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'agora';
    if (mins < 60) return `${mins}min atras`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h atras`;
    return `${Math.floor(hours / 24)}d atras`;
}

/* ============================================================
   SCRAPER MONITOR
   ============================================================ */
async function refreshScraperStatus() {
    try {
        const data = await api('/api/scraper/status');
        const isRunning = data.running || data.status === 'running';
        scraperRunning = isRunning;
        const dot = document.getElementById('scraper-status-dot');
        const label = document.getElementById('scraper-status-label');
        const btnStart = document.getElementById('btn-scraper-start');
        const btnStop = document.getElementById('btn-scraper-stop');

        if (isRunning) {
            dot.className = 'status-dot running';
            label.textContent = 'Executando';
            btnStart.style.display = 'none';
            btnStop.style.display = '';
        } else {
            dot.className = 'status-dot offline';
            label.textContent = data.last_run ? 'Ultimo Run' : 'Parado';
            btnStart.style.display = '';
            btnStop.style.display = 'none';
        }

        const stats = data.stats || data;
        const cities = data.cities || stats.cities_completed || [];
        document.getElementById('scraper-city').textContent = data.current_city || (cities.length ? `${cities.length} cidades` : '--');
        document.getElementById('scraper-categories').textContent = data.total_categories || data.category_count || '--';
        document.getElementById('scraper-new').textContent = stats.total_new ?? stats.new_found ?? 0;
        document.getElementById('scraper-site').textContent = stats.with_website ?? stats.with_site ?? 0;
        document.getElementById('scraper-nosite').textContent = stats.without_website ?? stats.no_site ?? 0;
        document.getElementById('scraper-errors').textContent = (Array.isArray(stats.errors) ? stats.errors.length : stats.errors) ?? 0;

        let progress = data.progress ?? 0;
        if (!progress && data.category_index && data.total_categories) {
            progress = Math.round((data.category_index / data.total_categories) * 100);
        }
        if (!progress && data.last_run) progress = 100;
        document.getElementById('scraper-progress').style.width = `${Math.min(100, progress)}%`;

        const logData = data.log_tail || data.log || [];
        if (logData.length) {
            const logEl = document.getElementById('scraper-log');
            logEl.innerHTML = logData.slice(-8).map(l => {
                if (typeof l === 'string') return `<div class="log-line">${escapeHtml(l)}</div>`;
                return `<div class="log-line"><span class="log-time">${formatTime(l.time || l.timestamp) || now()}</span>${escapeHtml(l.message || l.text || l)}</div>`;
            }).join('');
            logEl.scrollTop = logEl.scrollHeight;
        }
    } catch {
        document.getElementById('scraper-status-dot').className = 'status-dot offline';
        document.getElementById('scraper-status-label').textContent = 'Sem conexao';
    }
}

async function scraperStop() {
    try {
        await api('/api/scraper/stop', { method: 'POST' });
        toast('Scraper parado', 'success');
        refreshScraperStatus();
    } catch (e) { toast('Erro ao parar scraper: ' + e.message, 'error'); }
}

/* --- Scraper Config Modal --- */
const SCRAPER_PRESETS = {
    all: null,
    cuiaba: ['Cuiaba'],
    neighbors: ['Cuiaba','Varzea Grande','Chapada dos Guimaraes','Pocone','Nossa Senhora do Livramento','Santo Antonio de Leverger','Campo Verde'],
    custom: 'custom',
};
let scraperSelectedPreset = 'all';

function openScraperModal() {
    scraperPreset('all');
    scraperTabSwitch('manual');
    parsedNlConfig = null;
    document.getElementById('scraper-nl-input').value = '';
    document.getElementById('scraper-nl-result').style.display = 'none';
    document.getElementById('scraper-modal').classList.add('active');
}
function closeScraperModal() { document.getElementById('scraper-modal').classList.remove('active'); }

function scraperPreset(key) {
    scraperSelectedPreset = key;
    document.querySelectorAll('.scraper-preset').forEach(b => b.classList.toggle('active', b.dataset.preset === key));
    const citiesSection = document.getElementById('scraper-cities-section');
    citiesSection.style.display = key === 'custom' ? '' : 'none';

    if (key !== 'custom') {
        const checks = document.querySelectorAll('#scraper-cities-section input[type="checkbox"]');
        const preset = SCRAPER_PRESETS[key];
        checks.forEach(cb => { cb.checked = !preset || preset.includes(cb.value); });
    }
    updateScraperSummary();
}

function scraperCitiesToggle(state) {
    document.querySelectorAll('#scraper-cities-section input[type="checkbox"]').forEach(cb => { cb.checked = state; });
    updateScraperSummary();
}

function updateScraperSummary() {
    const selected = [...document.querySelectorAll('#scraper-cities-section input[type="checkbox"]:checked')];
    const n = selected.length;
    const searches = n * 111;
    const est = Math.round(searches * 1.2 / 60);
    document.getElementById('scraper-summary-text').textContent =
        `${n} cidade${n !== 1 ? 's' : ''} x 111 categorias = ~${searches.toLocaleString()} buscas (~${est} min)`;
}

document.getElementById('scraper-cities-section').addEventListener('change', updateScraperSummary);

/* --- Scraper Tab Switching --- */
let activeScraperTab = 'manual';
let parsedNlConfig = null;

function scraperTabSwitch(tab) {
    activeScraperTab = tab;
    document.querySelectorAll('.scraper-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    document.getElementById('scraper-tab-manual').style.display = tab === 'manual' ? '' : 'none';
    document.getElementById('scraper-tab-nlp').style.display = tab === 'nlp' ? '' : 'none';
    const launchBtn = document.getElementById('scraper-launch-btn');
    if (tab === 'nlp' && !parsedNlConfig) {
        launchBtn.style.display = 'none';
    } else {
        launchBtn.style.display = '';
    }
}

/* --- NLP Prompt Parsing --- */
async function parseScraperPrompt() {
    const input = document.getElementById('scraper-nl-input').value.trim();
    if (!input) { toast('Digite uma descricao do que buscar', 'error'); return; }

    const btn = document.getElementById('scraper-nl-parse-btn');
    const resultDiv = document.getElementById('scraper-nl-result');
    btn.disabled = true;
    btn.innerHTML = '<svg class="spin" style="width:14px;height:14px"><use href="#i-gear"/></svg> Interpretando...';
    resultDiv.style.display = 'none';
    parsedNlConfig = null;

    try {
        const res = await api('/api/scraper/parse-prompt', {
            method: 'POST',
            body: JSON.stringify({ prompt: input }),
        });

        parsedNlConfig = res.config;

        document.getElementById('scraper-nl-explanation').textContent = res.explanation || '';
        document.getElementById('scraper-nl-terms').innerHTML =
            (res.config.search_terms || []).map(t => `<span class="nl-term-badge">${escapeHtml(t)}</span>`).join('');
        document.getElementById('scraper-nl-cities').textContent =
            res.config.cities ? res.config.cities.join(', ') : 'Todas as 16 cidades';
        document.getElementById('scraper-nl-filter').textContent =
            res.config.only_no_site ? 'Filtro: apenas estabelecimentos SEM website' : '';

        const nCities = res.config.cities ? res.config.cities.length : 16;
        const nTerms = (res.config.search_terms || []).length;
        const searches = nCities * nTerms;
        const est = Math.round(searches * 1.2 / 60);
        document.getElementById('scraper-nl-summary').textContent =
            `${nCities} cidade${nCities !== 1 ? 's' : ''} x ${nTerms} termos = ~${searches} buscas (~${est} min)`;

        resultDiv.style.display = '';
        document.getElementById('scraper-launch-btn').style.display = '';
    } catch (e) {
        toast('Erro ao interpretar: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg><use href="#i-lightbulb"/></svg> Interpretar com Claude';
    }
}

/* --- Launch Scraper (both modes) --- */
async function launchScraper() {
    let body;

    if (activeScraperTab === 'nlp') {
        if (!parsedNlConfig) { toast('Primeiro interprete o prompt', 'error'); return; }
        body = {
            cities: parsedNlConfig.cities,
            categories: parsedNlConfig.search_terms,
            only_no_site: parsedNlConfig.only_no_site || false,
            rate_limit: 1.0,
        };
    } else {
        const checks = [...document.querySelectorAll('#scraper-cities-section input[type="checkbox"]:checked')];
        if (!checks.length) { toast('Selecione pelo menos uma cidade', 'error'); return; }
        body = {
            cities: scraperSelectedPreset === 'all' ? null : checks.map(cb => cb.value),
            categories: null,
            only_no_site: false,
            rate_limit: 1.0,
        };
    }

    try {
        const res = await api('/api/scraper/start', { method: 'POST', body: JSON.stringify(body) });
        if (res.status === 'already_running') {
            toast('Scraper ja esta rodando (PID ' + res.pid + ')', 'warning');
        } else {
            const desc = body.categories ? `${body.categories.length} termos custom` : '111 categorias';
            toast(`Scraping iniciado! ${desc}, PID ${res.pid}`, 'success');
        }
        closeScraperModal();
        refreshScraperStatus();
    } catch (e) { toast('Erro ao iniciar: ' + e.message, 'error'); }
}

/* ============================================================
   PROSPECTS PAGE
   ============================================================ */
let filtersLoaded = false;

async function loadFilters() {
    if (filtersLoaded) return;
    try {
        const [cities, categories] = await Promise.all([
            api('/api/prospects/cities'),
            api('/api/prospects/categories')
        ]);
        const cityList = cities.cities || cities || [];
        const catList = categories.categories || categories || [];
        const citySelect = document.getElementById('filter-city');
        const catSelect = document.getElementById('filter-category');
        const pCitySelect = document.getElementById('proposal-filter-city');
        const pCatSelect = document.getElementById('proposal-filter-category');

        cityList.forEach(c => {
            const val = typeof c === 'string' ? c : c.name || c.city;
            if (val) {
                citySelect.innerHTML += `<option value="${escapeHtml(val)}">${escapeHtml(val)}</option>`;
                pCitySelect.innerHTML += `<option value="${escapeHtml(val)}">${escapeHtml(val)}</option>`;
            }
        });
        catList.forEach(c => {
            const val = typeof c === 'string' ? c : c.name || c.category;
            if (val) {
                catSelect.innerHTML += `<option value="${escapeHtml(val)}">${escapeHtml(val)}</option>`;
                pCatSelect.innerHTML += `<option value="${escapeHtml(val)}">${escapeHtml(val)}</option>`;
            }
        });
        filtersLoaded = true;
        // UX-RM-F2-B — restore persisted filter values after options are populated
        if (window.HermesFilterPersistence) {
            const pf = window.HermesFilterPersistence.get('prospects');
            if (pf['filter-city'])     { const el = document.getElementById('filter-city');     if (el) el.value = pf['filter-city']; }
            if (pf['filter-category']) { const el = document.getElementById('filter-category'); if (el) el.value = pf['filter-category']; }
            if (pf['filter-website'])  { const el = document.getElementById('filter-website');  if (el) el.value = pf['filter-website']; }
            if (pf['filter-stage'])    { const el = document.getElementById('filter-stage');    if (el) el.value = pf['filter-stage']; }
            const pp = window.HermesFilterPersistence.get('proposals');
            if (pp['proposal-filter-city'])     { const el = document.getElementById('proposal-filter-city');     if (el) el.value = pp['proposal-filter-city']; }
            if (pp['proposal-filter-category']) { const el = document.getElementById('proposal-filter-category'); if (el) el.value = pp['proposal-filter-category']; }
            if (pp['proposal-filter-sent'])     { const el = document.getElementById('proposal-filter-sent');     if (el) el.value = pp['proposal-filter-sent']; }
        }
    } catch { /* silent */ }
}

async function loadProspects() {
    const search = document.getElementById('prospect-search').value;
    const city = document.getElementById('filter-city').value;
    const category = document.getElementById('filter-category').value;
    const hasWebsite = document.getElementById('filter-website').value;
    const stage = document.getElementById('filter-stage').value;
    const params = new URLSearchParams({ limit: 50, offset: prospectsOffset });
    if (search) params.set('search', search);
    if (city) params.set('city', city);
    if (category) params.set('category', category);
    if (hasWebsite) params.set('has_website', hasWebsite);
    if (stage) params.set('stage', stage);

    // UX-RM-F7-A — skeleton while fetching (wrapped in valid <tr><td> for <tbody>)
    const _tbodyPre = document.getElementById('prospects-tbody');
    if (_tbodyPre && window.skeletonPatterns) {
        _tbodyPre.innerHTML = '<tr><td colspan="9" style="padding:8px 0">' +
            window.skeletonPatterns.table(20, 6) + '</td></tr>';
    }

    try {
        const data = await api(`/api/prospects?${params}`);
        const items = data.prospects || data.items || data || [];
        prospectsTotal = data.total ?? items.length;
        const tbody = document.getElementById('prospects-tbody');

        // Reset bulk selection
        bulkSelected.clear();
        updateBulkBar();
        document.getElementById('bulk-select-all').checked = false;

        if (!items.length) {
            tbody.innerHTML = `<tr><td colspan="9"><div class="empty-state"><svg><use href="#i-users"/></svg><span>Nenhum prospect encontrado</span></div></td></tr>`;
        } else {
            tbody.innerHTML = items.map(p => `<tr style="border-bottom:1px solid var(--border);cursor:pointer;transition:background 0.1s" onmouseover="this.style.background='var(--s3)'" onmouseout="this.style.background=''" onclick="openProspectPanel('${p.id}')">
                <td style="padding:8px 8px 8px 16px" onclick="event.stopPropagation()"><input type="checkbox" class="bulk-check" data-id="${p.id}" onchange="toggleBulkItem(${p.id},this.checked)" style="accent-color:var(--accent);width:14px;height:14px;cursor:pointer"></td>
                <td style="padding:8px"><div class="photo-thumb">${p.photo_ref ? `<img src="${photoUrl(p.photo_ref)}" onerror="this.parentElement.innerHTML='<svg><use href=\\'#i-store\\'/></svg>'">` : `<svg><use href="#i-store"/></svg>`}</div></td>
                <td style="padding:8px"><div style="font-size:12px;font-weight:600;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(p.name || p.business_name)}</div></td>
                <td style="padding:8px"><span style="font-size:11px;color:var(--text-2)">${escapeHtml(p.category || '--')}</span></td>
                <td style="padding:8px"><span style="font-size:11px;color:var(--text-2)">${escapeHtml(p.city || '--')}</span></td>
                <td style="padding:8px;text-align:center"><span class="score-badge ${scoreClass(p.score)}">${p.score ?? '--'}</span></td>
                <td style="padding:8px">${stageBadge(p.stage)}</td>
                <td style="padding:8px"><span style="font-size:11px;color:var(--text-2)">${escapeHtml(p.phone || '--')}</span></td>
                <td style="padding:8px 16px;text-align:right" onclick="event.stopPropagation()">
                    <div style="display:flex;gap:4px;justify-content:flex-end">
                        ${p.phone ? `<button class="btn-icon" title="WhatsApp" onclick="window.open('https://wa.me/${(p.phone||'').replace(/\\D/g,'')}','_blank')"><svg><use href="#i-message-circle"/></svg></button>` : ''}
                        ${p.website ? `<button class="btn-icon" title="Website" onclick="window.open('${escapeHtml(p.website)}','_blank')"><svg><use href="#i-globe"/></svg></button>` : ''}
                        <button class="btn-icon" title="Auditar" onclick="auditSingle(${p.id},this)"><svg><use href="#i-clipboard"/></svg></button>
                        <button class="btn-icon" title="Detalhes" onclick="openProspectPanel('${p.id}')"><svg><use href="#i-eye"/></svg></button>
                    </div>
                </td>
            </tr>`).join('');
        }

        const start = prospectsOffset + 1;
        const end = Math.min(prospectsOffset + items.length, prospectsTotal);
        document.getElementById('prospects-showing').textContent = `Mostrando ${start}-${end} de ${prospectsTotal}`;
        document.getElementById('btn-prev').disabled = prospectsOffset === 0;
        document.getElementById('btn-next').disabled = end >= prospectsTotal;
    } catch (e) {
        document.getElementById('prospects-tbody').innerHTML = `<tr><td colspan="8"><div class="empty-state"><svg><use href="#i-x"/></svg><span>Erro ao carregar: ${escapeHtml(e.message)}</span></div></td></tr>`;
    }
}

function prospectsPrev() { prospectsOffset = Math.max(0, prospectsOffset - 50); loadProspects(); }
function prospectsNext() { prospectsOffset += 50; loadProspects(); }

function toggleBulkItem(id, checked) {
    if (checked) bulkSelected.add(id);
    else bulkSelected.delete(id);
    updateBulkBar();
}

function toggleSelectAll(checked) {
    document.querySelectorAll('.bulk-check').forEach(cb => {
        cb.checked = checked;
        const id = parseInt(cb.dataset.id);
        if (checked) bulkSelected.add(id);
        else bulkSelected.delete(id);
    });
    updateBulkBar();
}

function updateBulkBar() {
    const bar = document.getElementById('bulk-bar');
    const count = bulkSelected.size;
    if (count > 0) {
        bar.style.display = '';
        document.getElementById('bulk-count').textContent = `${count} selecionado${count > 1 ? 's' : ''}`;
    } else {
        bar.style.display = 'none';
    }
}

function clearBulkSelection() {
    bulkSelected.clear();
    document.querySelectorAll('.bulk-check').forEach(cb => cb.checked = false);
    document.getElementById('bulk-select-all').checked = false;
    updateBulkBar();
}

async function bulkChangeStage() {
    const stage = document.getElementById('bulk-stage').value;
    if (!stage) { toast('Selecione um estagio', 'error'); return; }
    if (!bulkSelected.size) return;
    try {
        const result = await api('/api/prospects/bulk', {
            method: 'POST',
            body: JSON.stringify({ ids: [...bulkSelected], action: 'stage_change', value: stage })
        });
        toast(`${result.count || bulkSelected.size} prospects atualizados para ${stage}`, 'success');
        clearBulkSelection();
        loadProspects();
    } catch (e) { toast('Erro: ' + e.message, 'error'); }
}

async function bulkAudit() {
    if (!bulkSelected.size) return;
    const ids = [...bulkSelected];
    toast(`Auditando ${ids.length} prospects...`, 'info');
    let ok = 0;
    for (const id of ids) {
        try {
            await api(`/api/audit/prospect/${id}`, { method: 'POST' });
            ok++;
        } catch {}
    }
    toast(`${ok} prospects auditados`, 'success');
    clearBulkSelection();
    loadProspects();
}

/* ============================================================
   PROSPECT DETAIL PANEL
   ============================================================ */
async function openProspectPanel(id) {
    try {
        const p = await api(`/api/prospects/${id}`);
        currentProspect = p;
        const panel = document.getElementById('prospect-panel');
        const overlay = document.getElementById('panel-overlay');

        document.getElementById('panel-name').textContent = p.name || p.business_name || '--';
        document.getElementById('panel-catcity').textContent = `${p.category || '--'} - ${p.city || '--'}`;

        // Hero photo
        const heroImg = document.getElementById('panel-hero-img');
        const heroFallback = document.getElementById('panel-hero-fallback');
        if (p.photo_ref) {
            heroImg.src = photoUrl(p.photo_ref);
            heroImg.style.display = 'block';
            heroFallback.style.display = 'none';
        } else {
            heroImg.style.display = 'none';
            heroFallback.style.display = '';
        }

        // Thumb photo
        const photoEl = document.getElementById('panel-photo');
        if (p.photo_ref) {
            photoEl.innerHTML = `<img src="${photoUrl(p.photo_ref)}" onerror="this.parentElement.innerHTML='<svg><use href=\\'#i-store\\'/></svg>'">`;
        } else {
            photoEl.innerHTML = '<svg><use href="#i-store"/></svg>';
        }

        // Hide edit form on open
        document.getElementById('panel-edit-form').style.display = 'none';

        const scoreEl = document.getElementById('panel-score');
        scoreEl.textContent = p.score ?? '--';
        scoreEl.className = `score-badge ${scoreClass(p.score)}`;

        document.getElementById('panel-stage-select').value = p.stage || 'new';
        document.getElementById('panel-stars').innerHTML = starsHtml(p.rating);
        document.getElementById('panel-address').textContent = p.address || '--';
        document.getElementById('panel-phone').textContent = p.phone || '--';
        document.getElementById('panel-website').textContent = p.website || 'Sem site';
        document.getElementById('panel-discovered').textContent = formatDate(p.created_at || p.discovered_at);
        document.getElementById('panel-source').textContent = p.source || 'Google Maps';

        const mapsUrl = p.maps_url || p.google_maps_url || (p.name ? `https://www.google.com/maps/search/${encodeURIComponent(p.name + ' ' + (p.city || ''))}` : '#');
        document.getElementById('panel-maps-link').href = mapsUrl;

        // Audit tab — formatted display
        const auditEl = document.getElementById('panel-audit-content');
        const auditSummary = p.audit_summary || p.audit || p.audit_data;
        if (auditSummary) {
            const a = typeof auditSummary === 'string' ? auditSummary : JSON.stringify(auditSummary, null, 2);
            const hasWebsite = p.has_website || p.website;
            const hasSSL = a.toLowerCase().includes('ssl: true') || a.toLowerCase().includes('ssl ok');
            const hasMobile = a.toLowerCase().includes('mobile: true') || a.toLowerCase().includes('mobile ok');
            auditEl.innerHTML = `
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px">
                    <div style="background:var(--s3);border-radius:var(--r-sm);padding:10px;text-align:center">
                        <div style="font-size:10px;color:var(--text-3);text-transform:uppercase;margin-bottom:4px">Website</div>
                        <svg style="width:20px;height:20px;stroke:${hasWebsite ? 'var(--green)' : 'var(--red)'}"><use href="${hasWebsite ? '#i-check' : '#i-x'}"/></svg>
                    </div>
                    <div style="background:var(--s3);border-radius:var(--r-sm);padding:10px;text-align:center">
                        <div style="font-size:10px;color:var(--text-3);text-transform:uppercase;margin-bottom:4px">Score</div>
                        <span class="score-badge ${scoreClass(p.score)}" style="font-size:14px;width:auto;padding:2px 10px">${p.score ?? '--'}</span>
                    </div>
                </div>
                <div style="font-size:12px;line-height:1.7;white-space:pre-wrap;color:var(--text-2);background:var(--s3);border-radius:var(--r-sm);padding:12px;max-height:200px;overflow-y:auto">${escapeHtml(a)}</div>`;
        } else {
            auditEl.innerHTML = '<div class="empty-state"><svg><use href="#i-check-square"/></svg><span>Nenhum dado de auditoria disponivel</span></div>';
        }

        // Outreach tab
        const outreachEl = document.getElementById('panel-outreach-content');
        const msg = p.outreach_message || p.message;
        if (msg) {
            outreachEl.innerHTML = `<div style="background:var(--s3);border-radius:var(--r-sm);padding:14px;margin-bottom:12px">
                <div style="font-size:12px;line-height:1.6;white-space:pre-wrap;color:var(--text-2)">${escapeHtml(msg)}</div>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
                <button class="btn btn-ghost btn-sm" onclick="copyOutreach()"><svg><use href="#i-copy"/></svg> Copiar</button>
                ${p.phone ? `<button class="btn btn-primary btn-sm" onclick="window.open('https://wa.me/${(p.phone||'').replace(/\\D/g,'')}?text=${encodeURIComponent(msg)}','_blank')"><svg><use href="#i-send"/></svg> Enviar WhatsApp</button>` : ''}
                ${p.email ? `<button class="btn btn-ghost btn-sm" onclick="window.open('mailto:${escapeHtml(p.email)}?body=${encodeURIComponent(msg)}','_blank')"><svg><use href="#i-mail"/></svg> Email</button>` : ''}
                <button class="btn btn-ghost btn-sm" onclick="panelRegenOutreach()" id="panel-regen-btn"><svg><use href="#i-refresh"/></svg> Regenerar</button>
            </div>`;
        } else {
            outreachEl.innerHTML = `<div class="empty-state" style="padding:32px 24px">
                <svg style="width:40px;height:40px;stroke:var(--text-3);opacity:0.5"><use href="#i-send"/></svg>
                <span>Nenhuma mensagem de outreach</span>
                <button class="btn btn-primary" style="margin-top:12px" onclick="panelGenerateOutreach()"><svg><use href="#i-send"/></svg> Gerar Proposta</button>
            </div>`;
        }

        // Activity tab — load prospect-specific activities
        const actEl = document.getElementById('panel-activity-content');
        actEl.innerHTML = '<div class="empty-state"><svg style="animation:spin 1s linear infinite"><use href="#i-refresh"/></svg><span>Carregando...</span></div>';
        api(`/api/activities?prospect_id=${id}&limit=20`).then(data => {
            const acts = data.activities || [];
            if (!acts.length) {
                actEl.innerHTML = '<div class="empty-state"><svg><use href="#i-clock"/></svg><span>Nenhuma atividade registrada</span></div>';
            } else {
                actEl.innerHTML = acts.map(a => `<div style="display:flex;gap:10px;padding:10px 0;border-bottom:1px solid var(--border)">
                    <div style="width:32px;height:32px;border-radius:50%;background:var(--s3);display:flex;align-items:center;justify-content:center;flex-shrink:0">
                        <svg style="width:16px;height:16px;stroke:var(--text-2)"><use href="#i-${a.type === 'audit' ? 'clipboard' : a.type === 'outreach' ? 'send' : a.type === 'scraping' ? 'search' : 'clock'}"/></svg>
                    </div>
                    <div style="flex:1;min-width:0">
                        <div style="font-size:12px;font-weight:600">${escapeHtml(a.title || a.type)}</div>
                        ${a.description ? `<div style="font-size:11px;color:var(--text-2);margin-top:2px">${escapeHtml(a.description)}</div>` : ''}
                        <div style="font-size:10px;color:var(--text-3);margin-top:4px">${formatDate(a.created_at)} ${formatTime(a.created_at)}</div>
                    </div>
                </div>`).join('');
            }
        }).catch(() => {
            actEl.innerHTML = '<div class="empty-state"><svg><use href="#i-clock"/></svg><span>Nenhuma atividade registrada</span></div>';
        });

        // Show panel
        switchPanelTab('overview', document.querySelector('.tabs .tab-btn'));
        panel.classList.add('active');
        overlay.classList.add('active');
    } catch (e) {
        toast('Erro ao carregar prospect: ' + e.message, 'error');
    }
}

function closePanel() {
    document.getElementById('prospect-panel').classList.remove('active');
    document.getElementById('panel-overlay').classList.remove('active');
    currentProspect = null;
}

function switchPanelTab(tab, btn) {
    ['overview', 'audit', 'outreach', 'activity'].forEach(t => {
        const el = document.getElementById(`panel-tab-${t}`);
        if (el) el.style.display = t === tab ? '' : 'none';
    });
    document.querySelectorAll('.slide-panel .tab-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
}

async function updateProspectStage(stage) {
    if (!currentProspect) return;
    try {
        await api(`/api/prospects/${currentProspect.id}`, { method: 'PATCH', body: JSON.stringify({ stage }) });
        toast(`Estagio atualizado para ${stage}`, 'success');
        currentProspect.stage = stage;
    } catch (e) { toast('Erro: ' + e.message, 'error'); }
}

function openPanelLink(type) {
    if (!currentProspect) return;
    const p = currentProspect;
    switch (type) {
        case 'maps': window.open(p.maps_url || p.google_maps_url || `https://www.google.com/maps/search/${encodeURIComponent(p.name + ' ' + (p.city || ''))}`, '_blank'); break;
        case 'call': if (p.phone) window.open(`tel:${p.phone}`); break;
        case 'website': if (p.website) window.open(p.website, '_blank'); break;
        case 'whatsapp': if (p.phone) window.open(`https://wa.me/${(p.phone || '').replace(/\D/g, '')}`, '_blank'); break;
    }
}

function copyOutreach() {
    if (!currentProspect) return;
    const msg = currentProspect.outreach_message || currentProspect.message || '';
    navigator.clipboard.writeText(msg).then(() => toast('Mensagem copiada!', 'success')).catch(() => toast('Erro ao copiar', 'error'));
}

async function panelGenerateOutreach() {
    if (!currentProspect) return;
    const el = document.getElementById('panel-outreach-content');
    el.innerHTML = '<div class="empty-state"><svg style="animation:spin 1s linear infinite"><use href="#i-refresh"/></svg><span>Gerando proposta...</span></div>';
    try {
        const result = await api(`/api/outreach/generate/${currentProspect.id}`, { method: 'POST' });
        const msg = result.whatsapp_message || result.message || '';
        currentProspect.outreach_message = msg;
        toast('Proposta gerada!', 'success');
        openProspectPanel(currentProspect.id);
    } catch (e) {
        toast('Erro: ' + e.message, 'error');
        el.innerHTML = `<div class="empty-state"><svg><use href="#i-x"/></svg><span>Erro ao gerar: ${escapeHtml(e.message)}</span><button class="btn btn-primary" style="margin-top:12px" onclick="panelGenerateOutreach()"><svg><use href="#i-refresh"/></svg> Tentar novamente</button></div>`;
    }
}

async function panelRegenOutreach() {
    const btn = document.getElementById('panel-regen-btn');
    if (btn) { btn.innerHTML = '<svg style="animation:spin 1s linear infinite"><use href="#i-refresh"/></svg> Gerando...'; btn.disabled = true; }
    await panelGenerateOutreach();
}

function togglePanelEdit() {
    const form = document.getElementById('panel-edit-form');
    const visible = form.style.display !== 'none';
    if (visible) {
        form.style.display = 'none';
    } else {
        if (currentProspect) {
            document.getElementById('edit-name').value = currentProspect.business_name || currentProspect.name || '';
            document.getElementById('edit-phone').value = currentProspect.phone || '';
            document.getElementById('edit-website').value = currentProspect.website || '';
            document.getElementById('edit-email').value = currentProspect.email || '';
        }
        form.style.display = '';
        form.style.animation = 'fade-in 0.2s var(--ease) both';
        document.getElementById('edit-name').focus();
    }
}

async function savePanelEdit() {
    if (!currentProspect) return;
    const data = {
        business_name: document.getElementById('edit-name').value.trim(),
        phone: document.getElementById('edit-phone').value.trim(),
        website: document.getElementById('edit-website').value.trim(),
        email: document.getElementById('edit-email').value.trim(),
    };
    try {
        await api(`/api/prospects/${currentProspect.id}`, { method: 'PATCH', body: JSON.stringify(data) });
        Object.assign(currentProspect, data);
        if (data.business_name) {
            currentProspect.name = data.business_name;
            document.getElementById('panel-name').textContent = data.business_name;
        }
        document.getElementById('panel-phone').textContent = data.phone || '--';
        document.getElementById('panel-website').textContent = data.website || 'Sem site';
        document.getElementById('panel-edit-form').style.display = 'none';
        toast('Prospect atualizado!', 'success');
    } catch (e) { toast('Erro: ' + e.message, 'error'); }
}

async function requestStrategy() {
    if (!currentProspect) return;
    try {
        const result = await api(`/api/prospects/${currentProspect.id}/strategy`, { method: 'POST' });
        toast('Estrategia solicitada ao Claude', 'success');
        if (result.strategy || result.data) {
            const auditEl = document.getElementById('panel-audit-content');
            const content = result.strategy || result.data;
            auditEl.innerHTML = `<div style="font-size:12px;line-height:1.7;white-space:pre-wrap;color:var(--text-2)">${escapeHtml(typeof content === 'string' ? content : JSON.stringify(content, null, 2))}</div>`;
            switchPanelTab('audit', document.querySelectorAll('.slide-panel .tab-btn')[1]);
        }
    } catch (e) { toast('Erro: ' + e.message, 'error'); }
}

/* ============================================================
   PROPOSALS PAGE
   ============================================================ */
async function loadProposalFilters() {
    await loadFilters();
}

async function loadProposals() {
    const search = document.getElementById('proposal-search').value;
    const city = document.getElementById('proposal-filter-city').value;
    const category = document.getElementById('proposal-filter-category').value;
    const params = new URLSearchParams({ stage: 'qualified', limit: 50 });
    if (search) params.set('search', search);
    if (city) params.set('city', city);
    if (category) params.set('category', category);

    // UX-RM-F7-A — skeleton while fetching
    const _gridPre = document.getElementById('proposals-grid');
    if (_gridPre && window.skeletonPatterns) {
        _gridPre.innerHTML = window.skeletonPatterns.card_grid(10);
    }

    try {
        const data = await api(`/api/prospects?${params}`);
        proposalProspects = data.prospects || data.items || data || [];
        renderProposals();
    } catch (e) {
        document.getElementById('proposals-grid').innerHTML = `<div class="empty-state"><svg><use href="#i-x"/></svg><span>Erro: ${escapeHtml(e.message)}</span></div>`;
    }
}

function renderProposals() {
    const sentFilter = document.getElementById('proposal-filter-sent').value;
    let filtered = proposalProspects;
    if (sentFilter === 'sent') filtered = filtered.filter(p => sentProposals.includes(p.id));
    else if (sentFilter === 'unsent') filtered = filtered.filter(p => !sentProposals.includes(p.id));

    document.getElementById('proposal-count').textContent = `${filtered.length} propostas`;
    const grid = document.getElementById('proposals-grid');

    if (!filtered.length) {
        grid.innerHTML = '<div class="empty-state"><svg><use href="#i-send"/></svg><span>Nenhuma proposta encontrada</span></div>';
        return;
    }

    grid.innerHTML = filtered.map(p => {
        const isSent = sentProposals.includes(p.id);
        const msg = p.outreach_message || p.message || '';
        const hasWebsite = !!p.website;
        return `<div class="card" style="padding:0;overflow:hidden">
            <div class="photo-large">${p.photo_ref ? `<img src="${photoUrl(p.photo_ref)}" onerror="this.parentElement.innerHTML='<svg><use href=\\'#i-store\\'/></svg>'">` : `<svg><use href="#i-store"/></svg>`}</div>
            <div style="padding:16px">
                <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:6px">
                    <div style="font-size:15px;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">${escapeHtml(p.name || p.business_name)}</div>
                    <span class="score-badge ${scoreClass(p.score)}">${p.score ?? '--'}</span>
                </div>
                <div style="font-size:11px;color:var(--text-2);margin-bottom:10px">${escapeHtml(p.category || '')} - ${escapeHtml(p.city || '')}</div>
                <div style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap">
                    ${hasWebsite ? '<span class="badge badge-blue">Com site</span>' : '<span class="badge badge-amber">Sem site</span>'}
                    ${stageBadge(p.stage)}
                    ${isSent ? '<span class="badge badge-green">Enviado</span>' : ''}
                </div>
                ${msg ? `<details style="margin-bottom:12px"><summary style="font-size:11px;color:var(--text-2);cursor:pointer;margin-bottom:6px">Ver mensagem</summary><div style="font-size:12px;color:var(--text-2);line-height:1.5;background:var(--s3);border-radius:var(--r-sm);padding:10px;max-height:150px;overflow-y:auto;white-space:pre-wrap">${escapeHtml(msg)}</div></details>` : ''}
                <div style="display:flex;gap:6px;flex-wrap:wrap">
                    ${msg ? `<button class="btn btn-ghost btn-sm" onclick="copyText('${p.id}')"><svg><use href="#i-copy"/></svg> Copiar</button>` : ''}
                    ${p.phone ? `<button class="btn btn-ghost btn-sm" onclick="window.open('https://wa.me/${(p.phone||'').replace(/\\D/g,'')}${msg ? '?text=' + encodeURIComponent(msg) : ''}','_blank')"><svg><use href="#i-send"/></svg> WhatsApp</button>` : ''}
                    ${p.email ? `<button class="btn btn-ghost btn-sm" onclick="window.open('mailto:${escapeHtml(p.email)}','_blank')"><svg><use href="#i-mail"/></svg> Email</button>` : ''}
                    <button class="btn btn-ghost btn-sm ${isSent ? 'btn-green' : ''}" onclick="toggleSent('${p.id}',this)"><svg><use href="#i-check"/></svg> ${isSent ? 'Enviado' : 'Marcar Enviado'}</button>
                </div>
            </div>
        </div>`;
    }).join('');
    animateGridChildren('#proposals-grid');
}

function copyText(prospectId) {
    const p = proposalProspects.find(x => x.id === prospectId);
    if (!p) return;
    navigator.clipboard.writeText(p.outreach_message || p.message || '').then(() => toast('Copiado!', 'success')).catch(() => toast('Erro ao copiar', 'error'));
}

function toggleSent(id, btn) {
    const idx = sentProposals.indexOf(id);
    if (idx >= 0) {
        sentProposals.splice(idx, 1);
    } else {
        sentProposals.push(id);
    }
    localStorage.setItem('hermes_sent_proposals', JSON.stringify(sentProposals));
    renderProposals();
}

/* ============================================================
   PIPELINE PAGE
   ============================================================ */
/* ============================================================
   AUDIT PAGE
   ============================================================ */
let auditPollingInterval = null;

async function loadAuditPage() {
    loadAuditStats();
    loadAuditStatus();
    loadAuditResults();
}

async function loadAuditStats() {
    try {
        const data = await api('/api/dashboard');
        const stages = data.by_stage || {};
        const discovered = (stages.discovered || 0) + (stages.new || 0);
        const audited = (stages.audited || 0) + (stages.qualified || 0) + (stages.outreach || 0) + (stages.converted || 0);
        const total = data.total_prospects || 0;

        document.getElementById('audit-stat-pending').textContent = discovered.toLocaleString();
        document.getElementById('audit-stat-done').textContent = audited.toLocaleString();

        const prospectsData = await api('/api/prospects?min_score=70&limit=1&offset=0');
        document.getElementById('audit-stat-high').textContent = prospectsData.total?.toLocaleString() || '0';
    } catch { /* silent */ }
}

async function loadAuditStatus() {
    try {
        const data = await api('/api/audit/status');
        const dot = document.getElementById('audit-status-dot');
        const label = document.getElementById('audit-status-label');
        const btn = document.getElementById('btn-audit-start');
        const progressSection = document.getElementById('audit-progress-section');

        if (data.running) {
            dot.className = 'status-dot running';
            label.textContent = `Auditando... (${data.done}/${data.total})`;
            btn.disabled = true;
            btn.innerHTML = '<svg><use href="#i-clock"/></svg> Auditando...';
            progressSection.style.display = 'block';

            const pct = data.total > 0 ? Math.round((data.done / data.total) * 100) : 0;
            document.getElementById('audit-progress-text').textContent = `${data.done} / ${data.total} auditados`;
            document.getElementById('audit-progress-pct').textContent = `${pct}%`;
            document.getElementById('audit-progress-bar').style.width = `${pct}%`;

            if (data.results && data.results.length) {
                const log = document.getElementById('audit-log');
                log.innerHTML = data.results.slice(-15).map(r =>
                    `<div class="log-line"><span style="color:var(--${r.score >= 70 ? 'green' : r.score >= 50 ? 'amber' : 'text-3'})">[${r.score}]</span> ${escapeHtml(r.name)} &rarr; ${r.stage}</div>`
                ).join('');
                if (data.errors?.length) {
                    log.innerHTML += data.errors.slice(-5).map(e =>
                        `<div class="log-line" style="color:var(--red)">${escapeHtml(e)}</div>`
                    ).join('');
                }
                log.scrollTop = log.scrollHeight;
            }

            if (!auditPollingInterval) {
                auditPollingInterval = setInterval(loadAuditStatus, 3000);
            }
        } else {
            dot.className = 'status-dot';
            dot.style.background = data.finished_at ? 'var(--blue)' : 'var(--text-3)';
            label.textContent = data.finished_at ? `Concluido (${data.done} auditados)` : 'Idle';
            btn.disabled = false;
            btn.innerHTML = '<svg><use href="#i-play"/></svg> Iniciar Auditoria';

            if (data.total > 0) {
                progressSection.style.display = 'block';
                document.getElementById('audit-progress-text').textContent = `${data.done} / ${data.total} auditados`;
                document.getElementById('audit-progress-pct').textContent = '100%';
                document.getElementById('audit-progress-bar').style.width = '100%';
            }

            if (data.results && data.results.length) {
                const log = document.getElementById('audit-log');
                log.innerHTML = data.results.slice(-15).map(r =>
                    `<div class="log-line"><span style="color:var(--${r.score >= 70 ? 'green' : r.score >= 50 ? 'amber' : 'text-3'})">[${r.score}]</span> ${escapeHtml(r.name)} &rarr; ${r.stage}</div>`
                ).join('');
                if (data.errors?.length) {
                    log.innerHTML += data.errors.slice(-5).map(e =>
                        `<div class="log-line" style="color:var(--red)">${escapeHtml(e)}</div>`
                    ).join('');
                }
            }

            if (auditPollingInterval) {
                clearInterval(auditPollingInterval);
                auditPollingInterval = null;
                loadAuditStats();
                loadAuditResults();
            }
        }
    } catch (e) {
        document.getElementById('audit-status-label').textContent = 'Erro: ' + e.message;
    }
}

async function startAudit() {
    const stage = document.getElementById('audit-target-stage').value;
    const batchSize = parseInt(document.getElementById('audit-batch-size').value) || 50;

    try {
        const result = await api('/api/audit/start', {
            method: 'POST',
            body: JSON.stringify({ batch_size: batchSize, stage })
        });

        if (result.status === 'already_running') {
            toast('Auditoria ja esta em andamento', 'warning');
        } else if (result.status === 'nothing_to_audit') {
            toast('Nenhum prospect pendente para auditar neste estagio', 'info');
        } else {
            toast(`Auditoria iniciada: ${result.total} prospects`, 'success');
            document.getElementById('audit-log').innerHTML = `<div class="log-line" style="color:var(--blue)">Iniciando auditoria de ${result.total} prospects (stage: ${stage})...</div>`;
        }

        setTimeout(loadAuditStatus, 1000);
    } catch (e) {
        toast('Erro ao iniciar auditoria: ' + e.message, 'error');
    }
}

async function loadAuditResults() {
    try {
        const data = await api('/api/prospects?stage=audited&limit=30&offset=0');
        const tbody = document.getElementById('audit-results-tbody');
        const empty = document.getElementById('audit-results-empty');
        const count = document.getElementById('audit-results-count');
        const prospects = data.prospects || [];

        count.textContent = data.total || 0;

        if (!prospects.length) {
            tbody.innerHTML = '';
            empty.style.display = 'flex';
            return;
        }

        empty.style.display = 'none';
        tbody.innerHTML = prospects.map(p => {
            const audit = p.audit_summary || '';
            const hasSSL = !audit.includes('Sem HTTPS') && !audit.includes('SEM WEBSITE');
            const hasMobile = !audit.includes('viewport mobile');
            const hasWebsite = !audit.includes('SEM WEBSITE');
            const issues = [];
            if (audit.includes('SEM WEBSITE')) issues.push('Sem site');
            if (audit.includes('Sem HTTPS')) issues.push('Sem SSL');
            if (audit.includes('viewport mobile')) issues.push('Sem mobile');
            if (audit.includes('lento')) issues.push('Lento');
            if (audit.includes('inacess')) issues.push('Offline');

            const scoreColor = p.score >= 70 ? 'green' : p.score >= 50 ? 'amber' : 'text-3';
            const stageColors = {discovered:'var(--text-3)',qualified:'var(--lime)',audited:'var(--blue)',outreach:'var(--green)',converted:'var(--accent-l)'};

            return `<tr style="border-bottom:1px solid var(--border);transition:background 0.15s" onmouseover="this.style.background='var(--s3)'" onmouseout="this.style.background=''">
                <td style="padding:8px 16px;font-size:12px;font-weight:600;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(p.business_name || p.name)}</td>
                <td style="padding:8px;font-size:11px;color:var(--text-2)">${escapeHtml(p.category || '--')}</td>
                <td style="padding:8px;text-align:center"><span style="color:var(--${hasWebsite ? 'green' : 'red'})">${hasWebsite ? '<svg style="width:14px;height:14px"><use href="#i-check"/></svg>' : '<svg style="width:14px;height:14px"><use href="#i-x"/></svg>'}</span></td>
                <td style="padding:8px;text-align:center"><span style="color:var(--${hasSSL ? 'green' : 'red'})">${hasSSL ? '<svg style="width:14px;height:14px"><use href="#i-check"/></svg>' : '<svg style="width:14px;height:14px"><use href="#i-x"/></svg>'}</span></td>
                <td style="padding:8px;text-align:center"><span style="color:var(--${hasMobile ? 'green' : 'amber'})">${hasMobile ? '<svg style="width:14px;height:14px"><use href="#i-check"/></svg>' : '<svg style="width:14px;height:14px"><use href="#i-x"/></svg>'}</span></td>
                <td style="padding:8px;text-align:center"><span class="badge" style="background:var(--${scoreColor}-dim);color:var(--${scoreColor});font-size:11px;font-weight:700">${p.score}</span></td>
                <td style="padding:8px"><span class="badge" style="background:rgba(255,255,255,0.06);color:${stageColors[p.stage] || 'var(--text-2)'};font-size:10px">${p.stage}</span></td>
                <td style="padding:8px;font-size:11px;color:var(--text-2);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${issues.join(', ') || '<span style="color:var(--green)">Nenhum</span>'}</td>
            </tr>`;
        }).join('');
    } catch { /* silent */ }
}

async function auditSingle(prospectId, btn) {
    const origHTML = btn.innerHTML;
    btn.innerHTML = '<svg style="animation:spin 1s linear infinite"><use href="#i-refresh"/></svg>';
    btn.disabled = true;
    try {
        const result = await api(`/api/audit/prospect/${prospectId}`, { method: 'POST' });
        toast(`Auditado: score ${result.score} → ${result.new_stage}`, 'success');
        loadProspects();
    } catch (e) {
        toast('Erro na auditoria: ' + e.message, 'error');
    } finally {
        btn.innerHTML = origHTML;
        btn.disabled = false;
    }
}

/* ============================================================
   PIPELINE BUILDER
   ============================================================ */
let pipelinesData = [];
let currentExecId = null;
let execPollInterval = null;
let selectedPipelineType = 'linkedin_viewer';

const PIPELINE_TYPE_META = {
    linkedin_viewer: { icon: '#i-linkedin', label: 'LinkedIn Viewer', color: 'var(--blue)', defaultTargets: { roles: ['tech recruiter', 'project manager', 'SMB owner'], location: 'Brazil', max_profiles: 500 } },
    scraper: { icon: '#i-search', label: 'Scraper', color: 'var(--lime)', defaultTargets: { cities: ['Cuiaba'], categories: [], only_no_site: false } },
    audit: { icon: '#i-check-square', label: 'Auditoria', color: 'var(--amber)', defaultTargets: { batch_size: 50, stage: 'discovered' } },
    outreach: { icon: '#i-send', label: 'Outreach', color: 'var(--green)', defaultTargets: { batch_size: 30, stage: 'audited' } },
    custom: { icon: '#i-code', label: 'Custom', color: 'var(--accent-l)', defaultTargets: {} },
};

async function loadPipeline() {
    const grid = document.getElementById('pipeline-grid');
    try {
        const data = await api('/api/pipelines');
        pipelinesData = data.pipelines || [];
        if (!pipelinesData.length) {
            grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1">
                <svg><use href="#i-layers"/></svg>
                <span>Nenhum pipeline configurado ainda</span>
                <button class="btn btn-primary" style="margin-top:12px" onclick="openPipelineModal()"><svg><use href="#i-plus"/></svg> Criar Primeiro Pipeline</button>
            </div>`;
            return;
        }
        grid.innerHTML = pipelinesData.map(p => {
            const meta = PIPELINE_TYPE_META[p.type] || PIPELINE_TYPE_META.custom;
            const sched = p.schedule_config || {};
            const schedText = sched.repeat === 'daily' ? 'Diario' : sched.repeat === 'weekdays' ? 'Dias uteis' : sched.repeat === 'weekly' ? 'Semanal' : sched.repeat === 'custom' ? (sched.days||[]).join(', ') : 'Uma vez';
            const lastExec = p.last_execution;
            const statusBadge = lastExec ? `<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:var(--r-xs);background:${lastExec.status === 'completed' ? 'rgba(52,211,153,0.12)' : lastExec.status === 'running' ? 'rgba(209,254,23,0.12)' : 'rgba(251,113,133,0.12)'};color:${lastExec.status === 'completed' ? 'var(--green)' : lastExec.status === 'running' ? 'var(--lime)' : 'var(--pink)'}">${lastExec.status}</span>` : '';
            return `<div class="card pipeline-card" style="cursor:default;position:relative;overflow:hidden" data-pipeline-id="${p.id}">
                <div style="position:absolute;top:0;left:0;right:0;height:3px;background:${meta.color};opacity:0.6"></div>
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;padding-top:6px">
                    <div style="display:flex;gap:10px;align-items:center">
                        <div style="width:36px;height:36px;border-radius:var(--r-sm);background:var(--s3);display:flex;align-items:center;justify-content:center">
                            <svg style="width:18px;height:18px;stroke:${meta.color}"><use href="${meta.icon}"/></svg>
                        </div>
                        <div>
                            <div style="font-size:14px;font-weight:600;color:var(--text-1)">${escapeHtml(p.name)}</div>
                            <div style="font-size:11px;color:var(--text-3)">${meta.label} ${statusBadge}</div>
                        </div>
                    </div>
                    <div style="display:flex;gap:4px">
                        <button class="btn btn-ghost btn-sm" onclick="editPipeline(${p.id})" data-tip="Editar"><svg><use href="#i-edit"/></svg></button>
                        <button class="btn btn-ghost btn-sm" onclick="deletePipeline(${p.id})" data-tip="Excluir"><svg><use href="#i-trash"/></svg></button>
                    </div>
                </div>
                ${p.description ? `<div style="font-size:12px;color:var(--text-2);margin-bottom:12px;line-height:1.5">${escapeHtml(p.description)}</div>` : ''}
                ${p.prompt ? `<div style="font-size:11px;color:var(--text-3);background:var(--s2);border-radius:var(--r-xs);padding:8px 10px;margin-bottom:12px;max-height:60px;overflow:hidden;line-height:1.4">${escapeHtml(p.prompt.substring(0, 150))}${p.prompt.length > 150 ? '...' : ''}</div>` : ''}
                <div style="display:flex;gap:12px;font-size:11px;color:var(--text-3);margin-bottom:14px;flex-wrap:wrap">
                    <span style="display:flex;align-items:center;gap:4px"><svg style="width:12px;height:12px"><use href="#i-clock"/></svg> ${sched.time || '--:--'}</span>
                    <span style="display:flex;align-items:center;gap:4px"><svg style="width:12px;height:12px"><use href="#i-repeat"/></svg> ${schedText}</span>
                    <span style="display:flex;align-items:center;gap:4px"><svg style="width:12px;height:12px"><use href="#i-zap"/></svg> ${p.total_runs || 0} runs</span>
                </div>
                <div style="display:flex;gap:8px">
                    <button class="btn btn-primary btn-sm" onclick="executePipeline(${p.id})" style="flex:1"><svg><use href="#i-play"/></svg> Executar Agora</button>
                    <button class="btn btn-ghost btn-sm" onclick="viewPipelineExecutions(${p.id})"><svg><use href="#i-eye"/></svg> Historico</button>
                </div>
            </div>`;
        }).join('');
        const countEl = document.getElementById('pl-templates-count');
        if (countEl) countEl.textContent = `${pipelinesData.length} pipeline${pipelinesData.length !== 1 ? 's' : ''}`;
    } catch (e) {
        grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><svg><use href="#i-x"/></svg><span>Erro ao carregar pipelines: ${escapeHtml(e.message)}</span></div>`;
    }
    refreshPipelineLive();
    loadExecutionHistory();
}

function openPipelineModal(editData) {
    const modal = document.getElementById('pipeline-modal');
    document.getElementById('pipeline-modal-title').textContent = editData ? 'Editar Pipeline' : 'Novo Pipeline';
    document.getElementById('pl-edit-id').value = editData ? editData.id : '';
    document.getElementById('pl-name').value = editData ? editData.name : '';
    document.getElementById('pl-description').value = editData ? (editData.description || '') : '';
    document.getElementById('pl-prompt').value = editData ? (editData.prompt || '') : '';

    const type = editData ? editData.type : 'linkedin_viewer';
    selectedPipelineType = type;
    document.querySelectorAll('#pl-type-selector .wq-tab').forEach(b => {
        b.classList.toggle('active', b.dataset.pltype === type);
    });
    renderTargetFields(type, editData ? editData.targets_config : null);

    const sched = editData ? (editData.schedule_config || {}) : {};
    document.getElementById('pl-schedule-time').value = sched.time || '02:00';
    document.getElementById('pl-schedule-repeat').value = sched.repeat || 'once';
    const days = sched.days || [];
    document.querySelectorAll('#pl-schedule-days .wq-tab').forEach(b => {
        b.classList.toggle('active', days.includes(b.dataset.day));
    });

    modal.classList.add('active');
}

function closePipelineModal() {
    document.getElementById('pipeline-modal').classList.remove('active');
}

function selectPipelineType(type, btn) {
    selectedPipelineType = type;
    document.querySelectorAll('#pl-type-selector .wq-tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    renderTargetFields(type, null);
}

function renderTargetFields(type, existing) {
    const container = document.getElementById('pl-targets-fields');
    const defaults = PIPELINE_TYPE_META[type]?.defaultTargets || {};
    const data = existing || defaults;

    if (type === 'linkedin_viewer') {
        container.innerHTML = `
            <div class="input-wrap"><label>Roles (separados por virgula)</label>
                <input type="text" id="pl-t-roles" value="${(data.roles || defaults.roles || []).join(', ')}">
            </div>
            <div class="input-wrap"><label>Localizacao</label>
                <input type="text" id="pl-t-location" value="${data.location || defaults.location || 'Brazil'}">
            </div>
            <div class="input-wrap"><label>Max perfis por execucao</label>
                <input type="number" id="pl-t-max" value="${data.max_profiles || defaults.max_profiles || 500}">
            </div>
        `;
    } else if (type === 'scraper') {
        container.innerHTML = `
            <div class="input-wrap"><label>Cidades (separadas por virgula)</label>
                <input type="text" id="pl-t-cities" value="${(data.cities || []).join(', ')}">
            </div>
            <div class="input-wrap"><label>Categorias</label>
                <input type="text" id="pl-t-categories" value="${(data.categories || []).join(', ')}">
            </div>
        `;
    } else if (type === 'audit') {
        container.innerHTML = `
            <div class="input-wrap"><label>Batch size</label>
                <input type="number" id="pl-t-batch" value="${data.batch_size || 50}">
            </div>
            <div class="input-wrap"><label>Stage alvo</label>
                <input type="text" id="pl-t-stage" value="${data.stage || 'discovered'}">
            </div>
        `;
    } else if (type === 'outreach') {
        container.innerHTML = `
            <div class="input-wrap"><label>Batch size</label>
                <input type="number" id="pl-t-batch" value="${data.batch_size || 30}">
            </div>
            <div class="input-wrap"><label>Stage alvo</label>
                <input type="text" id="pl-t-stage" value="${data.stage || 'audited'}">
            </div>
        `;
    } else {
        container.innerHTML = `<div class="input-wrap" style="grid-column:1/-1"><label>Parametros JSON (opcional)</label>
            <textarea id="pl-t-custom" rows="3" style="width:100%;background:var(--s2);border:1px solid var(--border);border-radius:var(--r-sm);color:var(--text-1);padding:8px;font-size:11px;font-family:monospace;resize:vertical">${JSON.stringify(data, null, 2)}</textarea>
        </div>`;
    }
}

function getTargetsFromForm() {
    const type = selectedPipelineType;
    if (type === 'linkedin_viewer') {
        return {
            roles: (document.getElementById('pl-t-roles')?.value || '').split(',').map(s => s.trim()).filter(Boolean),
            location: document.getElementById('pl-t-location')?.value || 'Brazil',
            max_profiles: parseInt(document.getElementById('pl-t-max')?.value) || 500,
        };
    } else if (type === 'scraper') {
        return {
            cities: (document.getElementById('pl-t-cities')?.value || '').split(',').map(s => s.trim()).filter(Boolean),
            categories: (document.getElementById('pl-t-categories')?.value || '').split(',').map(s => s.trim()).filter(Boolean),
        };
    } else if (type === 'audit' || type === 'outreach') {
        return {
            batch_size: parseInt(document.getElementById('pl-t-batch')?.value) || 50,
            stage: document.getElementById('pl-t-stage')?.value || 'discovered',
        };
    } else {
        try { return JSON.parse(document.getElementById('pl-t-custom')?.value || '{}'); } catch { return {}; }
    }
}

function getScheduleFromForm() {
    const days = [];
    document.querySelectorAll('#pl-schedule-days .wq-tab.active').forEach(b => days.push(b.dataset.day));
    return {
        time: document.getElementById('pl-schedule-time')?.value || '02:00',
        repeat: document.getElementById('pl-schedule-repeat')?.value || 'once',
        days,
    };
}

function toggleScheduleDay(btn) {
    btn.classList.toggle('active');
}

async function savePipeline() {
    const editId = document.getElementById('pl-edit-id').value;
    const payload = {
        name: document.getElementById('pl-name').value.trim(),
        type: selectedPipelineType,
        description: document.getElementById('pl-description').value.trim(),
        prompt: document.getElementById('pl-prompt').value.trim(),
        targets_config: getTargetsFromForm(),
        schedule_config: getScheduleFromForm(),
    };
    if (!payload.name) { toast('Nome e obrigatorio', 'error'); return; }

    const btn = document.getElementById('pl-save-btn');
    btn.disabled = true;
    try {
        if (editId) {
            await api(`/api/pipelines/${editId}`, { method: 'PATCH', body: JSON.stringify(payload) });
            toast('Pipeline atualizado', 'success');
        } else {
            await api('/api/pipelines', { method: 'POST', body: JSON.stringify(payload) });
            toast('Pipeline criado', 'success');
        }
        closePipelineModal();
        loadPipeline();
    } catch (e) {
        toast('Erro: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
    }
}

async function editPipeline(id) {
    try {
        const data = await api(`/api/pipelines/${id}`);
        openPipelineModal(data);
    } catch (e) { toast('Erro ao carregar pipeline', 'error'); }
}

async function deletePipeline(id) {
    if (!confirm('Excluir este pipeline e todo seu historico?')) return;
    try {
        await api(`/api/pipelines/${id}`, { method: 'DELETE' });
        toast('Pipeline excluido', 'success');
        loadPipeline();
    } catch (e) { toast('Erro: ' + e.message, 'error'); }
}

async function executePipeline(id) {
    try {
        const result = await api(`/api/pipelines/${id}/execute`, { method: 'POST', body: JSON.stringify({ template_id: id }) });
        currentExecId = result.execution_id;
        plExecStartTime = Date.now();
        toast('Pipeline iniciado', 'success');
        activateCommandCenter();
        startPlLivePolling();
        loadPipeline();
    } catch (e) { toast('Erro ao executar: ' + e.message, 'error'); }
}

let plLivePollInterval = null;
let plFeedLogCount = 0;
let plExecStartTime = null;
let plElapsedInterval = null;

function activateCommandCenter() {
    const monitor = document.getElementById('pl-live-monitor');
    monitor.classList.remove('idle');
    document.getElementById('pl-pulse').classList.remove('idle');
    document.getElementById('pl-steps').style.display = 'flex';
    document.getElementById('pl-live-stats').style.display = 'grid';
    document.getElementById('pl-live-status').textContent = 'Executando...';
    document.getElementById('pl-feed').innerHTML = '<div class="hl-feed-line"><span class="hl-feed-time">' + new Date().toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit'}) + '</span><span class="hl-feed-phase" style="background:rgba(124,58,237,0.15);color:var(--accent-l)">init</span><span style="color:var(--text-2)">Pipeline disparado, conectando ao Hermes...</span></div>';
    plFeedLogCount = 0;
    document.getElementById('pl-live-monitor').scrollIntoView({ behavior: 'smooth', block: 'start' });

    if (plElapsedInterval) clearInterval(plElapsedInterval);
    plExecStartTime = Date.now();
    plElapsedInterval = setInterval(updateElapsedTimer, 1000);
}

function updateElapsedTimer() {
    if (!plExecStartTime) return;
    const elapsed = Math.floor((Date.now() - plExecStartTime) / 1000);
    const mm = String(Math.floor(elapsed / 60)).padStart(2, '0');
    const ss = String(elapsed % 60).padStart(2, '0');
    const el = document.getElementById('pl-stat-elapsed');
    if (el) el.textContent = `${mm}:${ss}`;
    const timerEl = document.getElementById('pl-live-timer');
    if (timerEl) timerEl.textContent = `${mm}:${ss}`;
}

function startPlLivePolling() {
    if (plLivePollInterval) clearInterval(plLivePollInterval);
    plLivePollInterval = setInterval(refreshPipelineLive, 2000);
}

async function refreshPipelineLive() {
    try {
        const data = await api('/api/pipeline-executions/active');
        const active = data.active || [];
        const recent = data.recent || [];
        const monitor = document.getElementById('pl-live-monitor');
        const pulse = document.getElementById('pl-pulse');
        const stepsEl = document.getElementById('pl-steps');
        const statsEl = document.getElementById('pl-live-stats');
        const statusText = document.getElementById('pl-live-status');
        const activeContainer = document.getElementById('pl-active-execs');
        const feed = document.getElementById('pl-feed');

        if (active.length > 0) {
            monitor.classList.remove('idle');
            pulse.classList.remove('idle');
            stepsEl.style.display = 'flex';
            statsEl.style.display = 'grid';
            statusText.textContent = `${active.length} pipeline${active.length > 1 ? 's' : ''} em execucao`;

            const resultsContainer = document.getElementById('pl-results-container');
            if (resultsContainer) resultsContainer.innerHTML = '';

            let totalProcessed = 0, totalItems = 0;
            active.forEach(ex => { totalProcessed += (ex.processed_items || 0); totalItems += (ex.total_items || 0); });
            document.getElementById('pl-stat-processed').textContent = totalProcessed;
            document.getElementById('pl-stat-total').textContent = totalItems || '?';
            document.getElementById('pl-stat-active').textContent = active.length;

            const mainExec = active[0];
            const logs = mainExec.log || [];
            const lastLog = logs.length ? logs[logs.length - 1] : null;
            const phase = lastLog?.phase || 'init';
            const stepIdx = PHASE_TO_STEP[phase] ?? 0;
            updatePlStepViz(stepIdx, false);

            activeContainer.innerHTML = active.map(ex => {
                const pct = ex.progress || 0;
                const meta = PIPELINE_TYPE_META[ex.pipeline_type] || PIPELINE_TYPE_META.custom;
                const elapsed = ex.started_at ? Math.floor((Date.now() - new Date(ex.started_at).getTime()) / 1000) : 0;
                const emm = String(Math.floor(elapsed / 60)).padStart(2, '0');
                const ess = String(elapsed % 60).padStart(2, '0');
                return `<div class="hl-exec-card running">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
                        <div style="display:flex;align-items:center;gap:10px">
                            <div style="width:32px;height:32px;border-radius:var(--r-xs);background:var(--s3);display:flex;align-items:center;justify-content:center">
                                <svg style="width:16px;height:16px;stroke:${meta.color}"><use href="${meta.icon}"/></svg>
                            </div>
                            <div>
                                <div style="font-size:13px;font-weight:600;color:var(--text-1)">${escapeHtml(ex.pipeline_name || 'Pipeline')}</div>
                                <div style="font-size:10px;color:var(--text-3)">${meta.label} · Iniciado ${ex.started_at ? new Date(ex.started_at).toLocaleTimeString() : '--'}</div>
                            </div>
                        </div>
                        <div style="display:flex;align-items:center;gap:8px">
                            <span style="font-size:12px;font-weight:700;color:var(--lime);font-family:monospace">${emm}:${ess}</span>
                            <span style="font-size:10px;font-weight:600;padding:3px 10px;border-radius:var(--r-xs);background:rgba(209,254,23,0.12);color:var(--lime);text-transform:uppercase">${ex.status}</span>
                        </div>
                    </div>
                    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:10px">
                        <div style="background:var(--s3);border-radius:var(--r-xs);padding:8px;text-align:center">
                            <div style="font-size:9px;color:var(--text-3);text-transform:uppercase;font-weight:600">Processados</div>
                            <div style="font-size:16px;font-weight:700;color:var(--lime)">${ex.processed_items || 0}</div>
                        </div>
                        <div style="background:var(--s3);border-radius:var(--r-xs);padding:8px;text-align:center">
                            <div style="font-size:9px;color:var(--text-3);text-transform:uppercase;font-weight:600">Total</div>
                            <div style="font-size:16px;font-weight:700;color:var(--text-1)">${ex.total_items || '?'}</div>
                        </div>
                        <div style="background:var(--s3);border-radius:var(--r-xs);padding:8px;text-align:center">
                            <div style="font-size:9px;color:var(--text-3);text-transform:uppercase;font-weight:600">Progresso</div>
                            <div style="font-size:16px;font-weight:700;color:var(--accent-l)">${pct}%</div>
                        </div>
                    </div>
                    <div style="height:4px;background:var(--s3);border-radius:2px;overflow:hidden">
                        <div style="height:100%;width:${pct}%;background:linear-gradient(90deg,var(--accent),var(--lime));border-radius:2px;transition:width 0.5s var(--ease)"></div>
                    </div>
                </div>`;
            }).join('');

            const allLogs = [];
            active.forEach(ex => {
                (ex.log || []).forEach(l => { l._pipeline = ex.pipeline_name; allLogs.push(l); });
            });
            allLogs.sort((a, b) => new Date(a.ts) - new Date(b.ts));
            if (allLogs.length !== plFeedLogCount) {
                plFeedLogCount = allLogs.length;
                feed.innerHTML = allLogs.slice(-40).map(renderFeedLine).join('');
                feed.scrollTop = feed.scrollHeight;
            }
        } else {
            if (plLivePollInterval) { clearInterval(plLivePollInterval); plLivePollInterval = null; }
            if (plElapsedInterval) { clearInterval(plElapsedInterval); plElapsedInterval = null; }

            monitor.classList.add('idle');
            pulse.classList.add('idle');
            stepsEl.style.display = 'none';
            statsEl.style.display = 'none';

            if (recent.length > 0) {
                const last = recent[0];
                const wasRunning = plExecStartTime !== null;
                statusText.textContent = wasRunning
                    ? `Concluido: ${last.pipeline_name || 'Pipeline'}`
                    : `Ultimo: ${last.pipeline_name || 'Pipeline'} (${last.status})`;

                if (wasRunning) {
                    plExecStartTime = null;
                    stepsEl.style.display = 'flex';
                    updatePlStepViz(4, last.status === 'failed');
                }

                activeContainer.innerHTML = recent.slice(0, 3).map(ex => {
                    const meta = PIPELINE_TYPE_META[ex.pipeline_type] || PIPELINE_TYPE_META.custom;
                    const statusColor = ex.status === 'completed' ? 'var(--green)' : 'var(--pink)';
                    const statusBg = ex.status === 'completed' ? 'rgba(52,211,153,0.12)' : 'rgba(251,113,133,0.12)';
                    const logs = ex.log || [];
                    const duration = ex.started_at && ex.completed_at ? Math.floor((new Date(ex.completed_at) - new Date(ex.started_at)) / 1000) : 0;
                    const dmm = String(Math.floor(duration / 60)).padStart(2, '0');
                    const dss = String(duration % 60).padStart(2, '0');
                    return `<button type="button" class="hl-exec-card" onclick="loadExecIntoFeed(${ex.id})" aria-label="Ver execucao ${escapeHtml(ex.pipeline_name || String(ex.id))}">
                        <div style="display:flex;justify-content:space-between;align-items:center">
                            <div style="display:flex;align-items:center;gap:10px">
                                <svg style="width:14px;height:14px;stroke:${statusColor}" aria-hidden="true"><use href="${meta.icon}"/></svg>
                                <span style="font-size:12px;font-weight:500;color:var(--text-2)">${escapeHtml(ex.pipeline_name || '')}</span>
                            </div>
                            <div style="display:flex;align-items:center;gap:8px">
                                <span style="font-size:10px;color:var(--text-3);font-family:monospace">${dmm}:${dss}</span>
                                <span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:var(--r-xs);background:${statusBg};color:${statusColor}">${ex.status}</span>
                                <span style="font-size:10px;color:var(--text-3)">${ex.completed_at ? new Date(ex.completed_at).toLocaleTimeString() : ''}</span>
                            </div>
                        </div>
                        ${logs.length ? `<div style="font-size:10px;color:var(--text-3);margin-top:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(logs[logs.length-1].msg.substring(0,100))}</div>` : ''}
                    </button>`;
                }).join('');

                const resultsContainer = document.getElementById('pl-results-container');
                if (resultsContainer) {
                    const resultsHtml = renderResultsPanel(recent[0]);
                    resultsContainer.innerHTML = resultsHtml || '';
                }

                const lastLogs = recent[0].log || [];
                if (lastLogs.length && (plFeedLogCount !== lastLogs.length || wasRunning)) {
                    plFeedLogCount = lastLogs.length;
                    feed.innerHTML = lastLogs.slice(-40).map(renderFeedLine).join('');
                }
            } else {
                statusText.textContent = 'Todos os sistemas idle';
                activeContainer.innerHTML = '';
                const rcEmpty = document.getElementById('pl-results-container');
                if (rcEmpty) rcEmpty.innerHTML = '';
                feed.innerHTML = '<div class="hl-feed-line" style="color:var(--text-3)"><span class="hl-feed-time">--:--</span><span>Hermes aguardando comandos. Crie ou execute um pipeline acima.</span></div>';
            }
        }
    } catch { /* silent */ }
}

let plResultsFilter = 'all';

function renderResultsPanel(exec) {
    if (!exec || !exec.result) return '';
    const r = exec.result;
    const type = r.type || exec.pipeline_type || 'custom';

    if (type === 'linkedin_viewer') return renderLinkedInResults(r, exec);
    if (type === 'scraper') return renderScraperResults(r, exec);
    return renderGenericResults(r, exec);
}

function renderLinkedInResults(r, exec) {
    const profiles = r.profiles || [];
    window._lastResultProfiles = profiles;
    const byRole = r.by_role || {};
    const byCity = r.by_city || {};
    const visited = r.profiles_visited || profiles.length;
    const found = r.profiles_found || visited;

    const roleColors = {
        'tech recruiter': { cls: 'recruiter', color: 'var(--blue)' },
        'project manager': { cls: 'pm', color: 'var(--amber)' },
        'SMB owner': { cls: 'owner', color: 'var(--green)' },
    };

    const topCities = Object.entries(byCity).sort((a,b) => b[1] - a[1]).slice(0, 5);

    let html = `<div class="pl-results">
        <div class="pl-results-header">
            <div class="pl-results-title">
                <svg style="width:18px;height:18px;stroke:var(--accent-l)"><use href="#i-linkedin"/></svg>
                Perfis Visitados
            </div>
            <span style="font-size:11px;color:var(--text-3)">${exec.completed_at ? new Date(exec.completed_at).toLocaleString('pt-BR') : ''}</span>
        </div>

        <div class="pl-results-stats">
            <div class="pl-rstat">
                <div class="pl-rstat-value" style="color:var(--lime)">${visited}</div>
                <div class="pl-rstat-label">Perfis Visitados</div>
            </div>
            <div class="pl-rstat">
                <div class="pl-rstat-value" style="color:var(--blue)">${found}</div>
                <div class="pl-rstat-label">Perfis Encontrados</div>
            </div>
            ${Object.entries(byRole).map(([role, count]) => {
                const rc = roleColors[role] || { color: 'var(--text-1)' };
                return `<div class="pl-rstat">
                    <div class="pl-rstat-value" style="color:${rc.color}">${count}</div>
                    <div class="pl-rstat-label">${escapeHtml(role)}</div>
                </div>`;
            }).join('')}
            ${topCities.length > 0 ? `<div class="pl-rstat">
                <div class="pl-rstat-value" style="color:var(--accent-l)">${topCities.length}</div>
                <div class="pl-rstat-label">Cidades</div>
            </div>` : ''}
        </div>

        <div class="pl-role-breakdown">
            <button type="button" class="pl-role-chip ${plResultsFilter === 'all' ? 'active' : ''}" onclick="filterProfiles('all')" aria-pressed="${plResultsFilter === 'all'}">
                Todos <span class="pl-role-chip-count">${profiles.length}</span>
            </button>
            ${Object.entries(byRole).map(([role, count]) => {
                const rc = roleColors[role] || { cls: '', color: 'var(--text-1)' };
                return `<button type="button" class="pl-role-chip ${plResultsFilter === role ? 'active' : ''}" onclick="filterProfiles('${escapeHtml(role)}')" aria-pressed="${plResultsFilter === role}">
                    ${escapeHtml(role)} <span class="pl-role-chip-count">${count}</span>
                </button>`;
            }).join('')}
        </div>

        <div class="pl-profile-grid" id="pl-profiles-grid">
            ${renderProfileCards(profiles)}
        </div>
    </div>`;

    return html;
}

function renderProfileCards(profiles) {
    const filtered = plResultsFilter === 'all'
        ? profiles
        : profiles.filter(p => p.role_match === plResultsFilter);

    if (!filtered.length) return '<div class="empty-state"><svg><use href="#i-users"/></svg><span>Nenhum perfil neste filtro</span></div>';

    return filtered.slice(0, 100).map(p => {
        const initials = (p.name || '??').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
        const roleColors = {
            'tech recruiter': 'recruiter',
            'project manager': 'pm',
            'SMB owner': 'owner',
        };
        const roleCls = roleColors[p.role_match] || '';
        return `<a class="pl-profile-card" href="${escapeHtml(p.url || '#')}" target="_blank" rel="noopener" title="Abrir perfil no LinkedIn">
            <div class="pl-avatar">${initials}</div>
            <div class="pl-profile-info">
                <div class="pl-profile-name">${escapeHtml(p.name)}</div>
                <div class="pl-profile-title">${escapeHtml(p.title)} · ${escapeHtml(p.company)}</div>
                <div class="pl-profile-meta">
                    <span class="pl-role-tag ${roleCls}">${escapeHtml(p.role_match || '')}</span>
                    <svg style="width:10px;height:10px"><use href="#i-map-pin"/></svg>${escapeHtml(p.city || '')}
                    ${p.visited ? '<svg style="width:10px;height:10px;stroke:var(--green)"><use href="#i-check"/></svg>' : ''}
                </div>
            </div>
            <svg style="width:14px;height:14px;stroke:var(--text-3);flex-shrink:0;align-self:center"><use href="#i-external-link"/></svg>
        </a>`;
    }).join('') + (filtered.length > 100 ? `<div style="padding:12px;text-align:center;font-size:11px;color:var(--text-3);grid-column:1/-1">Mostrando 100 de ${filtered.length} perfis</div>` : '');
}

function filterProfiles(role) {
    plResultsFilter = role;
    const grid = document.getElementById('pl-profiles-grid');
    if (!grid || !window._lastResultProfiles) return;
    grid.innerHTML = renderProfileCards(window._lastResultProfiles);
    document.querySelectorAll('.pl-role-chip').forEach(c => {
        const chipRole = c.textContent.trim().split(/\s+/).slice(0, -1).join(' ').toLowerCase();
        c.classList.toggle('active', role === 'all' ? c.textContent.includes('Todos') : chipRole === role.toLowerCase());
    });
    document.querySelectorAll('.pl-role-chip').forEach(c => {
        if (role === 'all') c.classList.toggle('active', c.onclick.toString().includes("'all'"));
        else c.classList.toggle('active', c.onclick.toString().includes(`'${role}'`));
    });
}

function renderScraperResults(r, exec) {
    return `<div class="pl-results">
        <div class="pl-results-header">
            <div class="pl-results-title"><svg style="width:18px;height:18px;stroke:var(--lime)"><use href="#i-search"/></svg> Resultados do Scraping</div>
        </div>
        <div class="pl-results-stats">
            <div class="pl-rstat"><div class="pl-rstat-value" style="color:var(--lime)">${r.total_found || 0}</div><div class="pl-rstat-label">Total Encontrados</div></div>
            <div class="pl-rstat"><div class="pl-rstat-value" style="color:var(--green)">${r.new_prospects || 0}</div><div class="pl-rstat-label">Novos Prospects</div></div>
            <div class="pl-rstat"><div class="pl-rstat-value" style="color:var(--blue)">${r.with_website || 0}</div><div class="pl-rstat-label">Com Website</div></div>
            <div class="pl-rstat"><div class="pl-rstat-value" style="color:var(--amber)">${r.without_website || 0}</div><div class="pl-rstat-label">Sem Website</div></div>
        </div>
    </div>`;
}

function renderGenericResults(r, exec) {
    const keys = Object.keys(r).filter(k => k !== 'type');
    if (!keys.length) return '';
    return `<div class="pl-results">
        <div class="pl-results-header">
            <div class="pl-results-title"><svg style="width:18px;height:18px;stroke:var(--accent-l)"><use href="#i-code"/></svg> Resultados</div>
        </div>
        <div class="pl-results-stats">
            ${keys.filter(k => typeof r[k] === 'number').map(k =>
                `<div class="pl-rstat"><div class="pl-rstat-value" style="color:var(--text-1)">${r[k]}</div><div class="pl-rstat-label">${escapeHtml(k.replace(/_/g,' '))}</div></div>`
            ).join('')}
        </div>
        ${typeof r === 'object' ? `<pre style="background:var(--s2);border-radius:var(--r-sm);padding:12px;font-size:11px;color:var(--text-2);max-height:200px;overflow:auto;white-space:pre-wrap">${escapeHtml(JSON.stringify(r, null, 2).substring(0, 2000))}</pre>` : ''}
    </div>`;
}

function updatePlStepViz(activeIdx, isFailed) {
    const steps = ['planning', 'connecting', 'executing', 'monitoring', 'done'];
    const connectors = ['pl-c1', 'pl-c2', 'pl-c3', 'pl-c4'];
    steps.forEach((s, i) => {
        const el = document.getElementById(`pl-s-${s}`);
        if (!el) return;
        el.classList.remove('active', 'done', 'error');
        if (i < activeIdx) el.classList.add('done');
        else if (i === activeIdx) el.classList.add(isFailed ? 'error' : 'active');
    });
    connectors.forEach((c, i) => {
        const el = document.getElementById(c);
        if (!el) return;
        el.classList.remove('done', 'active');
        if (i < activeIdx) el.classList.add('done');
        else if (i === activeIdx) el.classList.add('active');
    });
}

async function loadExecIntoFeed(execId) {
    try {
        const exec = await api(`/api/pipeline-executions/${execId}`);
        const logs = exec.log || [];
        const feed = document.getElementById('pl-feed');
        plFeedLogCount = logs.length;
        feed.innerHTML = logs.map(renderFeedLine).join('');
        feed.scrollTop = 0;

        const stepsEl = document.getElementById('pl-steps');
        if (logs.length) {
            stepsEl.style.display = 'flex';
            const lastPhase = logs[logs.length - 1].phase || 'done';
            const stepIdx = PHASE_TO_STEP[lastPhase] ?? 4;
            updatePlStepViz(stepIdx, exec.status === 'failed');
        }

        const resultsContainer = document.getElementById('pl-results-container');
        if (resultsContainer) {
            const resultsHtml = renderResultsPanel(exec);
            resultsContainer.innerHTML = resultsHtml || '';
        }
    } catch { /* silent */ }
}

async function viewPipelineExecutions(id) {
    try {
        const data = await api(`/api/pipelines/${id}/executions`);
        const execs = data.executions || [];
        const container = document.getElementById('exec-history');
        if (!execs.length) {
            container.innerHTML = '<div class="empty-state"><svg><use href="#i-clock"/></svg><span>Nenhuma execucao para este pipeline</span></div>';
            return;
        }
        container.innerHTML = execs.map(e => renderHistoryRow(e, e.pipeline_name)).join('');
    } catch (e) { toast('Erro ao carregar historico', 'error'); }
}

function renderHistoryRow(e, pipelineName) {
    const statusColor = e.status === 'completed' ? 'var(--green)' : e.status === 'running' ? 'var(--lime)' : e.status === 'failed' ? 'var(--pink)' : 'var(--text-3)';
    const statusBg = e.status === 'completed' ? 'rgba(52,211,153,0.12)' : e.status === 'running' ? 'rgba(209,254,23,0.12)' : e.status === 'failed' ? 'rgba(251,113,133,0.12)' : 'rgba(255,255,255,0.06)';
    const logs = (typeof e.log === 'string' ? JSON.parse(e.log) : e.log) || [];
    const lastLog = logs.length ? logs[logs.length - 1].msg : '';
    const duration = e.started_at && e.completed_at ? Math.floor((new Date(e.completed_at) - new Date(e.started_at)) / 1000) : 0;
    const dmm = String(Math.floor(duration / 60)).padStart(2, '0');
    const dss = String(duration % 60).padStart(2, '0');
    const name = pipelineName || e._pipeline_name || '';
    return `<button type="button" style="display:flex;align-items:center;gap:12px;padding:12px 14px;border-bottom:1px solid var(--border);border-left:none;border-right:none;border-top:none;cursor:pointer;transition:background 0.15s;width:100%;text-align:left;background:transparent;font:inherit;color:inherit" onmouseover="this.style.background='var(--s2)'" onmouseout="this.style.background=''" onclick="loadExecIntoFeed(${e.id})" aria-label="Ver execucao ${escapeHtml(name)} #${e.id}">
        <div style="width:8px;height:8px;border-radius:50%;background:${statusColor};flex-shrink:0" aria-hidden="true"></div>
        <div style="flex:1;min-width:0">
            <div style="display:flex;align-items:center;gap:8px">
                <span style="font-size:12px;color:var(--text-1);font-weight:600">${escapeHtml(name)}</span>
                <span style="font-size:10px;color:var(--text-3)">#${e.id}</span>
                <span style="font-size:9px;font-weight:600;padding:2px 6px;border-radius:3px;background:${statusBg};color:${statusColor}">${e.status}</span>
            </div>
            <div style="font-size:11px;color:var(--text-3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px">${escapeHtml(lastLog.substring(0, 100))}</div>
        </div>
        <div style="text-align:right;flex-shrink:0">
            <div style="font-size:11px;color:var(--text-2);font-family:monospace">${dmm}:${dss}</div>
            <div style="font-size:10px;color:var(--text-3)">${e.started_at ? new Date(e.started_at).toLocaleString('pt-BR', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}) : '--'}</div>
        </div>
    </button>`;
}

async function loadExecutionHistory() {
    const container = document.getElementById('exec-history');
    try {
        const allPipelines = pipelinesData.length ? pipelinesData : (await api('/api/pipelines')).pipelines || [];
        let allExecs = [];
        for (const p of allPipelines) {
            const data = await api(`/api/pipelines/${p.id}/executions?limit=10`);
            (data.executions || []).forEach(e => { e._pipeline_name = p.name; e.pipeline_type = p.type; allExecs.push(e); });
        }
        allExecs.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        if (!allExecs.length) {
            container.innerHTML = '<div class="empty-state"><svg><use href="#i-clock"/></svg><span>Nenhuma execucao registrada</span></div>';
            return;
        }
        container.innerHTML = allExecs.slice(0, 30).map(e => renderHistoryRow(e)).join('');
    } catch { container.innerHTML = '<div class="empty-state"><svg><use href="#i-clock"/></svg><span>Erro ao carregar historico</span></div>'; }
}

async function syncHermes() {
    const feed = document.getElementById('pl-feed');
    const line = `<div class="hl-feed-line"><span class="hl-feed-time">${new Date().toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}</span><span class="hl-feed-phase" style="background:rgba(124,58,237,0.15);color:var(--accent-l)">sync</span><span style="color:var(--text-2)">Sincronizando Hermes VM...</span></div>`;
    feed.innerHTML += line;
    feed.scrollTop = feed.scrollHeight;
    try {
        await api('/api/hermes/sync', { method: 'POST' });
        const ok = `<div class="hl-feed-line"><span class="hl-feed-time">${new Date().toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}</span><span class="hl-feed-phase" style="background:rgba(52,211,153,0.15);color:var(--green)">sync</span><span style="color:var(--green)">Hermes sincronizado com sucesso</span></div>`;
        feed.innerHTML += ok;
        feed.scrollTop = feed.scrollHeight;
        toast('Hermes sincronizado', 'success');
    } catch (e) {
        const err = `<div class="hl-feed-line"><span class="hl-feed-time">${new Date().toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}</span><span class="hl-feed-phase" style="background:rgba(251,113,133,0.15);color:var(--pink)">erro</span><span style="color:var(--pink)">Falha ao sincronizar: ${escapeHtml(e.message)}</span></div>`;
        feed.innerHTML += err;
        feed.scrollTop = feed.scrollHeight;
        toast('Erro ao sincronizar: ' + e.message, 'error');
    }
}

/* ============================================================
   WORK QUEUE (Fila do Dia)
   ============================================================ */
let workQueueData = [];
let wqFilter = 'all';

async function loadWorkQueue() {
    const grid = document.getElementById('wq-grid');
    grid.innerHTML = '<div class="empty-state" style="grid-column:1/-1"><svg style="animation:spin 1s linear infinite"><use href="#i-refresh"/></svg><span>Carregando fila...</span></div>';

    try {
        const data = await api('/api/workqueue?limit=30');
        workQueueData = data.queue || [];

        const genCount = workQueueData.filter(i => i.action === 'generate_outreach').length;
        const sendCount = workQueueData.filter(i => i.action === 'send_outreach').length;
        const auditCount = workQueueData.filter(i => i.action === 'audit').length;

        document.getElementById('wq-stat-generate').textContent = genCount;
        document.getElementById('wq-stat-send').textContent = sendCount;
        document.getElementById('wq-stat-audit').textContent = auditCount;
        document.getElementById('wq-stat-total').textContent = workQueueData.length;
        document.getElementById('wq-count').textContent = `${workQueueData.length} itens`;

        renderWorkQueue();
    } catch (e) {
        grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><svg><use href="#i-x"/></svg><span>Erro: ${escapeHtml(e.message)}</span></div>`;
    }
}

function filterWorkQueue(filter, btn) {
    wqFilter = filter;
    document.querySelectorAll('.wq-tab').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    renderWorkQueue();
}

function renderWorkQueue() {
    const grid = document.getElementById('wq-grid');
    const items = wqFilter === 'all' ? workQueueData : workQueueData.filter(i => i.action === wqFilter);

    if (!items.length) {
        grid.innerHTML = '<div class="empty-state" style="grid-column:1/-1"><svg><use href="#i-check"/></svg><span>Nenhum item nesta categoria</span></div>';
        return;
    }

    grid.innerHTML = items.map(p => {
        const actionIcons = {
            generate_outreach: '#i-send',
            send_outreach: '#i-message-circle',
            audit: '#i-clipboard'
        };
        const actionColors = {
            generate_outreach: 'green',
            send_outreach: 'lime',
            audit: 'blue'
        };
        const color = actionColors[p.action] || 'text-2';
        const icon = actionIcons[p.action] || '#i-check-square';
        const phone = (p.phone || '').replace(/\D/g, '');
        const hasPhoto = p.photo_ref;

        return `<div class="wq-card priority-${p.priority}" id="wq-${p.id}">
            ${hasPhoto ? `<img class="wq-photo" src="${photoUrl(p.photo_ref)}" onerror="this.style.display='none'" alt="">` : ''}
            <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:8px">
                <div style="min-width:0;flex:1">
                    <div style="font-size:13px;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(p.business_name || p.name)}</div>
                    <div style="font-size:11px;color:var(--text-2);margin-top:2px">${escapeHtml(p.category || '')} · ${escapeHtml(p.city || '')}</div>
                </div>
                <span class="badge" style="background:var(--${color}-dim);color:var(--${color});font-size:10px;white-space:nowrap;flex-shrink:0">
                    <svg style="width:12px;height:12px"><use href="${icon}"/></svg> ${escapeHtml(p.action_label)}
                </span>
            </div>
            <div style="font-size:11px;color:var(--text-2);margin-bottom:12px">${escapeHtml(p.reason)}</div>
            <div style="display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap">
                ${p.google_rating ? `<span class="badge badge-ghost"><svg style="width:12px;height:12px;stroke:var(--amber)"><use href="#i-star"/></svg> ${p.google_rating}/5</span>` : ''}
                ${p.google_reviews ? `<span class="badge badge-ghost">${p.google_reviews} reviews</span>` : ''}
                ${p.score ? `<span class="badge" style="background:var(--${p.score >= 70 ? 'green' : p.score >= 50 ? 'amber' : 'text-3'}-dim);color:var(--${p.score >= 70 ? 'green' : p.score >= 50 ? 'amber' : 'text-3'})">Score: ${p.score}</span>` : ''}
                ${p.has_website ? '<span class="badge badge-ghost"><svg style="width:12px;height:12px"><use href="#i-globe"/></svg> Com site</span>' : '<span class="badge" style="background:var(--red-dim);color:var(--red)">Sem site</span>'}
            </div>
            <div style="display:flex;gap:6px">
                ${p.action === 'generate_outreach' ? `<button class="wq-action-btn primary" onclick="wqGenerateOutreach(${p.id},this)"><svg><use href="#i-send"/></svg> Gerar Proposta</button>` : ''}
                ${p.action === 'send_outreach' ? `<button class="wq-action-btn green" onclick="wqPreviewOutreach(${p.id})"><svg><use href="#i-eye"/></svg> Ver Mensagem</button>` : ''}
                ${p.action === 'audit' ? `<button class="wq-action-btn primary" onclick="wqAuditProspect(${p.id},this)"><svg><use href="#i-clipboard"/></svg> Auditar</button>` : ''}
                ${phone ? `<button class="wq-action-btn" onclick="window.open('https://wa.me/${phone}','_blank')"><svg><use href="#i-message-circle"/></svg> WhatsApp</button>` : ''}
                <button class="wq-action-btn" onclick="openProspectPanel(${p.id})" title="Detalhes"><svg><use href="#i-eye"/></svg></button>
            </div>
            ${p.outreach_message ? `<div class="outreach-preview" style="margin-top:10px;display:none" id="outreach-${p.id}">${escapeHtml(p.outreach_message)}</div>` : ''}
        </div>`;
    }).join('');
    animateGridChildren('#wq-grid');
}

async function wqGenerateOutreach(id, btn) {
    const orig = btn.innerHTML;
    btn.innerHTML = '<svg style="animation:spin 1s linear infinite"><use href="#i-refresh"/></svg> Gerando...';
    btn.disabled = true;
    try {
        const result = await api(`/api/outreach/generate/${id}`, { method: 'POST' });
        toast('Proposta gerada com sucesso!', 'success');

        const card = document.getElementById(`wq-${id}`);
        if (card && result.whatsapp_message) {
            const previewEl = card.querySelector('.outreach-preview') || document.createElement('div');
            previewEl.className = 'outreach-preview';
            previewEl.style.marginTop = '10px';
            previewEl.style.display = 'block';
            previewEl.textContent = result.whatsapp_message;
            if (!card.querySelector('.outreach-preview')) card.appendChild(previewEl);

            btn.innerHTML = '<svg><use href="#i-check"/></svg> Gerada!';
            btn.className = 'wq-action-btn green';
            btn.disabled = false;
            btn.onclick = () => {
                const phone = (workQueueData.find(p => p.id === id)?.phone || '').replace(/\D/g, '');
                if (phone) {
                    const msg = encodeURIComponent(result.whatsapp_message);
                    window.open(`https://wa.me/${phone}?text=${msg}`, '_blank');
                }
            };
        }
    } catch (e) {
        toast('Erro: ' + e.message, 'error');
        btn.innerHTML = orig;
        btn.disabled = false;
    }
}

function wqPreviewOutreach(id) {
    const el = document.getElementById(`outreach-${id}`);
    if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';

    const p = workQueueData.find(i => i.id === id);
    if (p && p.outreach_message && p.phone) {
        const phone = p.phone.replace(/\D/g, '');
        const msg = encodeURIComponent(p.outreach_message);
        window.open(`https://wa.me/${phone}?text=${msg}`, '_blank');
    }
}

async function wqAuditProspect(id, btn) {
    const orig = btn.innerHTML;
    btn.innerHTML = '<svg style="animation:spin 1s linear infinite"><use href="#i-refresh"/></svg> Auditando...';
    btn.disabled = true;
    try {
        const result = await api(`/api/audit/prospect/${id}`, { method: 'POST' });
        toast(`Auditado: score ${result.score} -> ${result.new_stage}`, 'success');
        btn.innerHTML = `<svg><use href="#i-check"/></svg> Score: ${result.score}`;
        btn.className = 'wq-action-btn green';
        btn.disabled = true;
    } catch (e) {
        toast('Erro: ' + e.message, 'error');
        btn.innerHTML = orig;
        btn.disabled = false;
    }
}

// Keep old task functions for backwards compat
function loadTasks() { loadWorkQueue(); }
function openTaskModal() { document.getElementById('task-modal').classList.add('active'); }
function closeTaskModal() {
    document.getElementById('task-modal').classList.remove('active');
    document.getElementById('task-title').value = '';
    document.getElementById('task-desc').value = '';
    document.getElementById('task-priority').value = 'medium';
    document.getElementById('task-assigned').value = '';
}

async function createTask() {
    const title = document.getElementById('task-title').value.trim();
    const description = document.getElementById('task-desc').value.trim();
    const priority = document.getElementById('task-priority').value;
    const assigned_to = document.getElementById('task-assigned').value.trim();
    if (!title) { toast('Titulo obrigatorio', 'error'); return; }
    try {
        await api('/api/tasks', { method: 'POST', body: JSON.stringify({ title, description, priority, assigned_to: assigned_to || 'manual' }) });
        toast('Tarefa criada!', 'success');
        closeTaskModal();
        loadWorkQueue();
    } catch (e) { toast('Erro: ' + e.message, 'error'); }
}

async function updateTask(id, status) {
    try {
        await api(`/api/tasks/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) });
        toast(`Tarefa ${status === 'completed' ? 'aprovada' : 'rejeitada'}`, 'success');
    } catch (e) { toast('Erro: ' + e.message, 'error'); }
}

async function sendTaskToClaude(id) {
    try {
        await api(`/api/tasks/${id}/send-to-claude`, { method: 'POST' });
        toast('Tarefa enviada para Claude', 'success');
    } catch (e) { toast('Erro: ' + e.message, 'error'); }
}

/* ============================================================
   TRENDS PAGE
   ============================================================ */
function refreshTrendSuggestions() {
    toast('Sugestoes atualizadas', 'info');
}

/* ============================================================
   CLAUDE CODE PAGE
   ============================================================ */
function renderMarkdownTerminal(text) {
    let html = '';
    let inCodeBlock = false;
    let codeLines = [];
    let codeLang = '';
    const lines = text.split('\n');
    for (const line of lines) {
        if (line.startsWith('```')) {
            if (inCodeBlock) {
                html += `<div class="log-line" style="background:var(--s3);border-radius:var(--r-sm);padding:8px 12px;margin:4px 0;font-family:monospace;font-size:11px;white-space:pre-wrap;border-left:3px solid var(--lime)">${codeLines.map(l => escapeHtml(l)).join('\n')}</div>`;
                codeLines = [];
                inCodeBlock = false;
            } else {
                inCodeBlock = true;
                codeLang = line.slice(3).trim();
            }
            continue;
        }
        if (inCodeBlock) { codeLines.push(line); continue; }
        // Headers
        if (line.startsWith('### ')) {
            html += `<div class="log-line" style="color:var(--accent-l);font-weight:700;font-size:12px;margin-top:6px">${escapeHtml(line.slice(4))}</div>`;
        } else if (line.startsWith('## ')) {
            html += `<div class="log-line" style="color:var(--lime);font-weight:700;font-size:13px;margin-top:8px">${escapeHtml(line.slice(3))}</div>`;
        } else if (line.startsWith('# ')) {
            html += `<div class="log-line" style="color:var(--lime);font-weight:800;font-size:14px;margin-top:8px">${escapeHtml(line.slice(2))}</div>`;
        } else if (line.startsWith('- ') || line.startsWith('* ')) {
            html += `<div class="log-line" style="padding-left:12px"><span style="color:var(--lime);margin-right:6px">•</span>${formatInline(line.slice(2))}</div>`;
        } else if (/^\d+\.\s/.test(line)) {
            const m = line.match(/^(\d+)\.\s(.*)$/);
            html += `<div class="log-line" style="padding-left:12px"><span style="color:var(--accent-l);margin-right:6px;font-weight:700">${m[1]}.</span>${formatInline(m[2])}</div>`;
        } else if (line.trim() === '') {
            html += `<div class="log-line" style="height:4px"></div>`;
        } else {
            html += `<div class="log-line">${formatInline(line)}</div>`;
        }
    }
    if (inCodeBlock && codeLines.length) {
        html += `<div class="log-line" style="background:var(--s3);border-radius:var(--r-sm);padding:8px 12px;margin:4px 0;font-family:monospace;font-size:11px;white-space:pre-wrap;border-left:3px solid var(--lime)">${codeLines.map(l => escapeHtml(l)).join('\n')}</div>`;
    }
    // MERGED-019: defesa em profundidade — sanitize final antes do innerHTML.
    return sanitizeClaudeHtml(html);
}

function formatInline(text) {
    const html = escapeHtml(text)
        .replace(/`([^`]+)`/g, '<code style="background:var(--s3);padding:1px 5px;border-radius:3px;font-size:11px;color:var(--lime)">$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong style="color:var(--text);font-weight:700">$1</strong>')
        .replace(/\*([^*]+)\*/g, '<em style="color:var(--text-2)">$1</em>');
    return sanitizeClaudeHtml(html);
}

async function sendClaudeCommand() {
    const input = document.getElementById('claude-input');
    const cmd = input.value.trim();
    if (!cmd) return;
    input.value = '';

    const output = document.getElementById('claude-output');
    output.innerHTML += `<div class="log-line" style="color:var(--lime)"><span class="log-time">${now()}</span>> ${escapeHtml(cmd)}</div>`;
    output.scrollTop = output.scrollHeight;

    claudeHistory.unshift({ cmd, time: new Date().toISOString() });
    if (claudeHistory.length > 50) claudeHistory = claudeHistory.slice(0, 50);
    localStorage.setItem('claude_history', JSON.stringify(claudeHistory));
    renderClaudeHistory();

    try {
        output.innerHTML += `<div class="log-line typing-indicator" style="color:var(--text-3)"><span class="log-time">${now()}</span><span class="typing-dots">Processando</span></div>`;
        output.scrollTop = output.scrollHeight;
        const result = await api('/api/claude/execute', { method: 'POST', body: JSON.stringify({ command: cmd, context: 'terminal' }) });
        output.querySelector('.typing-indicator')?.remove();
        const provider = result.provider || 'unknown';
        const providerLabel = provider === 'agent_zero' ? 'Agent Zero' : provider === 'claude_cli' ? 'Claude CLI' : provider;
        const providerColor = provider === 'agent_zero' ? 'var(--accent-l)' : 'var(--lime)';
        const text = result.output || result.result || JSON.stringify(result, null, 2);
        output.innerHTML += `<div class="log-line" style="color:var(--text-3)"><span class="log-time">${now()}</span><span style="background:${providerColor};color:var(--bg);padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600">${providerLabel}</span></div>`;
        output.innerHTML += renderMarkdownTerminal(text);
    } catch (e) {
        output.querySelector('.typing-indicator')?.remove();
        output.innerHTML += `<div class="log-line" style="color:var(--red)"><span class="log-time">${now()}</span>ERRO: ${escapeHtml(e.message)}</div>`;
    }
    output.scrollTop = output.scrollHeight;
}

function quickClaudeCmd(cmd) {
    document.getElementById('claude-input').value = cmd;
    sendClaudeCommand();
}

function renderClaudeHistory() {
    const c = document.getElementById('claude-history');
    if (!claudeHistory.length) {
        c.innerHTML = '<div class="empty-state"><svg><use href="#i-clock"/></svg><span>Nenhum comando executado</span></div>';
        return;
    }
    c.innerHTML = claudeHistory.slice(0, 20).map(h => `<button type="button" class="list-row" style="padding:6px 12px" onclick="document.getElementById('claude-input').value='${escapeHtml(h.cmd)}';document.getElementById('claude-input').focus()" aria-label="Reutilizar comando: ${escapeHtml(h.cmd)}">
        <svg style="width:14px;height:14px;stroke:var(--text-3);flex-shrink:0" aria-hidden="true"><use href="#i-chevron-right"/></svg>
        <div style="flex:1;min-width:0"><div style="font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(h.cmd)}</div><div style="font-size:10px;color:var(--text-3)">${formatDate(h.time)} ${formatTime(h.time)}</div></div>
    </button>`).join('');
}

function clearClaudeHistory() {
    claudeHistory = [];
    localStorage.setItem('claude_history', '[]');
    renderClaudeHistory();
    document.getElementById('claude-output').innerHTML = `<div class="log-line" style="color:var(--lime)">Hermes Command Center v2.0</div><div class="log-line" style="color:var(--text-3)">Historico limpo. Pronto para receber comandos...</div>`;
    toast('Historico limpo', 'success');
}

/* ============================================================
   CONFIG MODAL
   ============================================================ */
function openConfigModal() {
    document.getElementById('config-api-url').value = localStorage.getItem('hermes_api') || '';
    document.getElementById('config-token').value = localStorage.getItem('hermes_token') || '';
    document.getElementById('config-modal').classList.add('active');
}

function closeConfigModal() {
    document.getElementById('config-modal').classList.remove('active');
}

function saveConfig() {
    const apiUrl = document.getElementById('config-api-url').value.trim().replace(/\/+$/, '');
    const token = document.getElementById('config-token').value.trim();
    localStorage.setItem('hermes_api', apiUrl);
    localStorage.setItem('hermes_token', token);
    toast('Configuracoes salvas! Recarregando...', 'success');
    closeConfigModal();
    setTimeout(() => location.reload(), 1000);
}

/* ============================================================
   WEBSOCKET
   ============================================================ */
let ws = null;

// F.2.5a — polling fallback ≥30s pra /api/daemon/subsystems quando WS down.
// _wsAlive toggled em ws.onopen/onclose/onerror. Polling NUNCA roda com WS up.
let _wsAlive = false;
// UX-RM-F7-A — reconnect attempt counter for exponential backoff (capped 30s).
let _wsRetryAttempt = 0;
let _subsystemsPollingTimer = null;

function startSubsystemsPollingFallback() {
    if (_subsystemsPollingTimer) return; // idempotent
    _subsystemsPollingTimer = setInterval(() => {
        if (_wsAlive) {
            // Safety: WS recovered fora do onopen path — para imediato
            clearInterval(_subsystemsPollingTimer);
            _subsystemsPollingTimer = null;
            return;
        }
        if (currentPage === 'control') {
            fetchAndRenderSubsystems().catch(() => {});
        }
    }, 30000); // 30s mínimo preserva WS-first principle
}

function stopSubsystemsPollingFallback() {
    if (_subsystemsPollingTimer) {
        clearInterval(_subsystemsPollingTimer);
        _subsystemsPollingTimer = null;
    }
}

async function fetchAndRenderSubsystems() {
    try {
        const data = await api('/api/daemon/subsystems');
        if (!data || !Array.isArray(data.subsystems)) return;
        if (!window.SubsystemTileGrid) return;
        data.subsystems.forEach(s => {
            if (s && s.name) window.SubsystemTileGrid.update(s.name, s);
        });
    } catch (e) {
        console.error('fetchAndRenderSubsystems failed:', e);
        if (window.hermesToast) window.hermesToast.error('Falha ao carregar subsistemas');
    }
}

function connectWS() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = localStorage.getItem('hermes_api')?.replace(/^https?:\/\//, '').replace(/\/+$/, '') || location.host;
    const token = localStorage.getItem('hermes_token') || '';
    ws = new WebSocket(`${protocol}//${host}/ws?token=${encodeURIComponent(token)}`);
    ws.onmessage = (e) => {
        try {
            const event = JSON.parse(e.data);
            handleWSEvent(event);
            // F.4.3 — fan-out for component listeners (modal PATH 1 ack, etc).
            if (event && event.event_type) {
                document.dispatchEvent(new CustomEvent('hermes-ws-event', { detail: event }));
                if (window.SkillProposalsStudio && typeof window.SkillProposalsStudio.handleWSEvent === 'function') {
                    try { window.SkillProposalsStudio.handleWSEvent(event); }
                    catch (err) { console.warn('SkillProposalsStudio WS handler failed', err); }
                }
            }
        } catch (err) {}
    };
    ws.onopen  = () => {
        _wsAlive = true;
        _wsRetryAttempt = 0;
        stopSubsystemsPollingFallback();
        if (window.HermesWSStatus) {
            window.HermesWSStatus.setState('connected');
        } else {
            document.getElementById('status-dot').className = 'status-dot';
            document.getElementById('status-text').textContent = 'Online';
        }
    };
    ws.onclose = () => {
        _wsAlive = false;
        startSubsystemsPollingFallback();
        ws = null;
        // UX-RM-F7-A — exponential backoff capped at 30s
        const attempt = ++_wsRetryAttempt;
        const delay = Math.min(1000 * Math.pow(2, attempt - 1), 30000);
        if (window.HermesWSStatus) {
            window.HermesWSStatus.setState('reconnecting', attempt);
        } else {
            document.getElementById('status-dot').className = 'status-dot offline';
            document.getElementById('status-text').textContent = 'Offline';
        }
        setTimeout(connectWS, delay);
    };
    ws.onerror = () => {
        _wsAlive = false;
        startSubsystemsPollingFallback();
        if (window.HermesWSStatus) window.HermesWSStatus.setState('reconnecting', _wsRetryAttempt);
        ws?.close();
    };
}

function handleWSEvent(event) {
    if (event.type === 'sync') {
        if (currentPage === 'dashboard') loadDashboard();
    } else if (event.type === 'pipeline_progress') {
        if (currentPage === 'pipeline') loadPipeline();
        if (currentPage === 'dashboard') refreshScraperStatus();
    } else if (event.type === 'audit_done') {
        if (currentPage === 'audit') loadAuditPage();
        toast('Auditoria concluida!', 'success');
    } else if (event.type === 'scraper_update') {
        if (currentPage === 'dashboard') refreshScraperStatus();
    }

    // Mission Control visual handlers
    if (currentPage === 'control') {
        if (event.type === 'daemon_state') updateDaemonState(event);
        if (event.type === 'activity') {
            addFeedItem(event);
            if (window._orbit) window._orbit.addEvent(event);
            updateTimelineBlock(event);
        }
        if (event.type === 'channel_update') updateChannelCard(event);
        if (event.type === 'reply_received') {
            addFeedItem(event, true);
            if (window._orbit) window._orbit.flash(event.prospect_id || 0, '#00ff88');
        }
        if (event.type === 'decision') addDecisionItem(event);
        if (event.type === 'alert') {
            addFeedItem({...event, category: 'system', action: event.message}, event.level === 'error');
        }
    }

    // F.2.3 — canonical dot-notation handlers (paralelos a `activity`/`decision` legacy).
    // Render fica no legacy até F.2.future cleanup; canonical aqui faz toast UX + hook
    // pra Mission Control v2 (F.2.5a SubsystemTileGrid se montar window._missionControl).
    if (event.type === 'daemon.subsystem_status') {
        const sub = String(event.subsystem || '').replace(/[^a-z0-9_-]/gi, '');
        const status = String(event.status || '').replace(/[^a-z]/gi, '');
        if (window._missionControl && typeof window._missionControl.updateSubsystem === 'function') {
            try { window._missionControl.updateSubsystem(event); } catch (e) { console.warn('mission_control updateSubsystem failed', e); }
        }
        if (currentPage === 'control' && sub && status && typeof toast === 'function') {
            // F.2.4 — .toast-warn agora existe (window.hermesToast). Reverte hotfix F.2.3 'info'→'warn'.
            const tone = status === 'healthy' ? 'success' : (status === 'paused' ? 'warn' : 'info');
            toast(`Subsistema ${sub} → ${status}`, tone);
        }
    }
    if (event.type === 'daemon.log_event') {
        // legacy `activity` ainda renderiza feed/orbit/timeline; canonical é hook futuro
        if (window._missionControl && typeof window._missionControl.appendLog === 'function') {
            try { window._missionControl.appendLog(event); } catch (e) { console.warn('mission_control appendLog failed', e); }
        }
        // F.2.5c — LiveLogTail consume real (stub F.2.5a → render virtualizado).
        if (window.HermesLiveLogTail && typeof window.HermesLiveLogTail.append === 'function') {
            try {
                window.HermesLiveLogTail.append({
                    ts: event.ts || Date.now(),
                    level: event.level || 'info',
                    emitter: event.emitter || 'daemon',
                    event_type: 'log',
                    message: event.message || '',
                    payload: event.payload || null,
                });
            } catch (e) { console.warn('LiveLogTail append (log_event) failed', e); }
        }
    }
    if (event.type === 'daemon.decision') {
        // legacy `decision` ainda renderiza decisions-list; canonical é hook futuro
        if (window._missionControl && typeof window._missionControl.appendDecision === 'function') {
            try { window._missionControl.appendDecision(event); } catch (e) { console.warn('mission_control appendDecision failed', e); }
        }
        // F.2.5c — LiveLogTail consume real (decision_event renderiza inline com payload).
        if (window.HermesLiveLogTail && typeof window.HermesLiveLogTail.append === 'function') {
            try {
                window.HermesLiveLogTail.append({
                    ts: event.ts || Date.now(),
                    level: event.level || 'info',
                    emitter: event.emitter || 'daemon',
                    event_type: 'decision',
                    message: `Decision: ${event.decision_event || event.message || 'unknown'}`,
                    payload: event,
                });
            } catch (e) { console.warn('LiveLogTail append (decision) failed', e); }
        }
    }

    // F.3.3 — Lab Cockpit WS handlers (8 events lab.*).
    // Delega pra window.HermesLabCockpit.appendEvent (no-op se cockpit não inicializado).
    // SE currentPage !== 'lab', cockpit ainda processa event pra manter state interno
    // (history list + active run tracking) caso owner navegue pra lab depois.
    const LAB_EVENT_TYPES = [
        'lab.run_started', 'lab.step_progress', 'lab.screenshot_captured',
        'lab.compliance_score', 'lab.fingerprint_dump', 'lab.run_completed',
        'lab.run_failed', 'lab.run_aborted',
    ];
    if (LAB_EVENT_TYPES.indexOf(event.type) !== -1 &&
        window.HermesLabCockpit &&
        typeof window.HermesLabCockpit.appendEvent === 'function') {
        try { window.HermesLabCockpit.appendEvent(event); }
        catch (e) { console.warn('HermesLabCockpit appendEvent failed', event.type, e); }
    }

    // F.6.4 — Brain Confirm Drawer WS handlers (2 events brain.*).
    // UX-RM-F7-A: lazy-load brain_confirm_card + drawer on first brain.* event.
    if (typeof event.type === 'string' && event.type.indexOf('brain.') === 0) {
        if (!window.BrainConfirmDrawer && window.loadComponent) {
            const _pendingEvent = event;
            window.loadComponent('brain_confirm_card').then(function () {
                return window.loadComponent('brain_confirm_drawer');
            }).then(function () {
                if (window.BrainConfirmDrawer && typeof window.BrainConfirmDrawer.onWSEvent === 'function') {
                    try { window.BrainConfirmDrawer.onWSEvent(_pendingEvent); }
                    catch (e) { console.warn('BrainConfirmDrawer onWSEvent failed', _pendingEvent.type, e); }
                }
            }).catch(function () {});
        } else if (window.BrainConfirmDrawer && typeof window.BrainConfirmDrawer.onWSEvent === 'function') {
            try { window.BrainConfirmDrawer.onWSEvent(event); }
            catch (e) { console.warn('BrainConfirmDrawer onWSEvent failed', event.type, e); }
        }
    }
}

/* ============================================================
   INIT
   ============================================================ */
function init() {
    checkAuth();
    connectWS();
}

window.addEventListener('hashchange', () => {
    const hash = window.location.hash.replace('#', '') || 'control';
    if (hash !== currentPage) navigate(hash);
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closePanel();
        closeConfigModal();
        closeTaskModal();
    }
});

/* ============================================================
   SKILLS
   ============================================================ */
async function loadSkills() {
    const grid = document.getElementById('skills-grid');
    try {
        const data = await api('/api/hermes/skills');
        if (!data || !data.length) {
            grid.innerHTML = '<div class="empty-state"><svg><use href="#i-zap"/></svg><span>Nenhuma skill encontrada. VM offline?</span></div>';
            return;
        }
        grid.innerHTML = data.map(s => `
            <div class="card" style="padding:14px;border:1px solid ${s.active ? 'var(--lime)' : 'var(--border)'}">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
                    <div>
                        <div style="font-size:13px;font-weight:700;color:var(--text)">${s.name}</div>
                        <div style="font-size:11px;color:var(--text-3);margin-top:2px">${s.description || ''}</div>
                    </div>
                    <label class="toggle-switch" style="cursor:pointer">
                        <input type="checkbox" ${s.active ? 'checked' : ''} onchange="toggleSkill('${s.name}', this.checked)" style="display:none">
                        <span style="width:36px;height:20px;border-radius:10px;background:${s.active ? 'var(--lime)' : 'var(--s3)'};display:block;position:relative;transition:background 0.2s">
                            <span style="width:16px;height:16px;border-radius:50%;background:var(--bg);position:absolute;top:2px;${s.active ? 'right:2px' : 'left:2px'};transition:all 0.2s"></span>
                        </span>
                    </label>
                </div>
                <div style="display:flex;gap:6px;flex-wrap:wrap">
                    <span class="badge badge-ghost">${s.model || 'N/A'}</span>
                    <span class="badge badge-ghost">${s.provider || 'N/A'}</span>
                    ${s.triggers ? s.triggers.slice(0,2).map(t => `<span class="badge badge-lime">${t}</span>`).join('') : ''}
                </div>
            </div>
        `).join('');
    } catch (e) {
        grid.innerHTML = '<div class="empty-state"><svg><use href="#i-zap"/></svg><span>Erro ao carregar skills</span></div>';
    }
}

async function toggleSkill(name, active) {
    const checkbox = document.querySelector(`input[onchange*="toggleSkill('${name}"]`);
    if (window.optimisticMutation && checkbox) {
        await window.optimisticMutation.mutate({
            optimisticUpdate: () => { checkbox.checked = active; },
            apiCall: () => api(`/api/hermes/skills/${name}`, { method: 'PATCH', body: JSON.stringify({ active }) }),
            rollback: () => { checkbox.checked = !active; },
            successToast: `Skill ${name} ${active ? 'ativada' : 'desativada'}`,
            liveRegionMsg: `Skill ${name} ${active ? 'ativada' : 'desativada'}`,
        }).then(() => loadSkills()).catch(() => {});
    } else {
        try {
            await api(`/api/hermes/skills/${name}`, { method: 'PATCH', body: JSON.stringify({ active }) });
            toast(`Skill ${name} ${active ? 'ativada' : 'desativada'}`, 'success');
            loadSkills();
        } catch (e) {
            toast('Erro ao alterar skill', 'error');
        }
    }
}

/* ============================================================
   MEMORY
   ============================================================ */
async function loadMemory() {
    const factsEl = document.getElementById('memory-facts');
    const prefsEl = document.getElementById('memory-preferences');
    try {
        const data = await api('/api/hermes/memory');
        if (!data) {
            factsEl.innerHTML = '<div class="empty-state"><svg><use href="#i-database"/></svg><span>Sem conexao com memoria</span></div>';
            return;
        }
        const facts = (data.facts || []);
        const prefs = (data.preferences || []);
        const patterns = (data.patterns || []);

        factsEl.innerHTML = facts.length ? facts.map(f => `
            <div style="display:flex;align-items:center;gap:8px;padding:8px 10px;background:var(--s3);border-radius:var(--r-sm)">
                <span style="flex:1;font-size:12px;color:var(--text)">${f.content}</span>
                <button class="btn-icon" onclick="deleteMemoryItem('${f.id}')" style="opacity:0.5"><svg style="width:14px;height:14px"><use href="#i-x"/></svg></button>
            </div>
        `).join('') : '<div class="empty-state"><svg><use href="#i-database"/></svg><span>Nenhum fato salvo</span></div>';

        prefsEl.innerHTML = [...prefs, ...patterns].length ? [...prefs, ...patterns].map(p => `
            <div style="display:flex;align-items:center;gap:8px;padding:8px 10px;background:var(--s3);border-radius:var(--r-sm)">
                <span class="badge ${p.type === 'preference' ? 'badge-blue' : 'badge-accent'}" style="font-size:9px">${p.type || 'pattern'}</span>
                <span style="flex:1;font-size:12px;color:var(--text)">${p.content}</span>
                <button class="btn-icon" onclick="deleteMemoryItem('${p.id}')" style="opacity:0.5"><svg style="width:14px;height:14px"><use href="#i-x"/></svg></button>
            </div>
        `).join('') : '<div class="empty-state"><svg><use href="#i-user"/></svg><span>Nenhuma preferencia salva</span></div>';
    } catch (e) {
        factsEl.innerHTML = '<div class="empty-state"><svg><use href="#i-database"/></svg><span>Erro ao carregar memoria</span></div>';
    }
}

async function addMemoryItem(type, content) {
    if (!content || !content.trim()) { toast('Digite o conteudo', 'error'); return; }
    try {
        await api('/api/hermes/memory', { method: 'POST', body: JSON.stringify({ type, content: content.trim() }) });
        document.getElementById('memory-new-fact').value = '';
        toast('Item adicionado', 'success');
        loadMemory();
    } catch (e) {
        toast('Erro ao adicionar', 'error');
    }
}

async function deleteMemoryItem(id) {
    try {
        await api(`/api/hermes/memory/${id}`, { method: 'DELETE' });
        toast('Item removido', 'success');
        loadMemory();
    } catch (e) {
        toast('Erro ao remover', 'error');
    }
}

/* ============================================================
   MISSIONS
   ============================================================ */
async function loadMissions() {
    const cal = document.getElementById('missions-calendar');
    const countEl = document.getElementById('missions-count');
    try {
        const pipelines = await api('/api/pipelines');
        const scheduled = (pipelines || []).filter(p => p.schedule_config);
        countEl.textContent = `(${scheduled.length} agendadas)`;

        const days = ['seg', 'ter', 'qua', 'qui', 'sex', 'sab', 'dom'];
        const dayNames = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'];
        const typeColors = { linkedin_viewer: 'badge-blue', scraper: 'badge-lime', audit: 'badge-amber', outreach: 'badge-pink' };

        cal.innerHTML = days.map((d, i) => {
            const dayMissions = scheduled.filter(p => (p.schedule_config.days || []).includes(d));
            return `
                <div style="min-height:200px">
                    <div style="font-size:10px;font-weight:700;color:var(--text-3);text-transform:uppercase;text-align:center;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--border)">${dayNames[i]}</div>
                    ${dayMissions.length ? dayMissions.map(m => `
                        <div style="padding:8px;background:var(--s3);border-radius:var(--r-sm);margin-bottom:6px;border-left:3px solid var(--accent-l)">
                            <div style="font-size:11px;font-weight:600;color:var(--text);margin-bottom:4px">${m.name || m.type}</div>
                            <span class="${typeColors[m.type] || 'badge-ghost'} badge" style="font-size:9px">${m.type}</span>
                            ${m.schedule_config.time ? `<span style="font-size:9px;color:var(--text-3);margin-left:4px">${m.schedule_config.time}</span>` : ''}
                        </div>
                    `).join('') : '<div style="font-size:10px;color:var(--text-3);text-align:center;padding:20px 0">—</div>'}
                </div>
            `;
        }).join('');
    } catch (e) {
        cal.innerHTML = '<div class="empty-state" style="grid-column:1/-1"><svg><use href="#i-calendar"/></svg><span>Erro ao carregar missoes</span></div>';
    }
}

function openMissionModal() {
    document.getElementById('mission-modal').classList.add('active');
}

function closeMissionModal() {
    document.getElementById('mission-modal').classList.remove('active');
}

async function createMission() {
    const name = document.getElementById('mission-name').value.trim();
    const type = document.getElementById('mission-type').value;
    const time = document.getElementById('mission-time').value;
    const desc = document.getElementById('mission-desc').value.trim();
    const activeDays = [...document.querySelectorAll('.mission-day.active')].map(b => b.dataset.day);

    if (!name) { toast('Nome obrigatorio', 'error'); return; }
    if (!activeDays.length) { toast('Selecione pelo menos um dia', 'error'); return; }

    try {
        await api('/api/pipelines', {
            method: 'POST',
            body: JSON.stringify({
                name,
                type,
                description: desc,
                schedule_config: { days: activeDays, time, active: true }
            })
        });
        toast('Missao criada!', 'success');
        closeMissionModal();
        loadMissions();
    } catch (e) {
        toast('Erro ao criar missao', 'error');
    }
}

/* ============================================================
   MISSION CONTROL
   ============================================================ */
let _feedFilter = 'all';
let _controlInterval = null;

// F.2.5b — Idempotente mount PanicButton + Preferências ⚙ no header MC.
function _mountMissionControlHeaderActions() {
    const host = document.getElementById('metrics-bar');
    if (!host) return;
    let actions = host.querySelector('.mc-header-actions');
    if (!actions) {
        actions = document.createElement('div');
        actions.className = 'mc-header-actions';
        actions.dataset.f25b = 'header-actions';
        host.appendChild(actions);
    }
    // Panic button (uma vez)
    if (window.HermesPanicButton && !actions.querySelector('[data-component="panic-button"]')) {
        try { window.HermesPanicButton.init(actions); } catch (e) { console.warn('panic init failed', e); }
    }
    // Preferências ⚙ btn (uma vez)
    if (!actions.querySelector('[data-role="pref-trigger"]')) {
        const prefBtn = document.createElement('button');
        prefBtn.type = 'button';
        prefBtn.className = 'pref-trigger';
        prefBtn.dataset.role = 'pref-trigger';
        prefBtn.setAttribute('aria-label', 'Abrir preferências');
        prefBtn.title = 'Preferências (Ctrl+,)';
        prefBtn.innerHTML = typeof window.icon === 'function' ? window.icon('settings', {label: 'Preferências'}) : '⚙';
        prefBtn.addEventListener('click', () => {
            if (window.HermesPrefPanel && typeof window.HermesPrefPanel.open === 'function') {
                window.HermesPrefPanel.open();
            }
        });
        actions.appendChild(prefBtn);
    }
}

async function loadMissionControl() {
    if (_controlInterval) clearInterval(_controlInterval);
    // F.2.5a — SubsystemTileGrid init + fetch inicial (WS atualiza depois).
    if (window.SubsystemTileGrid) {
        window.SubsystemTileGrid.init('[data-component="subsystem-tile-grid"]');
    }
    // F.2.5b — Panic button + PrefPanel init no header MC (idempotente).
    _mountMissionControlHeaderActions();
    if (window.HermesPrefPanel && typeof window.HermesPrefPanel.init === 'function') {
        window.HermesPrefPanel.init().catch(() => { /* offline OK */ });
    }
    // F.2.5c — LiveLogTail mount (idempotente — init checa _initialized).
    if (window.HermesLiveLogTail && typeof window.HermesLiveLogTail.init === 'function') {
        try { window.HermesLiveLogTail.init('[data-component="live-log-tail"]'); } catch (e) { console.warn('LiveLogTail init failed', e); }
    }
    await Promise.all([
        loadDaemonState(),
        loadDaemonChannels(),
        loadDaemonTimeline(),
        loadDaemonDecisions(),
        loadDaemonFeed(),
        fetchAndRenderSubsystems(),
    ]);
    initOrbitCanvas();
    _controlInterval = setInterval(loadDaemonState, 10000);
}

async function loadDaemonState() {
    try {
        const data = await api('/api/daemon/state');
        if (!data) return;

        // Update badge
        const badge = document.getElementById('daemon-badge');
        const _ic = typeof window.icon === 'function' ? window.icon : () => '';
        const stateMap = {
            idle:     { html: '<span class="status-dot status-dot-green" aria-hidden="true"></span>ONLINE',   cls: 'online' },
            working:  { html: _ic('zap')     + ' WORKING',   cls: 'working' },
            paused:   { html: _ic('pause')   + ' PAUSED',    cls: 'paused' },
            error:    { html: '<span class="status-dot status-dot-red" aria-hidden="true"></span>ERROR',      cls: 'error' },
            sleeping: { html: _ic('moon')    + ' SLEEPING',  cls: '' },
            cooldown: { html: _ic('hourglass') + ' COOLDOWN', cls: 'paused' },
            offline:  { html: '<span class="status-dot status-dot-grey" aria-hidden="true"></span>OFFLINE',   cls: '' },
        };
        const s = stateMap[data.state] || stateMap.offline;
        badge.innerHTML = s.html;
        badge.className = 'daemon-badge ' + s.cls;

        // Update counters
        const stats = data.stats_today || {};
        updateCounter('m-sent', stats.contacted || 0);
        updateCounter('m-opened', stats.enriched || 0);
        updateCounter('m-replied', stats.replied || 0);
        updateCounter('m-meetings', stats.meetings || 0);

        // Update energy
        const energy = data.energy || 0;
        const energyFill = document.getElementById('energy-fill');
        const energyPct = document.getElementById('energy-pct');
        energyFill.style.width = `${energy * 100}%`;
        energyFill.className = 'energy-fill' + (energy < 0.3 ? ' low' : '');
        energyPct.textContent = `${Math.round(energy * 100)}%`;

        // Update avatar
        updateHermesAvatar(data);

    } catch (e) {
        document.getElementById('daemon-badge').innerHTML = '<span class="status-dot status-dot-grey" aria-hidden="true"></span>OFFLINE';
        document.getElementById('daemon-badge').className = 'daemon-badge';
    }
}

function updateCounter(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    const old = parseInt(el.textContent) || 0;
    if (value !== old) {
        el.textContent = value;
        el.classList.add('bump');
        setTimeout(() => el.classList.remove('bump'), 300);
    }
}

function updateHermesAvatar(data) {
    const stateEl = document.getElementById('avatar-state');
    const detailEl = document.getElementById('avatar-detail');
    const ring = document.getElementById('avatar-ring');

    const state = data.state || data.current_task_type || 'idle';
    const stateLabels = {
        idle: 'IDLE',
        working: 'WORKING',
        paused: 'PAUSED',
        error: 'ERROR',
        sleeping: 'SLEEPING',
        cooldown: 'COOLDOWN',
    };

    stateEl.textContent = stateLabels[state] || state.toUpperCase();
    detailEl.textContent = data.current_task_detail || data.detail || 'Aguardando proxima acao';

    // Ring animation
    ring.className = 'avatar-ring';
    if (state === 'working') ring.classList.add('sending');
    else if (state === 'error') ring.classList.add('error');
    else if (state === 'idle' || state === 'online') ring.classList.add('active');
}

function updateDaemonState(event) {
    loadDaemonState();
}

async function loadDaemonChannels() {
    try {
        const data = await api('/api/daemon/channels');
        if (!data) return;
        for (const [name, ch] of Object.entries(data)) {
            updateChannelCard({ channel: name, ...ch });
        }
    } catch (e) {}
}

function updateChannelCard(event) {
    const ch = event.channel;
    const fill = document.getElementById(`ch-${ch}-fill`);
    const ratio = document.getElementById(`ch-${ch}-ratio`);
    const health = document.getElementById(`ch-${ch}-health`);
    const card = document.getElementById(`ch-${ch}`);
    if (!fill) return;

    const used = event.daily_used || 0;
    const limit = event.daily_limit || 50;
    const pct = Math.min((used / limit) * 100, 100);

    fill.style.width = `${pct}%`;
    fill.className = 'ch-fill' + (pct > 80 ? ' danger' : pct > 60 ? ' warning' : '');
    ratio.textContent = `${used}/${limit}`;

    // Health dots — null health (not_configured) renders gray + "n/c" label + configure link
    if (event.status === 'not_configured' || event.health === null || event.health === undefined) {
        health.innerHTML = Array.from({length: 5}, () =>
            `<span class="dot-off">●</span>`
        ).join('') + '<span style="font-size:10px;color:var(--text-3);margin-left:4px">n/c</span>' +
        '<a href="javascript:void(0)" onclick="navigate(\'skills\')" style="font-size:10px;color:var(--accent);margin-left:6px;text-decoration:none" title="Configurar canal">Configurar</a>';
    } else {
        const h = event.health;
        const dots = Math.round(h * 5);
        health.innerHTML = Array.from({length: 5}, (_, i) =>
            `<span class="${i < dots ? 'dot-on' : 'dot-off'}">●</span>`
        ).join('');
    }

    // Active/disabled state
    if (card) {
        card.classList.toggle('disabled', !event.is_active);
    }
}

async function loadDaemonTimeline() {
    try {
        const data = await api('/api/daemon/timeline');
        if (!data) return;
        const bar = document.getElementById('timeline-bar');
        const now = new Date().getHours();

        bar.innerHTML = Array.from({length: 24}, (_, h) => {
            const hourStr = String(h).zfill ? String(h).padStart(2, '0') : h.toString().padStart(2, '0');
            const hourData = data[hourStr] || { categories: {}, total: 0 };
            const total = hourData.total || 0;
            const height = Math.min(total * 3, 40) || 4;

            // Determine dominant category
            let cat = 'idle';
            let maxCount = 0;
            for (const [c, count] of Object.entries(hourData.categories || {})) {
                if (count > maxCount) { maxCount = count; cat = c; }
            }

            return `<div class="timeline-block ${cat}${h === now ? ' current' : ''}" style="height:${height}px" title="${hourStr}:00 — ${total} events (${cat})"></div>`;
        }).join('');

        document.getElementById('timeline-date').textContent = new Date().toLocaleDateString('pt-BR');
    } catch (e) {}
}

function updateTimelineBlock(event) {
    const hour = new Date().getHours();
    const bar = document.getElementById('timeline-bar');
    if (!bar) return;
    const blocks = bar.children;
    if (blocks[hour]) {
        const current = parseInt(blocks[hour].style.height) || 4;
        blocks[hour].style.height = Math.min(current + 3, 40) + 'px';
        blocks[hour].className = `timeline-block ${event.category || 'outreach'} current`;
    }
}

async function loadDaemonDecisions() {
    try {
        const data = await api('/api/daemon/decisions');
        if (!data || !data.length) {
            document.getElementById('decisions-list').innerHTML = '<div style="font-size:11px;color:var(--text-3);padding:12px;text-align:center">Nenhuma decisao registrada</div>';
            return;
        }
        const _di = typeof window.icon === 'function' ? window.icon : () => '';
        document.getElementById('decisions-list').innerHTML = data.slice(0, 10).map(d => {
            const icons = { handle_reply: 'message-circle', execute_sequence_step: 'inbox', enrich_batch: 'search', discovery_scrape: 'globe', batch_audit: 'clipboard', recalculate_scores: 'bar-chart', weekly_report: 'file-text' };
            const icon = _di(icons[d.action] || 'zap');
            const time = d.timestamp ? new Date(d.timestamp).toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit'}) : '';
            return `<div class="decision-item"><span class="decision-icon">${icon}</span><span class="decision-text">${d.reason}</span><span class="decision-time">${time}</span></div>`;
        }).join('');
    } catch (e) {}
}

function addDecisionItem(event) {
    const list = document.getElementById('decisions-list');
    if (!list) return;
    const _di2 = typeof window.icon === 'function' ? window.icon : () => '';
    const icons = { handle_reply: 'message-circle', execute_sequence_step: 'inbox', enrich_batch: 'search', discovery_scrape: 'globe', batch_audit: 'clipboard', send_proposal: 'send' };
    const icon = _di2(icons[event.action] || 'zap');
    const time = new Date().toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit'});
    const item = document.createElement('div');
    item.className = 'decision-item';
    item.innerHTML = `<span class="decision-icon">${icon}</span><span class="decision-text">${event.reason}</span><span class="decision-time">${time}</span>`;
    list.prepend(item);
    // Keep max 10
    while (list.children.length > 10) list.removeChild(list.lastChild);
}

async function loadDaemonFeed() {
    try {
        const data = await api('/api/daemon/log?limit=30');
        if (!data || !data.length) {
            document.getElementById('feed-list').innerHTML = '<div style="font-size:11px;color:var(--text-3);padding:20px;text-align:center">Nenhum evento registrado</div>';
            return;
        }
        document.getElementById('feed-list').innerHTML = data
            .filter(e => _feedFilter === 'all' || e.category === _feedFilter)
            .slice(0, 20)
            .map(e => renderFeedItem(e))
            .join('');
    } catch (e) {}
}

function renderFeedItem(event) {
    const _fi = typeof window.icon === 'function' ? window.icon : () => '';
    const catIcons = { outreach: 'inbox', reply: 'message-circle', discovery: 'search', enrichment: 'search', audit: 'clipboard', scoring: 'bar-chart', system: 'settings', error: 'alert-triangle' };
    const icon = _fi(catIcons[event.category] || 'zap');
    const time = event.timestamp ? new Date(event.timestamp).toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit'}) : '';
    const cat = event.category || 'system';
    const title = event.action || event.message || '';
    const detail = event.metadata?.prospect_name || event.metadata?.channel || '';
    const highlight = event.level === 'error' ? ' error' : (event.category === 'reply' ? ' highlight' : '');

    return `<div class="feed-item ${cat}${highlight}">
        <div class="feed-item-header"><span class="feed-item-icon">${icon}</span><span class="feed-item-time">${time}</span></div>
        <div class="feed-item-title">${title}</div>
        ${detail ? `<div class="feed-item-detail">${detail}</div>` : ''}
        ${event.metadata?.intent ? `<span class="feed-item-badge">${event.metadata.intent}</span>` : ''}
    </div>`;
}

function addFeedItem(event, highlight = false) {
    const list = document.getElementById('feed-list');
    if (!list) return;
    if (_feedFilter !== 'all' && event.category !== _feedFilter) return;

    const item = document.createElement('div');
    item.innerHTML = renderFeedItem({...event, level: highlight ? 'highlight' : event.level});
    const feedItem = item.firstElementChild;
    list.prepend(feedItem);

    // Keep max 30 items
    while (list.children.length > 30) list.removeChild(list.lastChild);
}

function filterFeed(filter) {
    _feedFilter = filter;
    document.querySelectorAll('.feed-filter').forEach(b => b.classList.toggle('active', b.dataset.filter === filter));
    loadDaemonFeed();
}

/* --- Activity Orbit (Canvas) --- */
function initOrbitCanvas() {
    const canvas = document.getElementById('orbit-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width = canvas.offsetWidth * 2;
    const H = canvas.height = canvas.offsetHeight * 2;
    ctx.scale(2, 2);
    const w = W / 2, h = H / 2;
    const cx = w / 2, cy = h / 2;

    const dots = [];
    const flashes = [];
    const beams = [];

    window._orbit = {
        addEvent(event) {
            if (event.action === 'message_sent' || event.type === 'activity') {
                // Add beam from center to random position on inner ring
                const angle = Math.random() * Math.PI * 2;
                const r = 60 + Math.random() * 20;
                beams.push({ x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r, life: 1.0, color: '#d1fe17' });
            }
            if (event.action === 'prospect_discovered' || event.category === 'discovery') {
                const angle = Math.random() * Math.PI * 2;
                dots.push({ angle, ring: 2, color: '#666', life: 1.0, r: 3 });
            }
        },
        flash(id, color) {
            const angle = Math.random() * Math.PI * 2;
            flashes.push({ angle, color, life: 1.0 });
        }
    };

    // Seed some initial dots
    for (let i = 0; i < 30; i++) {
        dots.push({ angle: Math.random() * Math.PI * 2, ring: Math.floor(Math.random() * 3), color: ['#7c3aed', '#34d399', '#60a5fa', '#fbbf24'][Math.floor(Math.random()*4)], life: 1, r: 2 + Math.random() * 2 });
    }

    function render() {
        ctx.clearRect(0, 0, w, h);

        // Draw rings
        [40, 70, 100].forEach((r, i) => {
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.strokeStyle = `rgba(255,255,255,${0.05 + i * 0.02})`;
            ctx.lineWidth = 1;
            ctx.stroke();
        });

        // Draw center (Hermes)
        ctx.beginPath();
        ctx.arc(cx, cy, 12, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(209,254,23,0.1)';
        ctx.fill();
        ctx.beginPath();
        ctx.arc(cx, cy, 6, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(209,254,23,0.5)';
        ctx.fill();

        // Draw dots (orbiting slowly)
        const time = Date.now() / 5000;
        dots.forEach(dot => {
            const ringR = [40, 70, 100][dot.ring] || 70;
            const speed = [0.3, 0.2, 0.1][dot.ring] || 0.1;
            const x = cx + Math.cos(dot.angle + time * speed) * ringR;
            const y = cy + Math.sin(dot.angle + time * speed) * ringR;
            ctx.beginPath();
            ctx.arc(x, y, dot.r, 0, Math.PI * 2);
            ctx.fillStyle = dot.color;
            ctx.globalAlpha = dot.ring === 2 ? 0.4 : 0.8;
            ctx.fill();
            ctx.globalAlpha = 1;
        });

        // Draw beams (fade out)
        for (let i = beams.length - 1; i >= 0; i--) {
            const beam = beams[i];
            ctx.beginPath();
            ctx.moveTo(cx, cy);
            ctx.lineTo(beam.x, beam.y);
            ctx.strokeStyle = beam.color;
            ctx.globalAlpha = beam.life;
            ctx.lineWidth = 2;
            ctx.stroke();
            ctx.globalAlpha = 1;
            beam.life -= 0.02;
            if (beam.life <= 0) beams.splice(i, 1);
        }

        // Draw flashes
        for (let i = flashes.length - 1; i >= 0; i--) {
            const f = flashes[i];
            const r = 70;
            const x = cx + Math.cos(f.angle) * r;
            const y = cy + Math.sin(f.angle) * r;
            ctx.beginPath();
            ctx.arc(x, y, 8 * f.life, 0, Math.PI * 2);
            ctx.fillStyle = f.color;
            ctx.globalAlpha = f.life;
            ctx.fill();
            ctx.globalAlpha = 1;
            f.life -= 0.03;
            if (f.life <= 0) flashes.splice(i, 1);
        }

        requestAnimationFrame(render);
    }
    render();
}

init();

/* ============================================================
   LINKEDIN PAGE
   ============================================================ */

let _liPollInterval = null;
let _liActiveCampaignId = null;

// ── Chip multi-select ──
document.addEventListener('click', e => {
    const chip = e.target.closest('.li-chip:not(.li-chip-custom)');
    if (chip) chip.classList.toggle('selected');
});

// ── Note template toggle ──
document.addEventListener('change', e => {
    if (e.target.id === 'li-connect-note') {
        const tmpl = document.getElementById('li-connect-note-template');
        if (tmpl) tmpl.style.display = e.target.checked ? 'block' : 'none';
    }
    if (e.target.id === 'li-view-loc-tabs' || e.target.closest('#li-view-loc-tabs')) {
        const val = document.querySelector('#li-view-loc-tabs .li-tab.active')?.dataset.val;
        const custom = document.getElementById('li-view-loc-custom');
        if (custom) custom.style.display = val === 'custom' ? 'block' : 'none';
    }
});

function liSelectTab(btn, groupId) {
    document.querySelectorAll(`#${groupId} .li-tab`).forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    // handle show/hide for location custom input
    if (groupId === 'li-view-loc-tabs') {
        const custom = document.getElementById('li-view-loc-custom');
        if (custom) custom.style.display = btn.dataset.val === 'custom' ? 'block' : 'none';
    }
}

function liConnectModeChange() {
    const mode = document.querySelector('#li-connect-mode-tabs .li-tab.active')?.dataset.val || 'search';
    document.getElementById('li-connect-search-fields').style.display = mode === 'search' ? 'block' : 'none';
    document.getElementById('li-connect-urls-fields').style.display = mode === 'urls' ? 'block' : 'none';
}

function liAddTag(event, containerId, inputId) {
    if (event.key !== 'Enter' && event.key !== ',') return;
    event.preventDefault();
    const input = document.getElementById(inputId);
    const val = input.value.trim().replace(/^#/, '');
    if (!val) return;
    const container = document.getElementById(containerId);
    const tag = document.createElement('span');
    tag.className = 'li-tag';
    tag.innerHTML = `${escapeHtml(val)} <span onclick="this.parentElement.remove()" style="cursor:pointer;opacity:.6">×</span>`;
    container.appendChild(tag);
    input.value = '';
}

function liAddCustomRole(cardType) {
    const val = prompt('Digite a função personalizada:');
    if (!val) return;
    const container = document.getElementById('li-chips-roles');
    const chip = document.createElement('div');
    chip.className = 'li-chip selected';
    chip.dataset.val = val;
    chip.textContent = val;
    const addBtn = container.querySelector('.li-chip-custom');
    container.insertBefore(chip, addBtn);
}

// ── Load page data ──
// ============================================================================
// LinkedIn — Phase 2 (real backend integration)
// ============================================================================
// Maps cryptic errors (Patchright / LinkedIn / network) into plain Portuguese.
function humanizeLiError(raw) {
    if (!raw) return '';
    const m = String(raw).toLowerCase();
    // Anti-bot / rate-limiting patterns
    if (m.includes('err_http_response_code_failure') && m.includes('/feed/')) {
        return 'LinkedIn recusou nosso acesso à página inicial. Geralmente significa que detectou padrão de robô e bloqueou temporariamente — coloca a conta em "quarentena" por 30-60 min. Não é problema do código; é proteção deles.';
    }
    if (m.includes('err_too_many_redirects')) {
        return 'O LinkedIn ficou redirecionando em loop — isso acontece quando o site quer forçar uma verificação humana (captcha, e-mail) ou suspeita da sessão. Aguarde ~30 min e tente de novo.';
    }
    if (m.includes('429') || m.includes('too many requests')) {
        return 'Limite de requisições atingido — fizemos chamadas demais em pouco tempo. O LinkedIn pede uma pausa.';
    }
    if (m.includes('err_connection_refused') || m.includes('err_name_not_resolved')) {
        return 'Não conseguimos nem chegar no LinkedIn. Pode ser problema de internet ou do proxy SOCKS5 (verifica se o SSH tunnel está rodando).';
    }
    if (m.includes('timeout') && m.includes('navigating')) {
        return 'O LinkedIn demorou demais para carregar a página (timeout). Pode ser instabilidade da rede ou throttling silencioso.';
    }
    if (m.includes('session max duration') || m.includes('session_max')) {
        return 'O contador interno de sessão atingiu o limite. O sistema reinicia automático na próxima campanha.';
    }
    if (m.includes('login') || m.includes('uas/login') || m.includes('checkpoint') || m.includes('challenge')) {
        return 'O LinkedIn pediu que façamos login de novo (cookie expirou ou foi invalidado). A extension do Chrome deveria captar o novo cookie automaticamente assim que você logar.';
    }
    if (m.includes('rate limit') && m.includes('weekly')) {
        return 'Atingimos o limite semanal de conexões para esta conta. Aguarda até a próxima semana ou aumenta o limite na config.';
    }
    if (m.includes('rate limit') && m.includes('daily')) {
        return 'Atingimos o limite diário desta conta. O contador reseta meia-noite UTC.';
    }
    if (m.includes('ollama') && m.includes('timeout')) {
        return 'A IA local (Ollama) demorou demais para gerar o texto. Verifica se o modelo qwen3:8b está rodando no seu PC.';
    }
    if (m.includes('ollama')) {
        return 'Falha ao conversar com a IA local (Ollama). Verifica se está rodando: http://localhost:11434';
    }
    if (m.includes('claude') && m.includes('subprocess')) {
        return 'Falha na validação do comentário pelo Claude Code (subprocess). Pode ser que o CLI não esteja disponível na VM.';
    }
    if (m.includes('no such file') && m.includes('session')) {
        return 'Arquivo de sessão do navegador não encontrado. Execute autenticação primeiro.';
    }
    if (m.includes('mandatory_spacing_30min') || m.includes('cooldown obrigatório')) {
        return 'Aguardando os 30 minutos obrigatórios entre uma campanha e outra (proteção da conta).';
    }
    if (m.includes('working hours') || m.includes('fora do horário') || m.includes('fora dos dias úteis')) {
        return 'Fora do horário comercial configurado. O sistema só roda campanhas em horário de trabalho para parecer uso humano real.';
    }
    if (m.includes('lurking') || m.includes('lurking phase')) {
        return 'Conta em fase de aquecimento — só browsing passivo nos primeiros dias para o LinkedIn confiar. Conexões e comentários liberam após o período inicial.';
    }
    if (m.includes('pré-aquecimento') || m.includes('pre-outreach') || m.includes('warming')) {
        return 'Simulando navegação humana antes da ação (feed, notificações, rede). Reduz drasticamente detecção de robô.';
    }
    if (m.includes('chromium_bundled') || m.includes('chrome stable não instalado')) {
        return 'Chrome real não está instalado no servidor — usando Chromium genérico. Fingerprint TLS pior. Recomendado instalar google-chrome-stable na VM.';
    }
    if (m.includes('patchright_response_code_failure')) {
        return 'O LinkedIn recusou o acesso do navegador automatizado. Conta em cooldown de 30 min.';
    }
    if (m.includes('http_429_detected_in_run')) {
        return 'O LinkedIn nos mandou um "calma aí" (HTTP 429) no meio da campanha. Bloqueamos novas tentativas por 30 min.';
    }
    if (m.includes('sem mais resultados')) {
        return 'A busca não retornou nenhum perfil compatível. Pode ser que os filtros estão muito restritivos ou o LinkedIn escondeu os resultados.';
    }
    // Generic fallback: trim noisy stack trace, return first useful line
    const firstLine = String(raw).split('\n')[0].slice(0, 200);
    return firstLine || 'Erro desconhecido';
}

async function loadLinkedInPage() {
    await Promise.all([loadLinkedInStatus(), loadLinkedInCampaigns()]);
}

async function loadLinkedInStatus() {
    try {
        const [data, health] = await Promise.all([
            api('/api/linkedin/status'),
            api('/api/linkedin/health').catch(() => ({state: 'unknown'})),
        ]);
        _renderLiStatus(data);
        _liHealth = health || {state: 'unknown'};
        _renderLiHealth(_liHealth);
        _applyLiHealthToButtons(_liHealth);
    } catch (e) {
        console.warn('LinkedIn status error:', e);
    }
}

let _liHealth = {state: 'unknown'};

function _renderLiHealth(h) {
    const badge = document.getElementById('li-health-badge');
    const dot = document.getElementById('li-health-dot');
    const lbl = document.getElementById('li-health-label');
    const retry = document.getElementById('li-health-retry');
    if (!badge || !dot || !lbl) return;
    badge.style.display = 'inline-flex';
    const colors = {
        ok: 'var(--lime)',
        cooldown: '#f59e0b',
        challenge: '#ef4444',
        blocked: '#ef4444',
        unknown: 'var(--text-3)',
    };
    const labels = {
        ok: 'LinkedIn OK',
        cooldown: 'Em cooldown',
        challenge: 'Sessão expirada',
        blocked: 'Bloqueado',
        unknown: 'Verificando...',
    };
    dot.style.background = colors[h.state] || colors.unknown;
    lbl.textContent = labels[h.state] || 'Desconhecido';
    if (h.state !== 'ok' && h.retry_after_seconds) {
        const min = Math.ceil(h.retry_after_seconds / 60);
        retry.textContent = ` · retry em ~${min}min`;
    } else {
        retry.textContent = '';
    }
}

function _applyLiHealthToButtons(h) {
    // v6: botões NUNCA são bloqueados — campanha sempre é enviada.
    // Se gates ativos, vira agendada. Tooltip explica o que vai acontecer.
    const healthOk = h?.state === 'ok' || h?.state === 'unknown';
    const wait = _liRateLimits?.next_launch_in_seconds || 0;
    const launchOk = wait <= 0;
    const hoursOk = _liRateLimits?.working_hours_ok !== false;
    const allOk = healthOk && launchOk && hoursOk;
    let tip = '';
    if (!hoursOk) {
        const reason = _liRateLimits?.working_hours_reason || 'fora do horário';
        tip = `Fora do horário (${reason}). Campanha será agendada para a próxima janela.`;
    } else if (!healthOk) {
        tip = `LinkedIn em ${h.state} — campanha será agendada até recuperar`;
    } else if (!launchOk) {
        tip = `Cooldown 30min entre launches: campanha será agendada para daqui ${Math.ceil(wait / 60)}min`;
    }
    document.querySelectorAll('.li-launch-btn').forEach(btn => {
        btn.disabled = false;
        btn.style.opacity = '';
        btn.style.cursor = '';
        if (tip) btn.setAttribute('title', tip); else btn.removeAttribute('title');
    });
    const retry = document.getElementById('li-health-retry');
    if (retry && healthOk && !launchOk) {
        retry.textContent = ` · próx. launch em ${Math.ceil(wait / 60)}min`;
    } else if (retry && healthOk && launchOk) {
        retry.textContent = '';
    }
}

let _liRateLimits = {};
let _liStatusTickerHandle = null;
let _liStatusRefreshHandle = null;

function _liStartLiveTickers() {
    // 1) 1-second visual ticker — decrements next_launch_in_seconds locally
    //    and re-applies button state when countdown hits zero.
    if (_liStatusTickerHandle) clearInterval(_liStatusTickerHandle);
    _liStatusTickerHandle = setInterval(() => {
        if (currentPage !== 'linkedin') return;
        const cur = _liRateLimits.next_launch_in_seconds || 0;
        if (cur <= 0) return;
        _liRateLimits.next_launch_in_seconds = cur - 1;
        _applyLiHealthToButtons(_liHealth);
        // When we cross zero, force a fresh server check to sync ground truth
        if (cur - 1 <= 0) {
            loadLinkedInStatus();
        }
    }, 1000);

    // 2) 30-second hard refresh — re-pulls status + health from server
    //    so anything done outside this tab (cron, other dashboard) syncs.
    if (_liStatusRefreshHandle) clearInterval(_liStatusRefreshHandle);
    _liStatusRefreshHandle = setInterval(() => {
        if (currentPage === 'linkedin') loadLinkedInStatus();
    }, 30000);

    // 3) Scheduled banner countdown ticker (1s)
    _liStartSchedTicker();
}

function _liStopLiveTickers() {
    if (_liStatusTickerHandle) { clearInterval(_liStatusTickerHandle); _liStatusTickerHandle = null; }
    if (_liStatusRefreshHandle) { clearInterval(_liStatusRefreshHandle); _liStatusRefreshHandle = null; }
    if (_liSchedTickerHandle) { clearInterval(_liSchedTickerHandle); _liSchedTickerHandle = null; }
}

// v6: Live countdown for scheduled campaign banners
let _liSchedTickerHandle = null;
function _liStartSchedTicker() {
    if (_liSchedTickerHandle) clearInterval(_liSchedTickerHandle);
    const tick = () => {
        const banners = document.querySelectorAll('.li-scheduled-banner');
        const now = Date.now();
        banners.forEach(b => {
            const targetMs = parseInt(b.getAttribute('data-target-ms') || '0');
            const span = b.querySelector('.li-sched-countdown');
            if (!span) return;
            const diff = Math.max(0, targetMs - now);
            if (diff <= 0) {
                span.textContent = 'qualquer segundo agora…';
                return;
            }
            const totalSec = Math.floor(diff / 1000);
            const h = Math.floor(totalSec / 3600);
            const m = Math.floor((totalSec % 3600) / 60);
            const s = totalSec % 60;
            span.textContent = h > 0
                ? `${h}h ${String(m).padStart(2,'0')}min`
                : (m > 0 ? `${m}min ${String(s).padStart(2,'0')}s` : `${s}s`);
        });
    };
    tick();
    _liSchedTickerHandle = setInterval(tick, 1000);
}

function _renderLiScheduledConfig(c) {
    let cfg = c.config;
    if (typeof cfg === 'string') { try { cfg = JSON.parse(cfg); } catch { cfg = {}; } }
    cfg = cfg || {};

    const accent = LI_TYPE_COLORS[c.type] || '#3b82f6';
    const big = (n) => `<span class="li-sc-num" style="color:${accent}">${n ?? '—'}</span>`;
    const chips = (arr, kind = '') => (arr && arr.length)
        ? arr.map(t => `<span class="li-sc-chip ${kind}">${escapeHtml(t)}</span>`).join('')
        : '<em class="li-sc-empty">nenhum configurado</em>';
    const yes = '<span class="li-sc-yes">✓ Sim</span>';
    const no = '<span class="li-sc-no">— Não</span>';

    let headline = '';
    let blocks = '';

    if (c.type === 'view') {
        const modeLabel = cfg.ghost_only ? 'Ghost View' : 'View + Interação';
        const modeDesc = cfg.ghost_only
            ? 'Visita o perfil sem nenhuma interação. O LinkedIn notifica o dono ("alguém viu seu perfil"), criando reciprocidade — muitos retornam o view ou seguem você.'
            : 'Visita + interação ativa: pode seguir, curtir um post recente, e gerar engajamento visível.';
        const n = cfg.max_profiles ?? '—';
        const noun = n === 1 ? 'perfil de recrutador' : 'perfis de recrutadores';
        headline = `Vai visitar até ${big(n)} <span class="li-sc-noun">${noun}</span> em <span class="li-sc-strong">${escapeHtml(cfg.location || '—')}</span>.`;
        blocks = `
            <div class="li-sc-block">
                <div class="li-sc-block-head">Filtros aplicados</div>
                <div class="li-sc-row">
                    <span class="li-sc-row-label">Tipos de recrutador</span>
                    <div class="li-sc-row-value li-sc-chips">${chips(cfg.roles)}</div>
                </div>
                <div class="li-sc-row">
                    <span class="li-sc-row-label">Localização</span>
                    <div class="li-sc-row-value">${escapeHtml(cfg.location || '—')}</div>
                </div>
            </div>
            <div class="li-sc-block">
                <div class="li-sc-block-head">Modo de interação</div>
                <div class="li-sc-mode">
                    <div class="li-sc-mode-title" style="color:${accent}">${escapeHtml(modeLabel)}</div>
                    <div class="li-sc-mode-desc">${escapeHtml(modeDesc)}</div>
                </div>
            </div>
        `;
    } else if (c.type === 'engage') {
        const toneLabels = {professional: 'Profissional', casual: 'Casual', technical: 'Técnico'};
        const actsDesc = [];
        if (cfg.do_like) actsDesc.push('curtir');
        if (cfg.do_comment) actsDesc.push('comentar com IA');
        const actsStr = actsDesc.length ? actsDesc.join(' e ') : 'apenas ler';
        const n = cfg.max_posts ?? '—';
        const noun = n === 1 ? 'post relevante' : 'posts relevantes';
        headline = `Vai ${actsStr} em até ${big(n)} <span class="li-sc-noun">${noun}</span>, tom <span class="li-sc-strong">${escapeHtml(toneLabels[cfg.tone] || cfg.tone || '—')}</span>.`;
        blocks = `
            <div class="li-sc-block">
                <div class="li-sc-block-head">O que buscar</div>
                <div class="li-sc-row">
                    <span class="li-sc-row-label">Keywords / hashtags</span>
                    <div class="li-sc-row-value li-sc-chips">${chips(cfg.keywords, 'g')}</div>
                </div>
                <div class="li-sc-row">
                    <span class="li-sc-row-label">Indústrias</span>
                    <div class="li-sc-row-value li-sc-chips">${chips(cfg.industries, 'g')}</div>
                </div>
            </div>
            <div class="li-sc-block">
                <div class="li-sc-block-head">Ações por post</div>
                <div class="li-sc-actions">
                    ${cfg.do_like
                        ? `<div class="li-sc-action li-sc-action-on">
                            <div class="li-sc-action-title">${yes} Curtir</div>
                            <div class="li-sc-action-desc">Like simples no post — sinal social de baixo custo.</div>
                          </div>`
                        : `<div class="li-sc-action li-sc-action-off"><div class="li-sc-action-title">${no} Curtir</div></div>`}
                    ${cfg.do_comment
                        ? `<div class="li-sc-action li-sc-action-on">
                            <div class="li-sc-action-title">${yes} Comentar com IA</div>
                            <div class="li-sc-action-desc">Ollama qwen3:8b gera comentário no tom "<strong>${escapeHtml(toneLabels[cfg.tone] || cfg.tone)}</strong>". Claude valida humanidade antes de postar.</div>
                          </div>`
                        : `<div class="li-sc-action li-sc-action-off"><div class="li-sc-action-title">${no} Comentar</div></div>`}
                </div>
            </div>
        `;
    } else if (c.type === 'connect') {
        const modeLabels = {search: 'Busca por função', urls: 'Lista de URLs', visited: 'Perfis já visitados'};
        const modeDescs = {
            search: 'Busca pessoas no LinkedIn que correspondem ao termo + localização.',
            urls: 'Envia convites direto pra cada URL fornecida — sem busca.',
            visited: 'Conecta com perfis que o pipeline view já abriu recentemente.',
        };
        const n = cfg.max_connections ?? '—';
        const noun = n === 1 ? 'convite de conexão' : 'convites de conexão';
        const noteStr = cfg.send_note ? 'com nota personalizada por IA' : 'sem nota personalizada';
        headline = `Vai enviar até ${big(n)} <span class="li-sc-noun">${noun}</span> ${noteStr}.`;
        let modeBlock = '';
        if (cfg.mode === 'search') {
            modeBlock = `
                <div class="li-sc-row">
                    <span class="li-sc-row-label">Termo de busca</span>
                    <div class="li-sc-row-value"><strong>${escapeHtml(cfg.query || '—')}</strong></div>
                </div>
                <div class="li-sc-row">
                    <span class="li-sc-row-label">Localização</span>
                    <div class="li-sc-row-value">${escapeHtml(cfg.location || '—')}</div>
                </div>`;
        } else if (cfg.mode === 'urls') {
            const urls = cfg.profile_urls || [];
            modeBlock = `
                <div class="li-sc-row">
                    <span class="li-sc-row-label">URLs fornecidas</span>
                    <div class="li-sc-row-value"><strong>${urls.length}</strong> ${urls.length === 1 ? 'URL alvo' : 'URLs alvo'}</div>
                </div>`;
        }
        blocks = `
            <div class="li-sc-block">
                <div class="li-sc-block-head">Origem dos perfis</div>
                <div class="li-sc-mode">
                    <div class="li-sc-mode-title" style="color:${accent}">${escapeHtml(modeLabels[cfg.mode] || cfg.mode || '—')}</div>
                    <div class="li-sc-mode-desc">${escapeHtml(modeDescs[cfg.mode] || '')}</div>
                </div>
                ${modeBlock}
            </div>
            <div class="li-sc-block">
                <div class="li-sc-block-head">Mensagem de conexão</div>
                ${cfg.send_note
                    ? `<div class="li-sc-mode">
                          <div class="li-sc-mode-title" style="color:#22c55e">${yes} Nota personalizada</div>
                          <div class="li-sc-mode-desc">Cada convite carrega uma nota gerada com Ollama, referenciando nome + empresa do alvo.</div>
                       </div>
                       ${cfg.note_template
                           ? `<div class="li-sc-template">
                                <div class="li-sc-template-label">Template usado</div>
                                <code>${escapeHtml(cfg.note_template)}</code>
                              </div>`
                           : ''}`
                    : `<div class="li-sc-mode">
                          <div class="li-sc-mode-title" style="color:var(--text-3)">${no} Convite seco</div>
                          <div class="li-sc-mode-desc">Envia só o botão "Conectar" sem mensagem. Aceite tende a ser menor.</div>
                       </div>`}
            </div>
        `;
    } else if (c.type === 'discover') {
        const scopeLabels = {recruiters_only: 'Só Recrutadores', hr_full: 'RH Completo', all_employees: 'Todos os funcionários'};
        const scopeDescs = {
            recruiters_only: 'Filtra título contendo "recruiter", "talent", "headhunter", "RH" e variantes.',
            hr_full: 'Inclui todos do departamento RH/People (não só recrutadores).',
            all_employees: 'Lista todos os funcionários visíveis (sem filtro de função).',
        };
        const actionLabels = {save: 'Só salvar', view: 'Visitar cada perfil', connect: 'Solicitar conexão direto'};
        const actionDescs = {
            save: 'Salva os perfis encontrados no banco — você revisa depois.',
            view: 'Encadeia uma campanha de Visitar Perfis com os perfis encontrados.',
            connect: 'Encadeia uma campanha de Conexão direto.',
        };
        const totalCompanies = (cfg.companies || []).length;
        const maxPer = cfg.max_per_company ?? '—';
        headline = `Vai descobrir até ${big(maxPer)} <span class="li-sc-noun">${maxPer === 1 ? 'perfil' : 'perfis'}</span> por empresa em <span class="li-sc-strong">${totalCompanies}</span> ${totalCompanies === 1 ? 'empresa' : 'empresas'}.`;
        blocks = `
            <div class="li-sc-block">
                <div class="li-sc-block-head">Empresas alvo</div>
                <div class="li-sc-row">
                    <div class="li-sc-row-value li-sc-chips" style="margin-left:0">${chips(cfg.companies, 'p')}</div>
                </div>
            </div>
            <div class="li-sc-block">
                <div class="li-sc-block-head">Critério de busca</div>
                <div class="li-sc-mode">
                    <div class="li-sc-mode-title" style="color:${accent}">${escapeHtml(scopeLabels[cfg.scope] || cfg.scope || '—')}</div>
                    <div class="li-sc-mode-desc">${escapeHtml(scopeDescs[cfg.scope] || '')}</div>
                </div>
            </div>
            <div class="li-sc-block">
                <div class="li-sc-block-head">Após descoberta</div>
                <div class="li-sc-mode">
                    <div class="li-sc-mode-title" style="color:${accent}">${escapeHtml(actionLabels[cfg.post_action] || cfg.post_action || '—')}</div>
                    <div class="li-sc-mode-desc">${escapeHtml(actionDescs[cfg.post_action] || '')}</div>
                </div>
            </div>
        `;
    } else {
        headline = `Configuração: <code>${escapeHtml(JSON.stringify(cfg))}</code>`;
    }

    return `<div class="li-sc-card" style="--sc-accent:${accent}">
        <div class="li-sc-headline">${headline}</div>
        <div class="li-sc-blocks">${blocks}</div>
    </div>`;
}

async function liCancelScheduled(campaignId) {
    if (!confirm(`Cancelar agendamento da campanha #${campaignId}?`)) return;
    try {
        const r = await api(`/api/linkedin/campaigns/${campaignId}/cancel`, { method: 'POST' });
        if (r.ok) {
            showToast(`Agendamento da #${campaignId} cancelado`, 'success');
            const c = _liAllCampaigns.find(x => x.id === campaignId);
            if (c) { c.status = 'cancelled'; _renderLiMonitor(); }
        } else {
            showToast(`Erro: ${r.error || 'falha ao cancelar'}`, 'error');
        }
    } catch (e) {
        showToast(`Erro: ${e.message || e}`, 'error');
    }
}

function _renderLiStatus(data) {
    const stats = data.rate_limits || {};
    _liRateLimits = stats;

    // v5: Working hours badge
    const hoursBadge = document.getElementById('li-hours-badge');
    const hoursDot = document.getElementById('li-hours-dot');
    const hoursLbl = document.getElementById('li-hours-label');
    if (hoursBadge && hoursDot && hoursLbl) {
        if (stats.working_hours_ok === false) {
            hoursBadge.style.display = 'inline-flex';
            hoursDot.style.background = '#f59e0b';
            const winStr = stats.working_hours_window || '';
            hoursLbl.textContent = `Fora do horário ${winStr}`;
            hoursBadge.title = stats.working_hours_reason
                ? `${stats.working_hours_reason} · próx: ${stats.next_working_window || 'amanhã'}`
                : '';
        } else if (stats.working_hours_window) {
            hoursBadge.style.display = 'inline-flex';
            hoursDot.style.background = 'var(--lime)';
            hoursLbl.textContent = `Horário ${stats.working_hours_window}`;
        }
    }

    // v5: Lurking phase badge
    const lurkBadge = document.getElementById('li-lurking-badge');
    const lurkLbl = document.getElementById('li-lurking-label');
    if (lurkBadge && lurkLbl) {
        if (stats.lurking_phase) {
            lurkBadge.style.display = 'inline-flex';
            const dayNum = stats.warmup_day || 0;
            const totalLurk = stats.lurking_days_total || 7;
            lurkLbl.textContent = `Lurking ${dayNum + 1}/${totalLurk}`;
            lurkBadge.title = 'Fase de aquecimento — só browsing passivo. Conexões/comentários bloqueados.';
        } else {
            lurkBadge.style.display = 'none';
        }
    }
    const dot = document.getElementById('li-session-dot');
    const acct = document.getElementById('li-status-account');
    const badge = document.getElementById('li-account-type-badge');
    const proxyDot = document.getElementById('li-proxy-dot');
    const proxyBadge = document.getElementById('li-proxy-badge');

    if (dot) dot.style.background = data.session_ok ? 'var(--lime)' : 'var(--red)';
    if (acct) acct.textContent = data.session_ok
        ? (data.account_email || 'Sessão ativa')
        : 'Sessão inativa — clique em Reconectar';
    if (badge) {
        badge.textContent = (data.account_type || 'free').toUpperCase();
        badge.className = 'li-status-badge li-badge-' + (data.account_type || 'free');
    }
    if (proxyDot) proxyDot.style.background = data.proxy_alive ? 'var(--lime)' : 'var(--red)';
    if (proxyBadge) {
        const txt = data.proxy_configured
            ? (data.proxy_alive ? '● Proxy BR/Cuiabá' : '● Proxy offline')
            : '● Direto (sem proxy)';
        proxyBadge.innerHTML = txt;
        proxyBadge.style.color = data.proxy_alive ? 'var(--lime)' : 'var(--red)';
    }

    // warmup
    const wu = stats.warmup_multiplier != null ? stats.warmup_multiplier : 1;
    const wuDay = stats.warmup_day || 14;
    const wuDays = stats.warmup_days || 14;
    const wuComplete = stats.warmup_complete;
    const fill = document.getElementById('li-warmup-fill');
    const label = document.getElementById('li-warmup-label');
    if (fill) fill.style.width = `${Math.round(wu * 100)}%`;
    if (label) label.textContent = wuComplete ? `Dia ${wuDay}/${wuDays} ✓` : `Dia ${wuDay}/${wuDays}`;

    // daily stats
    const sv = document.getElementById('li-stat-views');
    const sc = document.getElementById('li-stat-connects');
    const sl = document.getElementById('li-stat-likes');
    const sm = document.getElementById('li-stat-comments');
    if (sv) sv.textContent = stats.daily_views ?? '–';
    if (sc) sc.textContent = stats.daily_connections ?? '–';
    if (sl) sl.textContent = stats.daily_engagements ?? '–';
    if (sm) sm.textContent = stats.daily_comments ?? '–';
}

async function liReconnect() {
    showToast('Iniciando reconexão na VM...', 'info');
    try {
        const r = await api('/api/linkedin/auth', { method: 'POST' });
        if (r.ok) showToast('Sessão estabelecida!', 'success');
        else showToast(r.note || r.error || 'Verifique a VM', 'warning');
        await loadLinkedInStatus();
    } catch (e) {
        showToast('Erro ao reconectar: ' + e.message, 'error');
    }
}

// ── Start campaign ──
async function liStartCampaign(type) {
    const config = _buildLiCampaignConfig(type);
    if (!config) return;

    // v6: sem pré-flight bloqueante. Backend decide se vira agendada ou dispara.

    try {
        const r = await api(`/api/linkedin/campaigns/${type}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config),
        });
        if (r.status === 'scheduled') {
            const when = new Date(r.scheduled_for).toLocaleString('pt-BR', {
                day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
            });
            showToast(
                `📅 Campanha #${r.campaign_id} agendada para ${when} — ${r.schedule_reason || ''}`,
                'info'
            );
            loadLinkedInCampaigns();
            return;
        }
        if (r.status === 'cooldown') {
            showToast(`Bloqueado: ${r.reason}`, 'warning');
            if (r.health) { _liHealth = r.health; _renderLiHealth(r.health); _applyLiHealthToButtons(r.health); }
            return;
        }
        if (!r.ok && !r.campaign_id) throw new Error(r.error || 'Falha ao iniciar');
        showToast(`Campanha ${_liTypeName(type)} iniciada (ID ${r.campaign_id})`, 'success');
        openLiLogModal(r.campaign_id, type);
        loadLinkedInCampaigns();
    } catch (e) {
        showToast('Erro: ' + e.message, 'error');
    }
}

function _buildLiCampaignConfig(type) {
    if (type === 'view') {
        const roles = [...document.querySelectorAll('#li-chips-roles .li-chip.selected')]
            .map(c => c.dataset.val).filter(Boolean);
        if (!roles.length) { showToast('Selecione pelo menos um tipo de recrutador', 'warning'); return null; }
        const locTab = document.querySelector('#li-view-loc-tabs .li-tab.active')?.dataset.val || 'Brazil';
        const location = locTab === 'custom'
            ? (document.getElementById('li-view-loc-custom')?.value || 'Brazil')
            : locTab;
        const mode = document.querySelector('input[name="li-view-mode"]:checked')?.value || 'ghost';
        return {
            roles,
            location,
            ghost_only: mode === 'ghost',
            max_profiles: parseInt(document.getElementById('li-view-max')?.value || '25'),
        };
    }
    if (type === 'engage') {
        const tags = [...document.querySelectorAll('#li-engage-tags .li-tag')]
            .map(t => t.textContent.replace('×', '').trim()).filter(Boolean);
        const industries = [...document.querySelectorAll('#li-chips-industries .li-chip.selected')]
            .map(c => c.dataset.val).filter(Boolean);
        return {
            keywords: tags.length ? tags : ['recrutamento', 'tecnologia'],
            industries,
            do_like: document.getElementById('li-engage-like')?.checked ?? true,
            do_comment: document.getElementById('li-engage-comment')?.checked ?? true,
            tone: document.getElementById('li-engage-tone')?.value || 'professional',
            max_posts: parseInt(document.getElementById('li-engage-max')?.value || '10'),
        };
    }
    if (type === 'connect') {
        const mode = document.querySelector('#li-connect-mode-tabs .li-tab.active')?.dataset.val || 'search';
        const base = {
            mode,
            send_note: document.getElementById('li-connect-note')?.checked ?? false,
            note_template: document.getElementById('li-connect-note-template')?.value || '',
            max_connections: parseInt(document.getElementById('li-connect-max')?.value || '15'),
        };
        if (mode === 'search') {
            base.query = document.getElementById('li-connect-query')?.value || 'Tech Recruiter';
            base.location = document.getElementById('li-connect-location')?.value || 'Brazil';
        } else if (mode === 'urls') {
            const raw = document.getElementById('li-connect-urls')?.value || '';
            base.profile_urls = raw.split('\n').map(s => s.trim()).filter(s => s.startsWith('http'));
            if (!base.profile_urls.length) { showToast('Adicione pelo menos uma URL', 'warning'); return null; }
        }
        return base;
    }
    if (type === 'discover') {
        const raw = document.getElementById('li-discover-companies')?.value || '';
        const companies = raw.split('\n').map(s => s.trim()).filter(Boolean);
        if (!companies.length) { showToast('Adicione pelo menos uma empresa', 'warning'); return null; }
        return {
            companies,
            scope: document.querySelector('input[name="li-discover-scope"]:checked')?.value || 'recruiters_only',
            post_action: document.querySelector('input[name="li-discover-action"]:checked')?.value || 'save',
            max_per_company: parseInt(document.getElementById('li-discover-max')?.value || '10'),
        };
    }
    return null;
}

// ── Campaigns table ──
// ============================================================================
// LinkedIn — Campaigns Monitor (hierarchical: tabs + collapsible sections)
// ============================================================================
let _liAllCampaigns = [];
let _liActiveTab = localStorage.getItem('li_active_tab') || 'active';
let _liSelected = new Set();      // selected profile URLs across pipelines
let _liSelectedSource = '';        // 'view' | 'connect' | 'discover'
let _liFilters = { view: {}, connect: {} };
let _liHoverTimer = null;
let _liHoverHideTimer = null;
let _liExpandedPosts = new Set();

async function loadLinkedInCampaigns() {
    try {
        const data = await api('/api/linkedin/campaigns?limit=50');
        _liAllCampaigns = data.campaigns || [];
        _renderLiMonitor();
    } catch (e) { console.warn('LinkedIn campaigns error:', e); }
}

// Build profile cache from embedded campaign results (rows + grids contain rich data).
// Used by hover card to find profile data by URL.
function _liFindProfileByUrl(url) {
    if (!url) return null;
    for (const c of _liAllCampaigns) {
        const r = c.results;
        if (!r) continue;
        // view + connect campaigns have .profiles or .connections arrays
        const buckets = [
            r.profiles || [],
            r.connections || [],
        ];
        // discover: by_company is {name: [profiles...]}
        if (r.by_company) {
            for (const list of Object.values(r.by_company)) {
                if (Array.isArray(list)) buckets.push(list);
            }
        }
        for (const list of buckets) {
            for (const p of list) {
                const pu = p.profile_url || p.url;
                if (pu === url) return p;
            }
        }
    }
    return null;
}

const LI_TYPE_ICONS = {
    view: '#i-eye', engage: '#i-message-circle', connect: '#i-users', discover: '#i-briefcase'
};
const LI_TYPE_COLORS = {
    view: '#3b82f6', engage: '#10b981', connect: '#f59e0b', discover: '#a855f7'
};

function _liTypeName(type) {
    return { view: 'Visitar Perfis', engage: 'Engajar Posts', connect: 'Enviar Conexões', discover: 'Descobrir por Empresa' }[type] || type;
}

function liSwitchTab(tab) {
    _liActiveTab = tab;
    localStorage.setItem('li_active_tab', tab);
    document.querySelectorAll('.li-monitor-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.tab === tab);
    });
    liBatchClear();
    _renderLiMonitor();
}

function _liFilterByTab(campaigns, tab) {
    if (tab === 'active') return campaigns.filter(c => ['running','pending'].includes(c.status));
    if (tab === 'scheduled') return campaigns.filter(c => c.status === 'scheduled');
    if (tab === 'completed') return campaigns.filter(c => ['done','error','stopped','cancelled'].includes(c.status));
    return campaigns;
}

function _renderLiMonitor() {
    const body = document.getElementById('li-monitor-body');
    if (!body) return;

    const active = _liAllCampaigns.filter(c => ['running','pending'].includes(c.status));
    const completed = _liAllCampaigns.filter(c => ['done','error','stopped','cancelled'].includes(c.status));
    const scheduled = _liAllCampaigns.filter(c => c.status === 'scheduled');
    const cActive = document.getElementById('li-tab-count-active');
    const cScheduled = document.getElementById('li-tab-count-scheduled');
    const cCompleted = document.getElementById('li-tab-count-completed');
    const cAll = document.getElementById('li-tab-count-all');
    if (cActive) cActive.textContent = active.length;
    if (cScheduled) cScheduled.textContent = scheduled.length;
    if (cCompleted) cCompleted.textContent = completed.length;
    if (cAll) cAll.textContent = _liAllCampaigns.length;

    // Mark active tab
    document.querySelectorAll('.li-monitor-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.tab === _liActiveTab);
    });

    const list = _liFilterByTab(_liAllCampaigns, _liActiveTab);
    if (!list.length) {
        body.innerHTML = `<div class="li-monitor-empty">
            <svg style="width:32px;height:32px;stroke:var(--text-3)"><use href="#i-zap"/></svg>
            <p>Nenhuma campanha ${_liActiveTab === 'active' ? 'ativa' : _liActiveTab === 'completed' ? 'concluída' : ''} ainda</p>
        </div>`;
        return;
    }

    // Group by type
    const byType = { view: [], engage: [], connect: [], discover: [] };
    list.forEach(c => { if (byType[c.type]) byType[c.type].push(c); });

    body.innerHTML = ['view','engage','connect','discover'].map(type => {
        if (!byType[type].length) return '';
        return _renderLiSection(type, byType[type]);
    }).join('');
}

function _renderLiSection(type, campaigns) {
    const collapsedKey = `li_section_collapsed_${type}`;
    const isCollapsed = localStorage.getItem(collapsedKey) === '1';
    const color = LI_TYPE_COLORS[type];
    const icon = LI_TYPE_ICONS[type];
    const runningCount = campaigns.filter(c => c.status === 'running').length;
    const runningDot = runningCount > 0 ? '<span class="li-section-running-dot" title="Campanha rodando"></span>' : '';

    const bodyHtml = campaigns.map(c => _renderLiCampaignDetail(c)).join('');

    return `<div class="li-section ${isCollapsed ? 'collapsed' : ''}" data-type="${type}">
        <button type="button" class="li-section-header" onclick="liToggleSection('${type}')" aria-expanded="${!isCollapsed}" aria-controls="li-section-body-${type}">
            <svg class="li-section-chevron" aria-hidden="true"><use href="#i-chevron-right"/></svg>
            <div class="li-section-icon-wrap" style="background:${color}22" aria-hidden="true">
                <svg style="width:14px;height:14px;stroke:${color}"><use href="${icon}"/></svg>
            </div>
            <div class="li-section-title">${escapeHtml(_liTypeName(type))}</div>
            <div class="li-section-meta">
                ${runningDot}
                <span>${campaigns.length} ${campaigns.length === 1 ? 'campanha' : 'campanhas'}${runningCount ? ` · ${runningCount} ativa${runningCount > 1 ? 's' : ''}` : ''}</span>
            </div>
        </button>
        <div class="li-section-body" id="li-section-body-${type}">${bodyHtml}</div>
    </div>`;
}

function liToggleSection(type) {
    const sec = document.querySelector(`.li-section[data-type="${type}"]`);
    if (!sec) return;
    sec.classList.toggle('collapsed');
    localStorage.setItem(`li_section_collapsed_${type}`,
        sec.classList.contains('collapsed') ? '1' : '0');
}

function _renderLiCampaignDetail(c) {
    const color = LI_TYPE_COLORS[c.type];
    const isCollapsed = _liIsCampaignCollapsed(c);
    // Derive error/failure reason from log if c.error not populated
    if (!c.error && (c.status === 'error' || c.status === 'stopped')) {
        const log = c.log || [];
        const lastErr = [...log].reverse().find(e => e && e.phase === 'error');
        if (lastErr) c.error = lastErr.msg || '';
    }

    let progressEl = '';
    if (c.status === 'running') {
        progressEl = `<div class="li-campaign-card-progress">
            <div class="li-progress-bar"><div style="width:${c.progress||0}%;background:${color}"></div></div>
            <span>${c.progress||0}%</span>
        </div>`;
    } else if (c.status === 'done') {
        progressEl = `<div class="li-campaign-card-progress"><span style="color:#22c55e">✓ Concluída</span></div>`;
    } else if (c.status === 'error') {
        const errFull = humanizeLiError(c.error || 'Falha desconhecida');
        const errShort = _liErrorShortLabel(c.error || '');
        progressEl = `<div class="li-campaign-card-progress" title="${escapeHtml(errFull)}\n\n(técnico: ${escapeHtml((c.error||'').slice(0,300))})">
            <span style="color:#ef4444;display:flex;align-items:center;gap:5px;max-width:340px">
                <svg style="width:11px;height:11px;flex-shrink:0"><use href="#i-x"/></svg>
                <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(errShort)}</span>
            </span>
        </div>`;
    } else if (c.status === 'stopped') {
        progressEl = `<div class="li-campaign-card-progress"><span style="color:var(--text-3)">Parada</span></div>`;
    }

    const timeStr = c.status === 'running'
        ? `há ${_liRelTime(c.started_at)}`
        : c.completed_at
            ? `há ${_liRelTime(c.completed_at)}`
            : `Iniciada ${_liFmtTime(c.started_at)}`;

    const phaseChip = (c.status === 'running') ? _liPhaseChip(c) : '';
    const cfgSummary = _liConfigSummary(c);

    // B2 fix: actions are siblings of the toggle button — no nested interactive elements inside <button>
    const header = `<div class="li-campaign-card-top">
        <button type="button" class="li-campaign-card-header" onclick="liToggleCampaignCard(${c.id})" aria-expanded="${!isCollapsed}" aria-controls="li-campaign-body-${c.id}" aria-label="Campanha #${c.id} ${c.type}">
            <svg class="li-campaign-card-chevron" aria-hidden="true"><use href="#i-chevron-right"/></svg>
            ${_liStatusBadge(c.status)}
            <span class="li-campaign-card-id">#${c.id}</span>
            <span class="li-campaign-card-time" title="${escapeHtml(_liFmtTime(c.started_at))}">
                <svg aria-hidden="true"><use href="#i-eye"/></svg>${timeStr}
            </span>
            ${phaseChip}
            <div class="li-campaign-card-cfg">${cfgSummary}</div>
            <div class="li-campaign-card-inline-stats">${_liInlineStats(c)}</div>
            ${progressEl}
        </button>
        <div class="li-campaign-card-actions">
            <button class="btn btn-ghost btn-sm" onclick="openLiLogModal(${c.id},'${c.type}')" title="Ver log">
                <svg style="width:13px;height:13px"><use href="#i-message-circle"/></svg>
            </button>
            ${c.status === 'running' ? `<button class="btn btn-ghost btn-sm" onclick="liStopCampaignById(${c.id})" title="Parar"><svg style="width:13px;height:13px"><use href="#i-stop"/></svg></button>` : ''}
        </div>
    </div>`;

    let content = '';
    if (c.status === 'error' && c.error) {
        const friendly = humanizeLiError(c.error);
        const showTech = friendly !== c.error;
        content += `<div class="li-campaign-error-msg">
            ${typeof window.icon === 'function' ? window.icon('alert-triangle', {size:14}) : '⚠'} ${escapeHtml(friendly)}
            ${showTech ? `<details style="margin-top:6px;font-size:11px;opacity:.6">
                <summary style="cursor:pointer">Ver erro técnico</summary>
                <code style="display:block;white-space:pre-wrap;padding:6px;background:rgba(0,0,0,.2);border-radius:4px;margin-top:4px">${escapeHtml(c.error)}</code>
            </details>` : ''}
            <button class="btn btn-ghost btn-sm" style="margin-top:8px;font-size:11px"
                onclick="liDismissError(${c.id})" title="Dismiss error — permite sync sobrescrever estado">
                Dismiss error
            </button>
        </div>`;
    }
    // Cooldown banner (status=cooldown OR last log entry is cooldown)
    const lastLog = (c.log || []).slice(-1)[0];
    if (c.status === 'cooldown' || (lastLog && lastLog.phase === 'cooldown')) {
        const msg = lastLog?.msg || 'Campanha bloqueada por proteção anti-cooldown';
        content += `<div class="li-campaign-error-msg" style="background:rgba(245,158,11,.1);color:#f59e0b">
            ${typeof window.icon === 'function' ? window.icon('pause', {size:14}) : '⏸'} ${escapeHtml(humanizeLiError(msg))}
        </div>`;
    }
    // v6: Scheduled banner with live countdown + cancel button
    if (c.status === 'scheduled' && c.scheduled_for) {
        const target = new Date(c.scheduled_for);
        const targetMs = target.getTime();
        content += `<div class="li-campaign-error-msg li-scheduled-banner" data-target-ms="${targetMs}" data-cid="${c.id}"
                         style="background:rgba(59,130,246,.1);color:#3b82f6;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
            <span style="font-size:14px">📅</span>
            <div style="flex:1;min-width:200px">
                <div style="font-weight:600;font-size:13px">Agendada — iniciará em
                    <span class="li-sched-countdown" style="font-variant-numeric:tabular-nums">calculando…</span>
                </div>
                <div style="font-size:11px;opacity:.85;margin-top:2px">
                    ${escapeHtml(c.schedule_reason || 'Aguardando condições')}
                </div>
                <div style="font-size:10px;opacity:.6;margin-top:1px">
                    Data: ${target.toLocaleString('pt-BR')}
                </div>
            </div>
            <button class="btn btn-ghost btn-sm" onclick="liCancelScheduled(${c.id})"
                    style="color:#3b82f6;border-color:rgba(59,130,246,.3)">
                <svg style="width:12px;height:12px"><use href="#i-x"/></svg> Cancelar
            </button>
        </div>`;
    }
    if (c.status === 'cancelled') {
        content += `<div class="li-campaign-error-msg" style="background:rgba(107,114,128,.1);color:var(--text-3)">
            ✕ Agendamento cancelado pelo usuário
        </div>`;
    }
    // For scheduled campaigns: show the configuration preview instead of empty results
    if (c.status === 'scheduled') {
        content += _renderLiScheduledConfig(c);
    } else if (c.type === 'view') content += _renderLiViewCampaign(c);
    else if (c.type === 'engage') content += _renderLiEngageCampaign(c);
    else if (c.type === 'connect') content += _renderLiConnectCampaign(c);
    else if (c.type === 'discover') content += _renderLiDiscoverCampaign(c);

    const stateClass = c.status === 'running' ? 'is-running' : c.status === 'error' ? 'is-error' : '';

    return `<div class="li-campaign-card ${isCollapsed ? 'collapsed' : ''} ${stateClass}" data-campaign-id="${c.id}">
        ${header}
        <div class="li-campaign-card-body" id="li-campaign-body-${c.id}">${content}</div>
    </div>`;
}

// Build type-specific inline stats shown in card header (visible when collapsed)
function _liInlineStats(c) {
    const r = c.results || {};
    if (c.type === 'view') {
        const visited = r.profiles_visited ?? (r.profiles?.length || 0);
        const cities = Object.keys(r.by_city || {}).length;
        const roles = Object.keys(r.by_role || {}).length;
        return `
            <span class="li-inline-stat"><strong>${visited}</strong>visitados</span>
            ${roles ? `<span class="li-inline-stat-sep"></span><span class="li-inline-stat muted"><strong>${roles}</strong>funções</span>` : ''}
            ${cities ? `<span class="li-inline-stat-sep"></span><span class="li-inline-stat muted"><strong>${cities}</strong>cidades</span>` : ''}
        `;
    }
    if (c.type === 'engage') {
        const liked = r.liked ?? 0;
        const commented = r.commented ?? 0;
        const total = r.posts?.length ?? 0;
        return `
            <span class="li-inline-stat"><strong>${total}</strong>posts</span>
            <span class="li-inline-stat-sep"></span>
            <span class="li-inline-stat success"><strong>${liked}</strong>curtidos</span>
            <span class="li-inline-stat-sep"></span>
            <span class="li-inline-stat success"><strong>${commented}</strong>comentados</span>
        `;
    }
    if (c.type === 'connect') {
        const sent = r.connections_sent ?? 0;
        const acc = r.accepted ?? 0;
        const pen = r.pending ?? 0;
        const rej = r.rejected ?? 0;
        const ign = r.ignored ?? 0;
        return `
            <span class="li-inline-stat"><strong>${sent}</strong>enviadas</span>
            <span class="li-inline-stat-sep"></span>
            <span class="li-inline-stat success"><strong>${acc}</strong>aceitas</span>
            <span class="li-inline-stat-sep"></span>
            <span class="li-inline-stat warn"><strong>${pen}</strong>pendentes</span>
            ${rej ? `<span class="li-inline-stat-sep"></span><span class="li-inline-stat danger"><strong>${rej}</strong>recusadas</span>` : ''}
            ${ign ? `<span class="li-inline-stat-sep"></span><span class="li-inline-stat muted"><strong>${ign}</strong>ignoradas</span>` : ''}
        `;
    }
    if (c.type === 'discover') {
        const found = r.found ?? 0;
        const companies = Object.keys(r.by_company || {}).length;
        const totalCompanies = c.config?.companies?.length || companies;
        return `
            <span class="li-inline-stat"><strong>${found}</strong>encontrados</span>
            <span class="li-inline-stat-sep"></span>
            <span class="li-inline-stat muted"><strong>${companies}${c.status==='running' && totalCompanies > companies ? '/'+totalCompanies : ''}</strong>empresas</span>
        `;
    }
    return '';
}

// Short error label (max ~40 chars) for collapsed header. Full reason in tooltip.
function _liErrorShortLabel(raw) {
    if (!raw) return 'Falha desconhecida';
    const m = String(raw).toLowerCase();
    if (m.includes('órfã') || m.includes('orfã') || m.includes('processo morto')) return 'Processo morto durante deploy';
    if (m.includes('err_too_many_redirects')) return 'LinkedIn em loop de redirect (checkpoint)';
    if (m.includes('err_http_response_code_failure')) return 'LinkedIn bloqueou o acesso (provável 429/999)';
    if (m.includes('checkpoint') && m.includes('redirect')) return 'Sessão marcada — LinkedIn pediu verificação';
    if (m.includes('429') || m.includes('too many requests')) return 'Rate limit (429)';
    if (m.includes('err_connection_refused')) return 'Conexão recusada (proxy/SSH tunnel?)';
    if (m.includes('err_name_not_resolved')) return 'DNS falhou — proxy offline?';
    if (m.includes('timeout') && m.includes('navigating')) return 'Timeout de navegação';
    if (m.includes('session_max') || m.includes('session max duration')) return 'Sessão excedeu duração máxima';
    if (m.includes('uas/login') || m.includes('challenge')) return 'LinkedIn pediu re-login';
    if (m.includes('cookie') && (m.includes('expired') || m.includes('invalid'))) return 'Cookie LI_AT expirado';
    if (m.includes('ollama')) return 'Ollama indisponível';
    if (m.includes('claude') && m.includes('subprocess')) return 'Claude CLI falhou';
    if (m.includes('working hours') || m.includes('fora do horário')) return 'Fora do horário comercial';
    if (m.includes('lurking')) return 'Conta em fase lurking';
    if (m.includes('cooldown')) return 'Cooldown anti-bot ativo';
    // Fallback: first sentence of raw, capped
    const first = String(raw).split(/[.\n]/)[0].trim();
    return first.length > 60 ? first.slice(0, 57) + '…' : (first || 'Falha desconhecida');
}

// Type-specific config preview shown collapsed (keywords, mode, etc.)
function _liConfigSummary(c) {
    const cfg = c.config || {};
    const chip = (label, value, title) =>
        `<span class="li-cfg-chip" ${title ? `title="${escapeHtml(title)}"` : ''}>` +
        (label ? `<span class="li-cfg-chip-k">${label}</span>` : '') +
        `<span class="li-cfg-chip-v">${escapeHtml(String(value))}</span></span>`;
    const chips = [];
    if (c.type === 'view') {
        if (cfg.keywords) chips.push(chip('', cfg.keywords));
        if (cfg.location) chips.push(chip('em', cfg.location));
        if (cfg.target_urls?.length) chips.push(chip('', `${cfg.target_urls.length} URLs`));
        if (cfg.max_profiles) chips.push(chip('alvo', cfg.max_profiles));
    } else if (c.type === 'engage') {
        if (cfg.keyword) chips.push(chip('', cfg.keyword));
        else if (cfg.feed_mode) chips.push(chip('', cfg.feed_mode));
        if (cfg.tone) chips.push(chip('tom', cfg.tone));
        if (cfg.max_posts) chips.push(chip('alvo', cfg.max_posts));
    } else if (c.type === 'connect') {
        const mode = cfg.mode || (cfg.target_urls ? 'urls' : 'auto');
        chips.push(chip('modo', mode));
        if (cfg.target_urls?.length) chips.push(chip('', `${cfg.target_urls.length} URLs`));
        else if (cfg.urls_count) chips.push(chip('', `${cfg.urls_count} URLs`));
        else if (cfg.max_invites) chips.push(chip('alvo', cfg.max_invites));
        if (cfg.send_note) chips.push(chip('', 'nota IA', 'Envia nota personalizada via Ollama+Claude'));
    } else if (c.type === 'discover') {
        const comps = cfg.companies || [];
        if (comps.length) {
            const preview = comps.slice(0,2).join(', ') + (comps.length > 2 ? ` +${comps.length-2}` : '');
            chips.push(chip('', preview, comps.join(', ')));
        }
        if (cfg.scope) chips.push(chip('', cfg.scope.replace(/_/g,' ')));
        if (cfg.post_action) chips.push(chip('ação', cfg.post_action));
    }
    return chips.join('');
}

// Current phase chip — shows what running campaign is doing right now (warming/searching/...)
const _LI_PHASE_LABEL = {
    starting:       { label: 'iniciando',   color: '#94a3b8' },
    connecting:     { label: 'conectando',  color: '#60a5fa' },
    authenticating: { label: 'autenticando',color: '#60a5fa' },
    warming:        { label: 'aquecendo',   color: '#f59e0b' },
    planning:       { label: 'planejando',  color: '#a78bfa' },
    searching:      { label: 'buscando',    color: '#a78bfa' },
    visiting:       { label: 'visitando',   color: '#22c55e' },
    engaging:       { label: 'engajando',   color: '#22c55e' },
    commenting:     { label: 'comentando',  color: '#22c55e' },
    connecting_send:{ label: 'conectando',  color: '#22c55e' },
    discovering:    { label: 'descobrindo', color: '#22c55e' },
    cooldown:       { label: 'cooldown',    color: '#f59e0b' },
};
function _liPhaseChip(c) {
    const log = c.log || [];
    const last = log.slice(-1)[0];
    if (!last || !last.phase) return '';
    const info = _LI_PHASE_LABEL[last.phase] || { label: last.phase, color: '#94a3b8' };
    const tip = last.msg ? `${last.phase}: ${last.msg}` : last.phase;
    return `<span class="li-phase-chip" style="--phase:${info.color}" title="${escapeHtml(tip)}">
        <span class="li-phase-dot"></span>${info.label}
    </span>`;
}

// Format ISO timestamp as "32 min", "2h", "3 dias"
function _liRelTime(iso) {
    if (!iso) return '–';
    const d = new Date(iso);
    const diff = (Date.now() - d) / 1000;
    if (diff < 60) return `${Math.floor(diff)}s`;
    if (diff < 3600) return `${Math.floor(diff/60)} min`;
    if (diff < 86400) return `${Math.floor(diff/3600)}h`;
    return `${Math.floor(diff/86400)} dias`;
}

// Decide initial collapsed state for a campaign card
// Priority: localStorage > status default
function _liIsCampaignCollapsed(c) {
    const stored = localStorage.getItem(`li_campaign_collapsed_${c.id}`);
    if (stored === '1') return true;
    if (stored === '0') return false;
    // Default: collapse non-running campaigns
    return c.status !== 'running' && c.status !== 'pending';
}

function liToggleCampaignCard(id) {
    const card = document.querySelector(`.li-campaign-card[data-campaign-id="${id}"]`);
    if (!card) return;
    card.classList.toggle('collapsed');
    const collapsed = card.classList.contains('collapsed');
    localStorage.setItem(`li_campaign_collapsed_${id}`, collapsed ? '1' : '0');
    // B1 fix: keep aria-expanded in sync with DOM state
    const btn = card.querySelector('.li-campaign-card-header');
    if (btn) btn.setAttribute('aria-expanded', String(!collapsed));
}

function _liFmtTime(iso) {
    const d = new Date(iso);
    const now = new Date();
    const diffH = (now - d) / 3600000;
    if (diffH < 24) {
        return d.toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit'});
    }
    return d.toLocaleDateString('pt-BR', {day:'2-digit', month:'2-digit'});
}

// ── VIEW campaign rendering ─────────────────────────────────────────────
function _renderLiViewCampaign(c) {
    const profiles = c.results?.profiles || [];
    if (!profiles.length) return `<div class="li-section-empty">Nenhum perfil visitado ainda</div>`;

    // Stats summary
    const stats = `<div class="li-campaign-stats">
        <div><strong>${profiles.length}</strong><span>Visitados</span></div>
        ${Object.entries(c.results.by_role || {}).slice(0,2).map(([k,v]) =>
            `<div><strong>${v}</strong><span>${escapeHtml(k)}</span></div>`).join('')}
        <div><strong>${Object.keys(c.results.by_city || {}).length}</strong><span>Cidades</span></div>
    </div>`;

    // Filters
    const roles = [...new Set(profiles.map(p => p.current_role).filter(Boolean))];
    const cities = [...new Set(profiles.map(p => (p.location||'').split(',')[0].trim()).filter(Boolean))];
    const filterKey = `view_${c.id}`;
    const activeFilter = _liFilters[filterKey] || {};
    const filtersRow = `<div class="li-filters-row">
        <span class="li-filter-label">Função:</span>
        <span class="li-mini-chip ${!activeFilter.role ? 'active' : ''}" onclick="liSetFilter('${filterKey}','role','')">Todas</span>
        ${roles.slice(0,4).map(r => `<span class="li-mini-chip ${activeFilter.role === r ? 'active' : ''}" onclick="liSetFilter('${filterKey}','role','${escapeHtml(r)}')">${escapeHtml(r)}</span>`).join('')}
        <span style="width:1px;height:14px;background:var(--border);margin:0 4px"></span>
        <span class="li-filter-label">Cidade:</span>
        <span class="li-mini-chip ${!activeFilter.city ? 'active' : ''}" onclick="liSetFilter('${filterKey}','city','')">Todas</span>
        ${cities.slice(0,3).map(ci => `<span class="li-mini-chip ${activeFilter.city === ci ? 'active' : ''}" onclick="liSetFilter('${filterKey}','city','${escapeHtml(ci)}')">${escapeHtml(ci)}</span>`).join('')}
    </div>`;

    // Apply filters
    let filtered = profiles;
    if (activeFilter.role) filtered = filtered.filter(p => p.current_role === activeFilter.role);
    if (activeFilter.city) filtered = filtered.filter(p => (p.location||'').startsWith(activeFilter.city));

    const rows = filtered.map(p => _renderLiProfileRow(p, 'view', c.id)).join('');

    return stats + filtersRow + `<table class="li-profile-table">
        <thead><tr>
            <th class="li-th-check"><input type="checkbox" class="li-check" onchange="liSelectAllInTable(this, ${c.id}, 'view')"></th>
            <th>Perfil</th>
            <th>Empresa</th>
            <th>Localização</th>
            <th>Mutual</th>
            <th>Visitado</th>
            <th></th>
        </tr></thead>
        <tbody>${rows}</tbody>
    </table>`;
}

function liSetFilter(key, field, value) {
    if (!_liFilters[key]) _liFilters[key] = {};
    _liFilters[key][field] = value;
    _renderLiMonitor();
}

function _renderLiProfileRow(p, source, campaignId) {
    const profKey = `${campaignId}:${p.profile_url}`;
    const checked = _liSelected.has(profKey) ? 'checked' : '';
    const visitedAt = p.visited_at ? _liFmtTime(p.visited_at) : '–';
    return `<tr class="li-profile-row">
        <td class="li-td-check">
            <input type="checkbox" class="li-check" ${checked} onchange="liToggleSelect('${escapeHtml(profKey)}','${source}',${campaignId})">
        </td>
        <td>
            <div class="li-profile-name-cell">
                <img class="li-profile-avatar" src="${p.photo}" alt="" loading="lazy" onerror="this.style.background='var(--s3)';this.src='data:image/svg+xml;utf8,<svg xmlns=&quot;http://www.w3.org/2000/svg&quot;/>'">
                <div style="min-width:0">
                    <a href="${p.profile_url}" target="_blank" rel="noopener" class="li-profile-name li-hover-trigger" data-profile-url="${p.profile_url||''}" onclick="event.stopPropagation()">
                        ${escapeHtml(p.name)}<span class="li-profile-degree">${p.degree || '3rd'}</span>
                    </a>
                    <div class="li-profile-headline">${escapeHtml(p.headline||'')}</div>
                </div>
            </div>
        </td>
        <td>
            <div class="li-company-cell">
                ${p.company_logo ? `<img class="li-company-logo" src="${p.company_logo}" alt="" loading="lazy" onerror="this.outerHTML='<span class=&quot;li-company-logo-fallback&quot;>&#8226;</span>'">` : '<span class="li-company-logo-fallback">·</span>'}
                <span style="font-size:12px;color:var(--text-2)">${escapeHtml(p.current_company||'')}</span>
            </div>
        </td>
        <td style="font-size:12px;color:var(--text-2)">${escapeHtml(p.location||'–')}</td>
        <td>
            <span class="li-mutual-badge">
                <svg style="width:11px;height:11px"><use href="#i-users"/></svg>
                ${p.mutual_count || 0}
            </span>
        </td>
        <td style="font-size:11px;color:var(--text-3)">${visitedAt}</td>
        <td>
            <a class="li-profile-link-btn" href="${p.profile_url}" target="_blank" rel="noopener" title="Abrir no LinkedIn">
                <svg style="width:13px;height:13px"><use href="#i-external-link"/></svg>
            </a>
        </td>
    </tr>`;
}

function liSelectAllInTable(checkbox, campaignId, source) {
    const table = checkbox.closest('table');
    const checks = table.querySelectorAll('tbody .li-check');
    checks.forEach(cb => {
        cb.checked = checkbox.checked;
        const profKey = cb.getAttribute('onchange').match(/'([^']+)'/)[1];
        if (checkbox.checked) _liSelected.add(profKey); else _liSelected.delete(profKey);
    });
    _liSelectedSource = source;
    _liUpdateBatchBar();
}

// ── ENGAGE campaign rendering ───────────────────────────────────────────
function _renderLiEngageCampaign(c) {
    const posts = c.results?.posts || [];
    if (!posts.length) return `<div class="li-section-empty">Nenhum post engajado ainda</div>`;

    const stats = `<div class="li-campaign-stats">
        <div><strong>${posts.length}</strong><span>Posts</span></div>
        <div><strong>${c.results.liked || 0}</strong><span>Curtidos</span></div>
        <div><strong>${c.results.commented || 0}</strong><span>Comentados</span></div>
    </div>`;

    const cards = posts.map(po => _renderLiEngageCard(po, c.id)).join('');
    return stats + `<div class="li-engage-list">${cards}</div>`;
}

function _renderLiEngageCard(po, campaignId) {
    const author = po.author || {};
    const expanded = _liExpandedPosts.has(`${campaignId}:${po.id}`) ? 'expanded' : '';
    return `<div class="li-engage-card">
        <div class="li-engage-author">
            <img class="li-profile-avatar" src="${author.photo}" alt="" loading="lazy">
            <div class="li-engage-author-info">
                <div class="li-engage-author-name li-hover-trigger" data-profile-url="${author.profile_url || po.author_url || ''}">
                    ${escapeHtml(author.name||'')}
                </div>
                <div class="li-engage-author-headline">${escapeHtml(author.headline||'')}</div>
                <div class="li-engage-meta">
                    <span>Postado ${escapeHtml(po.date_label||'')}</span>
                    <span><svg style="width:11px;height:11px;display:inline-block;vertical-align:middle"><use href="#i-heart"/></svg> ${po.engagement?.likes||0}</span>
                    <span><svg style="width:11px;height:11px;display:inline-block;vertical-align:middle"><use href="#i-message-circle"/></svg> ${po.engagement?.comments||0}</span>
                </div>
            </div>
            <a class="li-profile-link-btn" href="${po.post_url}" target="_blank" rel="noopener" title="Ver post no LinkedIn">
                <svg style="width:13px;height:13px"><use href="#i-external-link"/></svg>
            </a>
        </div>
        <div class="li-post-text ${expanded}">${escapeHtml(po.text||'')}</div>
        ${!expanded ? `<button class="li-post-expand-btn" onclick="liExpandPost(${campaignId},${po.id})">Ver post completo</button>` : ''}

        <div class="li-engage-actions-summary">
            <span class="li-engage-action-flag ${po.liked_at ? 'done' : ''}">
                <svg><use href="#i-heart"/></svg>
                ${po.liked_at ? `Curtido às ${po.liked_at}` : 'Não curtido'}
            </span>
            <span class="li-engage-action-flag ${po.comment_generated ? 'done' : ''}">
                <svg><use href="#i-message-circle"/></svg>
                ${po.comment_generated ? 'Comentado' : 'Não comentado'}
            </span>
        </div>

        ${po.comment_generated ? `<div class="li-comment-block">
            <div class="li-comment-block-header">
                <span>Comentário gerado</span>
                <span class="li-comment-block-tone">${escapeHtml(po.comment_tone || 'Profissional')}</span>
            </div>
            <div class="li-comment-text">${escapeHtml(po.comment_generated)}</div>
            <div class="li-comment-meta">
                <div class="li-comment-meta-row">↳ por <strong>Ollama ${escapeHtml(po.ollama_model||'')}</strong></div>
                <div class="li-comment-meta-row">↳ Claude: <span class="li-validation-score">APROVADO ${po.claude_validation_score?.toFixed(2)||''}</span></div>
                <div class="li-comment-meta-tooltip">
                    <strong>Validação Claude:</strong><br>
                    ${escapeHtml(po.claude_validation_note||'')}<br><br>
                    <strong>Tentativas:</strong> ${po.generation_attempts || 1}<br>
                    <strong>Comment ID:</strong> ${escapeHtml(po.comment_id||'–')}
                </div>
            </div>
        </div>` : ''}

        <div class="li-comment-actions">
            <a class="btn btn-ghost btn-sm" href="${po.post_url}" target="_blank" rel="noopener" style="margin-left:auto">
                <svg style="width:12px;height:12px"><use href="#i-external-link"/></svg> Ver no LinkedIn
            </a>
        </div>
    </div>`;
}

function liExpandPost(campaignId, postId) {
    _liExpandedPosts.add(`${campaignId}:${postId}`);
    _renderLiMonitor();
}

// ── CONNECT campaign rendering ──────────────────────────────────────────
function _renderLiConnectCampaign(c) {
    const conns = c.results?.connections || [];
    if (!conns.length && c.status !== 'error') return `<div class="li-section-empty">Nenhuma conexão enviada ainda</div>`;
    if (c.status === 'error') return '';

    const r = c.results;
    const total = r.connections_sent || conns.length;
    const accepted = r.accepted || 0;
    const acceptRate = total ? (accepted / total) : 0;
    const rateClass = acceptRate >= 0.30 ? 'good' : acceptRate >= 0.15 ? 'medium' : 'poor';

    const stats = `<div class="li-campaign-stats">
        <div><strong>${total}</strong><span>Enviadas</span></div>
        <div><strong style="color:#22c55e">${accepted}</strong><span>Aceitas</span></div>
        <div><strong style="color:#f59e0b">${r.pending||0}</strong><span>Pendentes</span></div>
        <div><strong style="color:#ef4444">${r.rejected||0}</strong><span>Recusadas</span></div>
        <div style="margin-left:auto"><span class="li-acceptance-rate ${rateClass}">Taxa de aceite ${(acceptRate*100).toFixed(0)}%</span></div>
    </div>`;

    const filterKey = `connect_${c.id}`;
    const activeFilter = _liFilters[filterKey] || {};
    const filtersRow = `<div class="li-filters-row">
        <span class="li-filter-label">Status:</span>
        <span class="li-mini-chip ${!activeFilter.status ? 'active' : ''}" onclick="liSetFilter('${filterKey}','status','')">Todas</span>
        <span class="li-mini-chip ${activeFilter.status === 'accepted' ? 'active' : ''}" onclick="liSetFilter('${filterKey}','status','accepted')">Aceitas</span>
        <span class="li-mini-chip ${activeFilter.status === 'pending' ? 'active' : ''}" onclick="liSetFilter('${filterKey}','status','pending')">Pendentes</span>
        <span class="li-mini-chip ${activeFilter.status === 'rejected' ? 'active' : ''}" onclick="liSetFilter('${filterKey}','status','rejected')">Recusadas</span>
        <span class="li-mini-chip ${activeFilter.status === 'ignored' ? 'active' : ''}" onclick="liSetFilter('${filterKey}','status','ignored')">Ignoradas</span>
    </div>`;

    let filtered = conns;
    if (activeFilter.status) filtered = filtered.filter(p => p.status === activeFilter.status);

    const rows = filtered.map(p => _renderLiConnectRow(p, c.id)).join('');

    return stats + filtersRow + `<table class="li-profile-table">
        <thead><tr>
            <th class="li-th-check"><input type="checkbox" class="li-check" onchange="liSelectAllInTable(this, ${c.id}, 'connect')"></th>
            <th>Perfil</th>
            <th>Empresa</th>
            <th>Status</th>
            <th>Nota IA</th>
            <th>Enviada</th>
            <th></th>
        </tr></thead>
        <tbody>${rows}</tbody>
    </table>`;
}

function _renderLiConnectRow(p, campaignId) {
    const profKey = `${campaignId}:${p.profile_url}`;
    const checked = _liSelected.has(profKey) ? 'checked' : '';
    const statusLabels = { accepted: 'Aceita', pending: 'Pendente', rejected: 'Recusada', ignored: 'Ignorada' };
    return `<tr class="li-profile-row">
        <td class="li-td-check">
            <input type="checkbox" class="li-check" ${checked} onchange="liToggleSelect('${escapeHtml(profKey)}','connect',${campaignId})">
        </td>
        <td>
            <div class="li-profile-name-cell">
                <img class="li-profile-avatar" src="${p.photo}" alt="" loading="lazy">
                <div style="min-width:0">
                    <a href="${p.profile_url}" target="_blank" rel="noopener" class="li-profile-name li-hover-trigger" data-profile-url="${p.profile_url||''}" onclick="event.stopPropagation()">
                        ${escapeHtml(p.name)}
                    </a>
                    <div class="li-profile-headline">${escapeHtml(p.headline||'')}</div>
                </div>
            </div>
        </td>
        <td>
            <div class="li-company-cell">
                ${p.company_logo ? `<img class="li-company-logo" src="${p.company_logo}" alt="" loading="lazy">` : ''}
                <span style="font-size:12px;color:var(--text-2)">${escapeHtml(p.current_company||'')}</span>
            </div>
        </td>
        <td><span class="li-status-pill ${p.status}">${statusLabels[p.status] || p.status}</span></td>
        <td>
            ${p.note_sent ? `<span class="li-note-cell"><svg><use href="#i-message-circle"/></svg>
                <span class="li-note-tooltip">${escapeHtml(p.note_sent)}</span>
            </span>` : '<span style="color:var(--text-3);font-size:11px">—</span>'}
        </td>
        <td style="font-size:11px;color:var(--text-3)">${p.sent_at ? _liFmtTime(p.sent_at) : '–'}</td>
        <td>
            <a class="li-profile-link-btn" href="${p.profile_url}" target="_blank" rel="noopener" title="Abrir no LinkedIn">
                <svg style="width:13px;height:13px"><use href="#i-external-link"/></svg>
            </a>
        </td>
    </tr>`;
}

// ── DISCOVER campaign rendering ─────────────────────────────────────────
function _renderLiDiscoverCampaign(c) {
    const byCompany = c.results?.by_company || {};
    const entries = Object.entries(byCompany);
    if (!entries.length) return `<div class="li-section-empty">Nenhuma empresa descoberta</div>`;

    const total = entries.reduce((s, [, list]) => s + list.length, 0);
    const stats = `<div class="li-campaign-stats">
        <div><strong>${total}</strong><span>Encontrados</span></div>
        <div><strong>${entries.length}</strong><span>Empresas</span></div>
        <div><strong>${c.config?.scope === 'recruiters_only' ? 'Recrutadores' : 'RH Completo'}</strong><span>Filtro</span></div>
    </div>`;

    const groups = entries.map(([companyName, profiles]) => {
        const firstP = profiles[0];
        const companyLogo = firstP?.company_logo || '';
        const allSelected = profiles.every(p => _liSelected.has(`${c.id}:${p.profile_url}`));
        return `<div class="li-discover-company-group">
            <div class="li-discover-company-header">
                ${companyLogo ? `<img class="li-discover-company-logo" src="${companyLogo}" alt="" onerror="this.style.display='none'">` : '<span class="li-discover-company-logo" style="display:flex;align-items:center;justify-content:center;color:var(--text-3)"><svg style="width:16px;height:16px"><use href=&quot;#i-briefcase&quot;/></svg></span>'}
                <div>
                    <div class="li-discover-company-name">${escapeHtml(companyName)}</div>
                    <div class="li-discover-company-count">${profiles.length} ${profiles.length === 1 ? 'recrutador encontrado' : 'recrutadores encontrados'}</div>
                </div>
                <div class="li-discover-company-actions">
                    <label class="li-toggle-row" style="font-size:11px;color:var(--text-2)">
                        <input type="checkbox" class="li-check" ${allSelected ? 'checked' : ''} onchange="liSelectAllInCompany(this, ${c.id}, '${escapeHtml(companyName)}')">
                        Selecionar todos
                    </label>
                </div>
            </div>
            <div class="li-discover-grid">
                ${profiles.map(p => _renderLiDiscoverCard(p, c.id)).join('')}
            </div>
        </div>`;
    }).join('');

    return stats + groups;
}

function _renderLiDiscoverCard(p, campaignId) {
    const profKey = `${campaignId}:${p.profile_url}`;
    const isSelected = _liSelected.has(profKey);
    return `<div class="li-discover-card ${isSelected ? 'selected' : ''} li-hover-trigger" data-profile-url="${p.profile_url||''}"
        onclick="liDiscoverCardClick(event, '${escapeHtml(profKey)}', '${p.profile_url}', ${campaignId})">
        <input type="checkbox" class="li-check li-discover-card-check" ${isSelected ? 'checked' : ''}
            onclick="event.stopPropagation()"
            onchange="liToggleSelect('${escapeHtml(profKey)}','discover',${campaignId})">
        <img class="li-discover-card-avatar" src="${p.photo}" alt="" loading="lazy">
        <div class="li-discover-card-name">${escapeHtml(p.name)}</div>
        <div class="li-discover-card-role">${escapeHtml(p.current_role||'')}</div>
    </div>`;
}

function liDiscoverCardClick(ev, profKey, url, campaignId) {
    // If clicked on checkbox area, ignore (handled by checkbox)
    if (ev.target.tagName === 'INPUT') return;
    // If shift/ctrl, toggle selection
    if (ev.shiftKey || ev.ctrlKey || ev.metaKey) {
        liToggleSelect(profKey, 'discover', campaignId);
        const cb = ev.currentTarget.querySelector('input.li-check');
        if (cb) cb.checked = _liSelected.has(profKey);
        ev.currentTarget.classList.toggle('selected', _liSelected.has(profKey));
        return;
    }
    // Otherwise open profile
    window.open(url, '_blank', 'noopener');
}

function liSelectAllInCompany(checkbox, campaignId, companyName) {
    const c = _liAllCampaigns.find(x => x.id === campaignId);
    if (!c) return;
    const profiles = c.results?.by_company?.[companyName] || [];
    profiles.forEach(p => {
        const k = `${campaignId}:${p.profile_url}`;
        if (checkbox.checked) _liSelected.add(k); else _liSelected.delete(k);
    });
    _liSelectedSource = 'discover';
    _renderLiMonitor();
    _liUpdateBatchBar();
}

// ── Multi-select & batch action bar ─────────────────────────────────────
function liToggleSelect(profKey, source, campaignId) {
    if (_liSelected.has(profKey)) _liSelected.delete(profKey);
    else _liSelected.add(profKey);
    _liSelectedSource = source;
    _liUpdateBatchBar();
    // Update visual state for discover cards
    document.querySelectorAll(`.li-discover-card`).forEach(card => {
        const cb = card.querySelector('input.li-check');
        if (cb) card.classList.toggle('selected', cb.checked);
    });
}

function _liUpdateBatchBar() {
    const bar = document.getElementById('li-batch-bar');
    const num = document.getElementById('li-batch-count-num');
    if (!bar || !num) return;
    if (_liSelected.size === 0) {
        bar.style.display = 'none';
    } else {
        bar.style.display = 'flex';
        num.textContent = _liSelected.size;
    }
}

function liBatchClear() {
    _liSelected.clear();
    document.querySelectorAll('.li-check').forEach(cb => { cb.checked = false; });
    document.querySelectorAll('.li-discover-card.selected').forEach(c => c.classList.remove('selected'));
    _liUpdateBatchBar();
}

async function liBatchAction(action) {
    const urls = [..._liSelected].map(k => k.split(':').slice(1).join(':'));
    if (!urls.length) return;
    if (action === 'view') {
        try {
            const r = await api('/api/linkedin/campaigns/view', {
                method: 'POST',
                body: { target_urls: urls, mode: 'urls', max_profiles: urls.length },
            });
            toast(`Campanha view criada (#${r.campaign_id}) — ${urls.length} URLs`, 'success');
            liBatchClear();
            loadLinkedInCampaigns();
        } catch (e) {
            toast('Erro: ' + (e.message || e), 'error');
        }
    } else if (action === 'connect') {
        document.getElementById('li-batch-connect-count').textContent = urls.length;
        document.getElementById('li-batch-connect-modal').style.display = 'flex';
    }
}

function liCloseBatchConnectModal() {
    document.getElementById('li-batch-connect-modal').style.display = 'none';
}

async function liConfirmBatchConnect() {
    const urls = [..._liSelected].map(k => k.split(':').slice(1).join(':'));
    const sendNote = document.getElementById('li-batch-connect-note').checked;
    const template = document.getElementById('li-batch-connect-template').value;
    try {
        const r = await api('/api/linkedin/campaigns/connect', {
            method: 'POST',
            body: {
                mode: 'urls',
                profile_urls: urls,
                send_note: sendNote,
                note_template: template,
                max_count: urls.length,
            },
        });
        toast(`Campanha connect criada (#${r.campaign_id}) — ${urls.length} convites`, 'success');
        liCloseBatchConnectModal();
        liBatchClear();
        loadLinkedInCampaigns();
    } catch (e) {
        toast('Erro: ' + (e.message || e), 'error');
    }
}

// ── Comment edit / delete (placeholder) ─────────────────────────────────
let _liCommentAction = null;

function liEditComment(campaignId, postId) {
    const c = _liAllCampaigns.find(x => x.id === campaignId);
    const po = c?.results?.posts?.find(x => x.id === postId);
    if (!po) return;
    _liCommentAction = { type: 'edit', campaignId, postId };
    document.getElementById('li-comment-modal-title').textContent = 'Editar Comentário';
    document.getElementById('li-comment-modal-body').innerHTML = `
        <p style="font-size:13px;color:var(--text-2);margin:0 0 10px">
            <strong>Funcionalidade em desenvolvimento</strong> — o endpoint da VM para edição de comentários está em construção.
            O frontend já está pronto.
        </p>
        <label style="font-size:11px;color:var(--text-3);text-transform:uppercase;letter-spacing:.5px">Comentário atual</label>
        <textarea style="width:100%;height:80px;padding:8px;border-radius:6px;border:1px solid var(--border);background:var(--s1);color:var(--text);font-size:13px;font-family:inherit;resize:vertical;margin-top:4px" id="li-comment-edit-text">${escapeHtml(po.comment_generated)}</textarea>
    `;
    document.getElementById('li-comment-modal-confirm').textContent = 'Salvar (placeholder)';
    document.getElementById('li-comment-modal').style.display = 'flex';
}

function liDeleteComment(campaignId, postId) {
    _liCommentAction = { type: 'delete', campaignId, postId };
    document.getElementById('li-comment-modal-title').textContent = 'Excluir Comentário';
    document.getElementById('li-comment-modal-body').innerHTML = `
        <p style="font-size:13px;color:var(--text-2);margin:0">
            <strong>Funcionalidade em desenvolvimento</strong> — o endpoint da VM para exclusão de comentários está em construção.
        </p>
        <p style="font-size:13px;color:var(--text-2);margin:10px 0 0">
            Quando ativo, isso vai navegar até o post no LinkedIn (via Patchright stealth) e remover o comentário.
        </p>
    `;
    document.getElementById('li-comment-modal-confirm').textContent = 'Confirmar (placeholder)';
    document.getElementById('li-comment-modal').style.display = 'flex';
}

function liCloseCommentModal() {
    document.getElementById('li-comment-modal').style.display = 'none';
    _liCommentAction = null;
}

async function liConfirmCommentAction() {
    const a = _liCommentAction;
    if (!a) return liCloseCommentModal();
    // Find post + comment_id from campaign
    const c = _liAllCampaigns.find(x => x.id === a.campaignId);
    const po = c?.results?.posts?.find(p => p.id === a.postId || p.post_url === a.postUrl);
    if (!po) {
        toast('Post não encontrado', 'error');
        return liCloseCommentModal();
    }
    const post_url = po.post_url;
    const comment_id = po.comment_id;
    if (!comment_id) {
        toast('Comment ID ausente — backend ainda não capturou', 'error');
        return liCloseCommentModal();
    }
    try {
        if (a.type === 'edit') {
            const new_text = document.getElementById('li-comment-edit-text').value;
            const r = await api('/api/linkedin/comment/edit', {
                method: 'POST',
                body: { post_url, comment_id, new_text },
            });
            if (r.ok) {
                toast('Comentário editado', 'success');
                loadLinkedInCampaigns();
            } else {
                toast('Erro: ' + (r.error || 'falha'), 'error');
            }
        } else {
            const r = await api('/api/linkedin/comment/delete', {
                method: 'POST',
                body: { post_url, comment_id },
            });
            if (r.ok) {
                toast('Comentário excluído', 'success');
                loadLinkedInCampaigns();
            } else {
                toast('Erro: ' + (r.error || 'falha'), 'error');
            }
        }
    } catch (e) {
        toast('Erro: ' + (e.message || e), 'error');
    }
    liCloseCommentModal();
}

// ── Hover card (rich profile preview) ───────────────────────────────────
function _renderLiHoverCardContent(p) {
    const card = document.getElementById('li-hover-card');
    if (!card) return;
    const photo = p.photo || '/dashboard/avatar-default.svg';
    card.innerHTML = `
        <div class="li-hover-card-top">
            <img class="li-hover-card-photo" src="${photo}" alt="" onerror="this.src='/dashboard/avatar-default.svg'">
            <div class="li-hover-card-info">
                <div class="li-hover-card-name">${escapeHtml(p.name || '–')}</div>
                <div class="li-hover-card-role">${escapeHtml(p.current_role||p.headline||'')}</div>
                <div class="li-hover-card-meta">
                    ${p.current_company ? `<span><svg style="width:11px;height:11px;display:inline-block;vertical-align:middle"><use href="#i-briefcase"/></svg> ${escapeHtml(p.current_company)}</span>` : ''}
                    ${p.location ? `<span><svg style="width:11px;height:11px;display:inline-block;vertical-align:middle"><use href="#i-map-pin"/></svg> ${escapeHtml(p.location)}</span>` : ''}
                </div>
            </div>
        </div>
        ${p.bio ? `<div class="li-hover-card-bio">${escapeHtml(p.bio)}</div>` : ''}
        ${(p.mutual_count !== undefined || p.degree) ? `<div class="li-hover-card-row">
            <svg><use href="#i-users"/></svg>
            <span><strong>${p.mutual_count || 0}</strong> conexões mútuas${p.degree ? ` · Conexão de ${p.degree} grau` : ''}</span>
        </div>` : ''}
        ${(p.top_skills && p.top_skills.length) ? `<div class="li-hover-card-skills">
            ${p.top_skills.slice(0,5).map(s => `<span class="li-hover-card-skill">${escapeHtml(s)}</span>`).join('')}
        </div>` : ''}
        ${p.last_activity ? `<div class="li-hover-card-row">
            <svg><use href="#i-eye"/></svg>
            <span>Última atividade: ${escapeHtml(p.last_activity)}</span>
        </div>` : ''}
        <div class="li-hover-card-footer">
            <a class="li-hover-card-btn" href="${p.profile_url||'#'}" target="_blank" rel="noopener">
                <svg style="width:12px;height:12px"><use href="#i-external-link"/></svg>
                Ver perfil no LinkedIn
            </a>
        </div>`;
}

async function _showLiHoverCard(triggerEl, profileUrl) {
    if (!profileUrl) return;
    // 1) Try embedded cache (campaign results)
    let p = _liFindProfileByUrl(profileUrl);
    // 2) Try API cache (linkedin_profiles table on VM)
    if (!p || !p.bio) {
        try {
            const cached = await api('/api/linkedin/profiles?url=' + encodeURIComponent(profileUrl));
            if (cached && cached._cache_hit !== false) {
                p = { ...(p || {}), ...cached };
            } else if (cached && cached.status === 'hydrating') {
                // 202 — hidratação assíncrona disparada; mostra o que temos + loader
                p = p || { profile_url: profileUrl, name: 'Carregando...' };
                p._hydrating = true;
            }
        } catch (e) { /* ignore */ }
    }
    if (!p) return;
    _renderLiHoverCardContent(p);
    const card = document.getElementById('li-hover-card');
    if (!card) return;

    // Position
    const rect = triggerEl.getBoundingClientRect();
    const cardW = 320, cardH = 380;
    const vpW = window.innerWidth, vpH = window.innerHeight;
    let left = rect.right + 8 + window.scrollX;
    let top = rect.top + window.scrollY;
    if (rect.right + cardW + 8 > vpW) {
        left = rect.left - cardW - 8 + window.scrollX;
    }
    if (rect.top + cardH > vpH) {
        top = Math.max(8, vpH - cardH - 8) + window.scrollY;
    }
    card.style.left = Math.max(8, left) + 'px';
    card.style.top = top + 'px';
    card.style.display = 'block';
}

function _hideLiHoverCard() {
    const card = document.getElementById('li-hover-card');
    if (card) card.style.display = 'none';
}

// Delegated listener for hover triggers
document.addEventListener('mouseenter', (e) => {
    const target = e.target;
    if (!(target instanceof Element)) return;
    const trigger = target.closest?.('.li-hover-trigger');
    if (!trigger) return;
    const profileUrl = trigger.getAttribute('data-profile-url');
    if (!profileUrl) return;
    clearTimeout(_liHoverHideTimer);
    clearTimeout(_liHoverTimer);
    _liHoverTimer = setTimeout(() => _showLiHoverCard(trigger, profileUrl), 300);
}, true);

document.addEventListener('mouseleave', (e) => {
    const target = e.target;
    if (!(target instanceof Element)) return;
    const trigger = target.closest?.('.li-hover-trigger');
    if (!trigger) return;
    clearTimeout(_liHoverTimer);
    _liHoverHideTimer = setTimeout(_hideLiHoverCard, 200);
}, true);

// Keep card visible when hovering card itself
document.addEventListener('mouseenter', (e) => {
    if (e.target && e.target.id === 'li-hover-card') {
        clearTimeout(_liHoverHideTimer);
    }
}, true);
document.addEventListener('mouseleave', (e) => {
    if (e.target && e.target.id === 'li-hover-card') {
        _liHoverHideTimer = setTimeout(_hideLiHoverCard, 200);
    }
}, true);

function liDismissError(id) {
    api(`/api/linkedin/campaigns/${id}/dismiss-error`, { method: 'POST' })
        .then(() => { loadLinkedInCampaigns(); })
        .catch(e => console.warn('dismiss-error falhou:', e));
}

function liStopCampaignById(id) {
    if (!confirm('Parar esta campanha?')) return;
    api(`/api/linkedin/campaigns/${id}/stop`, { method: 'POST' })
        .then(() => { toast('Campanha parada', 'info'); loadLinkedInCampaigns(); });
}

function _liStatusBadge(status) {
    const map = {
        pending:   ['badge-amber', 'Pendente'],
        running:   ['badge-blue',  'Rodando'],
        done:      ['badge-lime',  'Concluída'],
        error:     ['badge-red',   'Erro'],
        stopped:   ['badge-gray',  'Parada'],
        cooldown:  ['badge-amber', 'Bloqueada — cooldown'],
        scheduled: ['badge-blue',  '📅 Agendada'],
        cancelled: ['badge-gray',  '✕ Cancelada'],
    };
    const [cls, label] = map[status] || ['badge-gray', status];
    return `<span class="badge ${cls}">${label}</span>`;
}

function _liResultSummary(c) {
    const r = c.results || {};
    if (c.type === 'view') return `${r.profiles_visited ?? 0} visitados`;
    if (c.type === 'engage') return `${r.liked ?? 0} curtidas · ${r.commented ?? 0} comentários`;
    if (c.type === 'connect') return `${r.connections_sent ?? 0} enviadas`;
    if (c.type === 'discover') return `${r.found ?? 0} encontrados`;
    return '–';
}

// ── Log modal ──
function openLiLogModal(campaignId, type) {
    _liActiveCampaignId = campaignId;
    document.getElementById('li-log-modal').style.display = 'flex';
    document.getElementById('li-log-modal-title').textContent = `Log — ${_liTypeName(type)} #${campaignId}`;
    document.getElementById('li-log-stream').innerHTML = '';
    document.getElementById('li-log-profiles').innerHTML = '';
    document.getElementById('li-log-summary').innerHTML = '';
    _pollLiLog(campaignId);
}

function closeLiLogModal() {
    document.getElementById('li-log-modal').style.display = 'none';
    if (_liPollInterval) { clearInterval(_liPollInterval); _liPollInterval = null; }
    _liActiveCampaignId = null;
}

function _pollLiLog(campaignId) {
    if (_liPollInterval) clearInterval(_liPollInterval);
    const fetch_ = async () => {
        try {
            const data = await api(`/api/linkedin/campaigns/${campaignId}/log`);
            _renderLiLog(data);
            if (['done', 'error', 'stopped'].includes(data.status)) {
                clearInterval(_liPollInterval);
                _liPollInterval = null;
                document.getElementById('li-log-stop-btn').style.display = 'none';
                loadLinkedInCampaigns();
            }
        } catch (e) { /* silent */ }
    };
    fetch_();
    _liPollInterval = setInterval(fetch_, 3000);
}

function _renderLiLog(data) {
    const stream = document.getElementById('li-log-stream');
    const summary = document.getElementById('li-log-summary');
    const profiles = document.getElementById('li-log-profiles');
    if (!stream) return;

    // log stream
    const logs = data.log || [];
    const phaseColors = {
        starting: '#6366f1', connecting: '#3b82f6', authenticating: '#f59e0b',
        planning: '#8b5cf6', searching: '#06b6d4', visiting: '#10b981',
        generating: '#a855f7', monitoring: '#f59e0b', done: '#22c55e', error: '#ef4444',
        warming: '#06b6d4', cooldown: '#f59e0b',
    };
    stream.innerHTML = logs.map(entry => {
        const color = phaseColors[entry.phase] || 'var(--text-2)';
        const time = entry.time ? new Date(entry.time).toLocaleTimeString('pt-BR') : '';
        const raw = entry.msg || '';
        // For error/cooldown phases, show friendly version + collapsed raw
        const isErr = entry.phase === 'error' || entry.phase === 'cooldown';
        const friendly = isErr ? humanizeLiError(raw) : raw;
        const showRaw = isErr && friendly !== raw;
        return `<div style="display:flex;gap:8px;align-items:flex-start">
            <span style="color:var(--text-3);flex-shrink:0;width:52px">${time}</span>
            <span style="color:${color};flex-shrink:0;width:80px;font-size:11px">[${entry.phase||'info'}]</span>
            <span style="color:var(--text);flex:1">
                ${escapeHtml(friendly)}
                ${showRaw ? `<details style="margin-top:4px;opacity:.55;font-size:10px">
                    <summary style="cursor:pointer">técnico</summary>
                    <code style="display:block;white-space:pre-wrap;padding:4px;background:rgba(0,0,0,.2);border-radius:3px">${escapeHtml(raw)}</code>
                </details>` : ''}
            </span>
        </div>`;
    }).join('');
    stream.scrollTop = stream.scrollHeight;

    // results summary
    if (data.results) {
        const r = data.results;
        const items = [];
        if (r.profiles_visited != null) items.push(`<strong>${r.profiles_visited}</strong> perfis visitados`);
        if (r.liked != null) items.push(`<strong>${r.liked}</strong> curtidas`);
        if (r.commented != null) items.push(`<strong>${r.commented}</strong> comentários`);
        if (r.connections_sent != null) items.push(`<strong>${r.connections_sent}</strong> conexões enviadas`);
        if (r.found != null) items.push(`<strong>${r.found}</strong> perfis encontrados`);
        summary.innerHTML = items.map(i =>
            `<div style="background:var(--s2);border-radius:6px;padding:6px 12px;font-size:12px;color:var(--text)">${i}</div>`
        ).join('');

        // profiles list
        const profileList = r.profiles || r.connections || r.engagements || [];
        if (profileList.length) {
            profiles.innerHTML = `<div style="font-size:11px;font-weight:600;color:var(--text-2);margin:8px 0 6px">Perfis</div>` +
                profileList.slice(0, 50).map(p => `
                    <div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--border)">
                        <div style="flex:1;min-width:0">
                            <div style="font-size:12px;color:var(--text);font-weight:500">${escapeHtml(p.name || p.author || '–')}</div>
                            <div style="font-size:11px;color:var(--text-2)">${escapeHtml(p.title || p.comment_text || p.post_url || '')}</div>
                        </div>
                        ${p.url ? `<a href="${p.url}" target="_blank" class="btn btn-ghost btn-sm" style="padding:3px 6px">
                            <svg style="width:11px;height:11px"><use href="#i-external-link"/></svg>
                        </a>` : ''}
                    </div>`
                ).join('');
        }
    }
}

async function liStopCampaign() {
    if (!_liActiveCampaignId) return;
    try {
        await api(`/api/linkedin/campaigns/${_liActiveCampaignId}/stop`, { method: 'POST' });
        showToast('Campanha parada', 'info');
        closeLiLogModal();
        loadLinkedInCampaigns();
    } catch (e) {
        showToast('Erro ao parar: ' + e.message, 'error');
    }
}

// WebSocket handlers for LinkedIn real-time events
const _origHandleWsEvent = typeof handleWsEvent === 'function' ? handleWsEvent : null;
function handleWsEvent(event) {
    if (_origHandleWsEvent) _origHandleWsEvent(event);
    if (event.type === 'linkedin_campaign_done' && currentPage === 'linkedin') {
        loadLinkedInCampaigns();
        loadLinkedInStatus();
        if (_liActiveCampaignId === event.campaign_id) {
            _pollLiLog(event.campaign_id);
        }
    } else if (event.type === 'linkedin_campaign_created' && currentPage === 'linkedin') {
        // Push new campaign into local cache + re-render immediately
        const c = event.data;
        if (c && !_liAllCampaigns.find(x => x.id === c.id)) {
            _liAllCampaigns = [c, ..._liAllCampaigns];
            _renderLiMonitor();
        }
    } else if (event.type === 'linkedin_health') {
        _liHealth = event.data || {state: 'unknown'};
        _renderLiHealth(_liHealth);
        _applyLiHealthToButtons(_liHealth);
        if (_liHealth.state === 'ok') {
            showToast('LinkedIn liberado — campanhas habilitadas', 'success');
        } else if (_liHealth.state === 'cooldown') {
            const min = Math.ceil((_liHealth.retry_after_seconds || 0) / 60);
            showToast(`LinkedIn em cooldown (HTTP ${_liHealth.http_code}) — retry em ~${min}min`, 'warning');
        }
    } else if (event.type === 'linkedin_progress' && currentPage === 'linkedin') {
        const d = event.data || {};
        const c = _liAllCampaigns.find(x => x.id === d.campaign_id);
        if (c) {
            const oldStatus = c.status;
            if (d.status) c.status = d.status;
            if (typeof d.progress === 'number') c.progress = d.progress;
            if (d.partial_results) c.results = { ...(c.results || {}), ...d.partial_results };
            if (d.scheduled_for !== undefined) c.scheduled_for = d.scheduled_for;
            if (d.schedule_reason !== undefined) c.schedule_reason = d.schedule_reason;
            _renderLiMonitor();
            // Notify when scheduler fires
            if (oldStatus === 'scheduled' && d.status === 'pending') {
                showToast(`Agendamento da #${d.campaign_id} disparou agora!`, 'success');
            }
        } else {
            loadLinkedInCampaigns();
        }
    }
}

/* ============================================================
   UX-RM-F2-B — Command Palette registration + Filter Persistence wiring
   ============================================================ */
function _registerHermesCommands() {
    const palette = window.HermesCommandPalette;
    const shortcuts = window.HermesKeyboardShortcuts;
    if (!palette && !shortcuts) return;

    const NAV_COMMANDS = [
        { id: 'go-dashboard',       label: 'Ir para Dashboard',       group: 'Navegacao',    shortcut: 'g d', action: () => navigate('dashboard') },
        { id: 'go-control',         label: 'Ir para Mission Control',  group: 'Operacoes',    shortcut: 'g c', action: () => navigate('control') },
        { id: 'go-cobaia',          label: 'Ir para Cobaia',           group: 'Operacoes',    shortcut: 'g b', action: () => navigate('cobaia') },
        { id: 'go-pipeline-studio', label: 'Ir para Pipeline Studio',  group: 'Operacoes',                    action: () => navigate('pipeline-studio') },
        { id: 'go-tasks',           label: 'Ir para Fila do Dia',      group: 'Operacoes',                    action: () => navigate('tasks') },
        { id: 'go-prospects',       label: 'Ir para Prospects',        group: 'Outreach',     shortcut: 'g p', action: () => navigate('prospects') },
        { id: 'go-proposals',       label: 'Ir para Propostas',        group: 'Outreach',     shortcut: 'g o', action: () => navigate('proposals') },
        { id: 'go-audit',           label: 'Ir para Auditoria',        group: 'Outreach',                     action: () => navigate('audit') },
        { id: 'go-linkedin',        label: 'Ir para LinkedIn',         group: 'Outreach',     shortcut: 'g l', action: () => navigate('linkedin') },
        { id: 'go-skills',          label: 'Ir para Skills',           group: 'Inteligencia', shortcut: 'g s', action: () => navigate('skills') },
        { id: 'go-skill-proposals', label: 'Ir para Skill Proposals',  group: 'Inteligencia',                 action: () => navigate('skill-proposals') },
        { id: 'go-lab',             label: 'Ir para Lab Stealth',      group: 'Inteligencia',                 action: () => navigate('lab') },
        { id: 'go-memory',          label: 'Ir para Memoria',          group: 'Inteligencia', shortcut: 'g m', action: () => navigate('memory') },
        { id: 'go-missions',        label: 'Ir para Missoes',          group: 'Inteligencia',                 action: () => navigate('missions') },
        { id: 'go-claude',          label: 'Ir para AI Terminal',      group: 'DevTools',                     action: () => navigate('claude') },
        { id: 'go-mcp-gateway',     label: 'Ir para MCP Gateway',      group: 'DevTools',                     action: () => navigate('mcp-gateway') },
        { id: 'go-observability',   label: 'Ir para Observability',    group: 'DevTools',     shortcut: 'g x', action: () => navigate('observability') },
    ];

    const ACTION_COMMANDS = [
        {
            id: 'action-panic', label: 'Panic Stop — Parar tudo', group: 'Acoes',
            action: () => { if (window.HermesPanicButton) window.HermesPanicButton.open(); }
        },
        {
            id: 'action-cobaia-pause', label: 'Pausar Cobaia', group: 'Acoes',
            action: async () => {
                try { await api('/api/linkedin/cobaia/pause', { method: 'POST' }); toast('Cobaia pausada', 'warning'); }
                catch (e) { toast('Erro: ' + e.message, 'error'); }
            }
        },
        {
            id: 'action-cobaia-resume', label: 'Retomar Cobaia', group: 'Acoes',
            action: async () => {
                try { await api('/api/linkedin/cobaia/resume', { method: 'POST' }); toast('Cobaia retomada', 'success'); }
                catch (e) { toast('Erro: ' + e.message, 'error'); }
            }
        },
        {
            id: 'action-shortcuts', label: 'Mostrar Atalhos de Teclado', group: 'Ajuda', shortcut: '?',
            action: () => { if (window.HermesShortcutsHelp) window.HermesShortcutsHelp.show(); }
        },
        {
            id: 'action-theme-cycle', label: 'Alternar Tema (Auto/Dark/Light)', group: 'Aparencia',
            action: () => { if (window.HermesThemeToggle) window.HermesThemeToggle.cycle(); }
        },
        {
            id: 'action-theme-dark',  label: 'Tema Escuro', group: 'Aparencia',
            action: () => { if (window.HermesThemeToggle) window.HermesThemeToggle.setTheme('dark'); }
        },
        {
            id: 'action-theme-light', label: 'Tema Claro', group: 'Aparencia',
            action: () => { if (window.HermesThemeToggle) window.HermesThemeToggle.setTheme('light'); }
        },
        {
            id: 'action-theme-auto',  label: 'Tema Automatico (Sistema)', group: 'Aparencia',
            action: () => { if (window.HermesThemeToggle) window.HermesThemeToggle.setTheme('auto'); }
        },
    ];

    if (palette) {
        [...NAV_COMMANDS, ...ACTION_COMMANDS].forEach(c => palette.register(c));
    }

    if (shortcuts) {
        const SHORTCUTS = [
            ['g d', () => navigate('dashboard'),      'Ir para Dashboard',      'Navegacao'],
            ['g c', () => navigate('control'),         'Ir para Mission Control', 'Operacoes'],
            ['g b', () => navigate('cobaia'),          'Ir para Cobaia',          'Operacoes'],
            ['g p', () => navigate('prospects'),       'Ir para Prospects',       'Outreach'],
            ['g o', () => navigate('proposals'),       'Ir para Propostas',       'Outreach'],
            ['g l', () => navigate('linkedin'),        'Ir para LinkedIn',        'Outreach'],
            ['g s', () => navigate('skills'),          'Ir para Skills',          'Inteligencia'],
            ['g m', () => navigate('memory'),          'Ir para Memoria',         'Inteligencia'],
            ['g x', () => navigate('observability'),   'Ir para Observability',   'DevTools'],
        ];
        SHORTCUTS.forEach(([combo, action, label, category]) =>
            shortcuts.register(combo, action, label, category)
        );
    }
}

function _wireFilterPersistence() {
    const fp = window.HermesFilterPersistence;
    if (!fp) return;

    // Prospects filters — save on change
    ['filter-city', 'filter-category', 'filter-website', 'filter-stage'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.addEventListener('change', () => {
            const saved = fp.get('prospects');
            saved[id] = el.value;
            fp.set('prospects', saved);
        });
    });
    const searchEl = document.getElementById('prospect-search');
    if (searchEl) {
        searchEl.addEventListener('input', () => {
            const saved = fp.get('prospects');
            saved['search'] = searchEl.value;
            fp.set('prospects', saved);
        });
    }

    // Proposals filters — save on change
    ['proposal-filter-city', 'proposal-filter-category', 'proposal-filter-sent'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.addEventListener('change', () => {
            const saved = fp.get('proposals');
            saved[id] = el.value;
            fp.set('proposals', saved);
        });
    });
}

/* ============================================================
   UX-RM-F7-A — LAZY KEY HANDLERS (Ctrl+K, ?)
   ============================================================ */
function _registerLazyKeyHandlers() {
    // Ctrl/Cmd+K — lazy-load command_palette.js on first press
    document.addEventListener('keydown', async (e) => {
        if (window.HermesCommandPalette) return; // palette already loaded, its own handler fires
        const isMac = navigator.platform ? navigator.platform.toUpperCase().includes('MAC') : false;
        const trigger = isMac ? e.metaKey : e.ctrlKey;
        if (trigger && e.key === 'k') {
            e.preventDefault();
            e.stopImmediatePropagation();
            if (!window.loadComponent) return;
            try {
                await window.loadComponent('command_palette');
                _registerHermesCommands(); // wire commands into newly-loaded palette
                if (window.HermesCommandPalette) window.HermesCommandPalette.open();
            } catch (err) {
                if (window.hermesToast) window.hermesToast.error('Falha ao carregar paleta de comandos');
            }
        }
    }, true);

    // ? key — lazy-load shortcuts_help_overlay.js on first press
    document.addEventListener('keydown', async (e) => {
        if (e.key !== '?' || e.ctrlKey || e.metaKey) return;
        const tag = document.activeElement ? document.activeElement.tagName : '';
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
        if (window.HermesShortcutsHelp) { window.HermesShortcutsHelp.show(); return; }
        if (!window.loadComponent) return;
        try {
            await window.loadComponent('shortcuts_help_overlay');
            if (window.HermesShortcutsHelp) window.HermesShortcutsHelp.show();
        } catch (err) {
            if (window.hermesToast) window.hermesToast.error('Falha ao carregar atalhos');
        }
    });
}

/* ============================================================
   UX-RM-F3-A — ONBOARDING FIRST-RUN CHECK
   ============================================================ */
async function _checkOnboarding() {
    if (localStorage.getItem('hermes.onboarding.completed')) return;

    // UX-RM-F7-A: lazy-load wizard + all steps on first check
    if (!window.HermesOnboardingWizard && window.loadComponent) {
        try {
            await window.loadComponent('onboarding_wizard');
            await Promise.all([
                window.loadComponent('welcome', 'onboarding_steps'),
                window.loadComponent('profile', 'onboarding_steps'),
                window.loadComponent('channels', 'onboarding_steps'),
                window.loadComponent('icp', 'onboarding_steps'),
                window.loadComponent('launch', 'onboarding_steps'),
            ]);
        } catch (e) {
            if (window.hermesToast) window.hermesToast.error('Falha ao carregar wizard de onboarding');
            return;
        }
    }

    const wiz = window.HermesOnboardingWizard;
    if (!wiz) return;

    if (localStorage.getItem('hermes.onboarding.completed')) return;

    // Server-side check (authoritative)
    try {
        const r = await api('/api/onboarding/state');
        if (r && r.data && r.data.completed) {
            localStorage.setItem('hermes.onboarding.completed', '1');
            return;
        }
        const skipped = localStorage.getItem('hermes.onboarding.skipped');
        if (r && r.data && r.data.last_step > 0 && !skipped) {
            // Resume from where user left off
            wiz.open({ resume: true });
            return;
        }
        if (!skipped) {
            wiz.open();
        }
    } catch (_) {
        // Offline — fall back to localStorage
        const skipped = localStorage.getItem('hermes.onboarding.skipped');
        if (!skipped) wiz.open();
    }
}
