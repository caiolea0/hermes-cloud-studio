/* ============================================================
   UX-RM-F6-C — Sequence Dry-Run Modal
   ============================================================
   Simulates sequence execution: shows timeline of actions
   (Day 0, Day 3, Day 8…) with rendered message previews.
   NEVER triggers actual sends (actual_send === false enforced).

   API: window.HermesSequenceDryRun.{open, close}
   Exposes: window.sequenceDryRun (singleton)

   XSS: all user-supplied content uses textContent or DOMPurify.
   A11y: dialog role + aria-modal + focus trap + aria-live status.
   ============================================================ */
(function () {
    "use strict";

    var CHANNEL_ICONS = {
        linkedin: "💼",
        email: "✉️",
        whatsapp: "💬",
        default: "📨",
    };

    function _esc(str) {
        return String(str || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function HermesSequenceDryRun() {
        this._modal = null;
        this._seqId = null;
        this._onActivate = null;
    }

    HermesSequenceDryRun.prototype._ensureModal = function () {
        if (this._modal) return;

        var overlay = document.createElement("div");
        overlay.id = "seq-dry-run-overlay";
        overlay.setAttribute("role", "dialog");
        overlay.setAttribute("aria-modal", "true");
        overlay.setAttribute("aria-labelledby", "seq-dry-run-title");
        overlay.setAttribute("aria-describedby", "seq-dry-run-desc");
        overlay.classList.add("modal-scrim");
        overlay.style.cssText = [
            "position:fixed;inset:0;z-index:9000;display:none",
            "align-items:center;justify-content:center",
        ].join(";");

        var box = document.createElement("div");
        box.className = "seq-dry-run-box glass-floating";
        box.style.cssText = [
            "background:var(--bg-2,#111);border:1px solid var(--border,#2a2a35)",
            "border-radius:var(--r,14px);padding:1.5rem",
            "max-width:640px;width:calc(100vw - 3rem)",
            "max-height:80vh;overflow-y:auto;position:relative",
        ].join(";");

        box.innerHTML =
            '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem">' +
                '<h2 id="seq-dry-run-title" style="margin:0;font-size:1.1rem;font-weight:600">Pré-visualização da Sequência</h2>' +
                '<button class="btn btn-ghost btn-sm seq-dry-close-btn" aria-label="Fechar pré-visualização" style="padding:.25rem .5rem;font-size:1.2rem">&times;</button>' +
            '</div>' +
            '<p id="seq-dry-run-desc" style="color:var(--text-2,#aaa);font-size:.85rem;margin:0 0 1rem">' +
                'Simulação sem envio real. Revise cada etapa antes de ativar.' +
            '</p>' +
            '<div id="seq-dry-run-status" aria-live="polite" style="min-height:1.5rem;color:var(--text-2,#aaa);font-size:.85rem;margin-bottom:.5rem"></div>' +
            '<div id="seq-dry-run-timeline" role="list" aria-label="Cronograma da sequência"></div>' +
            '<div style="margin-top:1.5rem;display:flex;gap:.75rem;justify-content:flex-end">' +
                '<button class="btn btn-ghost btn-sm seq-dry-edit-btn">Editar sequência</button>' +
                '<button class="btn btn-primary btn-sm seq-dry-activate-btn" disabled aria-disabled="true">Ativar e inscrever prospects</button>' +
            '</div>';

        overlay.appendChild(box);
        document.body.appendChild(overlay);
        this._modal = overlay;

        var self = this;
        overlay.addEventListener("click", function (e) {
            if (e.target === overlay) self.close();
            var closeBtn = e.target.closest(".seq-dry-close-btn, .seq-dry-edit-btn");
            if (closeBtn) { self.close(); return; }
            var activateBtn = e.target.closest(".seq-dry-activate-btn");
            if (activateBtn && !activateBtn.disabled && self._onActivate) {
                self._onActivate();
                self.close();
            }
        });

        overlay.addEventListener("keydown", function (e) {
            if (e.key === "Escape") { self.close(); return; }
            // Focus trap
            if (e.key === "Tab") {
                var focusable = Array.from(
                    overlay.querySelectorAll('button:not([disabled]),a,input,[tabindex]:not([tabindex="-1"])')
                );
                if (!focusable.length) return;
                var first = focusable[0], last = focusable[focusable.length - 1];
                if (e.shiftKey && document.activeElement === first) {
                    e.preventDefault(); last.focus();
                } else if (!e.shiftKey && document.activeElement === last) {
                    e.preventDefault(); first.focus();
                }
            }
        });
    };

    HermesSequenceDryRun.prototype.open = function (seqId, opts) {
        opts = opts || {};
        this._seqId = seqId;
        this._onActivate = opts.onActivate || null;
        this._ensureModal();

        var overlay = this._modal;
        var status = overlay.querySelector("#seq-dry-run-status");
        var timeline = overlay.querySelector("#seq-dry-run-timeline");
        var activateBtn = overlay.querySelector(".seq-dry-activate-btn");

        status.textContent = "Calculando cronograma…";
        timeline.innerHTML = "";
        activateBtn.disabled = true;
        activateBtn.setAttribute("aria-disabled", "true");

        overlay.style.display = "flex";
        var closeBtn = overlay.querySelector(".seq-dry-close-btn");
        if (closeBtn) closeBtn.focus();

        var self = this;
        var url = (window.HERMES_API || "") + "/api/sequences/" + seqId + "/dry-run";
        var headers = {};
        if (window.HERMES_TOKEN) headers["X-Hermes-Token"] = window.HERMES_TOKEN;

        fetch(url, { method: "POST", headers: headers })
            .then(function (r) {
                if (!r.ok) throw new Error("HTTP " + r.status);
                return r.json();
            })
            .then(function (data) {
                status.textContent = "";
                self._renderTimeline(timeline, data);
                if (data.actual_send !== false) {
                    // Safeguard: should never happen but guard regardless
                    status.textContent = "⚠️ Aviso: dry-run não garantiu modo seguro.";
                } else if (data.timeline && data.timeline.length > 0) {
                    activateBtn.disabled = false;
                    activateBtn.removeAttribute("aria-disabled");
                } else {
                    status.textContent = "Nenhuma ação encontrada. Adicione nós de ação ao canvas.";
                }
            })
            .catch(function (err) {
                status.textContent = "Erro ao simular: " + _esc(err.message);
            });
    };

    HermesSequenceDryRun.prototype._renderTimeline = function (container, data) {
        var tl = data.timeline || [];
        if (!tl.length) {
            var empty = document.createElement("p");
            empty.style.color = "var(--text-2,#aaa)";
            empty.textContent = "Nenhuma etapa encontrada. Adicione ações ao canvas.";
            container.appendChild(empty);
            return;
        }

        tl.forEach(function (step, idx) {
            var item = document.createElement("div");
            item.setAttribute("role", "listitem");
            item.style.cssText = [
                "border:1px solid var(--border,#2a2a35)",
                "border-radius:var(--r,10px);padding:.875rem",
                "margin-bottom:.75rem;position:relative",
            ].join(";");

            var icon = CHANNEL_ICONS[step.channel] || CHANNEL_ICONS["default"];
            var dayLabel = step.day === 0 ? "Hoje" : ("Dia " + step.day);

            // Header row
            var header = document.createElement("div");
            header.style.cssText = "display:flex;align-items:center;gap:.5rem;margin-bottom:.5rem";
            header.innerHTML =
                '<span aria-hidden="true" style="font-size:1.1rem">' + icon + '</span>' +
                '<span style="font-weight:600;font-size:.9rem"></span>' +
                '<span style="margin-left:auto;font-size:.75rem;color:var(--text-2,#aaa)"></span>' +
                '<span style="font-size:.75rem;background:var(--bg-3,#1a1a22);border-radius:4px;padding:.1rem .4rem"></span>';

            header.children[1].textContent = dayLabel + " · " + (step.action || step.channel);
            header.children[2].textContent = "Envio: " + (step.send_window || "a calcular");
            header.children[3].textContent = (step.channel || "").toUpperCase();
            item.appendChild(header);

            // Rendered preview
            if (step.rendered_subject) {
                var subj = document.createElement("div");
                subj.style.cssText = "font-size:.8rem;color:var(--text-2,#aaa);margin-bottom:.35rem";
                var subjLabel = document.createElement("span");
                subjLabel.style.fontWeight = "600";
                subjLabel.textContent = "Assunto: ";
                subj.appendChild(subjLabel);
                var subjText = document.createElement("span");
                subjText.textContent = step.rendered_subject;
                subj.appendChild(subjText);
                item.appendChild(subj);
            }

            if (step.rendered_preview) {
                var preview = document.createElement("pre");
                preview.style.cssText = [
                    "font-size:.8rem;white-space:pre-wrap;word-break:break-word",
                    "background:var(--bg-3,#1a1a22);border-radius:6px",
                    "padding:.5rem .75rem;margin:0;color:var(--text-1,#e0e0e0)",
                    "max-height:140px;overflow-y:auto",
                ].join(";");
                preview.textContent = step.rendered_preview;
                item.appendChild(preview);
            } else {
                var noTpl = document.createElement("p");
                noTpl.style.cssText = "font-size:.8rem;color:var(--text-2,#aaa);margin:.25rem 0 0";
                noTpl.textContent = "Nenhum template vinculado. Clique no nó para configurar.";
                item.appendChild(noTpl);
            }

            container.appendChild(item);
        });

        // Summary footer
        var summary = document.createElement("p");
        summary.style.cssText = "font-size:.8rem;color:var(--text-2,#aaa);text-align:right;margin-top:.5rem";
        summary.textContent = tl.length + " etapa(s) · " + (data.total_days || 0) + " dias total";
        container.appendChild(summary);
    };

    HermesSequenceDryRun.prototype.close = function () {
        if (this._modal) {
            this._modal.style.display = "none";
        }
    };

    // Singleton
    window.HermesSequenceDryRun = HermesSequenceDryRun;
    window.sequenceDryRun = new HermesSequenceDryRun();
})();
