/* ============================================================
   Hermes Cloud Studio — Toast component (F.2.4c)
   ============================================================
   Standalone — carregado via <script src="components/toast.js" defer>.
   Expõe window.hermesToast = { success, warn, error, info, dismiss }.

   Namespace prefixado pra NÃO colidir com função legacy `toast()` em app.js (declaração
   top-level cria window.toast). Wrapper compat em app.js delega `toast(msg, type)` pra
   `window.hermesToast[type](msg)` quando disponível. F.2.future cleanup: remover wrapper
   + migrar callers diretos pra window.hermesToast.*.

   Cada método: toast.<type>(msg, opts?) onde opts = {
     duration: ms (default 4000),
     action: { label, callback }  // optional inline action button
   }

   XSS: msg passa por DOMPurify.sanitize (window.DOMPurify de purify.min.js, MERGED-019).
   Sem DOMPurify carregado → fallback usa textContent (escape automático), com console.warn.
   WCAG: container role=status aria-live=polite; toast role=alert; close button aria-label.

   CSS: depende de var(--color-*), var(--space-*), var(--radius-*), var(--shadow-*), var(--motion-*)
   definidos em styles/tokens.css.
   ============================================================ */
(function () {
    "use strict";

    const TYPES = ["success", "warn", "error", "info"];
    const DEFAULT_DURATION = 4000;

    let _container = null;

    function _ensureStyles() {
        if (document.getElementById("hermes-toast-styles")) return;
        const style = document.createElement("style");
        style.id = "hermes-toast-styles";
        style.textContent = `
            .hermes-toast-container {
                position: fixed;
                top: var(--space-md);
                right: var(--space-md);
                z-index: 9999;
                display: flex;
                flex-direction: column;
                gap: var(--space-sm);
                pointer-events: none;
                max-width: 360px;
            }
            .hermes-toast {
                background: var(--color-bg-2);
                backdrop-filter: blur(16px) saturate(1.4);
                -webkit-backdrop-filter: blur(16px) saturate(1.4);
                color: var(--color-fg);
                border: 1px solid var(--color-border);
                border-left: 4px solid var(--color-info);
                border-radius: var(--radius-md);
                padding: var(--space-sm) var(--space-md);
                box-shadow: var(--shadow-xl);
                font-family: var(--font-sans);
                font-size: var(--text-sm);
                display: flex;
                align-items: flex-start;
                gap: var(--space-sm);
                pointer-events: auto;
                opacity: 0;
                transform: translateX(16px);
                transition: opacity var(--motion-base) var(--ease-out), transform var(--motion-base) var(--ease-out);
            }
            .hermes-toast.is-visible { opacity: 1; transform: translateX(0); }
            .hermes-toast-success { border-left-color: var(--color-success); }
            .hermes-toast-warn { border-left-color: var(--color-warn); }
            .hermes-toast-error { border-left-color: var(--color-error); }
            .hermes-toast-info { border-left-color: var(--color-info); }
            .hermes-toast-icon {
                flex: 0 0 auto;
                width: 16px;
                height: 16px;
                margin-top: 2px;
            }
            .hermes-toast-success .hermes-toast-icon { color: var(--color-success); }
            .hermes-toast-warn .hermes-toast-icon { color: var(--color-warn); }
            .hermes-toast-error .hermes-toast-icon { color: var(--color-error); }
            .hermes-toast-info .hermes-toast-icon { color: var(--color-info); }
            .hermes-toast-msg { flex: 1 1 auto; line-height: 1.4; word-wrap: break-word; }
            .hermes-toast-action {
                background: transparent;
                border: 1px solid var(--color-border);
                color: var(--color-accent);
                border-radius: var(--radius-sm);
                padding: 2px var(--space-sm);
                font-size: var(--text-xs);
                font-family: var(--font-sans);
                cursor: pointer;
                margin-left: var(--space-sm);
            }
            .hermes-toast-action:hover { background: var(--color-bg-3); }
            .hermes-toast-action:focus-visible { outline: 2px solid var(--color-border-focus); outline-offset: 1px; }
            .hermes-toast-close {
                background: transparent;
                border: none;
                color: var(--color-fg-muted);
                cursor: pointer;
                padding: 0;
                font-size: var(--text-base);
                line-height: 1;
                flex: 0 0 auto;
                margin-left: var(--space-xs);
            }
            .hermes-toast-close:hover { color: var(--color-fg); }
            .hermes-toast-close:focus-visible { outline: 2px solid var(--color-border-focus); outline-offset: 1px; border-radius: var(--radius-sm); }
        `;
        document.head.appendChild(style);
    }

    function _ensureContainer() {
        if (_container && document.body.contains(_container)) return _container;
        _container = document.createElement("div");
        _container.className = "hermes-toast-container";
        _container.setAttribute("role", "status");
        _container.setAttribute("aria-live", "polite");
        _container.setAttribute("aria-atomic", "false");
        document.body.appendChild(_container);
        return _container;
    }

    function _sanitize(msg) {
        const text = String(msg == null ? "" : msg);
        if (window.DOMPurify && typeof window.DOMPurify.sanitize === "function") {
            return window.DOMPurify.sanitize(text, {
                ALLOWED_TAGS: ["b", "strong", "em", "i", "code", "br"],
                ALLOWED_ATTR: [],
            });
        }
        // Fallback: textContent path (CSS já vai escapar). Sem DOMPurify carregado = bug do vendor.
        console.warn("[hermes-toast] DOMPurify ausente — usando textContent fallback. Vendor purify.min.js não carregou?");
        return null;
    }

    function _iconSvg(type) {
        const paths = {
            success: '<path d="M5 13l4 4L19 7" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
            warn: '<path d="M12 2L1 21h22L12 2zm0 5l8 14H4l8-14zm-1 7h2v4h-2v-4zm0 5h2v2h-2v-2z" fill="currentColor"/>',
            error: '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" fill="currentColor"/>',
            info: '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" fill="currentColor"/>',
        };
        return `<svg class="hermes-toast-icon" viewBox="0 0 24 24" aria-hidden="true">${paths[type] || paths.info}</svg>`;
    }

    function _show(type, msg, opts) {
        opts = opts || {};
        const duration = typeof opts.duration === "number" ? opts.duration : DEFAULT_DURATION;
        const safeType = TYPES.indexOf(type) >= 0 ? type : "info";

        _ensureStyles();
        const container = _ensureContainer();

        const toast = document.createElement("div");
        toast.className = `hermes-toast hermes-toast-${safeType}`;
        toast.setAttribute("role", safeType === "error" || safeType === "warn" ? "alert" : "status");

        // Icon
        toast.insertAdjacentHTML("beforeend", _iconSvg(safeType));

        // Message — sanitized HTML OR textContent fallback
        const msgEl = document.createElement("div");
        msgEl.className = "hermes-toast-msg";
        const clean = _sanitize(msg);
        if (clean === null) {
            msgEl.textContent = String(msg == null ? "" : msg);
        } else {
            msgEl.innerHTML = clean;
        }
        toast.appendChild(msgEl);

        // Optional inline action button
        if (opts.action && typeof opts.action.callback === "function") {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "hermes-toast-action";
            btn.textContent = String(opts.action.label || "Action");
            btn.addEventListener("click", () => {
                try { opts.action.callback(); } catch (e) { console.warn("[hermes-toast] action callback threw", e); }
                _dismiss(toast);
            });
            toast.appendChild(btn);
        }

        // Close button
        const close = document.createElement("button");
        close.type = "button";
        close.className = "hermes-toast-close";
        close.setAttribute("aria-label", "Fechar notificação");
        close.textContent = "×";
        close.addEventListener("click", () => _dismiss(toast));
        toast.appendChild(close);

        container.appendChild(toast);
        requestAnimationFrame(() => toast.classList.add("is-visible"));

        // Auto-dismiss with hover-pause
        let remaining = duration;
        let startTs = Date.now();
        let timerId = null;
        const startTimer = () => {
            if (remaining <= 0) return;
            startTs = Date.now();
            timerId = setTimeout(() => _dismiss(toast), remaining);
        };
        const pauseTimer = () => {
            if (timerId) {
                clearTimeout(timerId);
                timerId = null;
                remaining -= Date.now() - startTs;
            }
        };
        toast.addEventListener("mouseenter", pauseTimer);
        toast.addEventListener("mouseleave", startTimer);
        toast.addEventListener("focusin", pauseTimer);
        toast.addEventListener("focusout", startTimer);
        if (duration > 0) startTimer();

        return toast;
    }

    function _dismiss(toast) {
        if (!toast || !toast.parentNode) return;
        toast.classList.remove("is-visible");
        setTimeout(() => {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 250);
    }

    const api = {};
    TYPES.forEach((t) => {
        api[t] = function (msg, opts) { return _show(t, msg, opts); };
    });
    api.dismiss = _dismiss;

    window.hermesToast = api;
})();
