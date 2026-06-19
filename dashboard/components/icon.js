/**
 * UX-RM-F4-B — Icon helper (global window.icon).
 *
 * Returns an SVG <use href="#i-{name}"> string from the inline sprite
 * defined in index.html <defs>. Zero external deps, zero CDN.
 *
 * Usage:
 *   element.innerHTML = window.icon('alert-triangle');
 *   element.innerHTML = window.icon('zap', { size: 20, label: 'Working' });
 *   element.innerHTML = window.icon('check', { cls: 'icon-success' });
 *
 * @param {string} name   Icon id (without "i-" prefix)
 * @param {object} [opts]
 *   opts.size  {number}  px — default 16
 *   opts.cls   {string}  extra CSS classes on <svg>
 *   opts.label {string}  aria-label (omit for decorative/aria-hidden)
 * @returns {string} HTML string safe to assign to .innerHTML
 */
(function () {
    'use strict';

    function icon(name, opts) {
        var size  = (opts && opts.size)  || 16;
        var cls   = (opts && opts.cls)   || '';
        var label = (opts && opts.label) || '';

        var aria  = label
            ? 'aria-label="' + label.replace(/"/g, '&quot;') + '"'
            : 'aria-hidden="true"';

        var classes = 'icon' + (cls ? ' ' + cls : '');

        return '<svg class="' + classes + '" ' +
               'width="' + size + '" height="' + size + '" ' +
               'viewBox="0 0 20 20" fill="none" ' +
               'stroke="currentColor" stroke-width="1.5" ' +
               'stroke-linecap="round" stroke-linejoin="round" ' +
               aria + ' focusable="false">' +
               '<use href="#i-' + name + '"/>' +
               '</svg>';
    }

    window.icon = icon;
})();
