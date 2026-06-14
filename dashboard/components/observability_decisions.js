/* ============================================================
   Hermes Cloud Studio — ObservabilityDecisions (F.8.3 C2 + C3)
   ============================================================
   Table brain_runs paginated + filters intent/search/status/run_id.
   Click row → inline accordion expand (D5) showing brain_decisions
   sub-table (sequence + state transition + tool + rationale + latency).

   Backend endpoint: GET /api/observability/decisions
     ?intent=&search=&status=&run_id=&offset=&limit=
   Response.items[].decisions is already truncated 2000 chars (D6 backend).

   Decisões F.8.3 D5: inline accordion (não drawer/modal).
   Decisões F.8.3 D6: CSV export server-side reuse.
   ============================================================ */
(function () {
    "use strict";

    var ROOT_SEL = '[data-component="observability-decisions"]';
    var PAGE_SIZE = 25;
    var state = {
        wired: false,
        offset: 0,
        total: 0,
        filters: { intent: "", search: "", status: "", run_id: "" },
        expanded: new Set(),
    };

    function _$(sel) { return document.querySelector(ROOT_SEL + " " + sel); }
    function _authHeaders() {
        var h = {};
        try { var t = localStorage.getItem("hermes_token") || ""; if (t) h["X-Hermes-Token"] = t; } catch (_) {}
        return h;
    }

    function _markup() {
        return ''
            + '<div class="observability-panel-toolbar" role="group" aria-label="Decisions filters">'
            + '  <label class="observability-filter-label">Intent'
            + '    <input type="text" class="observability-filter-input" data-filter="intent" placeholder="ex: brain.test"/>'
            + '  </label>'
            + '  <label class="observability-filter-label">Status'
            + '    <select class="observability-filter-select" data-filter="status">'
            + '      <option value="">(qualquer)</option>'
            + '      <option value="completed">completed</option>'
            + '      <option value="owner_blocked">owner_blocked</option>'
            + '      <option value="owner_approved">owner_approved</option>'
            + '      <option value="owner_rejected">owner_rejected</option>'
            + '      <option value="error">error</option>'
            + '    </select>'
            + '  </label>'
            + '  <label class="observability-filter-label">Search'
            + '    <input type="text" class="observability-filter-input" data-filter="search" placeholder="rationale OR context"/>'
            + '  </label>'
            + '  <label class="observability-filter-label">Run id'
            + '    <input type="text" class="observability-filter-input" data-filter="run_id" placeholder="exact run_id"/>'
            + '  </label>'
            + '</div>'
            + '<div class="observability-error-banner" data-role="error" aria-live="polite"></div>'
            + '<div data-role="list-wrap"></div>'
            + '<div class="observability-pager">'
            + '  <span data-role="pager-info">—</span>'
            + '  <span>'
            + '    <button type="button" data-action="prev">‹ Anterior</button>'
            + '    <button type="button" data-action="next">Próximo ›</button>'
            + '  </span>'
            + '</div>';
    }

    function _ensureMarkup() {
        var host = document.querySelector(ROOT_SEL);
        if (!host) return null;
        if (!host.firstElementChild) host.innerHTML = _markup();
        return host;
    }

    function _wireOnce() {
        if (state.wired) return;
        var host = document.querySelector(ROOT_SEL);
        if (!host) return;
        state.wired = true;
        host.addEventListener("change", function (e) {
            var sel = e.target.closest('select[data-filter]');
            if (!sel) return;
            state.filters[sel.dataset.filter] = sel.value;
            state.offset = 0;
            render();
        });
        host.addEventListener("input", function (e) {
            var inp = e.target.closest('input[data-filter]');
            if (!inp) return;
            state.filters[inp.dataset.filter] = inp.value;
            state.offset = 0;
            clearTimeout(state._typingTimer);
            state._typingTimer = setTimeout(render, 400);
        });
        host.addEventListener("click", function (e) {
            var pager = e.target.closest('[data-action="prev"], [data-action="next"]');
            if (pager) {
                if (pager.dataset.action === "prev") state.offset = Math.max(0, state.offset - PAGE_SIZE);
                else state.offset = state.offset + PAGE_SIZE;
                render();
                return;
            }
            var row = e.target.closest("tr.is-expandable");
            if (row) {
                _toggleAccordion(row);
            }
        });
    }

    function _setBanner(msg) {
        var el = _$('[data-role="error"]');
        if (!el) return;
        if (msg) { el.textContent = msg; el.classList.add("active"); }
        else { el.textContent = ""; el.classList.remove("active"); }
    }

    function _toggleAccordion(row) {
        var runId = row.getAttribute("data-run-id");
        if (!runId) return;
        var next = row.nextElementSibling;
        var icon = row.querySelector(".observability-expand-icon");
        if (next && next.classList.contains("observability-accordion-row") && next.getAttribute("data-accordion-for") === runId) {
            // toggle hidden
            var nowHidden = !next.hidden;
            next.hidden = nowHidden;
            if (icon) icon.textContent = nowHidden ? "▶" : "▼";
            if (nowHidden) state.expanded.delete(runId);
            else state.expanded.add(runId);
        }
    }

    function _renderRow(run) {
        var tr = document.createElement("tr");
        tr.className = "is-expandable";
        tr.setAttribute("data-run-id", String(run.id));
        var isOpen = state.expanded.has(String(run.id));

        function td(content, opts) {
            var el = document.createElement("td");
            if (opts && opts.num) el.className = "col-num";
            if (typeof content === "string") el.textContent = content;
            else if (content instanceof Node) el.appendChild(content);
            return el;
        }

        var iconSpan = document.createElement("span");
        iconSpan.className = "observability-expand-icon";
        iconSpan.textContent = isOpen ? "▼" : "▶";
        var firstCellWrap = document.createElement("span");
        firstCellWrap.appendChild(iconSpan);
        firstCellWrap.appendChild(document.createTextNode(String(run.intent || "—")));
        var tdIntent = document.createElement("td");
        tdIntent.appendChild(firstCellWrap);

        tr.appendChild(tdIntent);
        tr.appendChild(td(String(run.final_state || "—")));
        tr.appendChild(td(String(run.decisions_count != null ? run.decisions_count : (run.decisions ? run.decisions.length : 0)), { num: true }));
        tr.appendChild(td(run.total_latency_ms != null ? Number(run.total_latency_ms).toFixed(0) + "ms" : "—", { num: true }));
        tr.appendChild(td(run.started_at || "—"));

        var idCell = document.createElement("td");
        idCell.style.fontFamily = "var(--font-mono)";
        idCell.style.fontSize = "0.78rem";
        idCell.textContent = String(run.id || "").slice(0, 12);
        tr.appendChild(idCell);

        return tr;
    }

    function _renderAccordion(run) {
        var tr = document.createElement("tr");
        tr.className = "observability-accordion-row";
        tr.setAttribute("data-accordion-for", String(run.id));
        tr.hidden = !state.expanded.has(String(run.id));
        var td = document.createElement("td");
        td.colSpan = 6;

        var decisions = run.decisions || [];
        if (!decisions.length) {
            var empty = document.createElement("p");
            empty.className = "observability-empty-row";
            empty.textContent = "Sem decisions registradas para este run.";
            td.appendChild(empty);
        } else {
            var subTable = document.createElement("table");
            subTable.className = "observability-subtable";
            var thead = document.createElement("thead");
            var theadRow = document.createElement("tr");
            ["#", "State", "Tool", "Rationale", "Latency"].forEach(function (h) {
                var th = document.createElement("th"); th.scope = "col"; th.textContent = h; theadRow.appendChild(th);
            });
            thead.appendChild(theadRow); subTable.appendChild(thead);
            var tbody = document.createElement("tbody");
            decisions.forEach(function (d) {
                var dRow = document.createElement("tr");
                function cell(text, cls) {
                    var c = document.createElement("td");
                    if (cls) c.className = cls;
                    c.textContent = text;
                    return c;
                }
                dRow.appendChild(cell(String(d.sequence != null ? d.sequence : "—")));
                dRow.appendChild(cell((d.state_from || "—") + " → " + (d.state_to || "—")));
                dRow.appendChild(cell(d.tool_invoked || "—"));
                dRow.appendChild(cell(String(d.rationale || "—"), "rationale-cell"));
                dRow.appendChild(cell(d.latency_ms != null ? Number(d.latency_ms).toFixed(0) + "ms" : "—"));
                tbody.appendChild(dRow);
            });
            subTable.appendChild(tbody);
            td.appendChild(subTable);
        }
        tr.appendChild(td);
        return tr;
    }

    function _renderTable(data) {
        var wrap = _$('[data-role="list-wrap"]');
        if (!wrap) return;
        wrap.textContent = "";
        var items = (data && data.items) || [];
        if (!items.length) {
            var empty = document.createElement("p");
            empty.className = "observability-empty-row";
            empty.textContent = "Sem brain_runs neste filtro.";
            wrap.appendChild(empty);
            return;
        }
        var tableWrap = document.createElement("div");
        tableWrap.className = "observability-table-wrap";
        var table = document.createElement("table");
        table.className = "observability-table";
        var thead = document.createElement("thead");
        var theadRow = document.createElement("tr");
        ["Intent", "Final state", "Decisions", "Latency", "Started", "Run id"].forEach(function (h) {
            var th = document.createElement("th"); th.scope = "col"; th.textContent = h; theadRow.appendChild(th);
        });
        thead.appendChild(theadRow); table.appendChild(thead);
        var tbody = document.createElement("tbody");
        items.forEach(function (run) {
            tbody.appendChild(_renderRow(run));
            tbody.appendChild(_renderAccordion(run));
        });
        table.appendChild(tbody);
        tableWrap.appendChild(table);
        wrap.appendChild(tableWrap);
    }

    function _renderPager(data) {
        var info = _$('[data-role="pager-info"]');
        if (info) {
            var start = data.total ? state.offset + 1 : 0;
            var end = Math.min(state.offset + PAGE_SIZE, data.total || 0);
            info.textContent = start + "–" + end + " / " + (data.total || 0) + " runs";
        }
        var prev = _$('[data-action="prev"]');
        var next = _$('[data-action="next"]');
        if (prev) prev.disabled = state.offset <= 0;
        if (next) next.disabled = (state.offset + PAGE_SIZE) >= (data.total || 0);
    }

    async function render() {
        _ensureMarkup();
        _wireOnce();
        // sync filter UI with state (skip when focused — avoid resetting input)
        ["intent", "search", "run_id"].forEach(function (k) {
            var inp = _$('input[data-filter="' + k + '"]');
            if (inp && document.activeElement !== inp) inp.value = state.filters[k];
        });
        var statusSel = _$('select[data-filter="status"]'); if (statusSel) statusSel.value = state.filters.status;
        _setBanner(null);

        var qsObj = { offset: state.offset, limit: PAGE_SIZE };
        ["intent", "search", "status", "run_id"].forEach(function (k) {
            if (state.filters[k]) qsObj[k] = state.filters[k];
        });
        var qs = new URLSearchParams(qsObj);
        try {
            var r = await fetch("/api/observability/decisions?" + qs.toString(), { headers: _authHeaders() });
            if (!r.ok) {
                _setBanner("Falha ao carregar decisions (HTTP " + r.status + ")");
                _renderTable({}); _renderPager({});
                return;
            }
            var data = await r.json();
            state.total = data.total || 0;
            _renderTable(data);
            _renderPager(data);
        } catch (e) {
            _setBanner("Erro de rede: " + (e && e.message ? e.message : e));
        }
    }

    function destroy() {
        if (state._typingTimer) { clearTimeout(state._typingTimer); state._typingTimer = null; }
    }

    window.ObservabilityDecisions = { render: render, destroy: destroy };
})();
