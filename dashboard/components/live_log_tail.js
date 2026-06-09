/* ============================================================
   Hermes Cloud Studio — LiveLogTail (F.2.5c)
   ============================================================
   API global: window.HermesLiveLogTail.{init, append, clear, exportCsv,
                                          toggle, destroy, _ringBuffer (debug)}.

   Consome WS events `daemon.log_event` + `daemon.decision` (canonical F.2.3).
   Ring buffer FIFO 200 entries cap. Virtual list render apenas
   VIRTUAL_WINDOW=20 nodes viewport visible (DocumentFragment batch).

   Features:
     - Auto-scroll bottom (latest entry visible)
     - Pause-on-hover (mouse enter → _paused=true; mouse leave → resume + catch up)
     - Filtros chips: log_level (info/warn/error/debug) + emitter (daemon/loops/api/scheduler)
       Multi-select AND combine. Default ALL on.
     - Click entry → expand JSON payload inline (textContent JSON.stringify)
     - Botão "Limpar" → drain buffer + clear DOM
     - Botão "Exportar CSV" → download .csv com ISO timestamp safe (filename Windows-safe)
     - Toggle collapse via chevron header — persist via getUserPref/setUserPref
       'live_log_tail_collapsed' (default expanded=false)
     - Empty state UX (sem logs) → skeleton + placeholder "Aguardando eventos..."

   XSS hygiene: textContent para todo content runtime. innerHTML APENAS literal
     template no _buildShell. JSON payload sempre textContent JSON.stringify.

   Reuses:
     - window.hermesUtils.safeMerge (F.2.5b Step 0) — merge defensivo WS parcial
     - window.getUserPref/setUserPref (F.2.5b app.js) — persist collapse state
   ============================================================ */
