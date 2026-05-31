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

function checkAuth() {
    const token = localStorage.getItem('hermes_token') || '';
    const startPage = () => {
        const hash = window.location.hash.replace('#', '') || 'dashboard';
        navigate(hash);
    };
    if (!token) {
        fetch(VM_API + '/api/dashboard').then(r => {
            if (r.status === 401) showLoginScreen();
            else startPage();
        }).catch(() => startPage());
    } else {
        startPage();
    }
}

/* ============================================================
   TOAST SYSTEM
   ============================================================ */
function toast(msg, type = 'info') {
    const c = document.getElementById('toast-container');
    const icons = { success: '#i-check', error: '#i-x', info: '#i-lightbulb' };
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.innerHTML = `<svg><use href="${icons[type] || icons.info}"/></svg><span>${escapeHtml(msg)}</span>`;
    c.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateY(8px)'; setTimeout(() => el.remove(), 300); }, 4000);
}

/* ============================================================
   NAVIGATION
   ============================================================ */
function navigate(page) {
    currentPage = page;
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item[data-page]').forEach(n => n.classList.remove('active'));

    const pageEl = document.getElementById(`page-${page}`);
    const navEl = document.querySelector(`.nav-item[data-page="${page}"]`);
    if (pageEl) {
        pageEl.classList.add('active');
        pageEl.style.animation = 'none';
        void pageEl.offsetWidth;
        pageEl.style.animation = 'fade-in 0.25s var(--ease) both';
    }
    if (navEl) navEl.classList.add('active');

    const titles = {
        dashboard: 'Dashboard',
        prospects: 'Prospects',
        proposals: 'Centro de Propostas',
        audit: 'Auditoria Digital',
        pipeline: 'Pipeline',
        tasks: 'Fila do Dia',
        skills: 'Hermes Skills',
        memory: 'Memoria do Agente',
        missions: 'Missoes da Semana',
        claude: 'AI Terminal'
    };
    document.getElementById('topbar-title').textContent = titles[page] || page;
    window.location.hash = page;

    clearInterval(dashboardInterval);
    clearInterval(scraperInterval);
    if (auditPollingInterval) { clearInterval(auditPollingInterval); auditPollingInterval = null; }

    if (page === 'dashboard') {
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
    }
}

function refreshCurrentPage() {
    navigate(currentPage);
    toast('Pagina atualizada', 'success');
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
        c.innerHTML = items.map(p => `<div class="list-row" style="padding:8px 12px" onclick="openProspectPanel('${p.id}')">
            <div class="photo-thumb">${p.photo_ref ? `<img src="${photoUrl(p.photo_ref)}" onerror="this.parentElement.innerHTML='<svg><use href=\\'#i-store\\'/></svg>'">` : `<svg><use href="#i-store"/></svg>`}</div>
            <div style="flex:1;min-width:0"><div style="font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(p.name || p.business_name)}</div><div style="font-size:10px;color:var(--text-3)">${escapeHtml(p.category || '')} - ${escapeHtml(p.city || '')}</div></div>
            <span class="score-badge ${scoreClass(p.score)}">${p.score ?? '--'}</span>
        </div>`).join('');
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
                    return `<div class="hl-exec-card" style="cursor:pointer" onclick="loadExecIntoFeed(${ex.id})">
                        <div style="display:flex;justify-content:space-between;align-items:center">
                            <div style="display:flex;align-items:center;gap:10px">
                                <svg style="width:14px;height:14px;stroke:${statusColor}"><use href="${meta.icon}"/></svg>
                                <span style="font-size:12px;font-weight:500;color:var(--text-2)">${escapeHtml(ex.pipeline_name || '')}</span>
                            </div>
                            <div style="display:flex;align-items:center;gap:8px">
                                <span style="font-size:10px;color:var(--text-3);font-family:monospace">${dmm}:${dss}</span>
                                <span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:var(--r-xs);background:${statusBg};color:${statusColor}">${ex.status}</span>
                                <span style="font-size:10px;color:var(--text-3)">${ex.completed_at ? new Date(ex.completed_at).toLocaleTimeString() : ''}</span>
                            </div>
                        </div>
                        ${logs.length ? `<div style="font-size:10px;color:var(--text-3);margin-top:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(logs[logs.length-1].msg.substring(0,100))}</div>` : ''}
                    </div>`;
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
            <div class="pl-role-chip ${plResultsFilter === 'all' ? 'active' : ''}" onclick="filterProfiles('all')">
                Todos <span class="pl-role-chip-count">${profiles.length}</span>
            </div>
            ${Object.entries(byRole).map(([role, count]) => {
                const rc = roleColors[role] || { cls: '', color: 'var(--text-1)' };
                return `<div class="pl-role-chip ${plResultsFilter === role ? 'active' : ''}" onclick="filterProfiles('${escapeHtml(role)}')">
                    ${escapeHtml(role)} <span class="pl-role-chip-count">${count}</span>
                </div>`;
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
    return `<div style="display:flex;align-items:center;gap:12px;padding:12px 14px;border-bottom:1px solid var(--border);cursor:pointer;transition:background 0.15s" onmouseover="this.style.background='var(--s2)'" onmouseout="this.style.background=''" onclick="loadExecIntoFeed(${e.id})">
        <div style="width:8px;height:8px;border-radius:50%;background:${statusColor};flex-shrink:0"></div>
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
    </div>`;
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
    return html;
}

function formatInline(text) {
    return escapeHtml(text)
        .replace(/`([^`]+)`/g, '<code style="background:var(--s3);padding:1px 5px;border-radius:3px;font-size:11px;color:var(--lime)">$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong style="color:var(--text);font-weight:700">$1</strong>')
        .replace(/\*([^*]+)\*/g, '<em style="color:var(--text-2)">$1</em>');
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
    c.innerHTML = claudeHistory.slice(0, 20).map(h => `<div class="list-row" style="padding:6px 12px;cursor:pointer" onclick="document.getElementById('claude-input').value='${escapeHtml(h.cmd)}';document.getElementById('claude-input').focus()">
        <svg style="width:14px;height:14px;stroke:var(--text-3);flex-shrink:0"><use href="#i-chevron-right"/></svg>
        <div style="flex:1;min-width:0"><div style="font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(h.cmd)}</div><div style="font-size:10px;color:var(--text-3)">${formatDate(h.time)} ${formatTime(h.time)}</div></div>
    </div>`).join('');
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

function connectWS() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = localStorage.getItem('hermes_api')?.replace(/^https?:\/\//, '').replace(/\/+$/, '') || location.host;
    ws = new WebSocket(`${protocol}//${host}/ws`);
    ws.onmessage = (e) => {
        try {
            const event = JSON.parse(e.data);
            handleWSEvent(event);
        } catch (err) {}
    };
    ws.onclose = () => { ws = null; setTimeout(connectWS, 3000); };
    ws.onerror = () => { ws?.close(); };
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
}

/* ============================================================
   INIT
   ============================================================ */
function init() {
    checkAuth();
    connectWS();
}

window.addEventListener('hashchange', () => {
    const hash = window.location.hash.replace('#', '') || 'dashboard';
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
    try {
        await api(`/api/hermes/skills/${name}`, { method: 'PATCH', body: JSON.stringify({ active }) });
        toast(`Skill ${name} ${active ? 'ativada' : 'desativada'}`, 'success');
        loadSkills();
    } catch (e) {
        toast('Erro ao alterar skill', 'error');
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

init();
