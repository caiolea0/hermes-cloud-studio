/* dashboard/components/_utils.js
 * F.2.5b prep — shared utility helpers reusados em PrefPanel + LiveLogTail (F.2.5c) + F.6 Brain.
 *
 * window.hermesUtils.safeMerge(target, update)
 *   - Filtra entries cujo value === undefined ANTES de Object.assign
 *   - Defensivo contra WS broadcasts parciais que apagariam keys preservadas
 *   - Pattern já usado em F.2.5a (state merge defensivo SubsystemTileGrid)
 */
(function () {
    'use strict';
    window.hermesUtils = window.hermesUtils || {};

    if (typeof window.hermesUtils.safeMerge !== 'function') {
        window.hermesUtils.safeMerge = function safeMerge(target, update) {
            if (!update || typeof update !== 'object') return Object.assign({}, target || {});
            var cleaned = Object.entries(update).filter(function (e) { return e[1] !== undefined; });
            return Object.assign({}, target || {}, Object.fromEntries(cleaned));
        };
    }
})();
