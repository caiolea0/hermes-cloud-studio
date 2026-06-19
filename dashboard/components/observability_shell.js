/* ============================================================
   Hermes Cloud Studio — ObservabilityShell (F.8.3)
   ============================================================
   Tabs nav + auto-refresh 60s + visibilitychange pause.

   Decisões F.8.3 (cristalizadas commit 1256550):
   D1 tabs HORIZONTAL TOP (Costs/Performance/Errors/Decisions)
   D3 60s auto-refresh + manual button + visibilitychange API
   D7 mobile F.future (desktop only)

   API global: window.ObservabilityShell.{init, switchTab, refresh,
                                          getActiveTab, destroy}

   Pattern reference:
   - mcp_gateway.js F.5.6 (IIFE + clearInterval + auth headers)
   - brain_confirm_drawer.js F.6.4 (Esc handler + lastFocus)

   XSS: textContent para campos dinâmicos (timestamp). Tabs/panels
   são static markup index.html — JS só toggles 'active'/'hidden'.

   Memory leak prevention:
   - clearInterval em switchTab + destroy + visibilitychange hidden
   - Chama component.destroy() (chart.destroy()) ANTES de switch
   ============================================================ */
(function () {
    "use strict";

    var REFRESH_INTERVAL_MS = 60000;
    var TAB_KEYS = ["costs", "perf", "errors", "decisions", "mcp-coverage", "a11y"];
    var TAB_TO_COMPONENT = {
        costs: "ObservabilityCosts",
        perf: "ObservabilityPerf",
        errors: "ObservabilityErrors",
        decisions: "ObservabilityDecisions",
        "mcp-coverage": "ObservabilityMcpCoverage",
        "a11y": "ObservabilityA11y",
    };

    var state = {
        initialized: false,
        active: "costs",
        refreshTimer: null,
        root: null,
    };

    function _$(sel) {
        return state.root ? state.root.querySelector(sel) : null;
    }

    function _setText(el, text) {
        if (el) el.textContent = text == null ? "" : String(text);
    }

    function _callComponent(tab, method) {
        var name = TAB_TO_COMPONENT[tab];
        if (!name) return;
        var comp = window[name];
        if (!comp || typeof comp[method] !== "function") return;
        try { comp[method](); }
        catch (e) { console.warn("[ObservabilityShell] " + name + "." + method + " failed", e); }
    }

    function _stampLastRefresh() {
        var el = _$("#observability-last-refresh");
        if (!el) return;
        var now = new Date();
        var hh = String(now.getHours()).padStart(2, "0");
        var mm = String(now.getMinutes()).padStart(2, "0");
        var ss = String(now.getSeconds()).padStart(2, "0");
        _setText(el, "Atualizado " + hh + ":" + mm + ":" + ss);
    }

    function _startAutoRefresh() {
        _stopAutoRefresh();
        state.refreshTimer = setInterval(function () {
            if (document.visibilityState === "visible") {
                _callComponent(state.active, "render");
                _stampLastRefresh();
            }
        }, REFRESH_INTERVAL_MS);
    }

    function _stopAutoRefresh() {
        if (state.refreshTimer) {
            clearInterval(state.refreshTimer);
            state.refreshTimer = null;
        }
    }

    function switchTab(tab) {
        if (!TAB_KEYS.indexOf || TAB_KEYS.indexOf(tab) === -1) return;
        if (tab === state.active && state.initialized) {
            // re-entry on same tab → just refresh
            _callComponent(tab, "render");
            _stampLastRefresh();
            return;
        }
        // Cleanup previous tab (chart.destroy + clearInterval)
        _callComponent(state.active, "destroy");

        state.active = tab;

        // Toggle tab buttons + panels
        var btns = state.root ? state.root.querySelectorAll(".observability-tab-btn") : [];
        for (var i = 0; i < btns.length; i++) {
            var b = btns[i];
            var isActive = b.dataset && b.dataset.tab === tab;
            b.classList.toggle("active", isActive);
            b.setAttribute("aria-selected", isActive ? "true" : "false");
            b.tabIndex = isActive ? 0 : -1;
        }
        var panels = state.root ? state.root.querySelectorAll(".observability-panel") : [];
        for (var j = 0; j < panels.length; j++) {
            var p = panels[j];
            var match = p.dataset && p.dataset.tab === tab;
            p.hidden = !match;
        }

        _callComponent(tab, "render");
        _stampLastRefresh();
    }

    function refresh() {
        _callComponent(state.active, "render");
        _stampLastRefresh();
    }

    function getActiveTab() {
        return state.active;
    }

    function _onVisibilityChange() {
        if (document.visibilityState === "visible") {
            // Aba voltou ativa — refresh imediato + reinicia timer
            refresh();
            _startAutoRefresh();
        } else {
            _stopAutoRefresh();
        }
    }

    function _onTabClick(e) {
        var btn = e.target.closest ? e.target.closest(".observability-tab-btn") : null;
        if (!btn || !btn.dataset || !btn.dataset.tab) return;
        switchTab(btn.dataset.tab);
    }

    function _onTabKeydown(e) {
        // Keyboard nav: ArrowLeft/Right cycle tabs (WAI-ARIA tablist).
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        var idx = TAB_KEYS.indexOf(state.active);
        if (idx === -1) return;
        var next = e.key === "ArrowRight"
            ? TAB_KEYS[(idx + 1) % TAB_KEYS.length]
            : TAB_KEYS[(idx - 1 + TAB_KEYS.length) % TAB_KEYS.length];
        switchTab(next);
        var btn = state.root ? state.root.querySelector('.observability-tab-btn[data-tab="' + next + '"]') : null;
        if (btn) btn.focus();
    }

    function _wireDOM() {
        if (!state.root) return;
        var nav = state.root.querySelector(".observability-tabnav");
        if (nav && !nav.dataset.wired) {
            nav.dataset.wired = "1";
            nav.addEventListener("click", _onTabClick);
            nav.addEventListener("keydown", _onTabKeydown);
        }
        var btn = state.root.querySelector("#observability-refresh-btn");
        if (btn && !btn.dataset.wired) {
            btn.dataset.wired = "1";
            btn.addEventListener("click", function () { refresh(); });
        }
        document.addEventListener("visibilitychange", _onVisibilityChange);
    }

    function init(selector) {
        var root = typeof selector === "string"
            ? document.querySelector(selector)
            : selector;
        if (!root) {
            console.warn("[ObservabilityShell] root selector not found:", selector);
            return;
        }
        state.root = root;
        if (state.initialized) {
            // re-entry on navigate('observability') — just refresh active tab
            refresh();
            _startAutoRefresh();
            return;
        }
        state.initialized = true;
        _wireDOM();
        // Initial render = active tab (D1 default = costs)
        switchTab(state.active);
        _startAutoRefresh();
    }

    function destroy() {
        _stopAutoRefresh();
        document.removeEventListener("visibilitychange", _onVisibilityChange);
        // Destroy active component (chart cleanup)
        _callComponent(state.active, "destroy");
        state.initialized = false;
        state.root = null;
    }

    window.ObservabilityShell = {
        init: init,
        switchTab: switchTab,
        refresh: refresh,
        getActiveTab: getActiveTab,
        destroy: destroy,
        _state: state,
    };
})();
