/**
 * UX-RM-F4-B — Theme Toggle (global window.HermesThemeToggle).
 *
 * Manages 3-mode theme: auto (system) | light | dark.
 * Persists in localStorage key 'hermes.theme'.
 * Sets data-theme attribute on <html> element.
 * Coordinates with FOUC script in index.html (same key).
 *
 * API:
 *   window.HermesThemeToggle.setTheme('auto'|'light'|'dark')
 *   window.HermesThemeToggle.cycle()  — auto → dark → light → auto
 *   window.HermesThemeToggle.theme    — current value
 *   window.HermesThemeToggle.render(containerEl)
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'hermes.theme';

    class HermesThemeToggle {
        constructor() {
            this._theme = localStorage.getItem(STORAGE_KEY) || 'auto';
            this._apply();
        }

        get theme() { return this._theme; }

        setTheme(t) {
            if (t !== 'auto' && t !== 'light' && t !== 'dark') return;
            this._theme = t;
            localStorage.setItem(STORAGE_KEY, t);
            this._apply();
            document.dispatchEvent(new CustomEvent('hermes:theme-changed', { detail: { theme: t } }));
        }

        cycle() {
            var order = ['auto', 'dark', 'light'];
            var idx = order.indexOf(this._theme);
            this.setTheme(order[(idx + 1) % order.length]);
        }

        _apply() {
            var isDark = this._theme === 'dark' ||
                (this._theme === 'auto' &&
                 window.matchMedia &&
                 window.matchMedia('(prefers-color-scheme: dark)').matches);
            document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
        }

        render(container) {
            if (!container) return;
            var self = this;
            var themes = [
                { value: 'auto',  label: 'Auto' },
                { value: 'dark',  label: 'Dark' },
                { value: 'light', label: 'Light' },
            ];
            container.innerHTML =
                '<div class="theme-toggle" role="radiogroup" aria-label="Tema da interface">' +
                themes.map(function (t) {
                    var isActive = self._theme === t.value;
                    return '<button type="button" role="radio" ' +
                           'class="theme-toggle-btn' + (isActive ? ' active' : '') + '" ' +
                           'aria-checked="' + isActive + '" ' +
                           'data-theme-val="' + t.value + '">' +
                           t.label + '</button>';
                }).join('') +
                '</div>';

            container.querySelectorAll('[data-theme-val]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    self.setTheme(btn.dataset.themeVal);
                    self.render(container);
                });
            });
        }
    }

    window.HermesThemeToggle = new HermesThemeToggle();

    // Auto-respond to system prefers-color-scheme changes when in 'auto' mode
    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
            if (window.HermesThemeToggle.theme === 'auto') {
                window.HermesThemeToggle._apply();
            }
        });
    }
})();
