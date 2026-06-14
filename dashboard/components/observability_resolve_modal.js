/* ============================================================
   Hermes Cloud Studio — ObservabilityResolveModal (F.8.3 C3)
   ============================================================
   Modal confirm pra resolver errors_inbox row (action=resolve|wontfix
   + optional comment 500 chars). Hooks POST atomic backend F.8.2.

   Decisões F.8.3 cristalizadas D4 (modal confirm + optional comment):
   - Click "Resolver" row → modal opens com error preview
   - Action dropdown (resolve | wontfix) + textarea max 500 chars
   - Submit → POST /api/observability/errors/{id}/resolve
   - 409 race condition handle → toast "já resolvido em outra aba"
   - ESC + click backdrop fecham (cancel)
   - Z-index 1100 (acima drawer 950 + toast 1000) — observability.css

   API global: window.ObservabilityResolveModal.{open, close}
   ============================================================ */
(function () {
    "use strict";

    var MODAL_ID = "observability-resolve-modal";

    var state = {
        wired: false,
        lastFocus: null,
        currentErrorId: null,
        submitting: false,
    };

    function _$(id) { return document.getElementById(id); }
    function _root() { return _$(MODAL_ID); }
    function _authHeaders() {
        var h = { "Content-Type": "application/json" };
        try {
            var t = localStorage.getItem("hermes_token") || "";
            if (t) h["X-Hermes-Token"] = t;
        } catch (_) {}
        return h;
    }

    function _toast(msg, tone) {
        if (window.hermesToast && typeof window.hermesToast[tone || "info"] === "function") {
            try { window.hermesToast[tone || "info"](msg); return; } catch (_) {}
        }
        console.log("[observability-resolve]", tone || "info", msg);
    }

    function _setSubmitting(flag) {
        state.submitting = !!flag;
        var btn = _$("observability-resolve-modal-submit");
        if (btn) {
            btn.disabled = state.submitting;
            btn.textContent = state.submitting ? "Enviando..." : "Confirmar";
        }
    }

    function _onKeydown(e) {
        var root = _root();
        if (!root || root.hidden) return;
        if (e.key === "Escape") {
            e.preventDefault();
            close();
        }
    }

    function _onClick(e) {
        var root = _root();
        if (!root || root.hidden) return;
        var actionEl = e.target.closest("[data-action]");
        if (!actionEl) return;
        var action = actionEl.dataset.action;
        if (action === "cancel") {
            close();
        } else if (action === "submit") {
            submit();
        }
    }

    function _onCommentInput(e) {
        var counter = _$("observability-resolve-modal-counter");
        if (counter) counter.textContent = String((e.target.value || "").length) + " / 500";
    }

    function _wireOnce() {
        if (state.wired) return;
        state.wired = true;
        document.addEventListener("keydown", _onKeydown);
        var root = _root();
        if (root) root.addEventListener("click", _onClick);
        var textarea = _$("observability-resolve-modal-comment");
        if (textarea) textarea.addEventListener("input", _onCommentInput);
    }

    function open(errorRow) {
        if (!errorRow || errorRow.id == null) return;
        _wireOnce();
        var root = _root();
        if (!root) return;
        state.lastFocus = document.activeElement;
        state.currentErrorId = String(errorRow.id);

        var preview = _$("observability-resolve-modal-preview");
        if (preview) preview.textContent = String(errorRow.title || "(sem título)");

        var action = _$("observability-resolve-modal-action");
        if (action) action.value = "resolve";

        var textarea = _$("observability-resolve-modal-comment");
        if (textarea) textarea.value = "";

        var counter = _$("observability-resolve-modal-counter");
        if (counter) counter.textContent = "0 / 500";

        _setSubmitting(false);
        root.hidden = false;
        // focus first interactive element pra accessibility
        setTimeout(function () {
            var firstField = _$("observability-resolve-modal-action");
            if (firstField) firstField.focus();
        }, 0);
    }

    function close() {
        var root = _root();
        if (!root) return;
        root.hidden = true;
        state.currentErrorId = null;
        if (state.lastFocus && typeof state.lastFocus.focus === "function") {
            try { state.lastFocus.focus(); } catch (_) {}
        }
        state.lastFocus = null;
    }

    async function submit() {
        if (state.submitting) return;
        var id = state.currentErrorId;
        if (!id) { close(); return; }
        var action = (_$("observability-resolve-modal-action") || {}).value || "resolve";
        var comment = ((_$("observability-resolve-modal-comment") || {}).value || "").slice(0, 500);

        _setSubmitting(true);
        try {
            var r = await fetch("/api/observability/errors/" + encodeURIComponent(id) + "/resolve", {
                method: "POST",
                headers: _authHeaders(),
                body: JSON.stringify({ action: action, comment: comment }),
            });
            if (r.status === 200) {
                _toast("Erro resolvido (" + action + ")", "success");
                close();
                if (window.ObservabilityErrors && typeof window.ObservabilityErrors.render === "function") {
                    try { window.ObservabilityErrors.render(); } catch (_) {}
                }
                return;
            }
            if (r.status === 409) {
                _toast("Erro já resolvido em outra aba (409)", "warn");
                close();
                if (window.ObservabilityErrors && typeof window.ObservabilityErrors.render === "function") {
                    try { window.ObservabilityErrors.render(); } catch (_) {}
                }
                return;
            }
            if (r.status === 404) {
                _toast("Erro não encontrado (404)", "error");
                close();
                return;
            }
            var body = "";
            try { var j = await r.json(); body = j.detail || JSON.stringify(j); } catch (_) {}
            _toast("Falha HTTP " + r.status + " — " + body, "error");
        } catch (e) {
            _toast("Falha de rede: " + (e && e.message ? e.message : e), "error");
        } finally {
            _setSubmitting(false);
        }
    }

    window.ObservabilityResolveModal = { open: open, close: close, submit: submit };

    // Auto-wire em DOMContentLoaded (idempotent)
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", _wireOnce);
    } else {
        _wireOnce();
    }
})();
