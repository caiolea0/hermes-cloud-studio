(function () {
    'use strict';

    function _renderFallback(el) {
        const name = el.dataset.component || 'unknown';
        el.innerHTML = `
            <div class="error-boundary" role="alert" aria-live="assertive">
                <svg style="width:24px;height:24px;stroke:var(--red);flex-shrink:0" aria-hidden="true">
                    <use href="#i-alert-triangle"/>
                </svg>
                <div>
                    <h3 style="font-size: var(--text-sm);font-weight:700;color:var(--text-1);margin:0 0 4px">Componente ${_esc(name)} falhou</h3>
                    <p style="font-size: var(--text-xxs);color:var(--text-3);margin:0 0 8px">Erro inesperado ao renderizar este painel.</p>
                    <button type="button" class="btn btn-ghost btn-sm" onclick="location.reload()">Recarregar</button>
                </div>
            </div>
        `;
    }

    function _esc(str) {
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    function _reportComponentError(componentName, error) {
        try {
            const token = localStorage.getItem('hermes_token');
            if (!token) return;
            const apiBase = localStorage.getItem('hermes_api') || '';
            fetch(apiBase + '/api/observability/component-error', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Hermes-Token': token },
                body: JSON.stringify({
                    component: componentName,
                    error: String(error),
                    url: location.hash,
                    ts: Date.now(),
                }),
            }).catch(() => {});
        } catch (_) {}
    }

    window.addEventListener('error', function (e) {
        const el = e.target && e.target.closest && e.target.closest('[data-component]');
        if (el && el.dataset.component) {
            _renderFallback(el);
            _reportComponentError(el.dataset.component, e.message || e.error);
        }
    });

    window.addEventListener('unhandledrejection', function (e) {
        const msg = (e.reason && e.reason.message) || String(e.reason);
        console.warn('[ErrorBoundary] unhandled rejection:', msg);
    });

    window.HermesErrorBoundary = {
        wrap(componentEl, fn) {
            try {
                return fn();
            } catch (e) {
                if (componentEl && componentEl.dataset) {
                    _renderFallback(componentEl);
                    _reportComponentError(componentEl.dataset.component || 'unknown', e);
                }
                return null;
            }
        },
    };
})();
