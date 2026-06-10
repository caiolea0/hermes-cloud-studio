/* ============================================================
   Hermes Cloud Studio — LabFingerprintDiff (F.3.3)
   ============================================================
   Tabela side-by-side comparando 18 stealth signals entre 2 runs do flow
   fingerprint baseline. Auto-pick últimos 2 runs (ORDER BY started_at DESC),
   override via 2 dropdowns "Run A" / "Run B".

   API global: window.HermesLabFingerprintDiff.{init, render, destroy}.

   Data source: GET /api/lab/runs/{run_id} → array de events com type=fingerprint_dump
   (sanitized + whitelisted no F.3.2). Cada evento traz:
     { event: 'fingerprint_dump', site: 'creepjs|browserleaks|amiunique',
       signals: { ... }, hash: '...' }

   18 signals fixos:
     navigator.webdriver, navigator.languages, navigator.platform,
     navigator.hardwareConcurrency, navigator.deviceMemory,
     screen.width, screen.height, screen.colorDepth, screen.pixelRatio,
     viewport.width, viewport.height,
     webgl.vendor, webgl.renderer, webgl.unmasked_vendor, webgl.unmasked_renderer,
     canvas.hash, plugins.count, timezone

   Diff logic:
     match     → green (var(--color-success))
     mismatch  → red   (var(--color-error))
     missing   → muted (var(--color-fg-muted))

   XSS: TODOS signal values render via textContent (defesa em profundidade — backend
   já sanitizou em F.3.2 _event_emit.py, mas signals vêm de browser DOM real do CreepJS).
   ============================================================ */
