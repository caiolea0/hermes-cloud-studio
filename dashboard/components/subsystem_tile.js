/* ============================================================
   Hermes Cloud Studio — SubsystemTileGrid (F.2.5a)
   ============================================================
   6 tiles grid (linkedin/email/scraper/audit/daemon/tunnel).
   API global: window.SubsystemTileGrid.{init, update, destroy}.
   Adapter window._missionControl.{updateSubsystem, appendLog, appendDecision}
   pra compat com handlers WS já presentes em app.js (F.2.3).

   WS events consumidos (via app.js delegando):
     - daemon.subsystem_status → updateSubsystem({subsystem, status, paused_until_ts, emitter})
     - daemon.log_event        → appendLog (stub F.2.5b LiveLogTail)
     - daemon.decision         → appendDecision (stub F.2.5b)

   Render: incremental por tile (não rebuild grid).
   XSS: usa textContent pra todos campos dinâmicos do servidor (subsystem name,
   ip, emitter, ações). Sem innerHTML += em conteúdo runtime.
   ============================================================ */
(function () {
    "use strict";

    const SUBSYSTEMS = [
        { name: "linkedin", icon: "linkedin",  label: "LinkedIn" },
        { name: "email",    icon: "mail",       label: "Email" },
        { name: "scraper",  icon: "bug",        label: "Scraper" },
        { name: "audit",    icon: "shield",     label: "Audit" },
        { name: "daemon",   icon: "settings",   label: "Daemon" },
        { name: "tunnel",   icon: "globe",      label: "Tunnel" },
    ];

    const STATUS_ALLOWED = new Set([
        "healthy", "paused", "warn", "error", "offline", "warning",
    ]);

    let _root = null;
    let _initialized = false;
    const _state = Object.create(null);
    const _countdownTimers = Object.create(null);

    function _badgeForStatus(status) {
        if (status === "healthy") return "tile-badge-healthy";
        if (status === "paused") return "tile-badge-paused";
        if (status === "warn" || status === "warning") return "tile-badge-warn";
        if (status === "error") return "tile-badge-error";
        return "tile-badge-offline";
    }

    function _normalizeStatus(s) {
        const v = String(s || "").toLowerCase().replace(/[^a-z]/g, "");
        if (!STATUS_ALLOWED.has(v)) return "offline";
        if (v === "warning") return "warn";
        return v;
    }

    function _formatRelative(tsLike) {
        if (tsLike === undefined || tsLike === null || tsLike === "") return "—";
        try {
            const d = (typeof tsLike === "number")
                ? new Date(tsLike * 1000)
                : new Date(tsLike);
            const diffMs = Date.now() - d.getTime();
            if (Number.isNaN(diffMs)) return "—";
            const past = diffMs >= 0;
            const abs = Math.abs(diffMs);
            const sec = Math.floor(abs / 1000);
            if (sec < 60) return past ? `há ${sec}s` : `em ~${sec}s`;
            const min = Math.floor(sec / 60);
            if (min < 60) return past ? `há ${min}min` : `em ~${min}min`;
            const hr = Math.floor(min / 60);
            if (hr < 24) return past ? `há ${hr}h` : `em ~${hr}h`;
            const day = Math.floor(hr / 24);
            return past ? `há ${day}d` : `em ~${day}d`;
        } catch { return "—"; }
    }

    function _formatCountdown(secondsRemaining) {
        const s = Math.max(0, Math.floor(secondsRemaining));
        const mm = String(Math.floor(s / 60)).padStart(2, "0");
        const ss = String(s % 60).padStart(2, "0");
        return `${mm}:${ss}`;
    }

    function _buildTile(spec) {
        const tile = document.createElement("div");
        tile.className = "subsystem-tile";
        tile.dataset.subsystem = spec.name;
        tile.dataset.status = "offline";

        const header = document.createElement("header");
        header.className = "tile-header";
        const iconEl = document.createElement("span");
        iconEl.className = "tile-icon";
        iconEl.innerHTML = typeof window.icon === 'function' ? window.icon(spec.icon) : '';
        iconEl.setAttribute("aria-hidden", "true");
        const nameEl = document.createElement("span");
        nameEl.className = "tile-name";
        nameEl.textContent = spec.label;
        const badgeEl = document.createElement("span");
        badgeEl.className = "tile-badge tile-badge-offline";
        badgeEl.dataset.role = "badge";
        badgeEl.textContent = "offline";
        header.appendChild(iconEl);
        header.appendChild(nameEl);
        header.appendChild(badgeEl);

        const body = document.createElement("div");
        body.className = "tile-body";
        const mkMetric = (labelText, roleKey) => {
            const m = document.createElement("div");
            m.className = "tile-metric";
            const lbl = document.createElement("span");
            lbl.className = "tile-metric-label";
            lbl.textContent = labelText;
            const val = document.createElement("span");
            val.className = "tile-metric-value";
            val.dataset.role = roleKey;
            val.textContent = "—";
            m.appendChild(lbl);
            m.appendChild(val);
            return m;
        };
        body.appendChild(mkMetric("Última ação", "last-action"));
        body.appendChild(mkMetric("Próxima ação", "next-action"));

        const footer = document.createElement("footer");
        footer.className = "tile-footer";
        const pauseBtn = document.createElement("button");
        pauseBtn.type = "button";
        pauseBtn.className = "tile-action tile-pause";
        pauseBtn.dataset.role = "pause-btn";
        pauseBtn.setAttribute("aria-label", `Pausar ${spec.label} por 5 minutos`);
        pauseBtn.innerHTML = (typeof window.icon === 'function' ? window.icon('pause') : '') + ' Pausar 5min';
        pauseBtn.addEventListener("click", () => _onPauseClick(spec.name, pauseBtn));

        const resumeBtn = document.createElement("button");
        resumeBtn.type = "button";
        resumeBtn.className = "tile-action tile-resume";
        resumeBtn.dataset.role = "resume-btn";
        resumeBtn.setAttribute("aria-label", `Retomar ${spec.label}`);
        resumeBtn.textContent = "▶ Retomar";
        resumeBtn.hidden = true;
        resumeBtn.addEventListener("click", () => _onResumeClick(spec.name, resumeBtn));

        const countdown = document.createElement("span");
        countdown.className = "tile-countdown";
        countdown.dataset.role = "countdown";
        countdown.setAttribute("aria-live", "polite");
        countdown.hidden = true;

        footer.appendChild(pauseBtn);
        footer.appendChild(resumeBtn);
        footer.appendChild(countdown);

        tile.appendChild(header);
        tile.appendChild(body);
        tile.appendChild(footer);
        return tile;
    }

    async function _apiCall(method, path) {
        const base = (typeof VM_API !== "undefined" && VM_API) || localStorage.getItem("hermes_api") || "";
        const token = localStorage.getItem("hermes_token") || "";
        const headers = { "Content-Type": "application/json" };
        if (token) headers["X-Hermes-Token"] = token;
        const resp = await fetch(base + path, { method, headers });
        if (!resp.ok) {
            const txt = await resp.text().catch(() => "");
            throw new Error(`HTTP ${resp.status}: ${txt}`);
        }
        const ct = resp.headers.get("content-type") || "";
        return ct.includes("json") ? await resp.json() : await resp.text();
    }

    function _toast(type, msg) {
        if (window.hermesToast && typeof window.hermesToast[type] === "function") {
            window.hermesToast[type](msg);
            return;
        }
        if (typeof window.toast === "function") {
            window.toast(msg, type);
        }
    }

    async function _onPauseClick(name, btn) {
        btn.disabled = true;
        try {
            await _apiCall("POST", `/api/daemon/subsystems/${encodeURIComponent(name)}/pause?minutes=5`);
            _toast("warn", `Subsistema ${name} pausado 5 min`);
            // Optimistic: WS broadcast vai confirmar logo
            const untilTs = Math.floor(Date.now() / 1000) + 5 * 60;
            update(name, { status: "paused", paused_until_ts: untilTs });
        } catch (e) {
            console.error("[SubsystemTileGrid] pause failed", name, e);
            _toast("error", `Falha ao pausar ${name}: ${e.message || e}`);
        } finally {
            btn.disabled = false;
        }
    }

    async function _onResumeClick(name, btn) {
        btn.disabled = true;
        try {
            await _apiCall("POST", `/api/daemon/subsystems/${encodeURIComponent(name)}/resume`);
            _toast("success", `Subsistema ${name} retomado`);
            update(name, { status: "healthy", paused_until_ts: null });
        } catch (e) {
            console.error("[SubsystemTileGrid] resume failed", name, e);
            _toast("error", `Falha ao retomar ${name}: ${e.message || e}`);
        } finally {
            btn.disabled = false;
        }
    }

    function _clearCountdown(name) {
        const t = _countdownTimers[name];
        if (t) {
            clearInterval(t);
            delete _countdownTimers[name];
        }
    }

    function _startCountdown(name, untilTs, tileEl) {
        _clearCountdown(name);
        const countdownEl = tileEl.querySelector('[data-role="countdown"]');
        if (!countdownEl) return;
        const tick = () => {
            const remaining = untilTs - Math.floor(Date.now() / 1000);
            if (remaining <= 0) {
                _clearCountdown(name);
                countdownEl.hidden = true;
                countdownEl.textContent = "";
                update(name, { status: "healthy", paused_until_ts: null });
                return;
            }
            countdownEl.textContent = _formatCountdown(remaining);
        };
        countdownEl.hidden = false;
        tick();
        _countdownTimers[name] = setInterval(tick, 1000);
    }

    function _renderTile(name, data) {
        if (!_root) return;
        const tile = _root.querySelector(`.subsystem-tile[data-subsystem="${name}"]`);
        if (!tile) return;

        const status = _normalizeStatus(data.status);
        tile.dataset.status = status;

        const badge = tile.querySelector('[data-role="badge"]');
        if (badge) {
            badge.className = "tile-badge " + _badgeForStatus(status);
            badge.textContent = status;
        }

        const lastEl = tile.querySelector('[data-role="last-action"]');
        if (lastEl) {
            lastEl.textContent = _formatRelative(data.last_action_ts ?? data.last_action ?? null);
        }

        const nextEl = tile.querySelector('[data-role="next-action"]');
        if (nextEl) {
            nextEl.textContent = _formatRelative(data.next_action_ts ?? data.next_action ?? null);
        }

        const pauseBtn = tile.querySelector('[data-role="pause-btn"]');
        const resumeBtn = tile.querySelector('[data-role="resume-btn"]');
        const countdownEl = tile.querySelector('[data-role="countdown"]');

        if (status === "paused" && data.paused_until_ts) {
            if (pauseBtn) pauseBtn.hidden = true;
            if (resumeBtn) resumeBtn.hidden = false;
            _startCountdown(name, Number(data.paused_until_ts), tile);
        } else {
            if (pauseBtn) pauseBtn.hidden = false;
            if (resumeBtn) resumeBtn.hidden = true;
            if (countdownEl) {
                countdownEl.hidden = true;
                countdownEl.textContent = "";
            }
            _clearCountdown(name);
        }
    }

    function init(rootSelector, options) {
        const root = typeof rootSelector === "string"
            ? document.querySelector(rootSelector)
            : rootSelector;
        if (!root) {
            console.warn("[SubsystemTileGrid] root not found:", rootSelector);
            return false;
        }
        if (_initialized && _root === root) return true;
        if (_initialized) destroy();

        _root = root;
        _root.classList.add("subsystem-tile-grid");
        _root.setAttribute("role", "list");
        _root.setAttribute("aria-label", "Subsistemas do Hermes");
        // Clear any prior content (idempotent re-init)
        while (_root.firstChild) _root.removeChild(_root.firstChild);

        for (const spec of SUBSYSTEMS) {
            const tile = _buildTile(spec);
            tile.setAttribute("role", "listitem");
            _root.appendChild(tile);
        }
        _initialized = true;
        return true;
    }

    function update(name, data) {
        if (!_initialized || !_root) return;
        if (!name || typeof data !== "object" || data === null) return;
        const prev = _state[name] || {};
        // Defensive merge: ignore undefined keys so partial WS events (sem paused_until_ts)
        // não wipam state da optimistic update do click.
        const patch = {};
        for (const k of Object.keys(data)) {
            if (data[k] !== undefined) patch[k] = data[k];
        }
        const merged = { ...prev, ...patch };
        _state[name] = merged;
        _renderTile(name, merged);
    }

    function destroy() {
        for (const k of Object.keys(_countdownTimers)) _clearCountdown(k);
        if (_root) {
            while (_root.firstChild) _root.removeChild(_root.firstChild);
            _root.classList.remove("subsystem-tile-grid");
        }
        _root = null;
        _initialized = false;
        for (const k of Object.keys(_state)) delete _state[k];
    }

    window.SubsystemTileGrid = { init, update, destroy };

    // Adapter pra hooks F.2.3 já presentes em app.js (window._missionControl.*).
    // app.js delega WS canonical dot-notation aqui sem mudar o call-site original.
    window._missionControl = window._missionControl || {};
    window._missionControl.updateSubsystem = function (event) {
        if (!event || !event.subsystem) return;
        update(event.subsystem, {
            status: event.status,
            paused_until_ts: event.paused_until_ts,
            last_action_ts: event.last_action_ts,
            next_action_ts: event.next_action_ts,
            emitter: event.emitter,
        });
    };
    window._missionControl.appendLog = window._missionControl.appendLog || function (_event) {
        // F.2.5b LiveLogTail will consume this.
    };
    window._missionControl.appendDecision = window._missionControl.appendDecision || function (_event) {
        // F.2.5b decision feed will consume this.
    };
})();
