/* ============================================================
   Pipeline Studio Shell (F.9.3a — Commit 1)
   ============================================================
   4 sub-tabs nav + 60s auto-refresh + visibilitychange pause.

   API pública: window.PipelineStudioShell.{init, destroy, switchTab,
                                             getActiveTab}

   Padrão IIFE reusado de observability_shell.js (F.8.3).

   ARIA: role=tablist + role=tab + aria-selected + aria-controls.
   Keyboard: Tab entre tabs, Enter/Space ativa, Esc escapes modal.

   Memory leak prevention:
   - clearInterval em switchTab + destroy + visibilitychange hidden
   - Chama subcomponent.destroy() ANTES de trocar tab
   ============================================================ */
(function () {
    "use strict";

    var REFRESH_INTERVAL_MS = 60000;

    /* Mapeamento tab-key → window.PipelineStudio<Name> component */
    var TAB_KEYS = ["builder", "templates", "runs-monitor", "ab-compare"];
    var TAB_TO_COMPONENT = {
        "builder":       "PipelineStudioBuilder",
        "templates":     "PipelineStudioTemplates",
        "runs-monitor":  "PipelineStudioRunsMonitor",
        "ab-compare":    "PipelineStudioAbCompare",
    };

    var _state = {
        initialized: false,
        active: "builder",
        refreshTimer: null,
        root: null,
    };

    /* ---- helpers ---------------------------------------- */

    function _$(sel) {
        return _state.root ? _state.root.querySelector(sel) : document.querySelector(sel);
    }

    function _setText(el, text) {
        if (el) el.textContent = (text == null) ? "" : String(text);
    }

    function _callComponent(tabKey, method) {
        var compName = TAB_TO_COMPONENT[tabKey];
        if (!compName) return;
        var comp = window[compName];
        if (!comp || typeof comp[method] !== "function") return;
        try { comp[method](); }
        catch (e) { console.warn("[PipelineStudioShell] " + compName + "." + method + " failed", e); }
    }

    function _stampLastRefresh() {
        var el = _$("#ps-last-refresh");
        if (!el) return;
        var now = new Date();
        var hh = String(now.getHours()).padStart(2, "0");
        var mm = String(now.getMinutes()).padStart(2, "0");
        var ss = String(now.getSeconds()).padStart(2, "0");
        _setText(el, "Atualizado " + hh + ":" + mm + ":" + ss);
    }

    /* ---- Auto-refresh ----------------------------------- */

    function _startAutoRefresh() {
        _stopAutoRefresh();
        _state.refreshTimer = setInterval(function () {
            /* Builder tab: NÃO auto-refresh (D7 — owner edita, sem sobrescrever) */
            if (document.visibilityState === "visible" && _state.active !== "builder") {
                _callComponent(_state.active, "render");
                _stampLastRefresh();
            }
        }, REFRESH_INTERVAL_MS);
    }

    function _stopAutoRefresh() {
        if (_state.refreshTimer) {
            clearInterval(_state.refreshTimer);
            _state.refreshTimer = null;
        }
    }

    /* ---- Tab switch ------------------------------------- */

    function switchTab(tabKey, options) {
        if (!TAB_TO_COMPONENT[tabKey]) return;

        /* Destroy previous sub-component (memory leak prevention) */
        _callComponent(_state.active, "destroy");

        _state.active = tabKey;

        /* Update ARIA + visual on tab buttons */
        TAB_KEYS.forEach(function (k) {
            var btn = _$("#ps-tab-btn-" + k);
            if (!btn) return;
            var isActive = (k === tabKey);
            btn.setAttribute("aria-selected", isActive ? "true" : "false");
            btn.setAttribute("tabindex", isActive ? "0" : "-1");
            if (isActive) btn.classList.add("active");
            else btn.classList.remove("active");
        });

        /* Toggle panels */
        TAB_KEYS.forEach(function (k) {
            var panel = _$("#ps-panel-" + k);
            if (!panel) return;
            if (k === tabKey) panel.removeAttribute("hidden");
            else panel.setAttribute("hidden", "");
        });

        /* Init + render new sub-component */
        _callComponent(tabKey, "init");
        _callComponent(tabKey, "render");

        /* F.9.4 D2: clone redirect — load draft in Builder after DOM ready */
        if (tabKey === "builder" && options && options.draft_id) {
            var draftId = options.draft_id;
            setTimeout(function () {
                var comp = window["PipelineStudioBuilder"];
                if (comp && typeof comp.loadDraft === "function") {
                    comp.loadDraft(draftId);
                }
            }, 50);
        }

        /* Restart auto-refresh (builder skips, handled inside timer) */
        _startAutoRefresh();
    }

    /* ---- Keyboard nav for tab row ----------------------- */

    function _handleTabKeydown(e) {
        var tabBtns = Array.from(document.querySelectorAll(".ps-tab-btn"));
        if (!tabBtns.length) return;
        var idx = tabBtns.indexOf(e.target);
        if (idx === -1) return;

        var next = -1;
        if (e.key === "ArrowRight") next = (idx + 1) % tabBtns.length;
        if (e.key === "ArrowLeft")  next = (idx - 1 + tabBtns.length) % tabBtns.length;
        if (e.key === "Home")       next = 0;
        if (e.key === "End")        next = tabBtns.length - 1;

        if (next !== -1) {
            e.preventDefault();
            tabBtns[next].focus();
            var key = tabBtns[next].dataset.tab;
            if (key) switchTab(key);
        }
    }

    /* ---- visibilitychange ------------------------------- */

    function _onVisibilityChange() {
        if (document.visibilityState === "visible") {
            _startAutoRefresh();
        } else {
            _stopAutoRefresh();
        }
    }

    /* ---- Init ------------------------------------------- */

    function init(rootSelector) {
        if (_state.initialized) {
            /* Re-entry: refresh active tab */
            _callComponent(_state.active, "render");
            return;
        }

        var root = document.querySelector(rootSelector || "[data-component='pipeline-studio-shell']");
        _state.root = root;
        _state.initialized = true;

        /* Wire tab button clicks */
        TAB_KEYS.forEach(function (k) {
            var btn = _$("#ps-tab-btn-" + k);
            if (!btn) return;
            btn.addEventListener("click", function () { switchTab(k); });
        });

        /* Keyboard roving tabindex */
        var tabNav = _$(".ps-tabnav");
        if (tabNav) tabNav.addEventListener("keydown", _handleTabKeydown);

        /* visibilitychange */
        document.addEventListener("visibilitychange", _onVisibilityChange);

        /* Show initial tab (builder) */
        switchTab("builder");
    }

    /* ---- Destroy ---------------------------------------- */

    function destroy() {
        _stopAutoRefresh();
        _callComponent(_state.active, "destroy");
        document.removeEventListener("visibilitychange", _onVisibilityChange);
        _state.initialized = false;
        _state.root = null;
    }

    /* ---- Public API ------------------------------------- */

    window.PipelineStudioShell = {
        init:        init,
        destroy:     destroy,
        switchTab:   switchTab,
        getActiveTab: function () { return _state.active; },
    };

})();
