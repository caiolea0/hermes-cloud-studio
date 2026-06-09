/* ============================================================
   Hermes Cloud Studio — PanicButton (F.2.5b Step 3)
   ============================================================
   API global: window.HermesPanicButton.{init, destroy, open, close}.
   Renderiza botão "PANIC" no header Mission Control.
   Click → modal confirmação com:
     - Botão "Confirmar" DISABLED 2s (fade-in) anti-acidente
     - Botão "Cancelar" sempre enabled, foco default
     - ESC fecha (não confirma)
     - Click overlay backdrop fecha (não confirma)
     - Focus trap (Tab cycle dentro modal)
     - aria-modal="true" + role="alertdialog" + aria-labelledby + aria-describedby
     - Minutes selector dropdown: 1/5/15/30/60/120/240/720
       default = last-used via getUserPref('panic_default_minutes', 5)
   Confirma → POST /api/daemon/subsystems/all/pause?minutes=N
     - in-flight: btn loading + disabled
     - ok=true, failed.length=0: toast.warn "TODOS pausados N min" + close
     - failed[] não vazio: toast.warn "{paused.length}/6 pausados" + render failed inline
     - reject: toast.error + keep modal open p/ retry
   XSS: textContent para todo content runtime. innerHTML apenas literal template.
   ============================================================ */
