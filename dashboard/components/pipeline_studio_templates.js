/* ============================================================
   Pipeline Studio — Templates (F.9.3a STUB → F.9.3c REAL)
   ============================================================
   STUB para Commit 1. Implementação real em Commit 3 (F.9.3c).
   Expõe window.PipelineStudioTemplates.{init, render, destroy}.
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
        var panel = document.getElementById("ps-panel-templates");
        if (!panel) return;
        if (!panel.querySelector(".ps-templates-grid")) {
            panel.innerHTML = '<div class="ps-stub-placeholder">Carregando Templates...</div>';
        }
    }

    function destroy() {
        _initialized = false;
    }

    window.PipelineStudioTemplates = { init: init, render: render, destroy: destroy };

})();
