/* F.8.3 ObservabilityResolveModal — STUB Commit 1 (real impl Commit 3). */
(function () {
    "use strict";
    function open() { /* no-op stub */ }
    function close() {
        var m = document.getElementById("observability-resolve-modal");
        if (m) m.hidden = true;
    }
    window.ObservabilityResolveModal = { open: open, close: close };
})();
