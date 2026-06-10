/* ============================================================
   Hermes Cloud Studio — LabGauge (F.3.3)
   ============================================================
   SVG semicircular compliance gauge 0-100.
   API global: window.HermesLabGauge.{init, update, destroy}.

   Cor dinâmica via tokens design system F.2.4:
     <50  → var(--color-error)
     50-69 → var(--color-warn)
     >=70 → var(--color-success)   (threshold GUARDRAILS lab)

   Threshold tick em 70 (linha visual no arco).
   Tooltip hover mostra delta vs previous score (`+5` verde, `-3` vermelho).
   Animação tween via CSS transition (stroke-dashoffset + stroke).
     - var(--motion-slow) (400ms) + var(--ease-out)
     - prefers-reduced-motion → transition desabilitada.

   XSS: ZERO innerHTML runtime. Toda string vinda do server passa por textContent.
   WCAG: role="meter" + aria-valuenow/min/max + aria-label.
   ============================================================ */
(function () {
    "use strict";

    const ARC_LENGTH = 251.3; // perímetro do arco superior (calculado pra raio 80, semicírculo)
    const THRESHOLD = 70;

    const _instances = new Map();

    function _ensureStyles() {
        if (document.getElementById("hermes-lab-gauge-styles")) return;
        const style = document.createElement("style");
        style.id = "hermes-lab-gauge-styles";
        style.textContent = `
            .lab-gauge { width: 200px; height: 120px; display: block; }
            .lab-gauge-track { stroke: var(--color-bg-3); }
            .lab-gauge-fill {
                stroke: var(--color-success);
                transition: stroke-dashoffset var(--motion-slow, 400ms) var(--ease-out, ease-out),
                            stroke var(--motion-base, 250ms) var(--ease-out, ease-out);
            }
            .lab-gauge-threshold { stroke: var(--color-fg-muted); }
            .lab-gauge-value { fill: var(--color-fg); font-family: var(--font-mono, monospace); }
            .lab-gauge-label { fill: var(--color-fg-muted); font-family: var(--font-sans, sans-serif); }
            .lab-gauge-delta { fill: var(--color-fg-muted); font-family: var(--font-mono, monospace); }
            .lab-gauge-delta-up { fill: var(--color-success); }
            .lab-gauge-delta-down { fill: var(--color-error); }
            @media (prefers-reduced-motion: reduce) {
                .lab-gauge-fill { transition: none; }
            }
        `;
        document.head.appendChild(style);
    }

    function _resolveTarget(target) {
        if (typeof target === "string") return document.querySelector(target);
        if (target instanceof HTMLElement) return target;
        return null;
    }

    function _colorForScore(score) {
        if (score >= THRESHOLD) return "var(--color-success)";
        if (score >= 50) return "var(--color-warn)";
        return "var(--color-error)";
    }

    function _build(host) {
        const ns = "http://www.w3.org/2000/svg";
        const svg = document.createElementNS(ns, "svg");
        svg.classList.add("lab-gauge");
        svg.setAttribute("viewBox", "0 0 200 120");
        svg.setAttribute("role", "meter");
        svg.setAttribute("aria-valuenow", "0");
        svg.setAttribute("aria-valuemin", "0");
        svg.setAttribute("aria-valuemax", "100");
        svg.setAttribute("aria-label", "Compliance score");

        // Track (background arc)
        const track = document.createElementNS(ns, "path");
        track.setAttribute("class", "lab-gauge-track");
        track.setAttribute("d", "M20,100 A80,80 0 0,1 180,100");
        track.setAttribute("stroke-width", "14");
        track.setAttribute("fill", "none");
        track.setAttribute("stroke-linecap", "round");
        svg.appendChild(track);

        // Fill (animated arc)
        const fill = document.createElementNS(ns, "path");
        fill.setAttribute("class", "lab-gauge-fill");
        fill.setAttribute("d", "M20,100 A80,80 0 0,1 180,100");
        fill.setAttribute("stroke-width", "14");
        fill.setAttribute("fill", "none");
        fill.setAttribute("stroke-linecap", "round");
        fill.setAttribute("stroke-dasharray", String(ARC_LENGTH));
        fill.setAttribute("stroke-dashoffset", String(ARC_LENGTH));
        fill.dataset.role = "gauge-fill";
        svg.appendChild(fill);

        // Threshold tick at 70 (angle = 70/100 of 180deg from left = 126deg from x-axis)
        // Compute marker position on arc
        const thrAngle = Math.PI * (1 - THRESHOLD / 100); // from left (PI) sweeping to right (0)
        const cx = 100, cy = 100, r = 80;
        const tx = cx + r * Math.cos(thrAngle);
        const ty = cy - r * Math.sin(thrAngle);
        const tx2 = cx + (r + 10) * Math.cos(thrAngle);
        const ty2 = cy - (r + 10) * Math.sin(thrAngle);
        const threshold = document.createElementNS(ns, "line");
        threshold.setAttribute("class", "lab-gauge-threshold");
        threshold.setAttribute("x1", String(tx.toFixed(1)));
        threshold.setAttribute("y1", String(ty.toFixed(1)));
        threshold.setAttribute("x2", String(tx2.toFixed(1)));
        threshold.setAttribute("y2", String(ty2.toFixed(1)));
        threshold.setAttribute("stroke-width", "2");
        const thrTitle = document.createElementNS(ns, "title");
        thrTitle.textContent = "Threshold: 70 (gate inviolável)";
        threshold.appendChild(thrTitle);
        svg.appendChild(threshold);

        // Value text
        const valueText = document.createElementNS(ns, "text");
        valueText.setAttribute("class", "lab-gauge-value");
        valueText.setAttribute("x", "100");
        valueText.setAttribute("y", "92");
        valueText.setAttribute("text-anchor", "middle");
        valueText.setAttribute("font-size", "32");
        valueText.dataset.role = "gauge-value";
        valueText.textContent = "0";
        svg.appendChild(valueText);

        // Label
        const labelText = document.createElementNS(ns, "text");
        labelText.setAttribute("class", "lab-gauge-label");
        labelText.setAttribute("x", "100");
        labelText.setAttribute("y", "112");
        labelText.setAttribute("text-anchor", "middle");
        labelText.setAttribute("font-size", "11");
        labelText.textContent = "compliance";
        svg.appendChild(labelText);

        // Delta indicator (hidden initially)
        const deltaText = document.createElementNS(ns, "text");
        deltaText.setAttribute("class", "lab-gauge-delta");
        deltaText.setAttribute("x", "180");
        deltaText.setAttribute("y", "30");
        deltaText.setAttribute("text-anchor", "end");
        deltaText.setAttribute("font-size", "12");
        deltaText.dataset.role = "gauge-delta";
        deltaText.textContent = "";
        svg.appendChild(deltaText);

        // Tooltip via title
        const title = document.createElementNS(ns, "title");
        title.dataset.role = "gauge-tooltip";
        title.textContent = "Score: 0 / 100";
        svg.appendChild(title);

        host.appendChild(svg);
        return svg;
    }

    function init(targetSelector, options) {
        _ensureStyles();
        const host = _resolveTarget(targetSelector);
        if (!host) {
            console.warn("[HermesLabGauge] target não encontrado:", targetSelector);
            return null;
        }
        // Idempotent: clear prior content
        while (host.firstChild) host.removeChild(host.firstChild);
        const svg = _build(host);
        const inst = { svg, score: 0, prevScore: null };
        _instances.set(host, inst);
        return svg;
    }

    function update(targetSelector, score, options) {
        const host = _resolveTarget(targetSelector);
        if (!host) return;
        const inst = _instances.get(host);
        if (!inst) {
            console.warn("[HermesLabGauge] update sem init prévio");
            return;
        }
        const clamped = Math.max(0, Math.min(100, Number(score) || 0));
        const prev = inst.score;
        inst.prevScore = prev;
        inst.score = clamped;

        const fill = inst.svg.querySelector('[data-role="gauge-fill"]');
        const valueText = inst.svg.querySelector('[data-role="gauge-value"]');
        const deltaText = inst.svg.querySelector('[data-role="gauge-delta"]');
        const tooltip = inst.svg.querySelector('[data-role="gauge-tooltip"]');

        const offset = ARC_LENGTH * (1 - clamped / 100);
        if (fill) {
            fill.setAttribute("stroke-dashoffset", String(offset.toFixed(2)));
            fill.setAttribute("stroke", _colorForScore(clamped));
        }
        if (valueText) {
            valueText.textContent = String(Math.round(clamped));
            valueText.setAttribute("fill", _colorForScore(clamped));
        }
        inst.svg.setAttribute("aria-valuenow", String(Math.round(clamped)));

        // Delta
        if (deltaText) {
            if (prev > 0 || (options && options.showDeltaFromZero)) {
                const delta = clamped - prev;
                if (delta > 0) {
                    deltaText.textContent = `+${delta.toFixed(0)}`;
                    deltaText.classList.remove("lab-gauge-delta-down");
                    deltaText.classList.add("lab-gauge-delta-up");
                } else if (delta < 0) {
                    deltaText.textContent = String(delta.toFixed(0));
                    deltaText.classList.remove("lab-gauge-delta-up");
                    deltaText.classList.add("lab-gauge-delta-down");
                } else {
                    deltaText.textContent = "±0";
                    deltaText.classList.remove("lab-gauge-delta-up", "lab-gauge-delta-down");
                }
            } else {
                deltaText.textContent = "";
            }
        }
        if (tooltip) {
            const deltaSuffix = (prev !== null && prev > 0) ? ` (Δ ${(clamped - prev) >= 0 ? "+" : ""}${(clamped - prev).toFixed(0)})` : "";
            tooltip.textContent = `Score: ${Math.round(clamped)} / 100${deltaSuffix}`;
        }
    }

    function destroy(targetSelector) {
        const host = _resolveTarget(targetSelector);
        if (!host) return;
        const inst = _instances.get(host);
        if (inst && inst.svg && inst.svg.parentNode) {
            inst.svg.parentNode.removeChild(inst.svg);
        }
        _instances.delete(host);
    }

    window.HermesLabGauge = { init, update, destroy };
})();
