/* ============================================================
   Hermes Cloud Studio — LabCockpit (F.3.3)
   ============================================================
   Controller principal da Lab Cockpit page (#lab hash route).
   API global: window.HermesLabCockpit.{init, destroy, refreshRuns, startRun,
                                         abortRun, openRunDetails, closeDrawer,
                                         appendEvent}.

   Layout 3 sections (full-page):
     - header: flow selector + ▶ Run / ⏹ Abort
     - main: run history list (50/page paginated) + drawer slide-in right
     - footer: compliance gauge + fingerprint diff side-by-side

   WS events consumidos (via app.js delegating handleWSEvent):
     lab.run_started, lab.step_progress, lab.screenshot_captured,
     lab.compliance_score, lab.fingerprint_dump, lab.run_completed,
     lab.run_failed, lab.run_aborted

   Anti-acidente: abort exige modal confirmação 2s delay (pattern panic_button F.2.5b).
   Empty state: skeleton + texto helpful "Sem runs ainda — clica 'Run Fingerprint'".

   Reuses:
     - window.hermesUtils.safeMerge — merge defensivo
     - window.skeleton.show/hide — loading state
     - window.hermesToast.success/warn/error — feedback
     - window.HermesLabGauge — compliance gauge
     - window.HermesLabFingerprintDiff — fingerprint diff table
     - window.sanitizeClaudeHtml (app.js global) — innerHTML += defensive (drawer html template)

   XSS hygiene: textContent strict pra TODO content runtime (server data).
   innerHTML APENAS literal templates no _buildShell, sem interpolation de variável.
   ============================================================ */
