/* ============================================================
   Hermes Cloud Studio — PrefPanel (F.2.5b Step 3)
   ============================================================
   API global: window.HermesPrefPanel.{init, destroy, open, close, getCache}.
   Slide-in panel from right + backdrop overlay.
   Auto-save debounced 500ms (zero Save btn) → PUT /api/user-prefs delta.
   Status footer: "Salvo às HH:MM:SS" + spinner durante in-flight.
   ESC fecha + click overlay fecha (config já persistido).
   Botão ⚙ no header MC dispara open.

   Sections (5):
     1. Theme (light/dark/auto)
     2. Mission Control (refresh_rate 10/30/60s)
     3. Notifications (sound_notifications + badge_counter_unread_errors)
     4. Tile Order (drag + keyboard Alt+↑/↓ — WCAG accessible)
     5. Tile Visibility (6 toggles, ≥1 sempre visível)

   Storage embedded: {version, data} via runtime_state.user_prefs.
   Last-wins concurrency (frontend não envia version).

   XSS: textContent para labels + values. innerHTML apenas literal template.
   ============================================================ */
(function () {
    "use strict";

    const SUBSYSTEMS_DEFAULT = ["linkedin", "email", "scraper", "audit", "daemon", "tunnel"];
    const SUBSYSTEM_LABELS = {
        linkedin: "LinkedIn",
        email: "Email",
        scraper: "Scraper",
        audit: "Audit",
        daemon: "Daemon",
        tunnel: "Tunnel",
    };
    const DEBOUNCE_MS = 500;

    let _overlay = null;
    let _panel = null;
    let _statusEl = null;
    let _saveTimer = null;
    let _pendingDelta = {};
    let _initialized = false;
    let _previousFocus = null;
    let _cache = { version: 0, data: {} };
    let _listeners = [];

    function _toast(type, msg) {
        if (window.hermesToast && typeof window.hermesToast[type] === "function") {
            window.hermesToast[type](msg);
            return;
        }
        if (typeof window.toast === "function") window.toast(msg, type);
    }

    function _safeMerge(a, b) {
        if (window.hermesUtils && typeof window.hermesUtils.safeMerge === "function") {
            return window.hermesUtils.safeMerge(a, b);
        }
        // Fallback inline
        if (!b || typeof b !== "object") return Object.assign({}, a || {});
        const cleaned = {};
        Object.entries(b).forEach(([k, v]) => { if (v !== undefined) cleaned[k] = v; });
        return Object.assign({}, a || {}, cleaned);
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
        return resp.json();
    }

    function _fmtTime(d) {
        const hh = String(d.getHours()).padStart(2, "0");
        const mm = String(d.getMinutes()).padStart(2, "0");
        const ss = String(d.getSeconds()).padStart(2, "0");
        return `${hh}:${mm}:${ss}`;
    }

    function _setStatus(state, msg) {
        if (!_statusEl) return;
        _statusEl.dataset.state = state;
        _statusEl.textContent = msg;
    }

    function _scheduleSave() {
        if (_saveTimer) clearTimeout(_saveTimer);
        _setStatus("pending", "Salvando…");
        _saveTimer = setTimeout(_flushSave, DEBOUNCE_MS);
    }

    async function _flushSave() {
        if (!_pendingDelta || Object.keys(_pendingDelta).length === 0) {
            _setStatus("idle", "");
            return;
        }
        const delta = _pendingDelta;
        _pendingDelta = {};
        try {
            const next = await _apiCall("PUT", "/api/user-prefs", delta);
            _cache = next;
            try { localStorage.setItem("hermes_user_prefs", JSON.stringify(next)); } catch { /* noop */ }
            _setStatus("saved", `Salvo às ${_fmtTime(new Date())}`);
            _notify();
        } catch (e) {
            _setStatus("error", `Erro ao salvar: ${(e && e.message) || e}`);
            _toast("error", "Falha ao salvar preferências");
        }
    }

    function _notify() {
        _listeners.forEach((cb) => {
            try { cb(_cache.data); } catch (err) { console.warn("pref listener err", err); }
        });
    }

    function _queueDelta(key, value) {
        _pendingDelta[key] = value;
        // Optimistic update local cache
        _cache = { version: _cache.version, data: _safeMerge(_cache.data, { [key]: value }) };
        _scheduleSave();
    }

    function _section(title) {
        const sec = document.createElement("section");
        sec.className = "pref-section";
        const h = document.createElement("h3");
        h.className = "pref-section-title";
        h.textContent = title;
        sec.appendChild(h);
        return sec;
    }

    function _radioGroup(legendText, name, options, current, onChange) {
        const fieldset = document.createElement("fieldset");
        fieldset.className = "pref-radio-group";
        const legend = document.createElement("legend");
        legend.className = "pref-radio-legend";
        legend.textContent = legendText;
        fieldset.appendChild(legend);
        options.forEach((opt) => {
            const label = document.createElement("label");
            label.className = "pref-radio-label";
            const input = document.createElement("input");
            input.type = "radio";
            input.name = name;
            input.value = String(opt.value);
            if (String(opt.value) === String(current)) input.checked = true;
            input.addEventListener("change", () => onChange(opt.value));
            const span = document.createElement("span");
            span.textContent = opt.label;
            label.appendChild(input);
            label.appendChild(span);
            fieldset.appendChild(label);
        });
        return fieldset;
    }

    function _toggle(labelText, current, onChange) {
        const row = document.createElement("label");
        row.className = "pref-toggle-row";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.className = "pref-toggle";
        input.checked = !!current;
        input.addEventListener("change", () => onChange(input.checked));
        const txt = document.createElement("span");
        txt.className = "pref-toggle-label";
        txt.textContent = labelText;
        row.appendChild(input);
        row.appendChild(txt);
        return row;
    }

    function _tileOrderSection() {
        const sec = _section("Ordem dos tiles");
        const help = document.createElement("p");
        help.className = "pref-help";
        help.textContent = "Arraste ou use os botões ↑/↓ (Alt+↑/↓) para reordenar.";
        sec.appendChild(help);

        const list = document.createElement("ul");
        list.className = "pref-tile-list";
        list.setAttribute("role", "list");

        const currentOrder = Array.isArray(_cache.data.tile_order) && _cache.data.tile_order.length === SUBSYSTEMS_DEFAULT.length
            ? _cache.data.tile_order
            : SUBSYSTEMS_DEFAULT.slice();

        let order = currentOrder.slice();

        function persist() {
            _queueDelta("tile_order", order.slice());
        }

        function render() {
            list.replaceChildren();
            order.forEach((name, idx) => {
                const li = document.createElement("li");
                li.className = "pref-tile-row";
                li.draggable = true;
                li.dataset.name = name;
                li.tabIndex = 0;
                li.setAttribute("aria-label", `${SUBSYSTEM_LABELS[name] || name} — posição ${idx + 1} de ${order.length}`);

                const label = document.createElement("span");
                label.className = "pref-tile-row-label";
                label.textContent = SUBSYSTEM_LABELS[name] || name;

                const up = document.createElement("button");
                up.type = "button";
                up.className = "pref-tile-move";
                up.setAttribute("aria-label", `Mover ${SUBSYSTEM_LABELS[name] || name} para cima`);
                up.textContent = "↑";
                up.disabled = idx === 0;
                up.addEventListener("click", () => move(idx, idx - 1));

                const down = document.createElement("button");
                down.type = "button";
                down.className = "pref-tile-move";
                down.setAttribute("aria-label", `Mover ${SUBSYSTEM_LABELS[name] || name} para baixo`);
                down.textContent = "↓";
                down.disabled = idx === order.length - 1;
                down.addEventListener("click", () => move(idx, idx + 1));

                li.appendChild(label);
                li.appendChild(up);
                li.appendChild(down);

                li.addEventListener("dragstart", (e) => {
                    e.dataTransfer.effectAllowed = "move";
                    e.dataTransfer.setData("text/plain", String(idx));
                    li.classList.add("dragging");
                });
                li.addEventListener("dragend", () => li.classList.remove("dragging"));
                li.addEventListener("dragover", (e) => {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = "move";
                    li.classList.add("drag-over");
                });
                li.addEventListener("dragleave", () => li.classList.remove("drag-over"));
                li.addEventListener("drop", (e) => {
                    e.preventDefault();
                    li.classList.remove("drag-over");
                    const from = Number(e.dataTransfer.getData("text/plain"));
                    if (Number.isFinite(from) && from !== idx) move(from, idx);
                });
                li.addEventListener("keydown", (e) => {
                    if (!e.altKey) return;
                    if (e.key === "ArrowUp" && idx > 0) { e.preventDefault(); move(idx, idx - 1); }
                    if (e.key === "ArrowDown" && idx < order.length - 1) { e.preventDefault(); move(idx, idx + 1); }
                });

                list.appendChild(li);
            });
        }

        function move(from, to) {
            if (from === to || from < 0 || to < 0 || from >= order.length || to >= order.length) return;
            const item = order.splice(from, 1)[0];
            order.splice(to, 0, item);
            render();
            persist();
            const focusEl = list.querySelectorAll(".pref-tile-row")[to];
            if (focusEl) focusEl.focus();
        }

        render();
        sec.appendChild(list);
        return sec;
    }

    function _tileVisibilitySection() {
        const sec = _section("Visibilidade dos tiles");
        const help = document.createElement("p");
        help.className = "pref-help";
        help.textContent = "Pelo menos 1 tile deve permanecer visível.";
        sec.appendChild(help);

        const currentVis = (_cache.data.tile_visibility && typeof _cache.data.tile_visibility === "object")
            ? _cache.data.tile_visibility : {};

        const wrap = document.createElement("div");
        wrap.className = "pref-toggle-group";
        SUBSYSTEMS_DEFAULT.forEach((name) => {
            const checked = currentVis[name] !== false;
            const row = _toggle(SUBSYSTEM_LABELS[name] || name, checked, (val) => {
                const next = _safeMerge(_cache.data.tile_visibility, { [name]: val });
                const visibleCount = Object.values(next).filter((v) => v !== false).length;
                if (visibleCount === 0) {
                    _toast("warn", "Pelo menos 1 tile deve ficar visível");
                    // revert checkbox
                    const cb = row.querySelector(".pref-toggle");
                    if (cb) cb.checked = true;
                    return;
                }
                _queueDelta("tile_visibility", next);
            });
            wrap.appendChild(row);
        });
        sec.appendChild(wrap);
        return sec;
    }

    function _buildPanel() {
        const overlay = document.createElement("div");
        overlay.className = "pref-panel-overlay";
        overlay.hidden = true;
        overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });

        const panel = document.createElement("aside");
        panel.className = "pref-panel";
        panel.setAttribute("role", "dialog");
        panel.setAttribute("aria-modal", "false");
        panel.setAttribute("aria-labelledby", "pref-panel-title");
        panel.tabIndex = -1;

        const header = document.createElement("header");
        header.className = "pref-panel-header";
        const title = document.createElement("h2");
        title.id = "pref-panel-title";
        title.className = "pref-panel-title";
        title.textContent = "Preferências";
        const closeBtn = document.createElement("button");
        closeBtn.type = "button";
        closeBtn.className = "pref-panel-close";
        closeBtn.setAttribute("aria-label", "Fechar painel de preferências");
        closeBtn.textContent = "×";
        closeBtn.addEventListener("click", close);
        header.appendChild(title);
        header.appendChild(closeBtn);

        const body = document.createElement("div");
        body.className = "pref-panel-body";

        // Section 1: Theme
        const themeSec = _section("Tema");
        const currentTheme = _cache.data.theme || localStorage.getItem("hermes_theme") || "auto";
        const themeGrp = _radioGroup("Tema da UI", "pref-theme", [
            { value: "light", label: "Claro" },
            { value: "dark", label: "Escuro" },
            { value: "auto", label: "Sistema (auto)" },
        ], currentTheme, (v) => {
            try { localStorage.setItem("hermes_theme", v); } catch { /* noop */ }
            const dark = v === "dark" || (v === "auto" && window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches);
            document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
            _queueDelta("theme", v);
        });
        themeSec.appendChild(themeGrp);
        body.appendChild(themeSec);

        // Section 2: Mission Control
        const mcSec = _section("Mission Control");
        const currentRefresh = Number(_cache.data.refresh_rate) || 30;
        const refreshGrp = _radioGroup("Polling fallback (quando WS down)", "pref-refresh", [
            { value: 10, label: "10s" },
            { value: 30, label: "30s" },
            { value: 60, label: "60s" },
        ], currentRefresh, (v) => _queueDelta("refresh_rate", Number(v)));
        mcSec.appendChild(refreshGrp);
        body.appendChild(mcSec);

        // Section 3: Notifications
        const notifSec = _section("Notificações");
        notifSec.appendChild(_toggle(
            "Som em toasts de erro (beep sintetizado, local)",
            !!_cache.data.sound_notifications,
            (val) => _queueDelta("sound_notifications", val),
        ));
        notifSec.appendChild(_toggle(
            "Badge counter no título da aba (errors não lidos)",
            _cache.data.badge_counter_unread_errors !== false,
            (val) => {
                _queueDelta("badge_counter_unread_errors", val);
                if (typeof window.updateBadgeTitle === "function") window.updateBadgeTitle();
            },
        ));
        body.appendChild(notifSec);

        // Section 4: Tile Order
        body.appendChild(_tileOrderSection());

        // Section 5: Tile Visibility
        body.appendChild(_tileVisibilitySection());

        // Footer status
        const footer = document.createElement("footer");
        footer.className = "pref-panel-footer";
        const status = document.createElement("span");
        status.className = "pref-status";
        status.dataset.role = "status";
        status.dataset.state = "idle";
        status.setAttribute("aria-live", "polite");
        status.textContent = "";
        footer.appendChild(status);
        _statusEl = status;

        panel.appendChild(header);
        panel.appendChild(body);
        panel.appendChild(footer);
        overlay.appendChild(panel);
        document.body.appendChild(overlay);

        document.addEventListener("keydown", _onKeyDown);
        return overlay;
    }

    function _onKeyDown(e) {
        if (_overlay && !_overlay.hidden && e.key === "Escape") {
            e.preventDefault();
            close();
        }
    }

    async function _fetchPrefs() {
        try {
            const data = await _apiCall("GET", "/api/user-prefs");
            if (data && typeof data === "object" && "data" in data) {
                _cache = data;
                try { localStorage.setItem("hermes_user_prefs", JSON.stringify(data)); } catch { /* noop */ }
                _notify();
                return data;
            }
        } catch (e) {
            // Offline / login pendente — usa localStorage
            try {
                const raw = localStorage.getItem("hermes_user_prefs");
                if (raw) {
                    const parsed = JSON.parse(raw);
                    if (parsed && parsed.data) { _cache = parsed; _notify(); return parsed; }
                }
            } catch { /* noop */ }
        }
        return _cache;
    }

    async function open() {
        // Sempre re-fetch on open (last-wins atual)
        await _fetchPrefs();
        if (_overlay && _overlay.parentNode) {
            _overlay.parentNode.removeChild(_overlay);
            _overlay = null;
        }
        _previousFocus = document.activeElement;
        _overlay = _buildPanel();
        _overlay.hidden = false;
        const firstFocusable = _overlay.querySelector("input, button, select");
        if (firstFocusable) setTimeout(() => firstFocusable.focus(), 0);
    }

    function close() {
        if (!_overlay) return;
        // Flush pending save before close
        if (_pendingDelta && Object.keys(_pendingDelta).length > 0) _flushSave();
        _overlay.hidden = true;
        if (_previousFocus && typeof _previousFocus.focus === "function") {
            try { _previousFocus.focus(); } catch { /* noop */ }
        }
    }

    function destroy() {
        if (_overlay && _overlay.parentNode) _overlay.parentNode.removeChild(_overlay);
        document.removeEventListener("keydown", _onKeyDown);
        _overlay = null;
        _panel = null;
        _statusEl = null;
        _listeners = [];
        _initialized = false;
    }

    function getCache() {
        return JSON.parse(JSON.stringify(_cache));
    }

    function onChange(cb) {
        if (typeof cb === "function") _listeners.push(cb);
    }

    async function init() {
        if (_initialized) return;
        _initialized = true;
        // Best-effort fetch initial prefs (sem block UI)
        try { await _fetchPrefs(); } catch { /* noop */ }
    }

    window.HermesPrefPanel = { init, destroy, open, close, getCache, onChange };
})();