(function () {
    "use strict";

    const SIGNALS = [
        { key: "navigator.webdriver", path: ["navigator", "webdriver"], label: "navigator.webdriver" },
        { key: "navigator.languages", path: ["navigator", "languages"], label: "navigator.languages" },
        { key: "navigator.platform", path: ["navigator", "platform"], label: "navigator.platform" },
        { key: "navigator.hardwareConcurrency", path: ["navigator", "hardwareConcurrency"], label: "navigator.hardwareConcurrency" },
        { key: "navigator.deviceMemory", path: ["navigator", "deviceMemory"], label: "navigator.deviceMemory" },
        { key: "screen.width", path: ["screen", "width"], label: "screen.width" },
        { key: "screen.height", path: ["screen", "height"], label: "screen.height" },
        { key: "screen.colorDepth", path: ["screen", "colorDepth"], label: "screen.colorDepth" },
        { key: "screen.pixelRatio", path: ["screen", "pixelRatio"], label: "screen.pixelRatio" },
        { key: "viewport.width", path: ["viewport", "width"], label: "viewport.width" },
        { key: "viewport.height", path: ["viewport", "height"], label: "viewport.height" },
        { key: "webgl.vendor", path: ["webgl", "vendor"], label: "webgl.vendor" },
        { key: "webgl.renderer", path: ["webgl", "renderer"], label: "webgl.renderer" },
        { key: "webgl.unmasked_vendor", path: ["webgl", "unmasked_vendor"], label: "webgl.unmasked_vendor" },
        { key: "webgl.unmasked_renderer", path: ["webgl", "unmasked_renderer"], label: "webgl.unmasked_renderer" },
        { key: "canvas.hash", path: ["canvas", "hash"], label: "canvas.hash" },
        { key: "plugins.count", path: ["plugins", "count"], label: "plugins.count" },
        { key: "timezone", path: ["timezone"], label: "timezone" },
    ];

    let _root = null;
    let _selectA = null;
    let _selectB = null;
    let _tableBody = null;
    let _emptyState = null;
    let _availableRuns = [];
    let _initialized = false;

    function _resolveTarget(target) {
        if (typeof target === "string") return document.querySelector(target);
        if (target instanceof HTMLElement) return target;
        return null;
    }

    function _formatValue(v) {
        if (v === undefined || v === null) return "—";
        if (Array.isArray(v)) return v.join(", ");
        if (typeof v === "object") return JSON.stringify(v);
        return String(v);
    }

    function _digValue(obj, path) {
        let cur = obj;
        for (const p of path) {
            if (cur === undefined || cur === null) return undefined;
            cur = cur[p];
        }
        return cur;
    }

    function _statusOf(valA, valB) {
        const sa = _formatValue(valA);
        const sb = _formatValue(valB);
        if (sa === "—" || sb === "—") return "missing";
        return sa === sb ? "match" : "mismatch";
    }

    function _buildShell(host) {
        // Header com 2 dropdowns
        const header = document.createElement("div");
        header.className = "lab-fp-diff-header";

        const labelA = document.createElement("label");
        labelA.className = "lab-fp-diff-label";
        labelA.htmlFor = "lab-fp-select-a";
        labelA.textContent = "Run A:";
        const selA = document.createElement("select");
        selA.id = "lab-fp-select-a";
        selA.className = "lab-fp-diff-select";
        selA.setAttribute("aria-label", "Selecionar Run A para comparação");
        selA.addEventListener("change", _onSelectChange);
        labelA.appendChild(selA);

        const labelB = document.createElement("label");
        labelB.className = "lab-fp-diff-label";
        labelB.htmlFor = "lab-fp-select-b";
        labelB.textContent = "Run B:";
        const selB = document.createElement("select");
        selB.id = "lab-fp-select-b";
        selB.className = "lab-fp-diff-select";
        selB.setAttribute("aria-label", "Selecionar Run B para comparação");
        selB.addEventListener("change", _onSelectChange);
        labelB.appendChild(selB);

        header.appendChild(labelA);
        header.appendChild(labelB);
        host.appendChild(header);

        // Empty state placeholder
        const empty = document.createElement("div");
        empty.className = "lab-fp-diff-empty";
        empty.dataset.role = "fp-diff-empty";
        empty.hidden = true;
        empty.textContent = "Apenas 0 runs fingerprint disponíveis — rode fingerprint flow pra comparar.";
        host.appendChild(empty);

        // Table
        const table = document.createElement("table");
        table.className = "lab-fp-diff";
        table.setAttribute("role", "table");
        table.setAttribute("aria-label", "Fingerprint signals diff");
        const thead = document.createElement("thead");
        const trHead = document.createElement("tr");
        ["Signal", "Run A", "Run B", "Status"].forEach((h) => {
            const th = document.createElement("th");
            th.scope = "col";
            th.textContent = h;
            trHead.appendChild(th);
        });
        thead.appendChild(trHead);
        table.appendChild(thead);

        const tbody = document.createElement("tbody");
        tbody.dataset.role = "fp-diff-body";
        table.appendChild(tbody);
        host.appendChild(table);

        _selectA = selA;
        _selectB = selB;
        _tableBody = tbody;
        _emptyState = empty;
    }

    function _populateSelects(runs) {
        if (!_selectA || !_selectB) return;
        _selectA.replaceChildren();
        _selectB.replaceChildren();
        runs.forEach((run) => {
            const optA = document.createElement("option");
            optA.value = String(run.run_id);
            optA.textContent = `${run.run_id} — ${run.started_at || "?"}`;
            _selectA.appendChild(optA);
            const optB = optA.cloneNode(true);
            _selectB.appendChild(optB);
        });
        // Auto-pick: A=mais recente (idx 0), B=segundo mais recente (idx 1)
        if (runs.length >= 2) {
            _selectA.value = String(runs[0].run_id);
            _selectB.value = String(runs[1].run_id);
        } else if (runs.length === 1) {
            _selectA.value = String(runs[0].run_id);
            _selectB.value = String(runs[0].run_id);
        }
    }

    function _onSelectChange() {
        const runA = _availableRuns.find((r) => String(r.run_id) === _selectA.value);
        const runB = _availableRuns.find((r) => String(r.run_id) === _selectB.value);
        if (runA && runB) {
            _renderDiff(runA.fingerprint || {}, runB.fingerprint || {});
        }
    }

    function _renderDiff(fpA, fpB) {
        if (!_tableBody) return;
        _tableBody.replaceChildren();
        _emptyState.hidden = true;

        SIGNALS.forEach((sig) => {
            const valA = _digValue(fpA, sig.path);
            const valB = _digValue(fpB, sig.path);
            const status = _statusOf(valA, valB);

            const tr = document.createElement("tr");
            tr.dataset.status = status;

            const tdSignal = document.createElement("td");
            tdSignal.className = "lab-fp-diff-signal";
            tdSignal.textContent = sig.label;

            const tdA = document.createElement("td");
            tdA.className = "lab-fp-diff-val";
            tdA.textContent = _formatValue(valA);

            const tdB = document.createElement("td");
            tdB.className = "lab-fp-diff-val";
            tdB.textContent = _formatValue(valB);

            const tdStatus = document.createElement("td");
            tdStatus.className = `lab-fp-diff-status lab-fp-status-${status}`;
            tdStatus.textContent = status === "match" ? "✓" : (status === "mismatch" ? "✗" : "—");
            tdStatus.setAttribute("aria-label", status === "match" ? "Match" : (status === "mismatch" ? "Divergente" : "Ausente"));

            tr.appendChild(tdSignal);
            tr.appendChild(tdA);
            tr.appendChild(tdB);
            tr.appendChild(tdStatus);
            _tableBody.appendChild(tr);
        });
    }

    function _showEmpty(runsCount) {
        if (!_emptyState || !_tableBody) return;
        _tableBody.replaceChildren();
        _emptyState.textContent = `Apenas ${runsCount} run(s) fingerprint disponíveis — rode fingerprint flow pra comparar.`;
        _emptyState.hidden = false;
    }

    function init(targetSelector) {
        const host = _resolveTarget(targetSelector);
        if (!host) {
            console.warn("[HermesLabFingerprintDiff] target não encontrado:", targetSelector);
            return false;
        }
        if (_initialized) destroy();
        _root = host;
        while (_root.firstChild) _root.removeChild(_root.firstChild);
        _buildShell(_root);
        _initialized = true;
        return true;
    }

    /**
     * Render diff a partir de array de runs {run_id, started_at, fingerprint}.
     * Caller fornece runs já hidratados com fingerprint signals (extraído de events).
     */
    function render(runs) {
        if (!_initialized) return;
        if (!Array.isArray(runs)) runs = [];
        _availableRuns = runs;

        if (runs.length < 2) {
            // Limpar selects mas mostrar empty
            if (_selectA) _selectA.replaceChildren();
            if (_selectB) _selectB.replaceChildren();
            _showEmpty(runs.length);
            return;
        }
        _populateSelects(runs);
        _renderDiff(runs[0].fingerprint || {}, runs[1].fingerprint || {});
    }

    function destroy() {
        if (_root) {
            while (_root.firstChild) _root.removeChild(_root.firstChild);
        }
        _root = null;
        _selectA = null;
        _selectB = null;
        _tableBody = null;
        _emptyState = null;
        _availableRuns = [];
        _initialized = false;
    }

    window.HermesLabFingerprintDiff = { init, render, destroy };
})();
