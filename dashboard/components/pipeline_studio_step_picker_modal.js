/* ============================================================
   Pipeline Studio — Step Picker Modal (F.9.3b REAL)
   ============================================================
   Live fetch /api/pipeline-studio/steps + 60s sessionStorage
   cache (D2). 3 filtros combinables AND intersect (D6).
   Esc fecha. ARIA role=dialog + aria-modal + focus trap.
   Refresh manual invalida cache.

   API: window.PipelineStudioStepPickerModal.{open, close}

   XSS: textContent em todos os campos dinâmicos.
   Cache: sessionStorage 'pipeline_studio_steps_v1' TTL 60s.
   Z-index: 1100 (alinha F.8.3, acima F.6.4 drawer 950).
   ============================================================ */
(function () {
    "use strict";

    var CACHE_KEY    = "pipeline_studio_steps_v1";
    var CACHE_TTL_MS = 60000;

    var _onSelectCallback = null;
    var _allSteps         = [];
    var _loading          = false;
    var _firstFocusEl     = null;

    /* ---- DOM helpers ------------------------------------ */

    function _id(id)  { return document.getElementById(id); }
    function _qs(sel) { return document.querySelector(sel); }

    function _setText(el, text) {
        if (el) el.textContent = (text == null) ? "" : String(text);
    }

    /* ---- Cache ------------------------------------------ */

    function _cacheGet() {
        try {
            var raw = sessionStorage.getItem(CACHE_KEY);
            if (!raw) return null;
            var parsed = JSON.parse(raw);
            if ((Date.now() - parsed.timestamp) < CACHE_TTL_MS) return parsed.data;
        } catch (e) {}
        return null;
    }

    function _cacheSet(data) {
        try {
            sessionStorage.setItem(CACHE_KEY, JSON.stringify({
                data: data,
                timestamp: Date.now()
            }));
        } catch (e) {}
    }

    function _cacheInvalidate() {
        try { sessionStorage.removeItem(CACHE_KEY); } catch (e) {}
    }

    /* ---- Fetch steps ------------------------------------ */

    async function _fetchSteps(forceRefresh) {
        if (!forceRefresh) {
            var cached = _cacheGet();
            if (cached) return cached;
        }
        var token = localStorage.getItem("hermes_token") || "";
        var resp = await fetch("/api/pipeline-studio/steps", {
            headers: { "X-Hermes-Token": token }
        });
        if (!resp.ok) throw new Error("steps fetch " + resp.status);
        var data = await resp.json();
        _cacheSet(data);
        return data;
    }

    /* ---- Filter logic (D6: 3 filters AND intersect) ----- */

    function _applyFilters() {
        var chapterEl = _id("ps-filter-chapter");
        var tierEl    = _id("ps-filter-tier");
        var searchEl  = _id("ps-filter-search");
        var chapter   = chapterEl ? chapterEl.value : "";
        var tierVal   = tierEl ? tierEl.value : "";
        var search    = searchEl ? searchEl.value.toLowerCase().trim() : "";
        var tiers     = tierVal ? tierVal.split(",") : [];

        var filtered = _allSteps.filter(function (s) {
            if (chapter && (s.chapter_owner || "") !== chapter) return false;
            if (tiers.length && tiers.indexOf(s.tier || "") === -1) return false;
            if (search) {
                var sid   = (s.id || "").toLowerCase();
                var stool = (s.tool_name || "").toLowerCase();
                var sdesc = (s.description || "").toLowerCase();
                if (sid.indexOf(search) === -1 &&
                    stool.indexOf(search) === -1 &&
                    sdesc.indexOf(search) === -1) return false;
            }
            return true;
        });

        _renderTools(filtered);

        var countEl = _id("ps-filter-count");
        if (countEl) {
            _setText(countEl, "mostrando " + filtered.length + " de " + _allSteps.length + " tools");
        }
    }

    /* ---- Populate chapter filter dropdown --------------- */

    function _populateChapterFilter() {
        var select = _id("ps-filter-chapter");
        if (!select) return;
        var chapters = [];
        _allSteps.forEach(function (s) {
            var c = s.chapter_owner || "";
            if (c && chapters.indexOf(c) === -1) chapters.push(c);
        });
        chapters.sort();
        select.innerHTML = "";
        var optAll = document.createElement("option");
        optAll.value = "";
        optAll.textContent = "Todos os chapters";
        select.appendChild(optAll);
        chapters.forEach(function (c) {
            var opt = document.createElement("option");
            opt.value = c;
            opt.textContent = c;
            select.appendChild(opt);
        });
    }

    /* ---- Render tools list ------------------------------ */

    function _renderTools(steps) {
        var list = _id("ps-tools-list");
        if (!list) return;

        /* Clear previous */
        list.innerHTML = "";

        if (!steps.length) {
            var empty = document.createElement("div");
            empty.className = "ps-tools-empty";
            empty.textContent = "Nenhum tool encontrado com estes filtros.";
            list.appendChild(empty);
            return;
        }

        steps.forEach(function (step) {
            var row = document.createElement("div");
            row.className = "ps-tool-row";
            row.setAttribute("role", "listitem");
            row.setAttribute("tabindex", "0");
            row.dataset.stepId = step.id || "";

            var idEl = document.createElement("span");
            idEl.className = "ps-tool-id";
            idEl.textContent = step.id || "unknown";
            idEl.title = step.description || step.id || "";

            var chapterEl = document.createElement("span");
            chapterEl.className = "ps-tool-chapter";
            chapterEl.textContent = step.chapter_owner || "—";

            var tierEl = document.createElement("span");
            var tier = (step.tier || "").toLowerCase();
            tierEl.className = "ps-tool-tier " + (tier || "");
            tierEl.textContent = tier || "—";

            row.appendChild(idEl);
            row.appendChild(chapterEl);
            row.appendChild(tierEl);

            row.addEventListener("click", function () { _selectStep(step); });
            row.addEventListener("keydown", function (e) {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    _selectStep(step);
                }
            });

            list.appendChild(row);
        });
    }

    /* ---- Select step ------------------------------------ */

    function _selectStep(step) {
        if (typeof _onSelectCallback === "function") {
            _onSelectCallback({
                id:        step.id || "",
                tool_name: step.tool_name || step.id || "",
                mcp_server: step.mcp_server || "",
                description: step.description || ""
            });
        }
        close();
    }

    /* ---- Keyboard: Esc + focus trap --------------------- */

    function _onKeydown(e) {
        if (e.key === "Escape") {
            e.preventDefault();
            close();
            return;
        }
        /* Focus trap inside modal panel */
        if (e.key === "Tab") {
            var modal = _id("ps-step-picker-modal");
            if (!modal || modal.hidden) return;
            var focusable = Array.from(modal.querySelectorAll(
                'button:not([disabled]), [tabindex="0"], input, select'
            ));
            if (!focusable.length) return;
            var first = focusable[0];
            var last  = focusable[focusable.length - 1];
            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
            }
        }
    }

    /* ---- Wire filter events ----------------------------- */

    function _wireFilterEvents() {
        var chapterEl = _id("ps-filter-chapter");
        var tierEl    = _id("ps-filter-tier");
        var searchEl  = _id("ps-filter-search");
        var resetBtn  = _id("ps-filter-reset-btn");
        var refreshBtn = _id("ps-modal-refresh-btn");
        var closeBtn   = _id("ps-modal-close-btn");
        var backdrop   = _id("ps-modal-backdrop");

        if (chapterEl) chapterEl.addEventListener("change", _applyFilters);
        if (tierEl)    tierEl.addEventListener("change", _applyFilters);
        if (searchEl)  searchEl.addEventListener("input", _applyFilters);

        if (resetBtn) {
            resetBtn.addEventListener("click", function () {
                if (chapterEl) chapterEl.value = "";
                if (tierEl)    tierEl.value = "active,warning";
                if (searchEl)  searchEl.value = "";
                _applyFilters();
            });
        }

        if (refreshBtn) {
            refreshBtn.addEventListener("click", async function () {
                _cacheInvalidate();
                _setLoadingState(true);
                try {
                    var data = await _fetchSteps(true);
                    _allSteps = (data && data.steps) ? data.steps : [];
                    _populateChapterFilter();
                    _applyFilters();
                } catch (e) {
                    console.warn("[StepPickerModal] refresh failed", e);
                } finally {
                    _setLoadingState(false);
                }
            });
        }

        if (closeBtn)  closeBtn.addEventListener("click", close);
        if (backdrop)  backdrop.addEventListener("click", close);
    }

    /* ---- Loading state ---------------------------------- */

    function _setLoadingState(loading) {
        _loading = loading;
        var list = _id("ps-tools-list");
        if (!list) return;
        if (loading) {
            list.innerHTML = '<div class="ps-tools-empty">Carregando tools...</div>';
        }
    }

    /* ---- Open ------------------------------------------- */

    async function open(onSelect) {
        _onSelectCallback = onSelect;

        var modal = _id("ps-step-picker-modal");
        if (!modal) return;

        modal.removeAttribute("hidden");
        document.addEventListener("keydown", _onKeydown);

        /* Focus first focusable element */
        var closeBtn = _id("ps-modal-close-btn");
        if (closeBtn) {
            _firstFocusEl = document.activeElement;
            closeBtn.focus();
        }

        _wireFilterEvents();
        _setLoadingState(true);

        try {
            var data = await _fetchSteps(false);
            _allSteps = (data && data.steps) ? data.steps : [];
            _populateChapterFilter();
            _applyFilters();
        } catch (e) {
            var list = _id("ps-tools-list");
            if (list) {
                list.innerHTML = '<div class="ps-tools-empty">Erro ao carregar tools. Clique ↻ para tentar novamente.</div>';
            }
            console.warn("[StepPickerModal] fetch failed", e);
        } finally {
            _setLoadingState(false);
        }
    }

    /* ---- Close ------------------------------------------ */

    function close() {
        var modal = _id("ps-step-picker-modal");
        if (!modal) return;
        modal.setAttribute("hidden", "");
        document.removeEventListener("keydown", _onKeydown);
        /* Restore focus to caller element */
        if (_firstFocusEl && typeof _firstFocusEl.focus === "function") {
            _firstFocusEl.focus();
        }
        _firstFocusEl = null;
    }

    /* ---- Public API ------------------------------------- */

    window.PipelineStudioStepPickerModal = {
        open:  open,
        close: close,
        invalidateCache: _cacheInvalidate,
    };

})();
