/* ============================================================
   Pipeline Studio — Builder (F.9.3a STUB → F.9.3b REAL)
   ============================================================
   STUB para Commit 1. Implementação real em Commit 2 (F.9.3b).
   Expõe window.PipelineStudioBuilder.{init, render, destroy}.
   ============================================================ */
(function () {
    "use strict";

    var _initialized = false;

    function init() {
        if (_initialized) return;
        _initialized = true;
        render();
    }

    function render() {
        var panel = document.getElementById("ps-panel-builder");
        if (!panel) return;
        /* Stub placeholder — substituído em F.9.3b */
        var existing = panel.querySelector(".ps-builder-split");
        if (!existing) {
            panel.innerHTML = '<div class="ps-stub-placeholder">Carregando Builder...</div>';
        }
    }

    function destroy() {
        _initialized = false;
    }

    window.PipelineStudioBuilder = { init: init, render: render, destroy: destroy };

})();