(function () {
    "use strict";

    const MINUTES_OPTIONS = [1, 5, 15, 30, 60, 120, 240, 720];

    let _btn = null;
    let _overlay = null;
    let _confirmBtn = null;
    let _cancelBtn = null;
    let _minutesSelect = null;
    let _failedRegion = null;
    let _enableTimer = null;
    let _previousFocus = null;
    let _initialized = false;

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

    function _toast(type, msg) {
        if (window.hermesToast && typeof window.hermesToast[type] === "function") {
            window.hermesToast[type](msg);
            return;
        }
        if (typeof window.toast === "function") window.toast(msg, type);
    }

    async function _apiPost(path) {
        const base = (typeof window.VM_API !== "undefined" && window.VM_API) || localStorage.getItem("hermes_api") || "";
        const token = localStorage.getItem("hermes_token") || "";
        const headers = { "Content-Type": "application/json" };
        if (token) headers["X-Hermes-Token"] = token;
        const resp = await fetch(base + path, { method: "POST", headers });
        if (!resp.ok) {
            const txt = await resp.text().catch(() => "");
            throw new Error(`HTTP ${resp.status}: ${txt.slice(0, 200)}`);
        }
        return resp.json();
    }

    function _buildButton() {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "panic-button";
        b.dataset.component = "panic-button";
        b.setAttribute("aria-label", "Pausar todos subsistemas (panic button)");
        b.textContent = "⛔ PANIC";
        b.addEventListener("click", _open);
        return b;
    }

    function _buildModal() {
        const overlay = document.createElement("div");
        overlay.className = "panic-modal-overlay";
        overlay.dataset.role = "panic-overlay";
        overlay.hidden = true;
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) _close();
        });

        const modal = document.createElement("div");
        modal.className = "panic-confirm-modal";
        modal.setAttribute("role", "alertdialog");
        modal.setAttribute("aria-modal", "true");
        modal.setAttribute("aria-labelledby", "panic-title");
        modal.setAttribute("aria-describedby", "panic-desc");
        modal.tabIndex = -1;

        const title = document.createElement("h2");
        title.id = "panic-title";
        title.className = "panic-title";
        title.textContent = "⛔ Pausar TODOS os subsistemas?";

        const desc = document.createElement("p");
        desc.id = "panic-desc";
        desc.className = "panic-desc";
        desc.textContent = "Pausa LinkedIn, Email, Scraper, Audit, Daemon e Tunnel simultaneamente. Use em emergência (ban detectado, comportamento anômalo).";

        const selectorRow = document.createElement("div");
        selectorRow.className = "panic-selector-row";
        const selectorLabel = document.createElement("label");
        selectorLabel.className = "panic-selector-label";
        selectorLabel.htmlFor = "panic-minutes";
        selectorLabel.textContent = "Pausar por:";
        const select = document.createElement("select");
        select.id = "panic-minutes";
        select.className = "panic-minutes";
        const defaultMin = Number(_getPref("panic_default_minutes", 5)) || 5;
        MINUTES_OPTIONS.forEach((m) => {
            const opt = document.createElement("option");
            opt.value = String(m);
            opt.textContent = m >= 60 ? `${m / 60}h (${m}min)` : `${m}min`;
            if (m === defaultMin) opt.selected = true;
            select.appendChild(opt);
        });
        selectorRow.appendChild(selectorLabel);
        selectorRow.appendChild(select);
        _minutesSelect = select;

        const failed = document.createElement("div");
        failed.className = "panic-failed-region";
        failed.dataset.role = "panic-failed";
        failed.setAttribute("aria-live", "polite");
        failed.hidden = true;
        _failedRegion = failed;

        const actions = document.createElement("div");
        actions.className = "panic-actions";

        const cancel = document.createElement("button");
        cancel.type = "button";
        cancel.className = "panic-cancel";
        cancel.textContent = "Cancelar";
        cancel.addEventListener("click", _close);
        _cancelBtn = cancel;

        const confirm = document.createElement("button");
        confirm.type = "button";
        confirm.className = "panic-confirm";
        confirm.textContent = "Confirmar pausa";
        confirm.disabled = true;
        confirm.setAttribute("aria-disabled", "true");
        confirm.addEventListener("click", _onConfirm);
        _confirmBtn = confirm;

        actions.appendChild(cancel);
        actions.appendChild(confirm);

        modal.appendChild(title);
        modal.appendChild(desc);
        modal.appendChild(selectorRow);
        modal.appendChild(failed);
        modal.appendChild(actions);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        document.addEventListener("keydown", _onKeyDown);
        return overlay;
    }

    function _onKeyDown(e) {
        if (!_overlay || _overlay.hidden) return;
        if (e.key === "Escape") {
            e.preventDefault();
            _close();
            return;
        }
        if (e.key === "Tab") {
            // Focus trap — cycle entre cancel e confirm (+ select)
            const focusables = [_cancelBtn, _confirmBtn, _minutesSelect].filter(
                (el) => el && !el.disabled && el.tabIndex !== -1
            );
            if (focusables.length === 0) return;
            const idx = focusables.indexOf(document.activeElement);
            const next = e.shiftKey
                ? (idx <= 0 ? focusables[focusables.length - 1] : focusables[idx - 1])
                : (idx === -1 || idx === focusables.length - 1 ? focusables[0] : focusables[idx + 1]);
            e.preventDefault();
            next.focus();
        }
    }

    function _open() {
        if (!_overlay) _overlay = _buildModal();
        _previousFocus = document.activeElement;
        _failedRegion.hidden = true;
        _failedRegion.replaceChildren();
        _overlay.hidden = false;
        _confirmBtn.disabled = true;
        _confirmBtn.setAttribute("aria-disabled", "true");
        _confirmBtn.classList.add("panic-confirm-pending");
        // Foco default no cancel (UX safety)
        setTimeout(() => { if (_cancelBtn) _cancelBtn.focus(); }, 0);
        // 2s delay enable confirm
        if (_enableTimer) clearTimeout(_enableTimer);
        _enableTimer = setTimeout(() => {
            if (!_confirmBtn) return;
            _confirmBtn.disabled = false;
            _confirmBtn.setAttribute("aria-disabled", "false");
            _confirmBtn.classList.remove("panic-confirm-pending");
        }, 2000);
    }

    function _close() {
        if (!_overlay) return;
        _overlay.hidden = true;
        if (_enableTimer) { clearTimeout(_enableTimer); _enableTimer = null; }
        if (_previousFocus && typeof _previousFocus.focus === "function") {
            try { _previousFocus.focus(); } catch { /* noop */ }
        }
    }

    function _renderFailed(failed) {
        _failedRegion.replaceChildren();
        const heading = document.createElement("strong");
        heading.textContent = `Falha em ${failed.length} subsistema(s):`;
        _failedRegion.appendChild(heading);
        const list = document.createElement("ul");
        list.className = "panic-failed-list";
        failed.forEach((f) => {
            const li = document.createElement("li");
            const name = document.createElement("code");
            name.textContent = f.name || "?";
            const err = document.createElement("span");
            err.className = "panic-failed-msg";
            err.textContent = ` — ${(f.error || "erro desconhecido").slice(0, 200)}`;
            li.appendChild(name);
            li.appendChild(err);
            list.appendChild(li);
        });
        _failedRegion.appendChild(list);
        _failedRegion.hidden = false;
    }

    async function _onConfirm() {
        if (_confirmBtn.disabled) return;
        const minutes = Number(_minutesSelect.value) || 5;
        _setPref("panic_default_minutes", minutes);
        _confirmBtn.disabled = true;
        _confirmBtn.setAttribute("aria-busy", "true");
        const originalText = _confirmBtn.textContent;
        _confirmBtn.textContent = "Pausando…";
        try {
            const resp = await _apiPost(`/api/daemon/subsystems/all/pause?minutes=${minutes}`);
            const failed = Array.isArray(resp.failed) ? resp.failed : [];
            const paused = Array.isArray(resp.paused) ? resp.paused : [];
            if (failed.length === 0) {
                _toast("warn", `TODOS subsistemas pausados ${minutes}min`);
                _close();
            } else {
                _toast("warn", `${paused.length}/6 pausados, falha em ${failed.map((f) => f.name).join(", ")}`);
                _renderFailed(failed);
            }
        } catch (e) {
            _toast("error", `Panic falhou: ${(e && e.message) || e}`);
        } finally {
            _confirmBtn.disabled = false;
            _confirmBtn.removeAttribute("aria-busy");
            _confirmBtn.textContent = originalText;
        }
    }

    function init(targetSelector) {
        if (_initialized) return _btn;
        const host = typeof targetSelector === "string"
            ? document.querySelector(targetSelector)
            : targetSelector;
        if (!host) return null;
        _btn = _buildButton();
        host.appendChild(_btn);
        _initialized = true;
        return _btn;
    }

    function destroy() {
        if (_btn && _btn.parentNode) _btn.parentNode.removeChild(_btn);
        if (_overlay && _overlay.parentNode) _overlay.parentNode.removeChild(_overlay);
        document.removeEventListener("keydown", _onKeyDown);
        _btn = null;
        _overlay = null;
        _confirmBtn = null;
        _cancelBtn = null;
        _minutesSelect = null;
        _failedRegion = null;
        _initialized = false;
    }

    window.HermesPanicButton = { init, destroy, open: _open, close: _close };
})();
