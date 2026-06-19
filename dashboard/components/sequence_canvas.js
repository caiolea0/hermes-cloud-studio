/* ============================================================
   UX-RM-F6-A — Hermes Sequence Canvas (SVG-based, zero deps)
   ============================================================
   Lemlist-style multi-channel sequence visual editor.
   Drag-drop nodes, connect with edges, save/load round-trip.

   API: window.HermesSequenceCanvas.{mount, load, newSequence}
   Exposes: window.sequenceCanvas (instance singleton)

   XSS: never innerHTML with user data.
        textContent for all dynamic content.
        SVG attributes use setAttribute.

   A11y: nodes tabindex=0 + role=button + aria-label
         Keyboard: Tab/Shift+Tab = focus node,
                   Enter/Space = select, Delete = remove
                   Arrow keys = move selected node 10px

   Patterns:
   - IIFE for encapsulation (matches pipeline_studio_*.js)
   - _esc() for all user-supplied strings in HTML context
   - hermesToast for user feedback
   - loadingApi(true/false) NOT used (canvas is local-state first)
   ============================================================ */
(function () {
    "use strict";

    /* ─── Icons (inline Lucide-compatible SVG) ───────────────── */
    var ICONS = {
        "user-plus": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/></svg>',
        "message-circle": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
        "mail": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>',
        "phone": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.15 13 19.79 19.79 0 0 1 1.08 4.18 2 2 0 0 1 3.05 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 21 16.92z"/></svg>',
        "clock": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
        "git-branch": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>',
        "play": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
        "flag": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg>',
        "square": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>',
        "save": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>',
        "plus": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
        "trash": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>',
        "x": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    };

    function _icon(name) { return ICONS[name] || ""; }

    function _esc(str) {
        return String(str == null ? "" : str)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    /* ─── Node config helpers ────────────────────────────────── */

    var NODE_META = {
        start:     { label: "Inicio",     icon: "flag",           color: "var(--green)" },
        end:       { label: "Fim",        icon: "square",         color: "var(--red-l, var(--red))" },
        delay:     { label: "Aguardar",   icon: "clock",          color: "var(--accent)" },
        condition: { label: "Condicao",   icon: "git-branch",     color: "var(--lime)" },
        action: {
            linkedin: {
                connect: { label: "Conectar",  icon: "user-plus",      color: "var(--accent)" },
                message: { label: "Mensagem",  icon: "message-circle", color: "var(--accent)" },
            },
            email:     { email:   { label: "Email",    icon: "mail",           color: "var(--blue)" } },
            whatsapp:  { wa_text: { label: "WhatsApp", icon: "phone",          color: "var(--green)" } },
        },
    };

    function _nodeMeta(node) {
        if (node.type === "action" && node.channel && node.action) {
            var ch = (NODE_META.action || {})[node.channel] || {};
            var ac = ch[node.action] || {};
            return ac.label ? ac : { label: node.action, icon: "play", color: "var(--accent)" };
        }
        return NODE_META[node.type] || { label: node.type, icon: "play", color: "var(--accent)" };
    }

    function _nodeLabel(node) {
        var m = _nodeMeta(node);
        return m.label || node.type;
    }

    function _nodeIcon(node) {
        return _icon(_nodeMeta(node).icon || "play");
    }

    function _nodeColor(node) {
        return _nodeMeta(node).color || "var(--accent)";
    }

    function _defaultConfig(type, action) {
        if (type === "delay") return { delay_days: 3, delay_unit: "days" };
        if (type === "condition") return { rule: "if_accepted" };
        return {};
    }

    /* ─── HermesSequenceCanvas class ────────────────────────── */

    function HermesSequenceCanvas() {
        this._container = null;
        this._sequenceId = null;
        this._sequenceName = "Nova Sequencia";
        this._sequenceDescription = "";
        this._nodes = [];
        this._edges = [];
        this._selectedNodeId = null;
        this._dragState = null;   // {nodeId, startX, startY, origX, origY}
        this._connectState = null; // {fromId}
        this._viewport = { x: 0, y: 0, zoom: 1 };
        this._svgEl = null;
        this._nodesG = null;
        this._edgesG = null;
        this._inspectorEl = null;
        this._mounted = false;
        this._boundKeydown = this._onKeydown.bind(this);
    }

    /* ── Mount ─────────────────────────────────────────── */

    HermesSequenceCanvas.prototype.mount = function (container) {
        if (this._mounted) {
            this._refresh();
            return;
        }
        this._container = container;
        this._mounted = true;
        this._buildDOM();
        this._bindEvents();
        if (!this._nodes.length) this._initDefaultNodes();
        this._renderAll();
    };

    HermesSequenceCanvas.prototype._buildDOM = function () {
        this._container.innerHTML = "";
        this._container.setAttribute("data-component", "sequence-canvas");

        /* toolbar */
        var toolbar = document.createElement("div");
        toolbar.className = "seq-toolbar";
        toolbar.setAttribute("role", "toolbar");
        toolbar.setAttribute("aria-label", "Ferramentas de sequencia");
        toolbar.innerHTML =
            '<button class="btn btn-sm seq-tb-btn" data-add="action|linkedin|connect" aria-label="Adicionar acao LinkedIn Connect">' + _icon("user-plus") + ' LI Connect</button>' +
            '<button class="btn btn-sm seq-tb-btn" data-add="action|linkedin|message" aria-label="Adicionar acao LinkedIn Mensagem">' + _icon("message-circle") + ' LI Mensagem</button>' +
            '<button class="btn btn-sm seq-tb-btn" data-add="action|email|email" aria-label="Adicionar acao Email">' + _icon("mail") + ' Email</button>' +
            '<button class="btn btn-sm seq-tb-btn" data-add="action|whatsapp|wa_text" aria-label="Adicionar acao WhatsApp">' + _icon("phone") + ' WhatsApp</button>' +
            '<span class="seq-tb-sep" aria-hidden="true"></span>' +
            '<button class="btn btn-sm seq-tb-btn" data-add="delay" aria-label="Adicionar espera">' + _icon("clock") + ' Aguardar</button>' +
            '<button class="btn btn-sm seq-tb-btn" data-add="condition" aria-label="Adicionar condicao">' + _icon("git-branch") + ' Condicao</button>' +
            '<span class="seq-tb-sep seq-tb-spacer" aria-hidden="true"></span>' +
            '<button class="btn btn-primary btn-sm seq-save-btn" aria-label="Salvar sequencia">' + _icon("save") + ' Salvar</button>';
        this._container.appendChild(toolbar);

        /* main area: canvas + inspector */
        var layout = document.createElement("div");
        layout.className = "seq-layout";

        /* SVG canvas */
        var canvasWrap = document.createElement("div");
        canvasWrap.className = "seq-canvas-wrap";

        var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("class", "seq-canvas-svg");
        svg.setAttribute("id", "seq-canvas-svg-" + (this._uid = Math.random().toString(36).slice(2, 8)));
        svg.setAttribute("aria-label", "Canvas de sequencia");
        svg.setAttribute("role", "application");

        var defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
        defs.innerHTML = '<marker id="seq-arrow-' + this._uid + '" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="var(--accent)"/></marker>';
        svg.appendChild(defs);

        this._edgesG = document.createElementNS("http://www.w3.org/2000/svg", "g");
        this._edgesG.setAttribute("class", "seq-edges");
        svg.appendChild(this._edgesG);

        this._nodesG = document.createElementNS("http://www.w3.org/2000/svg", "g");
        this._nodesG.setAttribute("class", "seq-nodes");
        svg.appendChild(this._nodesG);

        this._svgEl = svg;
        canvasWrap.appendChild(svg);

        /* zoom controls */
        var zoomCtrl = document.createElement("div");
        zoomCtrl.className = "seq-zoom";
        zoomCtrl.setAttribute("role", "group");
        zoomCtrl.setAttribute("aria-label", "Controles de zoom");
        zoomCtrl.innerHTML =
            '<button class="btn btn-ghost btn-sm seq-zoom-btn" data-zoom="in" aria-label="Ampliar">+</button>' +
            '<button class="btn btn-ghost btn-sm seq-zoom-btn" data-zoom="reset" aria-label="Resetar zoom">100%</button>' +
            '<button class="btn btn-ghost btn-sm seq-zoom-btn" data-zoom="out" aria-label="Reduzir">−</button>';
        canvasWrap.appendChild(zoomCtrl);

        layout.appendChild(canvasWrap);

        /* inspector panel */
        var inspector = document.createElement("aside");
        inspector.className = "seq-inspector";
        inspector.setAttribute("aria-label", "Propriedades do no selecionado");
        inspector.innerHTML = '<p class="seq-inspector-empty">Clique em um no para editar</p>';
        this._inspectorEl = inspector;
        layout.appendChild(inspector);

        this._container.appendChild(layout);
    };

    /* ── Default nodes (Start + End) ────────────────────── */

    HermesSequenceCanvas.prototype._initDefaultNodes = function () {
        this._nodes = [
            { id: this._genId(), type: "start",  channel: null, action: null, x: 510, y: 80,  config: {} },
            { id: this._genId(), type: "end",    channel: null, action: null, x: 510, y: 500, config: {} },
        ];
        this._edges = [];
    };

    HermesSequenceCanvas.prototype._genId = function () {
        return "n_" + Math.random().toString(36).slice(2, 11);
    };

    /* ── Render ─────────────────────────────────────────── */

    HermesSequenceCanvas.prototype._renderAll = function () {
        this._renderEdges();
        this._renderNodes();
    };

    var NODE_W = 180;
    var NODE_H = 64;
    var PORT_R = 6;

    HermesSequenceCanvas.prototype._renderNodes = function () {
        var self = this;
        /* clear */
        while (this._nodesG.firstChild) this._nodesG.removeChild(this._nodesG.firstChild);

        this._nodes.forEach(function (n) {
            var g = document.createElementNS("http://www.w3.org/2000/svg", "g");
            g.setAttribute("class", "seq-node" + (self._selectedNodeId === n.id ? " selected" : ""));
            g.setAttribute("transform", "translate(" + n.x + "," + n.y + ")");
            g.setAttribute("tabindex", "0");
            g.setAttribute("role", "button");
            g.setAttribute("aria-label", _nodeLabel(n) + " no " + (n.channel ? n.channel + " " : "") + (n.action || ""));
            g.setAttribute("aria-pressed", self._selectedNodeId === n.id ? "true" : "false");
            g.dataset.nodeId = n.id;

            /* background rect */
            var rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
            rect.setAttribute("class", "seq-node-rect");
            rect.setAttribute("width", NODE_W);
            rect.setAttribute("height", NODE_H);
            rect.setAttribute("rx", "8");
            g.appendChild(rect);

            /* color accent bar */
            var bar = document.createElementNS("http://www.w3.org/2000/svg", "rect");
            bar.setAttribute("class", "seq-node-bar");
            bar.setAttribute("x", "0");
            bar.setAttribute("y", "0");
            bar.setAttribute("width", "4");
            bar.setAttribute("height", NODE_H);
            bar.setAttribute("rx", "8");
            bar.setAttribute("fill", _nodeColor(n));
            g.appendChild(bar);

            /* foreignObject content */
            var fo = document.createElementNS("http://www.w3.org/2000/svg", "foreignObject");
            fo.setAttribute("x", "14");
            fo.setAttribute("y", "10");
            fo.setAttribute("width", String(NODE_W - 20));
            fo.setAttribute("height", String(NODE_H - 20));
            fo.setAttribute("class", "seq-node-fo");
            var div = document.createElement("div");
            div.setAttribute("xmlns", "http://www.w3.org/1999/xhtml");
            div.className = "seq-node-content";
            var iconSpan = document.createElement("span");
            iconSpan.className = "seq-node-icon";
            iconSpan.innerHTML = _nodeIcon(n);
            var textDiv = document.createElement("div");
            textDiv.className = "seq-node-text";
            var strong = document.createElement("strong");
            strong.textContent = _nodeLabel(n);
            textDiv.appendChild(strong);
            if (n.type === "delay" && n.config && n.config.delay_days) {
                var small = document.createElement("small");
                small.textContent = n.config.delay_days + " " + (n.config.delay_unit || "dias");
                textDiv.appendChild(small);
            } else if (n.type === "condition" && n.config && n.config.rule) {
                var small = document.createElement("small");
                small.textContent = n.config.rule.replace(/_/g, " ");
                textDiv.appendChild(small);
            } else if (n.channel) {
                var small = document.createElement("small");
                small.textContent = n.channel;
                textDiv.appendChild(small);
            }
            div.appendChild(iconSpan);
            div.appendChild(textDiv);
            fo.appendChild(div);
            g.appendChild(fo);

            /* port-in (top) — decorative drop target, aria-hidden */
            if (n.type !== "start") {
                var portIn = document.createElementNS("http://www.w3.org/2000/svg", "circle");
                portIn.setAttribute("class", "seq-port seq-port-in");
                portIn.setAttribute("cx", String(NODE_W / 2));
                portIn.setAttribute("cy", "0");
                portIn.setAttribute("r", String(PORT_R));
                portIn.setAttribute("aria-hidden", "true");
                g.appendChild(portIn);
            }
            /* port-out (bottom) — interactive: drag to connect */
            if (n.type !== "end") {
                var portOut = document.createElementNS("http://www.w3.org/2000/svg", "circle");
                portOut.setAttribute("class", "seq-port seq-port-out");
                portOut.setAttribute("cx", String(NODE_W / 2));
                portOut.setAttribute("cy", String(NODE_H));
                portOut.setAttribute("r", String(PORT_R));
                portOut.setAttribute("data-port-out", "1");
                portOut.setAttribute("role", "button");
                portOut.setAttribute("tabindex", "0");
                portOut.setAttribute("aria-label", "Conectar saida");
                g.appendChild(portOut);
            }

            self._nodesG.appendChild(g);
        });
    };

    HermesSequenceCanvas.prototype._renderEdges = function () {
        var self = this;
        while (this._edgesG.firstChild) this._edgesG.removeChild(this._edgesG.firstChild);

        this._edges.forEach(function (e) {
            var fromNode = self._nodes.find(function (n) { return n.id === e.from; });
            var toNode   = self._nodes.find(function (n) { return n.id === e.to; });
            if (!fromNode || !toNode) return;

            var x1 = fromNode.x + NODE_W / 2;
            var y1 = fromNode.y + NODE_H;
            var x2 = toNode.x   + NODE_W / 2;
            var y2 = toNode.y;
            var cy = (y1 + y2) / 2;

            var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
            path.setAttribute("class", "seq-edge");
            path.setAttribute("d", "M " + x1 + " " + y1 + " C " + x1 + " " + cy + " " + x2 + " " + cy + " " + x2 + " " + y2);
            path.setAttribute("marker-end", "url(#seq-arrow-" + self._uid + ")");
            path.setAttribute("data-from", e.from);
            path.setAttribute("data-to", e.to);

            self._edgesG.appendChild(path);
        });
    };

    /* ── Bind events ────────────────────────────────────── */

    HermesSequenceCanvas.prototype._bindEvents = function () {
        var self = this;
        var container = this._container;

        /* toolbar buttons */
        container.addEventListener("click", function (e) {
            var addBtn = e.target.closest("[data-add]");
            if (addBtn) {
                var parts = addBtn.dataset.add.split("|");
                self.addNode(parts[0], parts[1] || null, parts[2] || null);
                return;
            }
            var saveBtn = e.target.closest(".seq-save-btn");
            if (saveBtn) { self.save(); return; }

            var zoomBtn = e.target.closest("[data-zoom]");
            if (zoomBtn) {
                var z = zoomBtn.dataset.zoom;
                if (z === "in")    self._zoomBy(0.15);
                else if (z === "out")   self._zoomBy(-0.15);
                else if (z === "reset") self._resetZoom();
                return;
            }
        });

        /* SVG drag, connect, select */
        var svg = this._svgEl;

        svg.addEventListener("mousedown", function (e) {
            /* port-out drag → start connect */
            if (e.target.dataset.portOut) {
                var nodeG = e.target.closest(".seq-node");
                if (nodeG) {
                    self._connectState = { fromId: nodeG.dataset.nodeId };
                    e.preventDefault();
                    return;
                }
            }
            /* node drag */
            var nodeG = e.target.closest(".seq-node");
            if (nodeG) {
                var nodeId = nodeG.dataset.nodeId;
                var node = self._nodes.find(function (n) { return n.id === nodeId; });
                if (node) {
                    self._dragState = { nodeId: nodeId, startX: e.clientX, startY: e.clientY, origX: node.x, origY: node.y };
                    e.preventDefault();
                }
            }
        });

        svg.addEventListener("mousemove", function (e) {
            if (!self._dragState) return;
            var dx = e.clientX - self._dragState.startX;
            var dy = e.clientY - self._dragState.startY;
            var node = self._nodes.find(function (n) { return n.id === self._dragState.nodeId; });
            if (node) {
                node.x = self._dragState.origX + dx / self._viewport.zoom;
                node.y = self._dragState.origY + dy / self._viewport.zoom;
                self._renderAll();
            }
        });

        svg.addEventListener("mouseup", function (e) {
            /* complete connect */
            if (self._connectState) {
                var targetNodeG = e.target.closest(".seq-node");
                if (targetNodeG && targetNodeG.dataset.nodeId !== self._connectState.fromId) {
                    /* avoid duplicate edges */
                    var fromId = self._connectState.fromId;
                    var toId   = targetNodeG.dataset.nodeId;
                    var dup = self._edges.some(function (ed) { return ed.from === fromId && ed.to === toId; });
                    if (!dup) {
                        self._edges.push({ from: fromId, to: toId, type: "default" });
                        self._renderEdges();
                    }
                }
                self._connectState = null;
            }
            self._dragState = null;
        });

        /* click to select node */
        svg.addEventListener("click", function (e) {
            var nodeG = e.target.closest(".seq-node");
            if (nodeG) {
                self._selectNode(nodeG.dataset.nodeId);
                return;
            }
            /* click on empty area → deselect */
            if (e.target === svg || e.target.tagName === "svg") {
                self._selectNode(null);
            }
        });

        /* keyboard navigation on nodes */
        svg.addEventListener("keydown", function (e) {
            var nodeG = e.target.closest(".seq-node");
            if (!nodeG) return;
            var nodeId = nodeG.dataset.nodeId;
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                self._selectNode(nodeId);
            }
            if (e.key === "Delete" || e.key === "Backspace") {
                e.preventDefault();
                self._removeNode(nodeId);
            }
            var node = self._nodes.find(function (n) { return n.id === nodeId; });
            if (node) {
                var moved = false;
                if (e.key === "ArrowUp")    { node.y -= 10; moved = true; }
                if (e.key === "ArrowDown")  { node.y += 10; moved = true; }
                if (e.key === "ArrowLeft")  { node.x -= 10; moved = true; }
                if (e.key === "ArrowRight") { node.x += 10; moved = true; }
                if (moved) { e.preventDefault(); self._renderAll(); }
            }
        });

        /* global Delete key for selected node */
        document.addEventListener("keydown", this._boundKeydown);
    };

    HermesSequenceCanvas.prototype._onKeydown = function (e) {
        if (!this._selectedNodeId) return;
        if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT")) return;
        if (e.key === "Delete" || e.key === "Backspace") {
            this._removeNode(this._selectedNodeId);
        }
    };

    /* ── Node operations ────────────────────────────────── */

    HermesSequenceCanvas.prototype.addNode = function (type, channel, action) {
        var offsetX = 80 + (this._nodes.length % 3) * 60;
        var offsetY = 160 + Math.floor(this._nodes.length / 3) * 120;
        var node = {
            id: this._genId(),
            type: type,
            channel: channel || null,
            action: action || null,
            x: offsetX + Math.random() * 40,
            y: offsetY + Math.random() * 40,
            config: _defaultConfig(type, action),
        };
        this._nodes.push(node);
        this._renderAll();
        this._selectNode(node.id);
    };

    HermesSequenceCanvas.prototype._removeNode = function (nodeId) {
        var node = this._nodes.find(function (n) { return n.id === nodeId; });
        if (!node) return;
        if (node.type === "start" || node.type === "end") {
            if (window.hermesToast) window.hermesToast.warn("Nao e possivel remover nos de inicio/fim");
            return;
        }
        this._nodes = this._nodes.filter(function (n) { return n.id !== nodeId; });
        this._edges = this._edges.filter(function (e) { return e.from !== nodeId && e.to !== nodeId; });
        if (this._selectedNodeId === nodeId) this._selectedNodeId = null;
        this._renderAll();
        this._renderInspector();
    };

    HermesSequenceCanvas.prototype._selectNode = function (nodeId) {
        this._selectedNodeId = nodeId;
        this._renderNodes();
        this._renderInspector();
    };

    /* ── Inspector panel ────────────────────────────────── */

    HermesSequenceCanvas.prototype._renderInspector = function () {
        var self = this;
        var panel = this._inspectorEl;
        if (!panel) return;
        var node = this._selectedNodeId
            ? this._nodes.find(function (n) { return n.id === self._selectedNodeId; })
            : null;

        if (!node) {
            panel.innerHTML = '<p class="seq-inspector-empty">Clique em um no para editar</p>';
            return;
        }

        panel.innerHTML = "";

        /* title */
        var title = document.createElement("h3");
        title.className = "seq-inspector-title";
        title.textContent = _nodeLabel(node);
        panel.appendChild(title);

        /* label field */
        var formGroup = function (label, id, inputEl) {
            var wrap = document.createElement("div");
            wrap.className = "seq-field";
            var lbl = document.createElement("label");
            lbl.setAttribute("for", id);
            lbl.textContent = label;
            inputEl.setAttribute("id", id);
            inputEl.className = "seq-field-input";
            wrap.appendChild(lbl);
            wrap.appendChild(inputEl);
            return wrap;
        };

        /* delay config */
        if (node.type === "delay") {
            var delayInput = document.createElement("input");
            delayInput.setAttribute("type", "number");
            delayInput.setAttribute("min", "1");
            delayInput.setAttribute("max", "90");
            delayInput.value = String(node.config.delay_days || 3);
            delayInput.addEventListener("change", function () {
                node.config.delay_days = parseInt(this.value, 10) || 1;
                self._renderNodes();
            });
            panel.appendChild(formGroup("Dias de espera", "insp-delay-days-" + node.id, delayInput));

            var unitSel = document.createElement("select");
            ["hours", "days"].forEach(function (u) {
                var opt = document.createElement("option");
                opt.value = u;
                opt.textContent = u === "hours" ? "Horas" : "Dias";
                if (node.config.delay_unit === u) opt.selected = true;
                unitSel.appendChild(opt);
            });
            unitSel.addEventListener("change", function () {
                node.config.delay_unit = this.value;
                self._renderNodes();
            });
            panel.appendChild(formGroup("Unidade", "insp-delay-unit-" + node.id, unitSel));
        }

        /* condition config */
        if (node.type === "condition") {
            var condSel = document.createElement("select");
            [
                ["if_accepted",    "Se aceito (LI Connect)"],
                ["if_replied",     "Se respondeu"],
                ["if_clicked",     "Se clicou"],
                ["if_opened",      "Se abriu email"],
                ["if_not_replied", "Se nao respondeu"],
            ].forEach(function (pair) {
                var opt = document.createElement("option");
                opt.value = pair[0];
                opt.textContent = pair[1];
                if (node.config.rule === pair[0]) opt.selected = true;
                condSel.appendChild(opt);
            });
            condSel.addEventListener("change", function () {
                node.config.rule = this.value;
                self._renderNodes();
            });
            panel.appendChild(formGroup("Regra", "insp-cond-rule-" + node.id, condSel));
        }

        /* action: channel (read-only label) */
        if (node.type === "action") {
            var chLabel = document.createElement("p");
            chLabel.className = "seq-inspector-meta";
            chLabel.textContent = "Canal: " + (node.channel || "—") + " / Acao: " + (node.action || "—");
            panel.appendChild(chLabel);

            var tmplNote = document.createElement("p");
            tmplNote.className = "seq-inspector-note";
            tmplNote.textContent = "Templates e personalizacao: disponivel em F6-B.";
            panel.appendChild(tmplNote);
        }

        /* remove button (not for start/end) */
        if (node.type !== "start" && node.type !== "end") {
            var removeBtn = document.createElement("button");
            removeBtn.className = "btn btn-ghost btn-sm seq-inspector-remove";
            removeBtn.innerHTML = _icon("trash") + " Remover no";
            removeBtn.addEventListener("click", function () {
                self._removeNode(node.id);
            });
            panel.appendChild(removeBtn);
        }
    };

    /* ── Save / Load ────────────────────────────────────── */

    HermesSequenceCanvas.prototype.save = function () {
        var self = this;
        var canvas = {
            nodes: this._nodes.map(function (n) {
                return { id: n.id, type: n.type, channel: n.channel, action: n.action, x: n.x, y: n.y, config: n.config };
            }),
            edges: this._edges.map(function (e) {
                return { "from": e.from, to: e.to, type: e.type };
            }),
        };
        var payload = {
            name: this._sequenceName,
            description: this._sequenceDescription,
            canvas_json: canvas,
        };

        var url = this._sequenceId ? "/api/sequences/" + this._sequenceId : "/api/sequences";
        var method = this._sequenceId ? "PUT" : "POST";

        fetch(url, {
            method: method,
            headers: {
                "Content-Type": "application/json",
                "X-Hermes-Token": (typeof getToken === "function" ? getToken() : (localStorage.getItem("hermes_token") || "")),
            },
            body: JSON.stringify(payload),
        })
        .then(function (r) {
            if (!r.ok) throw new Error("HTTP " + r.status);
            return r.json();
        })
        .then(function (data) {
            if (data.id) self._sequenceId = data.id;
            if (window.hermesToast) window.hermesToast.success("Sequencia salva");
        })
        .catch(function (err) {
            if (window.hermesToast) window.hermesToast.error("Erro ao salvar: " + err.message);
        });
    };

    HermesSequenceCanvas.prototype.load = function (seqId) {
        var self = this;
        fetch("/api/sequences/" + seqId, {
            headers: {
                "X-Hermes-Token": (typeof getToken === "function" ? getToken() : (localStorage.getItem("hermes_token") || "")),
            },
        })
        .then(function (r) {
            if (!r.ok) throw new Error("HTTP " + r.status);
            return r.json();
        })
        .then(function (data) {
            self._sequenceId = seqId;
            self._sequenceName = data.sequence.name || "Sequencia";
            self._sequenceDescription = data.sequence.description || "";
            self._nodes = (data.nodes || []).map(function (n) {
                return {
                    id: n.id,
                    type: n.node_type,
                    channel: n.channel,
                    action: n.action_type,
                    x: n.position_x,
                    y: n.position_y,
                    config: (function () { try { return JSON.parse(n.config_json || "{}"); } catch (e) { return {}; } })(),
                };
            });
            self._edges = (data.edges || []).map(function (e) {
                return { from: e.from_node, to: e.to_node, type: e.edge_type };
            });
            self._renderAll();
        })
        .catch(function (err) {
            if (window.hermesToast) window.hermesToast.error("Erro ao carregar sequencia: " + err.message);
        });
    };

    HermesSequenceCanvas.prototype.newSequence = function () {
        this._sequenceId = null;
        this._sequenceName = "Nova Sequencia";
        this._sequenceDescription = "";
        this._selectedNodeId = null;
        this._nodes = [];
        this._edges = [];
        this._initDefaultNodes();
        this._renderAll();
        this._renderInspector();
    };

    /* ── Zoom ────────────────────────────────────────────── */

    HermesSequenceCanvas.prototype._zoomBy = function (delta) {
        this._viewport.zoom = Math.max(0.3, Math.min(2.5, this._viewport.zoom + delta));
        this._applyViewport();
    };

    HermesSequenceCanvas.prototype._resetZoom = function () {
        this._viewport.zoom = 1;
        this._applyViewport();
    };

    HermesSequenceCanvas.prototype._applyViewport = function () {
        if (this._nodesG) this._nodesG.setAttribute("transform", "scale(" + this._viewport.zoom + ")");
        if (this._edgesG) this._edgesG.setAttribute("transform", "scale(" + this._viewport.zoom + ")");
    };

    /* ── Refresh (re-mount safe) ───────────────────────── */

    HermesSequenceCanvas.prototype._refresh = function () {
        this._renderAll();
        this._renderInspector();
    };

    /* ── Destroy ────────────────────────────────────────── */

    HermesSequenceCanvas.prototype.destroy = function () {
        document.removeEventListener("keydown", this._boundKeydown);
        if (this._container) this._container.innerHTML = "";
        this._mounted = false;
    };

    /* ─── Expose singleton ──────────────────────────────── */

    window.HermesSequenceCanvas = HermesSequenceCanvas;
    window.sequenceCanvas = new HermesSequenceCanvas();

})();
