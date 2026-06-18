/* ============================================================
   Hermes Cloud Studio — Component Lazy Loader (UX-RM-F7-A)
   ============================================================
   Expoe window.loadComponent(name, subdir?) — carrega JS sob-demanda.
   Cache-busting via BUNDLE_VERSION. Dedup em-flight: chamadas
   concorrentes para o mesmo componente retornam a mesma Promise.
   Fail-graceful: rejeita promise com Error descritivo — caller
   deve capturar e exibir hermesToast.error.
   ============================================================ */
(function () {
    'use strict';

    var BUNDLE_VERSION = 'f7a-2026-06-18';
    var _loaded = new Set();
    var _loading = new Map();

    /**
     * @param {string} name - nome do arquivo sem .js (ex: 'command_palette')
     * @param {string} [subdir] - subpasta dentro de components/ (ex: 'onboarding_steps')
     * @returns {Promise<void>}
     */
    function loadComponent(name, subdir) {
        var key = subdir ? subdir + '/' + name : name;
        if (_loaded.has(key)) return Promise.resolve();
        if (_loading.has(key)) return _loading.get(key);

        var src = subdir
            ? '/dashboard/components/' + subdir + '/' + name + '.js?v=' + BUNDLE_VERSION
            : '/dashboard/components/' + name + '.js?v=' + BUNDLE_VERSION;

        var promise = new Promise(function (resolve, reject) {
            var script = document.createElement('script');
            script.src = src;
            script.onload = function () { _loaded.add(key); resolve(); };
            script.onerror = function () {
                reject(new Error('loadComponent: falha ao carregar ' + key));
            };
            document.head.appendChild(script);
        });

        _loading.set(key, promise);
        promise.then(
            function () { _loading.delete(key); },
            function () { _loading.delete(key); }
        );
        return promise;
    }

    window.loadComponent = loadComponent;
    window.BUNDLE_VERSION = BUNDLE_VERSION;
})();
