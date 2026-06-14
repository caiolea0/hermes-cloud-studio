/* ============================================================
   Hermes Cloud Studio — BrainConfirmCard (F.6.4)
   ============================================================
   Renderer pra summary card individual de pending owner-blocked run.

   Decisão D7 cristalizada: summary card 3 lines (what / why / cost +
   iterations) + expand <details> ReAct trace via GET /api/brain/runs/{id}.
   D2 approve/deny + optional 500-char textarea (auto-show ao clicar).

   API global: window.BrainConfirmCard.{render, escape}
   Render contract: render(run, opts) -> HTMLElement
     run: {run_id, intent, action_class, confidence, confirm_reason,
           started_at, summary_card: {what, why, cost, iterations}}
     opts: {onAction(runId, action, comment)} callback que faz POST /confirm

   XSS: TODOS valores via textContent. ZERO innerHTML em conteúdo dinâmico.
   DOMPurify fallback se houver HTML embebido (não usado aqui — defesa).
   Accessibility: ARIA buttons + aria-label clear + keyboard focusable nativo.
   ============================================================ */
(function () {
    "use strict";

    function _conf_class(c) {
        if (c >= 0.8) return "conf-high";
        if (c >= 0.5) return "conf-mid";
        return "conf-low";
    }

    function _fmt_pct(c) {
        return Math.round((c || 0) * 100) + "%";
    }

    function _fmt_cost(c) {
        if (!c) return "0";
        if (c < 0.01) return c.toFixed(4);
        return c.toFixed(2);
    }

    function _make_el(tag, attrs, text) {
        var el = document.createElement(tag);
        if (attrs) {
            Object.keys(attrs).forEach(function (k) {
                if (k === "className") el.className = attrs[k];
                else if (k === "dataset") {
                    Object.keys(attrs[k]).forEach(function (dk) { el.dataset[dk] = attrs[k][dk]; });
                } else {
                    el.setAttribute(k, attrs[k]);
                }
            });
        }
        if (text != null) el.textContent = String(text);
        return el;
    }

    function _build_summary(run) {
        var sc = run.summary_card || {};
        var wrap = _make_el("div", { className: "brain-confirm-summary" });

        var pWhat = _make_el("p");
        pWhat.appendChild(_make_el("strong", null, "O que:"));
        pWhat.appendChild(document.createTextNode(" " + (sc.what || "—")));
        wrap.appendChild(pWhat);

        if (sc.why) {
            var pWhy = _make_el("p");
            pWhy.appendChild(_make_el("strong", null, "Por que confirm:"));
            pWhy.appendChild(document.createTextNode(" " + sc.why));
            wrap.appendChild(pWhy);
        }

        var pCost = _make_el("p");
        pCost.appendChild(_make_el("strong", null, "Custo/iter:"));
        var iters = (sc.iterations != null) ? sc.iterations : 0;
        pCost.appendChild(document.createTextNode(" " + _fmt_cost(sc.cost) + " credits · " + iters + " iter"));
        wrap.appendChild(pCost);

        return wrap;
    }

    function _build_trace(run) {
        var details = _make_el("details", { className: "brain-confirm-trace" });
        var summary = _make_el("summary", null, "Expandir ReAct trace");
        details.appendChild(summary);
        var content = _make_el("div", { className: "brain-confirm-trace-content", "data-trace": "1" }, "Clique pra carregar...");
        details.appendChild(content);

        details.addEventListener("toggle", function () {
            if (!details.open || content.dataset.loaded === "1") return;
            content.textContent = "Carregando...";
            var token = localStorage.getItem("hermes_token") || "";
            fetch("/api/brain/runs/" + encodeURIComponent(run.run_id), {
                headers: { "X-Hermes-Token": token },
            })
                .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
                .then(function (data) {
                    content.dataset.loaded = "1";
                    var decisions = (data && data.decisions) || [];
                    if (!decisions.length) { content.textContent = "(no decisions persisted)"; return; }
                    var lines = decisions.map(function (d) {
                        var prefix = "[" + d.sequence + "] " + d.state_from + "→" + d.state_to;
                        var tool = d.tool_invoked ? "  tool=" + d.tool_invoked : "";
                        var rationale = d.rationale ? "\n    " + d.rationale : "";
                        return prefix + tool + rationale;
                    });
                    content.textContent = lines.join("\n");
                })
                .catch(function (err) {
                    content.textContent = "(erro carregando trace: " + err + ")";
                });
        });
        return details;
    }

    function _build_actions(card, run, onAction) {
        var actions = _make_el("div", { className: "brain-confirm-actions" });

        var btnApprove = _make_el("button", {
            type: "button",
            className: "brain-confirm-btn brain-confirm-btn-approve",
            "data-action": "approve",
            "aria-label": "Aprovar run " + run.run_id,
        }, "Aprovar");

        var btnDeny = _make_el("button", {
            type: "button",
            className: "brain-confirm-btn brain-confirm-btn-deny",
            "data-action": "deny",
            "aria-label": "Negar run " + run.run_id,
        }, "Negar");

        var btnCancel = _make_el("button", {
            type: "button",
            className: "brain-confirm-btn brain-confirm-btn-cancel",
            "data-action": "cancel",
            "aria-label": "Cancelar run " + run.run_id,
        }, "Cancelar run");

        actions.appendChild(btnApprove);
        actions.appendChild(btnDeny);
        actions.appendChild(btnCancel);

        // Comment input (D2) — collapsed by default; expands when btn clicked
        var commentWrap = _make_el("div", { className: "brain-confirm-comment", hidden: "" });
        var textarea = _make_el("textarea", {
            maxlength: "500",
            placeholder: "Comentário opcional (max 500 chars)",
            "aria-label": "Comentário opcional",
        });
        var counter = _make_el("span", { className: "brain-confirm-comment-count" }, "0 / 500");
        textarea.addEventListener("input", function () {
            counter.textContent = textarea.value.length + " / 500";
        });
        var btnSubmit = _make_el("button", {
            type: "button",
            className: "brain-confirm-btn brain-confirm-btn-approve",
            "data-action": "submit",
        }, "Confirmar ação");
        var btnDiscard = _make_el("button", {
            type: "button",
            className: "brain-confirm-btn brain-confirm-btn-cancel",
            "data-action": "discard",
        }, "Voltar");
        commentWrap.appendChild(textarea);
        commentWrap.appendChild(counter);
        var commentActions = _make_el("div", { className: "brain-confirm-actions" });
        commentActions.appendChild(btnSubmit);
        commentActions.appendChild(btnDiscard);
        commentWrap.appendChild(commentActions);

        var pending = { action: null };

        function _openComment(act) {
            pending.action = act;
            commentWrap.hidden = false;
            textarea.focus();
        }
        function _closeComment() {
            pending.action = null;
            commentWrap.hidden = true;
            textarea.value = "";
            counter.textContent = "0 / 500";
        }

        btnApprove.addEventListener("click", function () { _openComment("approve"); });
        btnDeny.addEventListener("click", function () { _openComment("deny"); });
        btnCancel.addEventListener("click", function () { _openComment("cancel"); });
        btnDiscard.addEventListener("click", function () { _closeComment(); });
        btnSubmit.addEventListener("click", function () {
            if (!pending.action) return;
            var act = pending.action;
            var comment = textarea.value.slice(0, 500);
            card.classList.add("resolving");
            onAction(run.run_id, act, comment, function (err) {
                if (err) {
                    card.classList.remove("resolving");
                    card.classList.add("error");
                }
                _closeComment();
            });
        });

        var stack = document.createDocumentFragment();
        stack.appendChild(actions);
        stack.appendChild(commentWrap);
        return stack;
    }

    function render(run, opts) {
        opts = opts || {};
        var onAction = typeof opts.onAction === "function" ? opts.onAction : function () {};

        var card = _make_el("article", {
            className: "brain-confirm-card",
            "data-run-id": run.run_id || "",
            "aria-label": "Brain run aguardando confirmação " + (run.intent || ""),
        });

        var header = _make_el("div", { className: "brain-confirm-card-header" });
        header.appendChild(_make_el("span", { className: "brain-confirm-intent" }, run.intent || "—"));
        var conf = parseFloat(run.confidence) || 0;
        header.appendChild(_make_el("span", {
            className: "brain-confirm-confidence " + _conf_class(conf),
            "aria-label": "Confiança " + _fmt_pct(conf),
        }, _fmt_pct(conf) + " conf"));
        if (run.action_class) {
            header.appendChild(_make_el("span", { className: "brain-confirm-destructive" }, "⚠ " + run.action_class));
        }
        card.appendChild(header);

        card.appendChild(_build_summary(run));
        card.appendChild(_build_trace(run));
        card.appendChild(_build_actions(card, run, onAction));

        return card;
    }

    window.BrainConfirmCard = { render: render };
})();
