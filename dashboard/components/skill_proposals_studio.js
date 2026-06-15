/* ============================================================
   Skill Proposals Studio (F.4.3 C1) — 3-pane Mission Control
   ============================================================
   D1 Monaco editor 0.45+ lazy-load (vendor /dashboard/vendor/monaco)
   D2 Toggle split↔unified diff (Monaco diffEditor renderSideBySide)
   D6 3-pane layout: sidebar list / center editor / right rationale+actions

   API pública: window.SkillProposalsStudio.{init, render, destroy,
                                              selectProposal, refreshList}

   Padrão IIFE (REUSE pipeline_studio_shell.js F.9.3).
   WS event handler enganchado em app.js handleWSEvent (F.4.3 C2 expande).
   ============================================================ */
(function () {
    "use strict";

    var VENDOR_BASE = "/dashboard/vendor/monaco/min/vs";
    var DIFF_PREF_KEY = "f43_diff_mode";
    var FILTER_PREF_KEY = "f43_filter_status";

    var STATUS_FILTERS = [
        { key: "all",          label: "Todos" },
        { key: "draft",        label: "Draft" },
        { key: "lab_running",  label: "Lab Running" },
        { key: "lab_passed",   label: "Lab Passed" },
        { key: "lab_failed",   label: "Lab Failed" },
        { key: "pr_open",      label: "PR Open" },
        { key: "pr_merged",    label: "PR Merged" },
        { key: "archived",     label: "Rejected" },
    ];

    /* F.4.3 C2 W4 — WS dedup + throttle config */
    var WS_DEDUP_WINDOW_MS = 500;     /* skip identical event payloads inside window */
    var WS_DEDUP_LRU_CAP   = 100;     /* cap Set size, evict oldest on overflow */
    var WS_REFRESH_DEBOUNCE_MS = 250; /* coalesce burst of WS events into 1 refresh */

    var _state = {
        initialized: false,
        root: null,
        proposals: [],
        selectedId: null,
        selectedDetail: null,
        filterStatus: "all",
        searchQuery: "",
        loading: false,
        monacoLoaded: false,
        monacoLoading: null,
        editor: null,
        diffEditor: null,
        diffMode: "unified",
        existingYaml: "",
        /* C2 W4 — WS RT throttle/dedup */
        wsDedupSet: new Map(),       /* hash → timestamp insert order; Map iter preserves insertion */
        wsRefreshTimer: null,
        wsRefreshSelectedId: null,
        wsLastTickAt: 0,
        wsDedupSkipped: 0,
        /* C2 lab tree expand state — keys collapsed by default except status+latency */
        labTreeOpen: { status: true, latency_ms: true, ok: true },
    };

    /* ---- C2 W4 — WS dedup + throttle helpers ------------- */

    function _wsEventHash(event) {
        if (!event || !event.event_type) return null;
        var p = event.payload || {};
        return event.event_type + ":" + (p.proposal_id || p.run_id || "") + ":" + (p.status || p.new_status || "");
    }

    function _wsDedupSeen(hash) {
        if (!hash) return false;
        var now = Date.now();
        var prev = _state.wsDedupSet.get(hash);
        if (prev != null && (now - prev) < WS_DEDUP_WINDOW_MS) {
            _state.wsDedupSkipped += 1;
            return true;
        }
        _state.wsDedupSet.set(hash, now);
        /* LRU cap — evict oldest (Map keeps insertion order). */
        if (_state.wsDedupSet.size > WS_DEDUP_LRU_CAP) {
            var firstKey = _state.wsDedupSet.keys().next().value;
            _state.wsDedupSet.delete(firstKey);
        }
        return false;
    }

    function _scheduleWsRefresh(payload) {
        if (payload && payload.proposal_id && payload.proposal_id === _state.selectedId) {
            _state.wsRefreshSelectedId = payload.proposal_id;
        }
        if (_state.wsRefreshTimer) return; /* already scheduled */
        _state.wsRefreshTimer = setTimeout(function () {
            _state.wsRefreshTimer = null;
            var reselect = _state.wsRefreshSelectedId;
            _state.wsRefreshSelectedId = null;
            refreshList();
            if (reselect) selectProposal(reselect);
        }, WS_REFRESH_DEBOUNCE_MS);
    }

    /* ---- helpers ---------------------------------------- */

    function _$(sel) {
        return _state.root ? _state.root.querySelector(sel) : document.querySelector(sel);
    }

    function _escape(s) {
        if (s == null) return "";
        return String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function _authToken() {
        try { return localStorage.getItem("hermes_token") || ""; }
        catch (e) { return ""; }
    }

    function _apiFetch(url, options) {
        var opts = options || {};
        opts.headers = Object.assign({
            "Content-Type": "application/json",
            "X-Hermes-Token": _authToken(),
        }, opts.headers || {});
        return fetch(url, opts);
    }

    function _toast(msg, kind) {
        if (typeof window.toast === "function") {
            window.toast(msg, kind || "info");
        } else {
            console.log("[SkillProposals]", msg);
        }
    }

    function _loadDiffPref() {
        try {
            var v = localStorage.getItem(DIFF_PREF_KEY);
            return (v === "split" || v === "unified") ? v : "unified";
        } catch (e) { return "unified"; }
    }

    function _saveDiffPref(mode) {
        try { localStorage.setItem(DIFF_PREF_KEY, mode); }
        catch (e) {}
    }

    function _loadFilterPref() {
        try {
            var v = localStorage.getItem(FILTER_PREF_KEY);
            return v || "all";
        } catch (e) { return "all"; }
    }

    function _saveFilterPref(f) {
        try { localStorage.setItem(FILTER_PREF_KEY, f); }
        catch (e) {}
    }

    function _stampRefresh() {
        var el = _$("#sp-last-refresh");
        if (!el) return;
        var now = new Date();
        var hh = String(now.getHours()).padStart(2, "0");
        var mm = String(now.getMinutes()).padStart(2, "0");
        var ss = String(now.getSeconds()).padStart(2, "0");
        el.textContent = "Atualizado " + hh + ":" + mm + ":" + ss;
    }

    /* ---- Monaco lazy loader ----------------------------- */

    function _loadMonaco() {
        if (_state.monacoLoaded) return Promise.resolve(window.monaco);
        if (_state.monacoLoading) return _state.monacoLoading;

        _state.monacoLoading = new Promise(function (resolve, reject) {
            var existing = document.getElementById("monaco-loader-script");
            function _afterLoaderReady() {
                try {
                    /* Configure base path for AMD modules */
                    window.require.config({ paths: { "vs": VENDOR_BASE } });
                    /* Worker shim: serve workerMain from same vendor */
                    window.MonacoEnvironment = {
                        getWorkerUrl: function () {
                            return "data:text/javascript;charset=utf-8," + encodeURIComponent(
                                "self.MonacoEnvironment = { baseUrl: '" + window.location.origin + VENDOR_BASE + "' };\n" +
                                "importScripts('" + window.location.origin + VENDOR_BASE + "/base/worker/workerMain.js');"
                            );
                        },
                    };
                    window.require(["vs/editor/editor.main"], function () {
                        _state.monacoLoaded = true;
                        resolve(window.monaco);
                    });
                } catch (err) {
                    reject(err);
                }
            }
            if (existing && window.require && typeof window.require.config === "function") {
                _afterLoaderReady();
                return;
            }
            var script = document.createElement("script");
            script.id = "monaco-loader-script";
            script.src = VENDOR_BASE + "/loader.js";
            script.async = true;
            script.onload = _afterLoaderReady;
            script.onerror = function () { reject(new Error("monaco_loader_failed")); };
            document.head.appendChild(script);
        });

        return _state.monacoLoading;
    }

    /* ---- Sidebar list ----------------------------------- */

    function _renderSidebar() {
        var listEl = _$("#sp-list");
        if (!listEl) return;

        var items = _state.proposals;
        var q = (_state.searchQuery || "").trim().toLowerCase();
        if (q) {
            items = items.filter(function (p) {
                return (p.name || "").toLowerCase().indexOf(q) !== -1;
            });
        }

        if (!items.length) {
            listEl.innerHTML = '<div class="sp-list-empty">Sem proposals para o filtro atual.</div>';
            return;
        }

        /* APG listbox roving tabindex — só o selected (ou primeiro como fallback) recebe 0. */
        var rovingIdx = -1;
        if (_state.selectedId) {
            for (var i = 0; i < items.length; i++) {
                if (items[i].id === _state.selectedId) { rovingIdx = i; break; }
            }
        }
        if (rovingIdx === -1) rovingIdx = 0;

        var html = items.map(function (p, idx) {
            var status = p.status || "draft";
            var selected = (p.id === _state.selectedId) ? "true" : "false";
            var tabidx = (idx === rovingIdx) ? "0" : "-1";
            return (
                '<div class="sp-card" role="option" tabindex="' + tabidx + '" data-id="' + _escape(p.id) + '" aria-selected="' + selected + '">' +
                    '<h4 class="sp-card-title">' + _escape(p.name || "(sem nome)") + '</h4>' +
                    '<div class="sp-card-meta">' +
                        '<span class="sp-status-badge sp-status-' + _escape(status) + '">' + _escape(status) + '</span>' +
                        '<span>' + _escape(p.source_pattern || "") + '</span>' +
                    '</div>' +
                '</div>'
            );
        }).join("");

        listEl.innerHTML = html;
    }

    function _wireSidebarEvents() {
        var listEl = _$("#sp-list");
        if (!listEl) return;
        listEl.addEventListener("click", function (e) {
            var card = e.target.closest(".sp-card");
            if (!card) return;
            var id = card.dataset.id;
            if (id) selectProposal(id);
        });
        listEl.addEventListener("keydown", function (e) {
            if (e.key !== "Enter" && e.key !== " ") return;
            var card = e.target.closest(".sp-card");
            if (!card) return;
            e.preventDefault();
            var id = card.dataset.id;
            if (id) selectProposal(id);
        });
    }

    function _wireFilters() {
        var chipsEl = _$("#sp-filter-chips");
        if (chipsEl) {
            chipsEl.addEventListener("click", function (e) {
                var btn = e.target.closest(".sp-chip[data-filter]");
                if (!btn) return;
                _setFilter(btn.dataset.filter);
            });
            chipsEl.addEventListener("keydown", function (e) {
                if (e.key === "Enter" || e.key === " ") {
                    var btn = e.target.closest(".sp-chip[data-filter]");
                    if (!btn) return;
                    e.preventDefault();
                    _setFilter(btn.dataset.filter);
                    return;
                }
                _handleChipsKeydown(e);
            });
        }
        var searchEl = _$("#sp-search");
        if (searchEl) {
            var debounceTimer = null;
            searchEl.addEventListener("input", function (e) {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(function () {
                    _state.searchQuery = e.target.value || "";
                    _renderSidebar();
                }, 180);
            });
        }
    }

    function _setFilter(filter) {
        if (_state.filterStatus === filter) return;
        _state.filterStatus = filter;
        _saveFilterPref(filter);
        _updateFilterChips();
        refreshList();
    }

    function _updateFilterChips() {
        var chipsEl = _$("#sp-filter-chips");
        if (!chipsEl) return;
        var chips = chipsEl.querySelectorAll(".sp-chip[data-filter]");
        chips.forEach(function (c) {
            var on = (c.dataset.filter === _state.filterStatus);
            c.setAttribute("aria-checked", on ? "true" : "false");
            c.setAttribute("tabindex", on ? "0" : "-1");
        });
    }

    /* C2 W6 — arrow-key roving navigation per APG radiogroup pattern. */
    function _handleChipsKeydown(e) {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight"
            && e.key !== "ArrowUp"   && e.key !== "ArrowDown"
            && e.key !== "Home"      && e.key !== "End") return;
        var chipsEl = _$("#sp-filter-chips");
        if (!chipsEl) return;
        var chips = Array.from(chipsEl.querySelectorAll(".sp-chip[data-filter]"));
        if (!chips.length) return;
        var idx = chips.indexOf(document.activeElement);
        if (idx === -1) return;
        e.preventDefault();
        var next = idx;
        if (e.key === "ArrowLeft" || e.key === "ArrowUp")   next = (idx - 1 + chips.length) % chips.length;
        if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (idx + 1) % chips.length;
        if (e.key === "Home") next = 0;
        if (e.key === "End")  next = chips.length - 1;
        chips[next].focus();
        var f = chips[next].dataset.filter;
        if (f) _setFilter(f);
    }

    /* ---- Center pane (editor + diff) -------------------- */

    function _renderCenterEmpty() {
        var titleEl = _$("#sp-center-title");
        if (titleEl) titleEl.textContent = "Selecione um proposal";
        var diffToggle = _$("#sp-diff-toggle");
        if (diffToggle) diffToggle.setAttribute("hidden", "");
        var container = _$("#sp-editor-container");
        if (container) container.innerHTML = '<div class="sp-editor-empty">Sem proposal selecionado.</div>';
        _disposeEditors();
    }

    function _renderCenterLoading() {
        var container = _$("#sp-editor-container");
        if (container) container.innerHTML = '<div class="sp-editor-loading">Carregando Monaco editor…</div>';
    }

    function _disposeEditors() {
        try { if (_state.editor) { _state.editor.dispose(); _state.editor = null; } }
        catch (e) { _state.editor = null; }
        try { if (_state.diffEditor) { _state.diffEditor.dispose(); _state.diffEditor = null; } }
        catch (e) { _state.diffEditor = null; }
    }

    function _mountEditor(monaco, yaml) {
        var container = _$("#sp-editor-container");
        if (!container) return;
        _disposeEditors();
        container.innerHTML = "";
        _state.editor = monaco.editor.create(container, {
            value: yaml || "",
            language: "yaml",
            theme: "vs-dark",
            readOnly: true,
            automaticLayout: true,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            fontSize: 13,
        });
    }

    function _mountDiffEditor(monaco, oldYaml, newYaml, sideBySide) {
        var container = _$("#sp-editor-container");
        if (!container) return;
        _disposeEditors();
        container.innerHTML = "";
        _state.diffEditor = monaco.editor.createDiffEditor(container, {
            theme: "vs-dark",
            readOnly: true,
            automaticLayout: true,
            renderSideBySide: !!sideBySide,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            fontSize: 13,
        });
        _state.diffEditor.setModel({
            original: monaco.editor.createModel(oldYaml || "", "yaml"),
            modified: monaco.editor.createModel(newYaml || "", "yaml"),
        });
    }

    function _wireDiffToggle() {
        var toggleEl = _$("#sp-diff-toggle");
        if (!toggleEl) return;
        toggleEl.addEventListener("click", function (e) {
            var btn = e.target.closest(".sp-chip[data-diff]");
            if (!btn) return;
            var mode = btn.dataset.diff;
            if (mode === _state.diffMode) return;
            _state.diffMode = mode;
            _saveDiffPref(mode);
            _updateDiffChips();
            _renderCenterContent();
        });
    }

    function _updateDiffChips() {
        var toggleEl = _$("#sp-diff-toggle");
        if (!toggleEl) return;
        toggleEl.querySelectorAll(".sp-chip[data-diff]").forEach(function (c) {
            c.setAttribute("aria-pressed", c.dataset.diff === _state.diffMode ? "true" : "false");
        });
    }

    function _renderCenterContent() {
        var detail = _state.selectedDetail;
        if (!detail) { _renderCenterEmpty(); return; }
        var titleEl = _$("#sp-center-title");
        if (titleEl) titleEl.textContent = detail.name + " — " + (detail.status || "draft");
        var diffToggle = _$("#sp-diff-toggle");
        if (diffToggle) diffToggle.removeAttribute("hidden");
        _updateDiffChips();
        _renderCenterLoading();

        _loadMonaco().then(function (monaco) {
            if (_state.diffMode === "unified" || _state.diffMode === "split") {
                _mountDiffEditor(monaco, _state.existingYaml, detail.yaml_blob || "", _state.diffMode === "split");
            } else {
                _mountEditor(monaco, detail.yaml_blob || "");
            }
        }).catch(function (err) {
            console.error("[SkillProposals] Monaco load failed", err);
            var container = _$("#sp-editor-container");
            if (container) {
                container.innerHTML = '<div class="sp-editor-empty">Falha ao carregar Monaco. <br>Veja console para detalhes.</div>';
            }
        });
    }

    /* ---- Right pane (rationale + actions) --------------- */

    function _renderRightEmpty() {
        var bodyEl = _$("#sp-right-body");
        if (!bodyEl) return;
        bodyEl.innerHTML = '<div class="sp-empty-state">Selecione um proposal para ver rationale + ações.</div>';
    }

    function _renderRight() {
        var detail = _state.selectedDetail;
        if (!detail) { _renderRightEmpty(); return; }
        var bodyEl = _$("#sp-right-body");
        if (!bodyEl) return;

        var rationale = detail.description || "(sem descrição/rationale)";
        var labResult = detail.lab_test_result;
        var labParsed = null;
        if (labResult) {
            try {
                labParsed = (typeof labResult === "string") ? JSON.parse(labResult) : labResult;
            } catch (e) {
                labParsed = { raw: String(labResult) };
            }
        }
        var labTreeHtml = labParsed ? _renderLabTree(labParsed) : "";

        var prRow = "";
        if (detail.pr_url) {
            /* Defense in depth — only allow http(s) schemes (no javascript: / data:) */
            var safeUrl = /^https?:\/\//i.test(detail.pr_url) ? detail.pr_url : "#";
            prRow = '<div class="sp-meta-row"><span class="sp-meta-key">PR</span>' +
                    '<a class="sp-pr-link" href="' + _escape(safeUrl) + '" target="_blank" rel="noopener noreferrer">' + _escape(safeUrl) + '</a></div>';
        }

        var status = detail.status || "draft";
        var canDecide = (status === "draft" || status === "lab_passed");
        var canRunWorkflow = (status === "lab_passed" || status === "draft");

        bodyEl.innerHTML = (
            '<div>' +
                '<h4 class="sp-section-title">Status</h4>' +
                '<div class="sp-meta-list">' +
                    '<div class="sp-meta-row"><span class="sp-meta-key">Estado</span><span class="sp-status-badge sp-status-' + _escape(status) + '">' + _escape(status) + '</span></div>' +
                    '<div class="sp-meta-row"><span class="sp-meta-key">Source</span><span class="sp-meta-val">' + _escape(detail.source_pattern || "—") + '</span></div>' +
                    '<div class="sp-meta-row"><span class="sp-meta-key">Lab</span><span class="sp-meta-val">' + _escape(detail.lab_test_status || "pending") + '</span></div>' +
                    '<div class="sp-meta-row"><span class="sp-meta-key">PR</span><span class="sp-meta-val">' + _escape(detail.pr_status || "not_created") + '</span></div>' +
                    prRow +
                '</div>' +
            '</div>' +
            '<div>' +
                '<h4 class="sp-section-title">Brain rationale</h4>' +
                '<div class="sp-rationale">' + _escape(rationale) + '</div>' +
            '</div>' +
            (labTreeHtml ? (
                '<div>' +
                    '<h4 class="sp-section-title">Lab result</h4>' +
                    '<div class="sp-lab-tree" id="sp-lab-tree" role="tree" aria-label="Lab result details">' +
                        labTreeHtml +
                    '</div>' +
                '</div>'
            ) : "") +
            '<div class="sp-actions">' +
                '<button class="sp-btn sp-btn-primary" id="sp-btn-accept" type="button" ' + (canDecide ? "" : "disabled") + ' aria-label="Aceitar proposal e disparar lab + PR">✓ Accept</button>' +
                '<button class="sp-btn sp-btn-danger" id="sp-btn-reject" type="button" ' + (canDecide ? "" : "disabled") + ' aria-label="Rejeitar proposal com motivo">✗ Reject</button>' +
                '<button class="sp-btn" id="sp-btn-runworkflow" type="button" ' + (canRunWorkflow ? "" : "disabled") + ' aria-label="Disparar workflow de sintetização agora">⚡ Run Workflow Now</button>' +
            '</div>'
        );

        _wireActionButtons();
        _wireLabTree();
    }

    /* ---- C2 — Lab result JSON tree (collapsible) -------- */

    function _renderLabTree(obj) {
        if (obj == null) return "";
        var keys = Object.keys(obj);
        if (!keys.length) return '<div class="sp-tree-empty">(vazio)</div>';
        return keys.map(function (k) {
            var v = obj[k];
            return _renderTreeNode(k, v);
        }).join("");
    }

    function _renderTreeNode(key, value) {
        var open = (_state.labTreeOpen[key] === true) ? "true" : "false";
        var isObj = (value && typeof value === "object" && !Array.isArray(value));
        var isArr = Array.isArray(value);
        var preview;
        var body;
        if (isObj) {
            preview = "{" + Object.keys(value).length + " keys}";
            body = '<div class="sp-tree-children" ' + (open === "true" ? "" : "hidden") + '>' + _renderLabTree(value) + '</div>';
        } else if (isArr) {
            preview = "[" + value.length + "]";
            var arrChildren = value.map(function (item, i) {
                return _renderTreeNode("[" + i + "]", item);
            }).join("");
            body = '<div class="sp-tree-children" ' + (open === "true" ? "" : "hidden") + '>' + arrChildren + '</div>';
        } else {
            preview = _formatLeaf(value);
            body = "";
        }
        var hasChildren = isObj || isArr;
        /* APG: aria-expanded MUST be absent on non-expandable treeitems (leaves). */
        var expandedAttr = hasChildren ? (' aria-expanded="' + open + '"') : "";
        var chev = hasChildren ? ('<span class="sp-tree-chev" aria-hidden="true">' + (open === "true" ? "▼" : "▶") + '</span>') : '<span class="sp-tree-chev sp-tree-chev-leaf" aria-hidden="true">•</span>';
        return (
            '<div class="sp-tree-node" role="treeitem"' + expandedAttr + '>' +
                '<div class="sp-tree-row" tabindex="0" data-key="' + _escape(key) + '" data-toggleable="' + (hasChildren ? "1" : "0") + '">' +
                    chev +
                    '<span class="sp-tree-key">' + _escape(key) + '</span>' +
                    '<span class="sp-tree-preview">' + _escape(preview) + '</span>' +
                '</div>' +
                body +
            '</div>'
        );
    }

    function _formatLeaf(v) {
        if (v == null) return String(v);
        if (typeof v === "string") {
            return v.length > 200 ? (v.substring(0, 200) + "…") : v;
        }
        if (typeof v === "number" || typeof v === "boolean") return String(v);
        try { return JSON.stringify(v); } catch (e) { return String(v); }
    }

    function _wireLabTree() {
        var treeEl = _$("#sp-lab-tree");
        if (!treeEl) return;
        function toggleRow(row) {
            if (!row || row.dataset.toggleable !== "1") return;
            var node = row.parentElement;
            var children = node.querySelector(":scope > .sp-tree-children");
            var chev = row.querySelector(".sp-tree-chev");
            var willOpen = node.getAttribute("aria-expanded") !== "true";
            node.setAttribute("aria-expanded", willOpen ? "true" : "false");
            _state.labTreeOpen[row.dataset.key] = willOpen;
            if (children) {
                if (willOpen) children.removeAttribute("hidden");
                else children.setAttribute("hidden", "");
            }
            if (chev) chev.textContent = willOpen ? "▼" : "▶";
        }
        treeEl.addEventListener("click", function (e) {
            var row = e.target.closest(".sp-tree-row");
            toggleRow(row);
        });
        treeEl.addEventListener("keydown", function (e) {
            if (e.key !== "Enter" && e.key !== " ") return;
            var row = e.target.closest(".sp-tree-row");
            if (!row) return;
            e.preventDefault();
            toggleRow(row);
        });
    }

    function _wireActionButtons() {
        var acceptBtn = _$("#sp-btn-accept");
        if (acceptBtn) {
            acceptBtn.addEventListener("click", function () {
                if (window.SkillProposalsModal && _state.selectedDetail) {
                    window.SkillProposalsModal.openAccept(_state.selectedDetail);
                }
            });
        }
        var rejectBtn = _$("#sp-btn-reject");
        if (rejectBtn) {
            rejectBtn.addEventListener("click", function () {
                if (window.SkillProposalsModal && _state.selectedDetail) {
                    window.SkillProposalsModal.openReject(_state.selectedDetail);
                }
            });
        }
        var runBtn = _$("#sp-btn-runworkflow");
        if (runBtn) {
            runBtn.addEventListener("click", function () {
                if (window.SkillProposalsModal && _state.selectedDetail) {
                    window.SkillProposalsModal.openPath1(_state.selectedDetail);
                }
            });
        }
    }

    /* ---- API calls -------------------------------------- */

    function refreshList() {
        var url = "/api/skills/proposals?limit=200";
        if (_state.filterStatus && _state.filterStatus !== "all") {
            url += "&status=" + encodeURIComponent(_state.filterStatus);
        }
        _state.loading = true;
        return _apiFetch(url)
            .then(function (r) { if (!r.ok) throw new Error("http_" + r.status); return r.json(); })
            .then(function (data) {
                _state.proposals = (data && data.items) ? data.items : [];
                _renderSidebar();
                _stampRefresh();
            })
            .catch(function (err) {
                console.error("[SkillProposals] list failed", err);
                _toast("Falha ao carregar proposals: " + err.message, "error");
            })
            .finally(function () { _state.loading = false; });
    }

    function selectProposal(proposalId) {
        if (!proposalId) return;
        _state.selectedId = proposalId;
        _renderSidebar();
        _renderCenterLoading();

        _apiFetch("/api/skills/proposals/" + encodeURIComponent(proposalId))
            .then(function (r) { if (!r.ok) throw new Error("http_" + r.status); return r.json(); })
            .then(function (detail) {
                _state.selectedDetail = detail;
                _state.existingYaml = "";
                _renderCenterContent();
                _renderRight();
                /* fetch closest existing skill yaml for diff (best-effort) */
                return _apiFetch("/api/skills/proposals/" + encodeURIComponent(proposalId) + "/yaml-preview")
                    .then(function (r) { return r.ok ? r.json() : null; })
                    .catch(function () { return null; });
            })
            .then(function (preview) {
                if (preview && preview.existing_yaml) {
                    _state.existingYaml = preview.existing_yaml;
                    _renderCenterContent();
                }
            })
            .catch(function (err) {
                console.error("[SkillProposals] detail failed", err);
                _toast("Falha ao carregar proposal: " + err.message, "error");
                _renderCenterEmpty();
                _renderRightEmpty();
            });
    }

    /* ---- WS event handler (called by app.js) ------------- */

    function handleWSEvent(event) {
        if (!event || !event.event_type) return;
        var t = event.event_type;
        var relevant = (
            t === "brain.skill_proposal_created"
            || t === "brain.skill_proposal_updated"
            || t === "brain.skill_proposal_rejected"
            || t === "brain.skill_lab_done"
            || t === "brain.skill_pr_dispatched"
            || t === "brain.skill_synthesis_queued"
            || t === "brain.skill_synthesis_completed"
        );
        if (!relevant) return;

        /* C2 W4 — dedup identical events inside 500ms window. */
        var hash = _wsEventHash(event);
        if (_wsDedupSeen(hash)) return;

        /* C2 W4 — debounce refresh into single 250ms window (coalesce burst). */
        _scheduleWsRefresh(event.payload || {});
    }

    /* ---- Init / destroy --------------------------------- */

    function _renderShell() {
        if (!_state.root) return;
        /* C2 W6 — filter chips refactored to APG radiogroup pattern.
           Mutually-exclusive single-select → role=radio + aria-checked.
           Roving tabindex: only the checked radio is tabbable. */
        var filterChipsHtml = STATUS_FILTERS.map(function (f) {
            var checked = (f.key === _state.filterStatus);
            var tabidx = checked ? "0" : "-1";
            return '<button class="sp-chip" data-filter="' + _escape(f.key) +
                   '" type="button" role="radio" aria-checked="' + (checked ? "true" : "false") +
                   '" tabindex="' + tabidx +
                   '" aria-label="Filtro: ' + _escape(f.label) + '">' + _escape(f.label) + '</button>';
        }).join("");

        _state.root.innerHTML = (
            '<div class="sp-page">' +
                '<header class="sp-header">' +
                    '<h2 class="sp-title">Skill Proposals</h2>' +
                    '<div class="sp-header-actions">' +
                        '<span id="sp-last-refresh" class="sp-last-refresh" aria-live="polite">—</span>' +
                        '<button class="sp-btn" id="sp-btn-refresh" type="button" aria-label="Atualizar lista de proposals">↻ Atualizar</button>' +
                    '</div>' +
                '</header>' +
                '<div class="sp-body">' +
                    '<aside class="sp-pane-sidebar" aria-label="Lista de proposals">' +
                        '<div class="sp-sidebar-header">' +
                            '<div class="sp-filter-chips" id="sp-filter-chips" role="radiogroup" aria-label="Filtrar proposals por status">' +
                                filterChipsHtml +
                            '</div>' +
                            '<input type="search" class="sp-search" id="sp-search" placeholder="Buscar por nome..." aria-label="Buscar proposal por nome">' +
                        '</div>' +
                        '<div class="sp-list" id="sp-list" role="listbox" aria-label="Skill proposals"></div>' +
                    '</aside>' +
                    '<section class="sp-pane-center" aria-label="Editor YAML">' +
                        '<div class="sp-center-header">' +
                            '<h3 class="sp-center-title" id="sp-center-title">Selecione um proposal</h3>' +
                            '<div class="sp-diff-toggle" id="sp-diff-toggle" role="group" aria-label="Modo de diff" hidden>' +
                                '<button class="sp-chip" data-diff="unified" type="button" aria-pressed="true">Unified</button>' +
                                '<button class="sp-chip" data-diff="split" type="button" aria-pressed="false">Split</button>' +
                            '</div>' +
                        '</div>' +
                        '<div class="sp-editor-container" id="sp-editor-container">' +
                            '<div class="sp-editor-empty">Sem proposal selecionado.</div>' +
                        '</div>' +
                    '</section>' +
                    '<aside class="sp-pane-right" aria-label="Detalhes e ações">' +
                        '<div class="sp-right-header">Detalhes</div>' +
                        '<div class="sp-right-body" id="sp-right-body">' +
                            '<div class="sp-empty-state">Selecione um proposal para ver rationale + ações.</div>' +
                        '</div>' +
                    '</aside>' +
                '</div>' +
            '</div>'
        );
    }

    function init(rootSelector) {
        if (_state.initialized) { render(); return; }
        var root = document.querySelector(rootSelector || "[data-component='skill-proposals-studio']");
        if (!root) return;
        _state.root = root;
        _state.initialized = true;
        _state.diffMode = _loadDiffPref();
        _state.filterStatus = _loadFilterPref();

        _renderShell();

        /* wire interactions */
        _wireSidebarEvents();
        _wireFilters();
        _wireDiffToggle();
        var refreshBtn = _$("#sp-btn-refresh");
        if (refreshBtn) refreshBtn.addEventListener("click", function () { refreshList(); });

        refreshList();
    }

    function render() {
        if (!_state.initialized) return;
        refreshList();
    }

    function destroy() {
        _disposeEditors();
        if (_state.root) _state.root.innerHTML = "";
        _state.initialized = false;
        _state.root = null;
        _state.selectedId = null;
        _state.selectedDetail = null;
        _state.proposals = [];
    }

    /* ---- Public API ------------------------------------- */

    window.SkillProposalsStudio = {
        init: init,
        render: render,
        destroy: destroy,
        selectProposal: selectProposal,
        refreshList: refreshList,
        handleWSEvent: handleWSEvent,
    };

})();