(function () {
    "use strict";

    const PAGE_SIZE = 50;
    const FLOWS = [
        { value: "fingerprint", label: "Fingerprint Baseline (sites públicos)" },
        { value: "login", label: "Login (cobaia LinkedIn — CUIDADO)" },
        { value: "viewer", label: "Viewer (cobaia LinkedIn — CUIDADO)" },
    ];

    let _root = null;
    let _historyListEl = null;
    let _pageIndicatorEl = null;
    let _prevBtnEl = null;
    let _nextBtnEl = null;
    let _flowSelectEl = null;
    let _runBtnEl = null;
    let _abortBtnEl = null;
    let _drawerEl = null;
    let _drawerContentEl = null;
    let _gaugeEl = null;
    let _fpDiffEl = null;
    let _abortConfirmOverlay = null;
    let _abortConfirmBtn = null;
    let _abortCancelBtn = null;
    let _abortEnableTimer = null;

    let _runs = [];
    let _currentPage = 1;
    let _activeRunId = null;
    let _activeFlow = null;
    let _autoScrollPaused = false; // pause quando drawer aberto
    let _initialized = false;
    let _previousFocus = null;

    function _safeMerge(a, b) {
        if (window.hermesUtils && typeof window.hermesUtils.safeMerge === "function") {
            return window.hermesUtils.safeMerge(a, b);
        }
        return Object.assign({}, a || {}, b || {});
    }

    function _toast(type, msg) {
        if (window.hermesToast && typeof window.hermesToast[type] === "function") {
            window.hermesToast[type](msg);
            return;
        }
        if (typeof window.toast === "function") window.toast(msg, type);
    }

    async function _apiCall(method, path, body) {
        const base = (typeof window.VM_API !== "undefined" && window.VM_API) || localStorage.getItem("hermes_api") || "";
        const token = localStorage.getItem("hermes_token") || "";
        const headers = { "Content-Type": "application/json" };
        if (token) headers["X-Hermes-Token"] = token;
        const opts = { method, headers };
        if (body !== undefined) opts.body = JSON.stringify(body);
        const resp = await fetch(base + path, opts);
        if (!resp.ok) {
            const txt = await resp.text().catch(() => "");
            throw new Error(`HTTP ${resp.status}: ${txt.slice(0, 200)}`);
        }
        const ct = resp.headers.get("content-type") || "";
        return ct.includes("json") ? resp.json() : resp.text();
    }

    function _formatDuration(ms) {
        if (ms === null || ms === undefined || ms === "") return "—";
        const n = Number(ms);
        if (!Number.isFinite(n) || n < 0) return "—";
        if (n < 1000) return `${n.toFixed(0)}ms`;
        const s = n / 1000;
        if (s < 60) return `${s.toFixed(1)}s`;
        const m = Math.floor(s / 60);
        const rs = Math.floor(s % 60);
        return `${m}m${rs}s`;
    }

    function _formatTs(ts) {
        if (!ts) return "—";
        try {
            const d = (typeof ts === "number") ? new Date(ts * 1000) : new Date(ts);
            if (Number.isNaN(d.getTime())) return "—";
            const hh = String(d.getHours()).padStart(2, "0");
            const mm = String(d.getMinutes()).padStart(2, "0");
            const ss = String(d.getSeconds()).padStart(2, "0");
            const dd = String(d.getDate()).padStart(2, "0");
            const mo = String(d.getMonth() + 1).padStart(2, "0");
            return `${dd}/${mo} ${hh}:${mm}:${ss}`;
        } catch { return "—"; }
    }

    function _buildShell(host) {
        host.classList.add("lab-cockpit-page");

        // Header
        const header = document.createElement("header");
        header.className = "lab-header";
        const h1 = document.createElement("h1");
        h1.className = "lab-title";
        h1.textContent = "Lab Cockpit";
        const actions = document.createElement("div");
        actions.className = "lab-actions";

        const flowSelect = document.createElement("select");
        flowSelect.className = "lab-flow-select";
        flowSelect.setAttribute("aria-label", "Escolher flow do lab");
        FLOWS.forEach((f) => {
            const opt = document.createElement("option");
            opt.value = f.value;
            opt.textContent = f.label;
            flowSelect.appendChild(opt);
        });

        const runBtn = document.createElement("button");
        runBtn.type = "button";
        runBtn.className = "lab-btn-run";
        runBtn.setAttribute("aria-label", "Iniciar run do lab");
        runBtn.textContent = "▶ Run";
        runBtn.addEventListener("click", _onRunClick);

        const abortBtn = document.createElement("button");
        abortBtn.type = "button";
        abortBtn.className = "lab-btn-abort hidden";
        abortBtn.setAttribute("aria-label", "Abortar run em andamento");
        abortBtn.textContent = "Abort";
        abortBtn.addEventListener("click", _onAbortClick);

        actions.appendChild(flowSelect);
        actions.appendChild(runBtn);
        actions.appendChild(abortBtn);
        header.appendChild(h1);
        header.appendChild(actions);
        host.appendChild(header);

        // Main (history + drawer)
        const main = document.createElement("div");
        main.className = "lab-main";

        const historySection = document.createElement("section");
        historySection.className = "lab-history";
        const h2 = document.createElement("h2");
        h2.textContent = "Run History";
        const listEl = document.createElement("div");
        listEl.className = "lab-history-list";
        listEl.dataset.role = "history-list";
        listEl.setAttribute("role", "list");
        listEl.setAttribute("aria-label", "Histórico de runs do lab");
        const pagination = document.createElement("div");
        pagination.className = "lab-pagination";
        const prevBtn = document.createElement("button");
        prevBtn.type = "button";
        prevBtn.className = "lab-page-prev";
        prevBtn.setAttribute("aria-label", "Página anterior");
        prevBtn.textContent = "← Anterior";
        prevBtn.disabled = true;
        prevBtn.addEventListener("click", () => _onPageChange(-1));
        const pageIndicator = document.createElement("span");
        pageIndicator.className = "lab-page-indicator";
        pageIndicator.dataset.role = "page-indicator";
        pageIndicator.textContent = "Página 1 de 1";
        const nextBtn = document.createElement("button");
        nextBtn.type = "button";
        nextBtn.className = "lab-page-next";
        nextBtn.setAttribute("aria-label", "Próxima página");
        nextBtn.textContent = "Próxima →";
        nextBtn.disabled = true;
        nextBtn.addEventListener("click", () => _onPageChange(1));
        pagination.appendChild(prevBtn);
        pagination.appendChild(pageIndicator);
        pagination.appendChild(nextBtn);
        historySection.appendChild(h2);
        historySection.appendChild(listEl);
        historySection.appendChild(pagination);

        const drawer = document.createElement("aside");
        drawer.className = "lab-drawer hidden";
        drawer.setAttribute("aria-hidden", "true");
        drawer.setAttribute("role", "complementary");
        drawer.setAttribute("aria-label", "Detalhes do run selecionado");
        const drawerClose = document.createElement("button");
        drawerClose.type = "button";
        drawerClose.className = "lab-drawer-close";
        drawerClose.setAttribute("aria-label", "Fechar drawer de detalhes");
        drawerClose.textContent = "✕";
        drawerClose.addEventListener("click", closeDrawer);
        const drawerContent = document.createElement("div");
        drawerContent.className = "lab-drawer-content";
        drawerContent.dataset.role = "drawer-content";
        drawer.appendChild(drawerClose);
        drawer.appendChild(drawerContent);

        main.appendChild(historySection);
        main.appendChild(drawer);
        host.appendChild(main);

        // Footer (gauge + fingerprint diff)
        const footer = document.createElement("footer");
        footer.className = "lab-footer";
        const gaugeSection = document.createElement("section");
        gaugeSection.className = "lab-footer-section";
        const gaugeTitle = document.createElement("h3");
        gaugeTitle.textContent = "Compliance Score";
        const gaugeMount = document.createElement("div");
        gaugeMount.className = "lab-gauge-mount";
        gaugeMount.dataset.role = "gauge-mount";
        gaugeSection.appendChild(gaugeTitle);
        gaugeSection.appendChild(gaugeMount);

        const fpSection = document.createElement("section");
        fpSection.className = "lab-footer-section";
        const fpTitle = document.createElement("h3");
        fpTitle.textContent = "Fingerprint Diff";
        const fpMount = document.createElement("div");
        fpMount.className = "lab-fp-diff-mount";
        fpMount.dataset.role = "fp-diff-mount";
        fpSection.appendChild(fpTitle);
        fpSection.appendChild(fpMount);

        footer.appendChild(gaugeSection);
        footer.appendChild(fpSection);
        host.appendChild(footer);

        // Cache refs
        _historyListEl = listEl;
        _pageIndicatorEl = pageIndicator;
        _prevBtnEl = prevBtn;
        _nextBtnEl = nextBtn;
        _flowSelectEl = flowSelect;
        _runBtnEl = runBtn;
        _abortBtnEl = abortBtn;
        _drawerEl = drawer;
        _drawerContentEl = drawerContent;
        _gaugeEl = gaugeMount;
        _fpDiffEl = fpMount;
    }

    function _renderHistoryList() {
        if (!_historyListEl) return;
        _historyListEl.replaceChildren();

        if (!_runs || _runs.length === 0) {
            _renderEmptyState();
            _updatePagination();
            return;
        }

        const start = (_currentPage - 1) * PAGE_SIZE;
        const slice = _runs.slice(start, start + PAGE_SIZE);

        slice.forEach((run) => {
            const row = _buildRunRow(run);
            _historyListEl.appendChild(row);
        });
        _updatePagination();
    }

    function _renderEmptyState() {
        const emptyWrap = document.createElement("div");
        emptyWrap.className = "lab-empty-state";

        if (window.skeleton && typeof window.skeleton.show === "function") {
            // Skeleton placeholders
            const skel = document.createElement("div");
            skel.className = "lab-empty-skeleton";
            emptyWrap.appendChild(skel);
            window.skeleton.show(skel, { count: 3, height: "42px" });
        }

        const msg = document.createElement("p");
        msg.className = "lab-empty-msg";
        msg.textContent = "Sem runs ainda — clica 'Run' acima pra testar stealth contra CreepJS+browserleaks.";
        emptyWrap.appendChild(msg);

        _historyListEl.appendChild(emptyWrap);
    }

    function _buildRunRow(run) {
        const row = document.createElement("div");
        row.className = "lab-run-row";
        row.dataset.runId = String(run.run_id || "");
        row.dataset.status = String(run.status || "unknown");
        row.setAttribute("role", "button");
        row.setAttribute("tabindex", "0");
        row.setAttribute("aria-label", `Run ${run.run_id} flow ${run.flow} status ${run.status}`);

        const colId = document.createElement("span");
        colId.className = "lab-run-id";
        colId.textContent = `#${run.run_id}`;

        const colFlow = document.createElement("span");
        colFlow.className = "lab-run-flow";
        colFlow.textContent = String(run.flow || "?");

        const colTs = document.createElement("span");
        colTs.className = "lab-run-ts";
        colTs.textContent = _formatTs(run.started_at);

        const colDuration = document.createElement("span");
        colDuration.className = "lab-run-duration";
        colDuration.textContent = _formatDuration(run.duration_ms);

        const colScore = document.createElement("span");
        colScore.className = "lab-run-score";
        const score = run.compliance_score;
        colScore.textContent = (score === null || score === undefined) ? "—" : String(Math.round(Number(score)));

        const colStatus = document.createElement("span");
        colStatus.className = "lab-run-status";
        colStatus.textContent = String(run.status || "unknown");

        row.appendChild(colId);
        row.appendChild(colFlow);
        row.appendChild(colTs);
        row.appendChild(colDuration);
        row.appendChild(colScore);
        row.appendChild(colStatus);

        const open = () => openRunDetails(run.run_id);
        row.addEventListener("click", open);
        row.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                open();
            }
        });

        return row;
    }

    function _updatePagination() {
        const total = _runs.length;
        const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
        if (_pageIndicatorEl) {
            _pageIndicatorEl.textContent = `Página ${_currentPage} de ${totalPages}`;
        }
        if (_prevBtnEl) _prevBtnEl.disabled = _currentPage <= 1;
        if (_nextBtnEl) _nextBtnEl.disabled = _currentPage >= totalPages;
    }

    function _onPageChange(delta) {
        const total = _runs.length;
        const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
        const newPage = Math.max(1, Math.min(totalPages, _currentPage + delta));
        if (newPage !== _currentPage) {
            _currentPage = newPage;
            _renderHistoryList();
        }
    }

    function _renderDrawer(run) {
        if (!_drawerContentEl) return;
        _drawerContentEl.replaceChildren();

        // Metadata block
        const meta = document.createElement("div");
        meta.className = "lab-drawer-meta";

        const h = document.createElement("h2");
        h.textContent = `Run #${run.run_id || "?"}`;
        meta.appendChild(h);

        const fields = [
            ["Flow", run.flow],
            ["Status", run.status],
            ["Início", _formatTs(run.started_at)],
            ["Fim", _formatTs(run.completed_at)],
            ["Duração", _formatDuration(run.duration_ms)],
            ["Compliance", (run.compliance_score === null || run.compliance_score === undefined) ? "—" : String(Math.round(Number(run.compliance_score)))],
        ];
        const dl = document.createElement("dl");
        dl.className = "lab-drawer-fields";
        fields.forEach(([k, v]) => {
            const dt = document.createElement("dt");
            dt.textContent = k;
            const dd = document.createElement("dd");
            dd.textContent = String(v == null ? "—" : v);
            dl.appendChild(dt);
            dl.appendChild(dd);
        });
        meta.appendChild(dl);
        _drawerContentEl.appendChild(meta);

        // Artifacts (screenshots)
        if (Array.isArray(run.artifacts) && run.artifacts.length > 0) {
            const artH = document.createElement("h3");
            artH.textContent = "Screenshots";
            _drawerContentEl.appendChild(artH);
            const grid = document.createElement("div");
            grid.className = "lab-artifact-grid";
            run.artifacts.forEach((art) => {
                if (!art || !art.filename) return;
                const fig = document.createElement("figure");
                fig.className = "lab-artifact-item";
                const img = document.createElement("img");
                img.loading = "lazy";
                img.alt = String(art.site || art.filename || "screenshot");
                const base = (typeof window.VM_API !== "undefined" && window.VM_API) || localStorage.getItem("hermes_api") || "";
                const token = localStorage.getItem("hermes_token") || "";
                const tokenParam = token ? `?token=${encodeURIComponent(token)}` : "";
                img.src = `${base}/api/lab/runs/${encodeURIComponent(run.run_id)}/artifacts/${encodeURIComponent(art.filename)}${tokenParam}`;
                const cap = document.createElement("figcaption");
                cap.textContent = String(art.site || art.filename || "");
                fig.appendChild(img);
                fig.appendChild(cap);
                grid.appendChild(fig);
            });
            _drawerContentEl.appendChild(grid);
        }

        // Events timeline (collapsible)
        if (Array.isArray(run.events) && run.events.length > 0) {
            const det = document.createElement("details");
            det.className = "lab-drawer-events";
            const summary = document.createElement("summary");
            summary.textContent = `Events (${run.events.length})`;
            det.appendChild(summary);
            const pre = document.createElement("pre");
            pre.className = "lab-drawer-events-json";
            pre.textContent = JSON.stringify(run.events, null, 2);
            det.appendChild(pre);
            _drawerContentEl.appendChild(det);
        }
    }

    async function refreshRuns(options) {
        try {
            const data = await _apiCall("GET", "/api/lab/runs?limit=200");
            _runs = Array.isArray(data && data.runs) ? data.runs : [];
            // Order DESC by started_at if backend not already
            _runs.sort((a, b) => {
                const ta = new Date(a.started_at || 0).getTime();
                const tb = new Date(b.started_at || 0).getTime();
                return tb - ta;
            });
            _currentPage = 1;
            _renderHistoryList();
            _refreshFingerprintDiff();
        } catch (e) {
            console.error("[HermesLabCockpit] refreshRuns failed", e);
            _toast("error", `Falha ao carregar runs: ${e.message || e}`);
        }
    }

    async function _refreshFingerprintDiff() {
        if (!window.HermesLabFingerprintDiff) return;
        const fpRuns = _runs.filter((r) => r.flow === "fingerprint" && r.status === "success");
        const top2 = fpRuns.slice(0, 2);
        // Hydrate fingerprint signals from events (lazy fetch run details)
        const hydrated = await Promise.all(top2.map(async (r) => {
            try {
                const detail = await _apiCall("GET", `/api/lab/runs/${encodeURIComponent(r.run_id)}`);
                const events = (detail && Array.isArray(detail.events)) ? detail.events : [];
                const fpEvent = events.find((e) => e && (e.event === "fingerprint_dump" || e.type === "fingerprint_dump"));
                return {
                    run_id: r.run_id,
                    started_at: r.started_at,
                    fingerprint: fpEvent ? (fpEvent.signals || fpEvent.payload || {}) : {},
                };
            } catch { return { run_id: r.run_id, started_at: r.started_at, fingerprint: {} }; }
        }));
        try { window.HermesLabFingerprintDiff.render(hydrated); } catch (e) { console.warn("[HermesLabCockpit] fp diff render failed", e); }
    }

    async function startRun() {
        if (!_flowSelectEl) return;
        const flow = _flowSelectEl.value || "fingerprint";

        // WARN: flows que tocam cobaia LinkedIn real
        if (flow !== "fingerprint") {
            const confirmed = window.confirm(
                `Flow '${flow}' toca conta LinkedIn cobaia REAL.\n\n` +
                `Continua APENAS se:\n` +
                `  - Cobaia milgrauz está OK\n` +
                `  - Não vai burnar reputação\n\n` +
                `Confirmar início?`
            );
            if (!confirmed) return;
        }

        if (_runBtnEl) _runBtnEl.disabled = true;
        try {
            const resp = await _apiCall("POST", "/api/lab/start", { flow });
            _activeRunId = resp && resp.run_id;
            _activeFlow = flow;
            if (_abortBtnEl) _abortBtnEl.classList.remove("hidden");
            if (_runBtnEl) _runBtnEl.classList.add("hidden");
            _toast("success", `Run iniciado (flow=${flow}, id=${_activeRunId}) — aguardando WS events...`);
        } catch (e) {
            console.error("[HermesLabCockpit] startRun failed", e);
            _toast("error", `Falha ao iniciar run: ${e.message || e}`);
        } finally {
            if (_runBtnEl) _runBtnEl.disabled = false;
        }
    }

    function _openAbortConfirm() {
        if (!_activeRunId) {
            _toast("warn", "Nenhum run ativo pra abortar");
            return;
        }
        if (_abortConfirmOverlay) {
            _abortConfirmOverlay.hidden = false;
            _abortConfirmBtn.disabled = true;
            _abortConfirmBtn.setAttribute("aria-disabled", "true");
            _abortConfirmBtn.classList.add("lab-confirm-pending");
            setTimeout(() => { if (_abortCancelBtn) _abortCancelBtn.focus(); }, 0);
            if (_abortEnableTimer) clearTimeout(_abortEnableTimer);
            _abortEnableTimer = setTimeout(() => {
                if (!_abortConfirmBtn) return;
                _abortConfirmBtn.disabled = false;
                _abortConfirmBtn.setAttribute("aria-disabled", "false");
                _abortConfirmBtn.classList.remove("lab-confirm-pending");
            }, 2000);
            return;
        }
        // Build modal
        const overlay = document.createElement("div");
        overlay.className = "lab-confirm-overlay";
        overlay.addEventListener("click", (e) => { if (e.target === overlay) _closeAbortConfirm(); });

        const modal = document.createElement("div");
        modal.className = "lab-confirm-modal";
        modal.setAttribute("role", "alertdialog");
        modal.setAttribute("aria-modal", "true");
        modal.setAttribute("aria-labelledby", "lab-abort-title");
        modal.setAttribute("aria-describedby", "lab-abort-desc");
        modal.tabIndex = -1;

        const title = document.createElement("h2");
        title.id = "lab-abort-title";
        title.className = "lab-confirm-title";
        title.textContent = "Abortar run em andamento?";

        const desc = document.createElement("p");
        desc.id = "lab-abort-desc";
        desc.className = "lab-confirm-desc";
        desc.textContent = `Run #${_activeRunId} (flow=${_activeFlow || "?"}) será cancelado. Screenshots já capturados ficam preservados.`;

        const actions = document.createElement("div");
        actions.className = "lab-confirm-actions";
        const cancel = document.createElement("button");
        cancel.type = "button";
        cancel.className = "lab-confirm-cancel";
        cancel.textContent = "Cancelar";
        cancel.addEventListener("click", _closeAbortConfirm);

        const confirm = document.createElement("button");
        confirm.type = "button";
        confirm.className = "lab-confirm-confirm";
        confirm.textContent = "Confirmar abort";
        confirm.disabled = true;
        confirm.setAttribute("aria-disabled", "true");
        confirm.classList.add("lab-confirm-pending");
        confirm.addEventListener("click", _onAbortConfirm);

        actions.appendChild(cancel);
        actions.appendChild(confirm);
        modal.appendChild(title);
        modal.appendChild(desc);
        modal.appendChild(actions);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        _abortConfirmOverlay = overlay;
        _abortConfirmBtn = confirm;
        _abortCancelBtn = cancel;

        _previousFocus = document.activeElement;
        document.addEventListener("keydown", _onAbortKeyDown);
        setTimeout(() => cancel.focus(), 0);

        if (_abortEnableTimer) clearTimeout(_abortEnableTimer);
        _abortEnableTimer = setTimeout(() => {
            if (!_abortConfirmBtn) return;
            _abortConfirmBtn.disabled = false;
            _abortConfirmBtn.setAttribute("aria-disabled", "false");
            _abortConfirmBtn.classList.remove("lab-confirm-pending");
        }, 2000);
    }

    function _onAbortKeyDown(e) {
        if (!_abortConfirmOverlay || _abortConfirmOverlay.hidden) return;
        if (e.key === "Escape") {
            e.preventDefault();
            _closeAbortConfirm();
            return;
        }
        if (e.key === "Tab") {
            const focusables = [_abortCancelBtn, _abortConfirmBtn].filter((el) => el && !el.disabled);
            if (focusables.length === 0) return;
            const idx = focusables.indexOf(document.activeElement);
            const next = e.shiftKey
                ? (idx <= 0 ? focusables[focusables.length - 1] : focusables[idx - 1])
                : (idx === -1 || idx === focusables.length - 1 ? focusables[0] : focusables[idx + 1]);
            e.preventDefault();
            next.focus();
        }
    }

    function _closeAbortConfirm() {
        if (_abortConfirmOverlay) _abortConfirmOverlay.hidden = true;
        if (_abortEnableTimer) { clearTimeout(_abortEnableTimer); _abortEnableTimer = null; }
        document.removeEventListener("keydown", _onAbortKeyDown);
        if (_previousFocus && typeof _previousFocus.focus === "function") {
            try { _previousFocus.focus(); } catch { /* noop */ }
        }
    }

    async function _onAbortConfirm() {
        if (!_abortConfirmBtn || _abortConfirmBtn.disabled) return;
        const runId = _activeRunId;
        _abortConfirmBtn.disabled = true;
        const originalText = _abortConfirmBtn.textContent;
        _abortConfirmBtn.textContent = "Abortando...";
        try {
            await _apiCall("POST", `/api/lab/runs/${encodeURIComponent(runId)}/abort`);
            _toast("warn", `Run #${runId} abort solicitado`);
            _closeAbortConfirm();
        } catch (e) {
            console.error("[HermesLabCockpit] abort failed", e);
            _toast("error", `Falha ao abortar: ${e.message || e}`);
        } finally {
            if (_abortConfirmBtn) {
                _abortConfirmBtn.disabled = false;
                _abortConfirmBtn.textContent = originalText;
            }
        }
    }

    function abortRun() { _openAbortConfirm(); }

    async function openRunDetails(runId) {
        if (!_drawerEl) return;
        _drawerEl.classList.remove("hidden");
        _drawerEl.setAttribute("aria-hidden", "false");
        _autoScrollPaused = true;
        try {
            const detail = await _apiCall("GET", `/api/lab/runs/${encodeURIComponent(runId)}`);
            _renderDrawer(detail || { run_id: runId });
        } catch (e) {
            console.error("[HermesLabCockpit] openRunDetails failed", e);
            _toast("error", `Falha ao carregar detalhes: ${e.message || e}`);
            // Render minimal stub
            const r = _runs.find((x) => String(x.run_id) === String(runId)) || { run_id: runId };
            _renderDrawer(r);
        }
    }

    function closeDrawer() {
        if (!_drawerEl) return;
        _drawerEl.classList.add("hidden");
        _drawerEl.setAttribute("aria-hidden", "true");
        _autoScrollPaused = false;
    }

    function _onRunClick() { startRun(); }
    function _onAbortClick() { abortRun(); }

    function _applyEventToRun(runId, patch) {
        if (!runId) return;
        const idx = _runs.findIndex((r) => String(r.run_id) === String(runId));
        if (idx === -1) {
            // New run not yet in list — prepend
            _runs.unshift(_safeMerge({ run_id: runId }, patch));
        } else {
            _runs[idx] = _safeMerge(_runs[idx], patch);
        }
    }

    function appendEvent(event) {
        if (!_initialized || !event) return;
        const t = String(event.type || "");
        const runId = event.run_id;

        switch (t) {
            case "lab.run_started":
                _activeRunId = runId;
                _activeFlow = event.flow || _activeFlow;
                _applyEventToRun(runId, {
                    flow: event.flow,
                    status: "running",
                    started_at: event.started_at || new Date().toISOString(),
                });
                if (!_autoScrollPaused) _renderHistoryList();
                if (_runBtnEl) _runBtnEl.classList.add("hidden");
                if (_abortBtnEl) _abortBtnEl.classList.remove("hidden");
                break;

            case "lab.step_progress":
                // Visual feedback: highlight active row (no full re-render — performance)
                if (_historyListEl) {
                    const row = _historyListEl.querySelector(`.lab-run-row[data-run-id="${CSS.escape(String(runId))}"]`);
                    if (row) row.classList.add("lab-run-row-progress");
                }
                break;

            case "lab.screenshot_captured":
                // Trigger drawer refresh ONLY if drawer is open on this run
                if (_drawerEl && !_drawerEl.classList.contains("hidden")) {
                    const openId = _drawerContentEl && _drawerContentEl.dataset.runId;
                    if (String(openId) === String(runId)) {
                        // Lazy refetch
                        openRunDetails(runId);
                    }
                }
                break;

            case "lab.compliance_score":
                if (window.HermesLabGauge && _gaugeEl) {
                    try { window.HermesLabGauge.update(_gaugeEl, Number(event.score) || 0); } catch (e) { console.warn("gauge update failed", e); }
                }
                _applyEventToRun(runId, { compliance_score: Number(event.score) });
                if (!_autoScrollPaused) _renderHistoryList();
                break;

            case "lab.fingerprint_dump":
                // Defer to refreshFingerprintDiff after run completes
                break;

            case "lab.run_completed":
                _applyEventToRun(runId, {
                    status: "success",
                    duration_ms: event.duration_ms,
                    completed_at: new Date().toISOString(),
                });
                _toast("success", `Run #${runId} completed em ${_formatDuration(event.duration_ms)}`);
                _resetActiveRun();
                if (!_autoScrollPaused) _renderHistoryList();
                _refreshFingerprintDiff();
                break;

            case "lab.run_failed":
                _applyEventToRun(runId, {
                    status: "failed",
                    duration_ms: event.duration_ms,
                    completed_at: new Date().toISOString(),
                });
                _toast("error", `Run #${runId} falhou: ${String(event.error || "erro").slice(0, 120)}`);
                _resetActiveRun();
                if (!_autoScrollPaused) _renderHistoryList();
                break;

            case "lab.run_aborted":
                _applyEventToRun(runId, {
                    status: "aborted",
                    duration_ms: event.duration_ms,
                    completed_at: new Date().toISOString(),
                });
                _toast("warn", `Run #${runId} abortado`);
                _resetActiveRun();
                if (!_autoScrollPaused) _renderHistoryList();
                break;
        }
    }

    function _resetActiveRun() {
        _activeRunId = null;
        _activeFlow = null;
        if (_runBtnEl) _runBtnEl.classList.remove("hidden");
        if (_abortBtnEl) _abortBtnEl.classList.add("hidden");
    }

    function init(targetSelector) {
        const host = (typeof targetSelector === "string")
            ? document.querySelector(targetSelector)
            : targetSelector;
        if (!host) {
            console.warn("[HermesLabCockpit] target não encontrado:", targetSelector);
            return false;
        }
        if (_initialized && _root === host) return true;
        if (_initialized) destroy();

        _root = host;
        while (_root.firstChild) _root.removeChild(_root.firstChild);
        _buildShell(_root);

        // Init sub-components
        if (window.HermesLabGauge && _gaugeEl) {
            try { window.HermesLabGauge.init(_gaugeEl); } catch (e) { console.warn("gauge init failed", e); }
        }
        if (window.HermesLabFingerprintDiff && _fpDiffEl) {
            try { window.HermesLabFingerprintDiff.init(_fpDiffEl); } catch (e) { console.warn("fp diff init failed", e); }
        }

        _initialized = true;
        refreshRuns();
        return true;
    }

    function destroy() {
        if (_abortEnableTimer) { clearTimeout(_abortEnableTimer); _abortEnableTimer = null; }
        if (_abortConfirmOverlay && _abortConfirmOverlay.parentNode) {
            _abortConfirmOverlay.parentNode.removeChild(_abortConfirmOverlay);
        }
        document.removeEventListener("keydown", _onAbortKeyDown);
        if (window.HermesLabGauge && _gaugeEl) {
            try { window.HermesLabGauge.destroy(_gaugeEl); } catch { /* noop */ }
        }
        if (window.HermesLabFingerprintDiff) {
            try { window.HermesLabFingerprintDiff.destroy(); } catch { /* noop */ }
        }
        if (_root) {
            _root.classList.remove("lab-cockpit-page");
            while (_root.firstChild) _root.removeChild(_root.firstChild);
        }
        _root = null;
        _historyListEl = _pageIndicatorEl = _prevBtnEl = _nextBtnEl = null;
        _flowSelectEl = _runBtnEl = _abortBtnEl = null;
        _drawerEl = _drawerContentEl = _gaugeEl = _fpDiffEl = null;
        _abortConfirmOverlay = _abortConfirmBtn = _abortCancelBtn = null;
        _runs = [];
        _currentPage = 1;
        _activeRunId = null;
        _activeFlow = null;
        _autoScrollPaused = false;
        _initialized = false;
    }

    window.HermesLabCockpit = {
        init, destroy, refreshRuns, startRun, abortRun, openRunDetails, closeDrawer, appendEvent,
    };
})();
