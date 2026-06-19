/* ============================================================
   UX-RM-F6-B — Template Editor Modal
   ============================================================
   Per-channel message template CRUD with live variable preview.

   API: window.templateEditor.open(opts) / .close() / .save()
   Exposes: window.HermesTemplateEditor (class), window.templateEditor (singleton)

   XSS: escapeHtml on ALL user content rendered via innerHTML.
        _renderClient() output rendered via escapeHtml + <br> only.

   A11y: role=dialog, aria-modal, aria-labelledby, focus trap,
         textarea/input aria-label, chips role=group + keyboard,
         preview aria-live=polite.
   ============================================================ */
(function () {
    "use strict";

    var VALID_VARIABLES = [
        "firstName", "lastName", "fullName", "company", "jobTitle",
        "city", "industry", "customField1", "customField2", "senderName",
    ];

    var SAMPLE_DATA = {
        sample1: {
            firstName: "Joao", lastName: "Silva", fullName: "Joao Silva",
            company: "Acme SaaS", jobTitle: "Founder", city: "Cuiaba",
            industry: "tecnologia", senderName: "Caio",
            customField1: "", customField2: "",
        },
        sample2: {
            firstName: "Maria", lastName: "Costa", fullName: "Maria Costa",
            company: "Beta Agency", jobTitle: "Diretora", city: "Goiania",
            industry: "marketing", senderName: "Caio",
            customField1: "", customField2: "",
        },
    };

    function _esc(s) {
        return String(s == null ? "" : s)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;")
            .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    /* Deterministic client-side render: spintax picks first option */
    function _renderClient(template, data) {
        var result = template.replace(/\{spintax:\s*([^}]+)\}/g, function (m, opts) {
            var choices = opts.split("|");
            return (choices[0] || "").trim();
        });
        result = result.replace(/\{\{(\w+)\}\}/g, function (m, key) {
            var k = key.trim();
            return Object.prototype.hasOwnProperty.call(data, k) ? String(data[k]) : "[" + k + "]";
        });
        return result;
    }

    /* ── Constructor ─────────────────────────────────────── */

    function HermesTemplateEditor() {
        this._templateId = null;
        this._channel = null;
        this._actionType = null;
        this._onSave = null;
        this._el = null;
        this._previousFocus = null;
        this._boundKeyDown = this._handleKeyDown.bind(this);
    }

    HermesTemplateEditor.prototype.open = function (opts) {
        opts = opts || {};
        this._templateId = opts.templateId || null;
        this._channel = opts.channel || "linkedin";
        this._actionType = opts.actionType || null;
        this._onSave = opts.onSave || null;
        this._previousFocus = document.activeElement;
        this._render();
        if (opts.templateId) {
            this._loadTemplate(opts.templateId);
        }
    };

    HermesTemplateEditor.prototype.close = function () {
        if (this._el) {
            this._el.remove();
            this._el = null;
        }
        document.removeEventListener("keydown", this._boundKeyDown);
        if (this._previousFocus && this._previousFocus.focus) {
            this._previousFocus.focus();
        }
    };

    /* ── Render modal ─────────────────────────────────────── */

    HermesTemplateEditor.prototype._render = function () {
        var self = this;
        var isEmail = this._channel === "email";
        var channelLabel = { linkedin: "LinkedIn", email: "Email", whatsapp: "WhatsApp" }[this._channel] || this._channel;

        var overlay = document.createElement("div");
        overlay.className = "tpl-overlay";
        overlay.setAttribute("role", "presentation");
        overlay.addEventListener("click", function (e) {
            if (e.target === overlay) self.close();
        });

        var dialog = document.createElement("div");
        dialog.className = "tpl-dialog glass-overlay";
        dialog.setAttribute("role", "dialog");
        dialog.setAttribute("aria-modal", "true");
        dialog.setAttribute("aria-labelledby", "tpl-editor-title");

        dialog.innerHTML = [
            '<div class="tpl-header">',
            '  <h2 id="tpl-editor-title" class="tpl-title">Template ' + _esc(channelLabel) + '</h2>',
            '  <button class="tpl-close-btn" aria-label="Fechar editor de template">',
            '    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
            '  </button>',
            '</div>',
            '<div class="tpl-body">',
            '  <div class="tpl-form">',
            '    <div class="tpl-field">',
            '      <label for="tpl-name">Nome do template</label>',
            '      <input type="text" id="tpl-name" class="tpl-input" placeholder="Ex: LinkedIn Intro Cuiaba" aria-required="true">',
            '    </div>',
            isEmail ? [
                '<div class="tpl-field">',
                '  <label for="tpl-subject">Assunto</label>',
                '  <input type="text" id="tpl-subject" class="tpl-input" placeholder="{{firstName}}, sobre {{company}}">',
                '</div>',
            ].join("") : "",
            '    <div class="tpl-field">',
            '      <label for="tpl-body">Mensagem</label>',
            '      <textarea id="tpl-body" class="tpl-textarea" rows="7"',
            '        placeholder="Oi {{firstName}}, vi seu trabalho na {{company}}..."',
            '        aria-describedby="tpl-vars-help"></textarea>',
            '    </div>',
            '    <div class="tpl-vars" id="tpl-vars-help">',
            '      <p class="tpl-vars-label">Variaveis (clique para inserir no cursor):</p>',
            '      <div class="tpl-var-chips" role="group" aria-label="Variaveis disponiveis">',
            VALID_VARIABLES.map(function (v) {
                return '<button class="tpl-var-chip" type="button" data-var="' + _esc(v) + '" title="Inserir {{' + _esc(v) + '}}">{{' + _esc(v) + '}}</button>';
            }).join(""),
            '      </div>',
            '      <details class="tpl-spintax-help">',
            '        <summary>Spintax — variacao anti-spam</summary>',
            '        <code>{spintax: opcao1|opcao2|opcao3}</code> — preview mostra a primeira; envio real sorteia.',
            '      </details>',
            '    </div>',
            '  </div>',
            '  <div class="tpl-preview-panel">',
            '    <div class="tpl-preview-header">',
            '      <h3 class="tpl-preview-title">Preview</h3>',
            '      <div class="tpl-field tpl-preview-select-wrap">',
            '        <label for="tpl-preview-sample" class="sr-only">Prospect de exemplo</label>',
            '        <select id="tpl-preview-sample" class="tpl-input tpl-select">',
            '          <option value="sample1">Joao Silva — Acme SaaS — Cuiaba</option>',
            '          <option value="sample2">Maria Costa — Beta Agency — Goiania</option>',
            '        </select>',
            '      </div>',
            '    </div>',
            '    <div id="tpl-preview-rendered" class="tpl-rendered" aria-live="polite" aria-label="Preview renderizado"></div>',
            '  </div>',
            '</div>',
            '<div class="tpl-footer">',
            '  <button class="btn btn-ghost" type="button" id="tpl-cancel-btn">Cancelar</button>',
            '  <button class="btn btn-primary" type="button" id="tpl-save-btn">',
            '    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>',
            '    Salvar template',
            '  </button>',
            '</div>',
        ].join("");

        overlay.appendChild(dialog);
        document.body.appendChild(overlay);
        this._el = overlay;

        /* Wire events */
        overlay.querySelector(".tpl-close-btn").addEventListener("click", function () { self.close(); });
        overlay.querySelector("#tpl-cancel-btn").addEventListener("click", function () { self.close(); });
        overlay.querySelector("#tpl-save-btn").addEventListener("click", function () { self.save(); });

        var bodyEl = overlay.querySelector("#tpl-body");
        var subjectEl = overlay.querySelector("#tpl-subject");
        var sampleSel = overlay.querySelector("#tpl-preview-sample");

        bodyEl.addEventListener("input", function () { self._updatePreview(); });
        if (subjectEl) subjectEl.addEventListener("input", function () { self._updatePreview(); });
        sampleSel.addEventListener("change", function () { self._updatePreview(); });

        /* Variable chip insert */
        overlay.querySelector(".tpl-var-chips").addEventListener("click", function (e) {
            var chip = e.target.closest("[data-var]");
            if (chip) self.insertVar(chip.getAttribute("data-var"));
        });

        /* Focus trap */
        document.addEventListener("keydown", this._boundKeyDown);

        /* Initial focus */
        var nameEl = overlay.querySelector("#tpl-name");
        if (nameEl) nameEl.focus();

        this._updatePreview();
    };

    HermesTemplateEditor.prototype._handleKeyDown = function (e) {
        if (!this._el) return;
        if (e.key === "Escape") {
            e.preventDefault();
            this.close();
            return;
        }
        if (e.key === "Tab") {
            var focusable = Array.from(this._el.querySelectorAll(
                'button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
            )).filter(function (el) { return !el.disabled && el.offsetParent !== null; });
            if (!focusable.length) return;
            var first = focusable[0], last = focusable[focusable.length - 1];
            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault(); last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault(); first.focus();
            }
        }
    };

    HermesTemplateEditor.prototype.insertVar = function (varName) {
        if (!this._el) return;
        var bodyEl = this._el.querySelector("#tpl-body");
        if (!bodyEl) return;
        var pos = bodyEl.selectionStart || 0;
        var text = bodyEl.value;
        var insert = "{{" + varName + "}}";
        bodyEl.value = text.slice(0, pos) + insert + text.slice(pos);
        bodyEl.selectionStart = bodyEl.selectionEnd = pos + insert.length;
        bodyEl.focus();
        this._updatePreview();
    };

    HermesTemplateEditor.prototype._updatePreview = function () {
        if (!this._el) return;
        var bodyEl = this._el.querySelector("#tpl-body");
        var subjectEl = this._el.querySelector("#tpl-subject");
        var sampleSel = this._el.querySelector("#tpl-preview-sample");
        var previewEl = this._el.querySelector("#tpl-preview-rendered");
        if (!bodyEl || !previewEl) return;

        var data = SAMPLE_DATA[sampleSel ? sampleSel.value : "sample1"] || SAMPLE_DATA.sample1;
        var body = bodyEl.value;
        var subject = subjectEl ? subjectEl.value : "";

        var renderedBody = _renderClient(body, data);
        var renderedSubject = subject ? _renderClient(subject, data) : "";

        var html = "";
        if (renderedSubject) {
            html += '<strong class="tpl-preview-subject">' + _esc(renderedSubject) + '</strong>';
            html += '<hr class="tpl-preview-hr">';
        }
        html += '<p class="tpl-preview-body">' + _esc(renderedBody).replace(/\n/g, "<br>") + "</p>";

        /* Highlight missing vars */
        html = html.replace(/\[(\w+)\]/g, '<span class="tpl-missing-var">[$1]</span>');

        previewEl.innerHTML = html;
    };

    HermesTemplateEditor.prototype._loadTemplate = function (templateId) {
        var self = this;
        if (typeof api !== "function") return;
        api("/api/templates/" + templateId)
            .then(function (data) {
                var t = data.template;
                if (!t || !self._el) return;
                var nameEl = self._el.querySelector("#tpl-name");
                var bodyEl = self._el.querySelector("#tpl-body");
                var subjectEl = self._el.querySelector("#tpl-subject");
                if (nameEl) nameEl.value = t.name || "";
                if (bodyEl) bodyEl.value = t.body || "";
                if (subjectEl) subjectEl.value = t.subject || "";
                self._updatePreview();
            })
            .catch(function (e) {
                if (window.hermesToast) window.hermesToast.error("Erro ao carregar template");
            });
    };

    HermesTemplateEditor.prototype.save = function () {
        var self = this;
        if (!this._el) return;

        var nameEl = this._el.querySelector("#tpl-name");
        var bodyEl = this._el.querySelector("#tpl-body");
        var subjectEl = this._el.querySelector("#tpl-subject");

        var name = (nameEl ? nameEl.value : "").trim();
        var body = (bodyEl ? bodyEl.value : "").trim();

        if (!name) {
            if (nameEl) nameEl.focus();
            if (window.hermesToast) window.hermesToast.error("Nome do template obrigatorio");
            return;
        }
        if (!body) {
            if (bodyEl) bodyEl.focus();
            if (window.hermesToast) window.hermesToast.error("Corpo da mensagem obrigatorio");
            return;
        }

        var payload = {
            name: name,
            channel: this._channel,
            action_type: this._actionType,
            body: body,
            subject: subjectEl ? subjectEl.value : null,
        };

        var url = this._templateId
            ? "/api/templates/" + this._templateId
            : "/api/templates";
        var method = this._templateId ? "PUT" : "POST";

        var saveBtn = this._el.querySelector("#tpl-save-btn");
        if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = "Salvando..."; }

        if (typeof api !== "function") {
            if (window.hermesToast) window.hermesToast.error("API nao disponivel");
            if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = "Salvar template"; }
            return;
        }

        api(url, { method: method, body: JSON.stringify(payload) })
            .then(function (data) {
                if (window.hermesToast) window.hermesToast.success("Template salvo");
                var savedId = data.id || self._templateId;
                if (self._onSave) self._onSave(savedId, payload);
                self.close();
            })
            .catch(function (e) {
                if (window.hermesToast) window.hermesToast.error("Erro: " + (e.message || e));
                if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = "Salvar template"; }
            });
    };

    /* ── Export ───────────────────────────────────────────── */
    window.HermesTemplateEditor = HermesTemplateEditor;
    window.templateEditor = new HermesTemplateEditor();

}());
