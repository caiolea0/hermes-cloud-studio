/* ============================================================
   Pipeline Studio — Runs Monitor (F.9.3a STUB → F.9.3c REAL)
   ============================================================
   STUB para Commit 1. Implementação real em Commit 3 (F.9.3c).
   Expõe window.PipelineStudioRunsMonitor.{init, render, destroy}.
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
        var panel = document.getElementById("ps-panel-runs-monitor");
        if (!panel) return;
        if (!panel.querySelector(".ps-runs-list")) {
            panel.innerHTML = '<div class="ps-stub-placeholder">Carregando Runs Monitor...</div>';
        }
    }

    function destroy() {
        _initialized = false;
    }

    window.PipelineStudioRunsMonitor = { init: init, render: render, destroy: destroy };

})();
