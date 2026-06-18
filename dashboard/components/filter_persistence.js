/* UX-RM-F2-B — Filter Persistence
 * API global: window.HermesFilterPersistence.{get, set, clear}
 * Namespace: hermes.filters.<page>
 */
(function () {
    'use strict';

    const _NS = 'hermes.filters';

    function get(page) {
        try {
            return JSON.parse(localStorage.getItem(`${_NS}.${page}`) || '{}');
        } catch {
            return {};
        }
    }

    function set(page, filters) {
        try {
            localStorage.setItem(`${_NS}.${page}`, JSON.stringify(filters));
        } catch { /* storage quota exceeded — silent */ }
    }

    function clear(page) {
        try {
            localStorage.removeItem(`${_NS}.${page}`);
        } catch { /* noop */ }
    }

    window.HermesFilterPersistence = { get, set, clear };
})();