(function () {
    "use strict";

    const MAX_ENTRIES = 200;
    const VIRTUAL_WINDOW = 20;
    const LEVELS = ["info", "warn", "error", "debug"];
    const EMITTERS = ["daemon", "loops", "api", "scheduler"];

    let _root = null;
    let _list = null;
    let _body = null;
    let _empty = null;
    let _counterEl = null;
    let _section = null;
    let _ringBuffer = [];
    let _filters = {
        levels: new Set(LEVELS),
        emitters: new Set(EMITTERS),
    };
    let _paused = false;
    let _initialized = false;
    let _expandedPayloadIds = new Set();
    let _nextEntryId = 1;

    function _safeMerge(target, update) {
        if (window.hermesUtils && typeof window.hermesUtils.safeMerge === "function") {
            return window.hermesUtils.safeMerge(target, update);
        }
        return Object.assign({}, target || {}, update || {});
    }

    function _getPref(key, fallback) {
        if (typeof window.getUserPref === "function") {
            try { return window.getUserPref(key, fallback); } catch { return fallback; }
        }
        return fallback;
    }

    function _setPref(key, value) {
        if (typeof window.setUserPref === "function") {
            try { window.setUserPref(key, value); } catch { /* noop */ }
        }
    }

    function _formatTs(ts) {
        try {
            const d = new Date(ts);
            const hh = String(d.getHours()).padStart(2, "0");
            const mm = String(d.getMinutes()).padStart(2, "0");
            const ss = String(d.getSeconds()).padStart(2, "0");
            return `${hh}:${mm}:${ss}`;
        } catch {
            return "--:--:--";
        }
    }

    function _safeFilenameTimestamp() {
        // ISO 2026-06-08T15:42:13 → 2026-06-08T15-42-13 (Windows-safe: sem : / \ * ? " < > |)
        const iso = new Date().toISOString().slice(0, 19);
        return iso.replace(/[:/\\*?"<>|]/g, "-");
    }

    function _buildShell() {
        const section = document.createElement("section");
        section.className = "live-log-tail";
        section.dataset.component = "live-log-tail-section";
        const startCollapsed = _getPref("live_log_tail_collapsed", false) === true;
        section.dataset.collapsed = startCollapsed ? "true" : "false";

        // innerHTML APENAS literal template — sem interpolação runtime.
        section.innerHTML = `
            <header class="live-log-header">
                <button type="button" class="live-log-toggle" aria-label="Colapsar Live Log" aria-expanded="${startCollapsed ? "false" : "true"}">
                    <span class="chevron" aria-hidden="true">▼</span>
                    <span class="live-log-title">Live Log</span>
                    <span class="live-log-count" aria-live="polite" aria-atomic="true">0</span>
                </button>
                <div class="live-log-filters">
                    <div class="live-log-filter-group" role="group" aria-label="Filtro por nível">
                        <button type="button" class="filter-chip active" data-filter-kind="level" data-filter-value="info" aria-pressed="true">info</button>
                        <button type="button" class="filter-chip active" data-filter-kind="level" data-filter-value="warn" aria-pressed="true">warn</button>
                        <button type="button" class="filter-chip active" data-filter-kind="level" data-filter-value="error" aria-pressed="true">error</button>
                        <button type="button" class="filter-chip active" data-filter-kind="level" data-filter-value="debug" aria-pressed="true">debug</button>
                    </div>
                    <div class="live-log-filter-group" role="group" aria-label="Filtro por emitter">
                        <button type="button" class="filter-chip active" data-filter-kind="emitter" data-filter-value="daemon" aria-pressed="true">daemon</button>
                        <button type="button" class="filter-chip active" data-filter-kind="emitter" data-filter-value="loops" aria-pressed="true">loops</button>
                        <button type="button" class="filter-chip active" data-filter-kind="emitter" data-filter-value="api" aria-pressed="true">api</button>
                        <button type="button" class="filter-chip active" data-filter-kind="emitter" data-filter-value="scheduler" aria-pressed="true">scheduler</button>
                    </div>
                </div>
                <div class="live-log-actions">
                    <button type="button" class="live-log-clear" aria-label="Limpar logs">Limpar</button>
                    <button type="button" class="live-log-export" aria-label="Exportar CSV">Exportar</button>
                </div>
            </header>
            <div class="live-log-body" role="log" aria-live="polite" aria-atomic="false" aria-relevant="additions">
                <ul class="live-log-list"></ul>
                <div class="live-log-empty">
                    <div class="hermes-skeleton-block"></div>
                    <p>Aguardando eventos do daemon...</p>
                </div>
            </div>
        `;
        return section;
    }

    function _bindEvents() {
        const toggleBtn = _section.querySelector(".live-log-toggle");
        if (toggleBtn) toggleBtn.addEventListener("click", _toggle);

        // Filter chips — event delegation
        _section.querySelectorAll(".live-log-filters").forEach((group) => {
            group.addEventListener("click", _onFilterClick);
            group.addEventListener("keydown", _onFilterKey);
        });

        const clearBtn = _section.querySelector(".live-log-clear");
        if (clearBtn) clearBtn.addEventListener("click", _onClearClick);

        const exportBtn = _section.querySelector(".live-log-export");
        if (exportBtn) exportBtn.addEventListener("click", _onExportClick);

        // Pause-on-hover
        if (_body) {
            _body.addEventListener("mouseenter", _onBodyEnter);
            _body.addEventListener("mouseleave", _onBodyLeave);
        }
    }

    function _onFilterClick(e) {
        const chip = e.target.closest(".filter-chip");
        if (!chip) return;
        _toggleFilter(chip);
    }

    function _onFilterKey(e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        const chip = e.target.closest(".filter-chip");
        if (!chip) return;
        e.preventDefault();
        _toggleFilter(chip);
    }

    function _toggleFilter(chip) {
        const kind = chip.dataset.filterKind;
        const value = chip.dataset.filterValue;
        if (!kind || !value) return;
        const set = kind === "level" ? _filters.levels : _filters.emitters;
        if (set.has(value)) {
            set.delete(value);
            chip.classList.remove("active");
            chip.setAttribute("aria-pressed", "false");
        } else {
            set.add(value);
            chip.classList.add("active");
            chip.setAttribute("aria-pressed", "true");
        }
        _renderVisible();
    }

    function _onClearClick() {
        clear();
    }

    function _onExportClick() {
        try {
            exportCsv();
        } catch (e) {
            console.error("LiveLogTail exportCsv failed", e);
            if (window.hermesToast && typeof window.hermesToast.error === "function") {
                window.hermesToast.error("Falha ao exportar CSV");
            }
        }
    }

    function _onBodyEnter() {
        _paused = true;
    }

    function _onBodyLeave() {
        _paused = false;
        _renderVisible();
    }

    function _toggle() {
        if (!_section) return;
        const collapsed = _section.dataset.collapsed === "true";
        const next = !collapsed;
        _section.dataset.collapsed = next ? "true" : "false";
        const toggleBtn = _section.querySelector(".live-log-toggle");
        if (toggleBtn) toggleBtn.setAttribute("aria-expanded", next ? "false" : "true");
        _setPref("live_log_tail_collapsed", next);
    }

    function _updateCounter(visibleCount) {
        if (_counterEl) _counterEl.textContent = String(visibleCount);
    }

    function _updateEmpty(visibleCount) {
        if (!_empty || !_list) return;
        const empty = visibleCount === 0;
        _empty.hidden = !empty;
        _list.hidden = empty;
    }

    function _renderVisible() {
        if (!_list) return;
        const filtered = _ringBuffer.filter((entry) =>
            _filters.levels.has(entry.level) && _filters.emitters.has(entry.emitter)
        );
        const visible = filtered.slice(-VIRTUAL_WINDOW);

        const fragment = document.createDocumentFragment();
        visible.forEach((entry) => {
            const li = document.createElement("li");
            li.className = `log-entry log-entry-${entry.level}`;
            li.dataset.emitter = entry.emitter;
            li.dataset.entryId = String(entry._id);

            const ts = document.createElement("span");
            ts.className = "log-ts";
            ts.textContent = _formatTs(entry.ts);

            const emitter = document.createElement("span");
            emitter.className = "log-emitter";
            emitter.textContent = entry.emitter;

            const msg = document.createElement("span");
            msg.className = "log-msg";
            msg.textContent = entry.message || "";

            li.appendChild(ts);
            li.appendChild(emitter);
            li.appendChild(msg);

            if (entry.payload) {
                li.classList.add("has-payload");
                li.setAttribute("role", "button");
                li.setAttribute("tabindex", "0");
                li.setAttribute("aria-label", `Expandir payload do log ${entry.message || ""}`);
                li.addEventListener("click", () => _togglePayload(li, entry));
                li.addEventListener("keydown", (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        _togglePayload(li, entry);
                    }
                });
                if (_expandedPayloadIds.has(entry._id)) {
                    _appendPayloadDetail(li, entry.payload);
                }
            }
            fragment.appendChild(li);
        });

        _list.replaceChildren(fragment);

        if (!_paused && _body) {
            _body.scrollTop = _body.scrollHeight;
        }

        _updateCounter(filtered.length);
        _updateEmpty(filtered.length);
    }

    function _togglePayload(li, entry) {
        const existing = li.querySelector(".log-payload");
        if (existing) {
            existing.remove();
            _expandedPayloadIds.delete(entry._id);
            return;
        }
        _appendPayloadDetail(li, entry.payload);
        _expandedPayloadIds.add(entry._id);
    }

    function _appendPayloadDetail(li, payload) {
        const detail = document.createElement("pre");
        detail.className = "log-payload";
        try {
            detail.textContent = JSON.stringify(payload, null, 2);
        } catch {
            detail.textContent = String(payload);
        }
        li.appendChild(detail);
    }

    // ============================================================
    // PUBLIC API
    // ============================================================

    function init(rootSelector) {
        if (_initialized) return;
        const sel = rootSelector || '[data-component="live-log-tail"]';
        _root = typeof rootSelector === "string" || rootSelector === undefined
            ? document.querySelector(sel)
            : rootSelector;
        if (!_root) {
            console.warn("LiveLogTail.init: root not found", sel);
            return;
        }
        _section = _buildShell();
        _root.appendChild(_section);

        _list = _section.querySelector(".live-log-list");
        _body = _section.querySelector(".live-log-body");
        _empty = _section.querySelector(".live-log-empty");
        _counterEl = _section.querySelector(".live-log-count");

        _bindEvents();
        _updateEmpty(0);
        _initialized = true;
    }

    function append(event) {
        if (!event) return;
        const normalized = _safeMerge(
            {
                ts: Date.now(),
                level: "info",
                emitter: "unknown",
                event_type: "log",
                message: "",
                payload: null,
            },
            event
        );
        if (!LEVELS.includes(normalized.level)) normalized.level = "info";
        if (typeof normalized.emitter !== "string" || !normalized.emitter) {
            normalized.emitter = "unknown";
        }
        if (typeof normalized.message !== "string") {
            normalized.message = String(normalized.message || "");
        }
        normalized._id = _nextEntryId++;

        _ringBuffer.push(normalized);
        if (_ringBuffer.length > MAX_ENTRIES) {
            const dropped = _ringBuffer.shift();
            if (dropped && dropped._id != null) _expandedPayloadIds.delete(dropped._id);
        }

        if (!_initialized) return;
        if (!_paused) _renderVisible();
    }

    function clear() {
        _ringBuffer = [];
        _expandedPayloadIds.clear();
        if (_list) _list.replaceChildren();
        _updateCounter(0);
        _updateEmpty(0);
    }

    function exportCsv() {
        const headers = ["timestamp", "level", "emitter", "event_type", "message", "payload_json"];
        const escape = (v) => {
            const s = String(v == null ? "" : v).replace(/"/g, '""');
            return `"${s}"`;
        };
        const rows = _ringBuffer.map((e) => [
            escape(new Date(e.ts).toISOString()),
            escape(e.level),
            escape(e.emitter),
            escape(e.event_type),
            escape(e.message),
            escape(e.payload ? JSON.stringify(e.payload) : ""),
        ].join(","));
        const csv = [headers.map(escape).join(","), ...rows].join("\n");
        const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `hermes-logs-${_safeFilenameTimestamp()}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    function toggle() {
        _toggle();
    }

    function destroy() {
        if (!_initialized) return;
        if (_body) {
            _body.removeEventListener("mouseenter", _onBodyEnter);
            _body.removeEventListener("mouseleave", _onBodyLeave);
        }
        if (_section && _section.parentNode) _section.parentNode.removeChild(_section);
        _section = null;
        _root = null;
        _list = null;
        _body = null;
        _empty = null;
        _counterEl = null;
        _ringBuffer = [];
        _expandedPayloadIds = new Set();
        _filters = { levels: new Set(LEVELS), emitters: new Set(EMITTERS) };
        _initialized = false;
    }

    window.HermesLiveLogTail = {
        init,
        append,
        clear,
        exportCsv,
        toggle,
        destroy,
        get _ringBuffer() { return _ringBuffer.slice(); },
        get _initialized() { return _initialized; },
    };
})();
