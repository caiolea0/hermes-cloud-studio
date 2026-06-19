(function () {
    'use strict';

    class HermesOptimisticMutation {
        constructor() {
            this._pending = new Map();
        }

        async mutate({ optimisticUpdate, apiCall, rollback, successToast, liveRegionMsg }) {
            const id = Math.random().toString(36).slice(2);
            optimisticUpdate();
            if (liveRegionMsg) _announce(liveRegionMsg);
            this._pending.set(id, rollback);
            try {
                const result = await apiCall();
                this._pending.delete(id);
                if (successToast && typeof hermesToast !== 'undefined') {
                    hermesToast.success(successToast);
                } else if (successToast && typeof toast === 'function') {
                    toast(successToast, 'success');
                }
                return result;
            } catch (e) {
                rollback();
                this._pending.delete(id);
                if (liveRegionMsg) _announce('Falha: ' + e.message);
                if (typeof toast === 'function') toast('Falha: ' + e.message, 'error');
                throw e;
            }
        }

        hasPending() {
            return this._pending.size > 0;
        }

        rollbackAll() {
            for (const rb of this._pending.values()) {
                try { rb(); } catch (_) {}
            }
            this._pending.clear();
        }
    }

    function _announce(msg) {
        let el = document.getElementById('hermes-a11y-live');
        if (!el) {
            el = document.createElement('div');
            el.id = 'hermes-a11y-live';
            el.setAttribute('aria-live', 'polite');
            el.setAttribute('aria-atomic', 'true');
            el.className = 'sr-only';
            document.body.appendChild(el);
        }
        el.textContent = '';
        requestAnimationFrame(() => { el.textContent = msg; });
    }

    window.optimisticMutation = new HermesOptimisticMutation();
    window.HermesOptimisticMutation = HermesOptimisticMutation;
})();
