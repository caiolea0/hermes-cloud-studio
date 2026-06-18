/* ============================================================
   Hermes Cloud Studio — Skeleton Pattern Presets (UX-RM-F7-A)
   ============================================================
   Expoe window.skeletonPatterns = { table, card_grid, kpi_strip, timeline }
   Cada metodo retorna HTML string com aria-busy + aria-label.
   Usa classe .skeleton (styles.css) para shimmer animation.
   prefers-reduced-motion respeitado via @media no styles.css.
   ============================================================ */
(function () {
    'use strict';

    function _cell(w, h) {
        return '<div class="skeleton" role="presentation" aria-hidden="true" style="width:' + w + ';height:' + h + ';border-radius:var(--radius-sm,4px)"></div>';
    }

    var PATTERNS = {
        /**
         * Skeleton para tabela de dados.
         * @param {number} [rows=5] - linhas
         * @param {number} [cols=4] - colunas
         */
        table: function (rows, cols) {
            rows = Math.max(1, rows || 5);
            cols = Math.max(1, cols || 4);
            var html = '<div class="skel-table" aria-busy="true" aria-label="Carregando tabela">';
            for (var r = 0; r < rows; r++) {
                html += '<div class="skel-row" style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--s2)">';
                for (var c = 0; c < cols; c++) {
                    var w = c === 0 ? '28%' : (c === cols - 1 ? '8%' : '18%');
                    html += '<div style="flex:1">' + _cell(w, '13px') + '</div>';
                }
                html += '</div>';
            }
            html += '</div>';
            return html;
        },

        /**
         * Skeleton para grade de cards.
         * @param {number} [n=6] - numero de cards
         */
        card_grid: function (n) {
            n = Math.max(1, n || 6);
            var html = '<div class="skel-card-grid" aria-busy="true" aria-label="Carregando cards" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px">';
            for (var i = 0; i < n; i++) {
                html += '<div class="skel-card" style="padding:16px;border-radius:var(--r);background:var(--s2)">';
                html += _cell('65%', '14px');
                html += '<div style="margin:10px 0">' + _cell('100%', '10px') + '</div>';
                html += _cell('80%', '10px');
                html += '</div>';
            }
            html += '</div>';
            return html;
        },

        /**
         * Skeleton para strip de KPIs.
         * @param {number} [n=4] - numero de KPIs
         */
        kpi_strip: function (n) {
            n = Math.max(1, n || 4);
            var html = '<div class="skel-kpi-strip" aria-busy="true" aria-label="Carregando KPIs" style="display:grid;grid-template-columns:repeat(' + n + ',1fr);gap:16px">';
            for (var i = 0; i < n; i++) {
                html += '<div class="skel-kpi" style="padding:16px;border-radius:var(--r);background:var(--s2)">';
                html += _cell('50%', '11px');
                html += '<div style="margin:10px 0">' + _cell('70%', '28px') + '</div>';
                html += _cell('40%', '10px');
                html += '</div>';
            }
            html += '</div>';
            return html;
        },

        /**
         * Skeleton para feed de timeline/atividades.
         * @param {number} [n=8] - numero de items
         */
        timeline: function (n) {
            n = Math.max(1, n || 8);
            var html = '<div class="skel-timeline" aria-busy="true" aria-label="Carregando timeline" style="display:flex;flex-direction:column;gap:12px">';
            for (var i = 0; i < n; i++) {
                var lineW = (50 + (i % 4) * 12) + '%';
                html += '<div class="skel-timeline-item" style="display:flex;align-items:center;gap:12px">';
                html += '<div>' + _cell('32px', '32px') + '</div>';
                html += '<div style="flex:1">' + _cell(lineW, '13px') + '</div>';
                html += '</div>';
            }
            html += '</div>';
            return html;
        },
    };

    window.skeletonPatterns = PATTERNS;
})();
