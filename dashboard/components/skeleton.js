/* ============================================================
   Hermes Cloud Studio — Skeleton loader component (F.2.4c)
   ============================================================
   Standalone — carregado via <script src="components/skeleton.js" defer>.
   Expõe window.skeleton = { show(target, opts?), hide(target) }.

   target: HTMLElement OR CSS selector string.
   opts = {
     count: N (default 3 — quantos blocks empilhados),
     height: '16px' (CSS value),
     width: '100%',
     gap: 'var(--space-sm)'
   }

   show(): substitui inner content do target por N skeleton-blocks.
   Conteúdo original guardado em dataset.hermesSkeletonOriginal pra restore via hide().

   CSS shimmer animation via gradient + transform translateX — sem reflow loop.
   Depende de tokens.css.
   ============================================================ */
(function () {
    "use strict";

    const ATTR_ORIGINAL = "hermesSkeletonOriginal";

    function _ensureStyles() {
        if (document.getElementById("hermes-skeleton-styles")) return;
        const style = document.createElement("style");
        style.id = "hermes-skeleton-styles";
        style.textContent = `
            @keyframes hermes-skeleton-shimmer {
                0% { transform: translateX(-100%); }
                100% { transform: translateX(100%); }
            }
            .hermes-skeleton-wrapper {
                display: flex;
                flex-direction: column;
                gap: var(--space-sm);
                width: 100%;
            }
            .hermes-skeleton-block {
                position: relative;
                overflow: hidden;
                background: var(--color-bg-2);
                border-radius: var(--radius-sm);
                width: 100%;
                height: 16px;
            }
            .hermes-skeleton-block::after {
                content: "";
                position: absolute;
                inset: 0;
                background: linear-gradient(
                    90deg,
                    transparent 0%,
                    var(--color-bg-3) 50%,
                    transparent 100%
                );
                animation: hermes-skeleton-shimmer 1.4s var(--ease-in-out) infinite;
                will-change: transform;
            }
            @media (prefers-reduced-motion: reduce) {
                .hermes-skeleton-block::after { animation: none; }
                .hermes-skeleton-block { opacity: 0.6; }
            }
        `;
        document.head.appendChild(style);
    }

    function _resolveTarget(target) {
        if (typeof target === "string") return document.querySelector(target);
        if (target instanceof HTMLElement) return target;
        return null;
    }

    function show(target, opts) {
        opts = opts || {};
        const el = _resolveTarget(target);
        if (!el) {
            console.warn("[hermes-skeleton] target não encontrado:", target);
            return null;
        }
        _ensureStyles();

        // Backup original content (idempotent: não sobrescreve se já em skeleton state)
        if (el.dataset[ATTR_ORIGINAL] === undefined) {
            el.dataset[ATTR_ORIGINAL] = el.innerHTML;
        }

        const count = Math.max(1, Math.min(20, Number(opts.count) || 3));
        const height = String(opts.height || "16px").replace(/[^0-9px%emrh.-]/gi, "");
        const width = String(opts.width || "100%").replace(/[^0-9px%emrh.-]/gi, "");

        const wrapper = document.createElement("div");
        wrapper.className = "hermes-skeleton-wrapper";
        wrapper.setAttribute("aria-busy", "true");
        wrapper.setAttribute("aria-label", "Carregando");
        for (let i = 0; i < count; i++) {
            const block = document.createElement("div");
            block.className = "hermes-skeleton-block";
            block.style.height = height;
            block.style.width = i === count - 1 && count > 1 ? "60%" : width;
            wrapper.appendChild(block);
        }

        // Replace inner content
        el.textContent = "";
        el.appendChild(wrapper);
        return wrapper;
    }

    function hide(target) {
        const el = _resolveTarget(target);
        if (!el) return;
        if (el.dataset[ATTR_ORIGINAL] !== undefined) {
            el.innerHTML = el.dataset[ATTR_ORIGINAL];
            delete el.dataset[ATTR_ORIGINAL];
        } else {
            // Fallback: clear wrapper se existir
            const w = el.querySelector(".hermes-skeleton-wrapper");
            if (w) w.remove();
        }
    }

    window.skeleton = { show: show, hide: hide };
})();
