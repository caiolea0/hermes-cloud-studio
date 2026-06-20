/* ============================================================
   UX-RM-F6-C — Sequence Enroll Modal
   ============================================================
   Multi-select prospect picker + start-date + enroll flow.
   Only available when sequence status === 'active'.

   API: window.HermesSequenceEnrollModal.{open, close}
   Exposes: window.sequenceEnrollModal (singleton)

   XSS: textContent for all user data. _esc() for HTML attrs.
   A11y: dialog + aria-modal + focus trap + aria-checked + live.
   ============================================================ */
(function () {
    "use strict";

    function _esc(str) {
        return String(str || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    var API_BASE = window.HERMES_API || "";
    var AUTH_HDR = { "Content-Type": "application/json" };

    function _authHeaders() {
        var h = Object.assign({}, AUTH_HDR);
        if (window.HERMES_TOKEN) h["X-Hermes-Token"] = window.HERMES_TOKEN;
        return h;
    }

    function HermesSequenceEnrollModal() {
        this._modal = null;
        this._seqId = null;
        this._seqName = "";
        this._selected = new Set();
        this._prospects = [];
        this._onEnrolled = null;
    }

    HermesSequenceEnrollModal.prototype._ensureModal = function () {
        if (this._modal) return;

        var overlay = document.createElement("div");
        overlay.id = "seq-enroll-overlay";
        overlay.setAttribute("role", "dialog");
        overlay.setAttribute("aria-modal", "true");
        overlay.setAttribute("aria-labelledby", "seq-enroll-title");
        overlay.classList.add("modal-scrim");
        overlay.style.cssText = [
            "position:fixed;inset:0;z-index:9100;display:none",
            "align-items:center;justify-content:center",
        ].join(";");

        var box = document.createElement("div");
        box.className = "seq-enroll-box glass-floating";
        box.style.cssText = [
            "background:var(--bg-2,#111);border:1px solid var(--border,#2a2a35)",
            "border-radius:var(--r,14px);padding:1.5rem",
            "max-width:560px;width:calc(100vw - 3rem)",
            "max-height:80vh;display:flex;flex-direction:column;gap:.75rem",
        ].join(";");

        box.innerHTML =
            '<div style="display:flex;align-items:center;justify-content:space-between">' +
                '<h2 id="seq-enroll-title" style="margin:0;font-size:1.1rem;font-weight:600">Inscrever Prospects</h2>' +
                '<button class="btn btn-ghost btn-sm seq-enroll-close-btn" aria-label="Fechar" style="font-size:1.2rem;padding:.25rem .5rem">&times;</button>' +
            '</div>' +
            '<p id="seq-enroll-name" style="margin:0;font-size:.85rem;color:var(--text-2,#aaa)"></p>' +
            '<div style="display:flex;gap:.5rem;align-items:center">' +
                '<input type="search" id="seq-enroll-search" placeholder="Filtrar prospects…" aria-label="Filtrar prospects" ' +
                    'style="flex:1;padding:.4rem .75rem;border-radius:6px;border:1px solid var(--border,#2a2a35);background:var(--bg-3,#1a1a22);color:var(--text-1,#e0e0e0);font-size:.85rem">' +
                '<button class="btn btn-ghost btn-sm" id="seq-enroll-select-all">Selec. todos</button>' +
            '</div>' +
            '<div id="seq-enroll-list" role="listbox" aria-multiselectable="true" aria-label="Prospects disponíveis" ' +
                'style="flex:1;overflow-y:auto;max-height:260px;border:1px solid var(--border,#2a2a35);border-radius:8px;padding:.25rem"></div>' +
            '<div aria-live="polite" id="seq-enroll-count" style="font-size:.8rem;color:var(--text-2,#aaa)">0 selecionados</div>' +
            '<div>' +
                '<label for="seq-enroll-start-at" style="font-size:.8rem;color:var(--text-2,#aaa);display:block;margin-bottom:.35rem">Início (opcional — padrão: agora, horário comercial)</label>' +
                '<input type="datetime-local" id="seq-enroll-start-at" ' +
                    'style="width:100%;padding:.4rem .75rem;border-radius:6px;border:1px solid var(--border,#2a2a35);background:var(--bg-3,#1a1a22);color:var(--text-1,#e0e0e0);font-size:.85rem">' +
            '</div>' +
            '<div id="seq-enroll-status" aria-live="assertive" style="font-size:.85rem;min-height:1.2rem;color:var(--text-2,#aaa)"></div>' +
            '<div style="display:flex;gap:.75rem;justify-content:flex-end">' +
                '<button class="btn btn-ghost btn-sm seq-enroll-close-btn">Cancelar</button>' +
                '<button class="btn btn-primary btn-sm" id="seq-enroll-submit" disabled aria-disabled="true">Inscrever 0 prospects</button>' +
            '</div>';

        overlay.appendChild(box);
        document.body.appendChild(overlay);
        this._modal = overlay;

        var self = this;

        overlay.addEventListener("click", function (e) {
            if (e.target === overlay) self.close();
            if (e.target.closest(".seq-enroll-close-btn")) { self.close(); return; }
            if (e.target.id === "seq-enroll-submit" && !e.target.disabled) { self._submit(); return; }
            if (e.target.id === "seq-enroll-select-all") { self._toggleAll(); return; }
        });

        overlay.addEventListener("keydown", function (e) {
            if (e.key === "Escape") { self.close(); return; }
            if (e.key === "Tab") {
                var focusable = Array.from(
                    overlay.querySelectorAll('button:not([disabled]),input,[tabindex]:not([tabindex="-1"])')
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

        overlay.querySelector("#seq-enroll-search").addEventListener("input", function () {
            self._renderList(this.value.toLowerCase());
        });

        overlay.querySelector("#seq-enroll-list").addEventListener("click", function (e) {
            var item = e.target.closest("[data-pid]");
            if (!item) return;
            var pid = parseInt(item.dataset.pid, 10);
            if (self._selected.has(pid)) {
                self._selected.delete(pid);
                item.setAttribute("aria-selected", "false");
                item.classList.remove("seq-enroll-selected");
            } else {
                self._selected.add(pid);
                item.setAttribute("aria-selected", "true");
                item.classList.add("seq-enroll-selected");
            }
            self._updateCount();
        });

        overlay.querySelector("#seq-enroll-list").addEventListener("keydown", function (e) {
            if (e.key === " " || e.key === "Enter") {
                var item = e.target.closest("[data-pid]");
                if (item) { e.preventDefault(); item.click(); }
            }
        });
    };

    HermesSequenceEnrollModal.prototype._renderList = function (filter) {
        var list = this._modal.querySelector("#seq-enroll-list");
        list.innerHTML = "";
        var prospects = this._prospects.filter(function (p) {
            if (!filter) return true;
            return (p.business_name || "").toLowerCase().includes(filter) ||
                   (p.city || "").toLowerCase().includes(filter);
        });

        if (!prospects.length) {
            var empty = document.createElement("p");
            empty.style.cssText = "text-align:center;color:var(--text-3,#666);padding:.75rem;font-size:.85rem";
            empty.textContent = filter ? "Nenhum resultado para \"" + filter + "\"." : "Nenhum prospect disponível.";
            list.appendChild(empty);
            return;
        }

        var self = this;
        var frag = document.createDocumentFragment();
        prospects.forEach(function (p) {
            var item = document.createElement("div");
            item.setAttribute("role", "option");
            item.setAttribute("tabindex", "0");
            item.setAttribute("data-pid", String(p.id));
            item.setAttribute("aria-selected", self._selected.has(p.id) ? "true" : "false");
            if (self._selected.has(p.id)) item.classList.add("seq-enroll-selected");
            item.style.cssText = [
                "display:flex;align-items:center;gap:.6rem;padding:.5rem .75rem",
                "border-radius:6px;cursor:pointer;font-size:.85rem",
                "transition:background .15s",
            ].join(";");

            var checkbox = document.createElement("span");
            checkbox.setAttribute("aria-hidden", "true");
            checkbox.style.cssText = "width:16px;height:16px;border:1.5px solid var(--border,#2a2a35);border-radius:3px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:.65rem";
            checkbox.textContent = self._selected.has(p.id) ? "✓" : "";
            item.appendChild(checkbox);

            var label = document.createElement("span");
            label.style.flex = "1";
            var name = document.createElement("span");
            name.textContent = p.business_name || ("Prospect #" + p.id);
            var meta = document.createElement("span");
            meta.style.cssText = "display:block;font-size:.75rem;color:var(--text-2,#aaa)";
            meta.textContent = [p.city, p.category].filter(Boolean).join(" · ");
            label.appendChild(name);
            label.appendChild(meta);
            item.appendChild(label);

            var stageBadge = document.createElement("span");
            stageBadge.style.cssText = "font-size:.7rem;background:var(--bg-3,#1a1a22);border-radius:3px;padding:.1rem .35rem;color:var(--text-2,#aaa)";
            stageBadge.textContent = p.stage || "discovered";
            item.appendChild(stageBadge);

            // Hover effect
            item.addEventListener("mouseenter", function () { this.style.background = "var(--bg-3,#1a1a22)"; });
            item.addEventListener("mouseleave", function () { this.style.background = ""; });

            frag.appendChild(item);
        });
        list.appendChild(frag);
    };

    HermesSequenceEnrollModal.prototype._toggleAll = function () {
        var visible = Array.from(this._modal.querySelectorAll("[data-pid]"));
        var visibleIds = visible.map(function (el) { return parseInt(el.dataset.pid, 10); });
        var allSelected = visibleIds.every(function (id) { return this._selected.has(id); }, this);
        if (allSelected) {
            visibleIds.forEach(function (id) { this._selected.delete(id); }, this);
        } else {
            visibleIds.forEach(function (id) { this._selected.add(id); }, this);
        }
        this._renderList(this._modal.querySelector("#seq-enroll-search").value.toLowerCase());
        this._updateCount();
    };

    HermesSequenceEnrollModal.prototype._updateCount = function () {
        var n = this._selected.size;
        var submitBtn = this._modal.querySelector("#seq-enroll-submit");
        var countEl = this._modal.querySelector("#seq-enroll-count");
        // Update all checkboxes in list
        var self = this;
        Array.from(this._modal.querySelectorAll("[data-pid]")).forEach(function (el) {
            var pid = parseInt(el.dataset.pid, 10);
            var chk = el.querySelector("span[aria-hidden]");
            var selected = self._selected.has(pid);
            el.setAttribute("aria-selected", selected ? "true" : "false");
            if (selected) { el.classList.add("seq-enroll-selected"); if (chk) chk.textContent = "✓"; }
            else { el.classList.remove("seq-enroll-selected"); if (chk) chk.textContent = ""; }
        });
        countEl.textContent = n + " prospect" + (n !== 1 ? "s" : "") + " selecionado" + (n !== 1 ? "s" : "");
        submitBtn.textContent = "Inscrever " + n + " prospect" + (n !== 1 ? "s" : "");
        if (n > 0) {
            submitBtn.disabled = false;
            submitBtn.removeAttribute("aria-disabled");
        } else {
            submitBtn.disabled = true;
            submitBtn.setAttribute("aria-disabled", "true");
        }
    };

    HermesSequenceEnrollModal.prototype._submit = function () {
        var self = this;
        var status = this._modal.querySelector("#seq-enroll-status");
        var submitBtn = this._modal.querySelector("#seq-enroll-submit");
        var startAt = this._modal.querySelector("#seq-enroll-start-at").value;

        if (!this._selected.size) return;

        submitBtn.disabled = true;
        submitBtn.setAttribute("aria-disabled", "true");
        status.textContent = "Inscrevendo…";

        var body = {
            prospect_ids: Array.from(this._selected),
        };
        if (startAt) body.start_at = startAt;

        fetch(API_BASE + "/api/sequences/" + this._seqId + "/enroll", {
            method: "POST",
            headers: _authHeaders(),
            body: JSON.stringify(body),
        })
            .then(function (r) {
                if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || "HTTP " + r.status); });
                return r.json();
            })
            .then(function (data) {
                var n = (data.enrolled || []).length;
                status.textContent = "";
                if (window.hermesToast && typeof window.hermesToast.success === "function") {
                    window.hermesToast.success(n + " prospect" + (n !== 1 ? "s inscritos" : " inscrito") + " na sequência!");
                }
                if (self._onEnrolled) self._onEnrolled(data);
                self.close();
            })
            .catch(function (err) {
                status.textContent = "Erro: " + _esc(err.message);
                submitBtn.disabled = false;
                submitBtn.removeAttribute("aria-disabled");
            });
    };

    HermesSequenceEnrollModal.prototype.open = function (seqId, seqName, opts) {
        opts = opts || {};
        this._seqId = seqId;
        this._seqName = seqName || ("Sequência #" + seqId);
        this._selected.clear();
        this._prospects = [];
        this._onEnrolled = opts.onEnrolled || null;
        this._ensureModal();

        var overlay = this._modal;
        var status = overlay.querySelector("#seq-enroll-status");
        var list = overlay.querySelector("#seq-enroll-list");
        var nameEl = overlay.querySelector("#seq-enroll-name");
        var submitBtn = overlay.querySelector("#seq-enroll-submit");

        nameEl.textContent = "Sequência: " + this._seqName;
        status.textContent = "Carregando prospects…";
        list.innerHTML = "";
        submitBtn.disabled = true;
        submitBtn.setAttribute("aria-disabled", "true");
        submitBtn.textContent = "Inscrever 0 prospects";
        overlay.querySelector("#seq-enroll-count").textContent = "0 selecionados";
        overlay.querySelector("#seq-enroll-search").value = "";

        overlay.style.display = "flex";
        var closeBtn = overlay.querySelector(".seq-enroll-close-btn");
        if (closeBtn) closeBtn.focus();

        var self = this;
        fetch(API_BASE + "/api/prospects?limit=200", { headers: _authHeaders() })
            .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)); })
            .then(function (data) {
                self._prospects = data.prospects || [];
                status.textContent = "";
                self._renderList("");
                self._updateCount();
            })
            .catch(function (err) {
                status.textContent = "Erro ao carregar: " + _esc(err.message);
            });
    };

    HermesSequenceEnrollModal.prototype.close = function () {
        if (this._modal) this._modal.style.display = "none";
        this._selected.clear();
    };

    // Singleton
    window.HermesSequenceEnrollModal = HermesSequenceEnrollModal;
    window.sequenceEnrollModal = new HermesSequenceEnrollModal();
})();
