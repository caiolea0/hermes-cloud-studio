/* ============================================================
   Pipeline Studio — Step Picker Modal (F.9.3a STUB → F.9.3b REAL)
   ============================================================
   STUB para Commit 1. Implementação real em Commit 2 (F.9.3b).
   Expõe window.PipelineStudioStepPickerModal.{open, close}.
   ============================================================ */
(function () {
    "use strict";

    function open(onSelect) {
        var modal = document.getElementById("ps-step-picker-modal");
        if (!modal) return;
        modal.removeAttribute("hidden");
        /* Stub placeholder — substituído em F.9.3b */
        var toolsList = modal.querySelector(".ps-tools-list");
        if (toolsList) {
            toolsList.innerHTML = '<div class="ps-tools-empty">Implementação completa em F.9.3b...</div>';
        }
    }

    function close() {
        var modal = document.getElementById("ps-step-picker-modal");
        if (!modal) return;
        modal.setAttribute("hidden", "");
    }

    window.PipelineStudioStepPickerModal = { open: open, close: close };

})();
