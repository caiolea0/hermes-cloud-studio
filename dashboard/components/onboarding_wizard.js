/* UX-RM-F3-A — HermesOnboardingWizard
 *
 * 3-step first-run wizard: Welcome → Profile Setup → Channel Config.
 * Opens automatically on first visit; skippable and resumable.
 *
 * API global: window.HermesOnboardingWizard.{open, close, skip, next, prev}
 * WCAG: role=dialog, aria-modal=true, focus trap, Escape closes, focus restored.
 * State: POST /api/onboarding/state (server) + localStorage fallback (offline).
 */
(function () {
    'use strict';

    var LS_COMPLETED = 'hermes.onboarding.completed';
    var LS_SKIPPED   = 'hermes.onboarding.skipped';
    var LS_STATE     = 'hermes.onboarding.state';

    var _steps = [];
    var _currentStep = 0;
    var _state = {};
    var _open = false;
    var _lastFocus = null;
    var _overlayEl = null;
    var _dialogEl = null;
    var _headerEl = null;
    var _bodyEl = null;

    // ── DOM build (idempotent) ─────────────────────────────────────────────

    function _build() {
        if (document.getElementById('onboarding-wizard-overlay')) {
            _overlayEl = document.getElementById('onboarding-wizard-overlay');
            _dialogEl  = document.getElementById('onboarding-wizard-dialog');
            _headerEl  = document.getElementById('onboarding-wizard-header');
            _bodyEl    = document.getElementById('onboarding-wizard-body');
            return;
        }

        _overlayEl = document.createElement('div');
        _overlayEl.id = 'onboarding-wizard-overlay';
        _overlayEl.className = 'wiz-overlay';
        _overlayEl.setAttribute('role', 'dialog');
        _overlayEl.setAttribute('aria-modal', 'true');
        _overlayEl.setAttribute('aria-labelledby', 'onboarding-wizard-title');

        _dialogEl = document.createElement('div');
        _dialogEl.id = 'onboarding-wizard-dialog';
        _dialogEl.className = 'wiz-dialog';
        _dialogEl.setAttribute('tabindex', '-1');

        _headerEl = document.createElement('div');
        _headerEl.id = 'onboarding-wizard-header';
        _headerEl.className = 'wiz-header';

        _bodyEl = document.createElement('div');
        _bodyEl.id = 'onboarding-wizard-body';
        _bodyEl.className = 'wiz-body';

        _dialogEl.appendChild(_headerEl);
        _dialogEl.appendChild(_bodyEl);
        _overlayEl.appendChild(_dialogEl);
        document.body.appendChild(_overlayEl);

        // Escape key
        document.addEventListener('keydown', function (e) {
            if (_open && e.key === 'Escape') { _skipOrClose(); }
        });

        // Focus trap on Tab
        _overlayEl.addEventListener('keydown', function (e) {
            if (!_open || e.key !== 'Tab') return;
            var focusable = _overlayEl.querySelectorAll(
                'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"]), a[href], details summary'
            );
            var arr = Array.prototype.slice.call(focusable);
            if (!arr.length) return;
            var first = arr[0];
            var last  = arr[arr.length - 1];
            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault(); last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault(); first.focus();
            }
        });
    }

    // ── State persistence ─────────────────────────────────────────────────

    function _saveState() {
        var payload = { lastStep: _currentStep, state: _state };
        if (typeof api === 'function') {
            api('/api/onboarding/state', {
                method: 'POST',
                body: JSON.stringify(payload),
                headers: { 'Content-Type': 'application/json' },
            }).catch(function () {
                localStorage.setItem(LS_STATE, JSON.stringify(payload));
            });
        } else {
            localStorage.setItem(LS_STATE, JSON.stringify(payload));
        }
    }

    function _loadSavedState(cb) {
        if (typeof api === 'function') {
            api('/api/onboarding/state').then(function (r) {
                cb(r && r.data && Object.keys(r.data).length ? r.data : null);
            }).catch(function () {
                var raw = localStorage.getItem(LS_STATE);
                cb(raw ? JSON.parse(raw) : null);
            });
        } else {
            var raw = localStorage.getItem(LS_STATE);
            cb(raw ? JSON.parse(raw) : null);
        }
    }

    function _markCompleted() {
        localStorage.setItem(LS_COMPLETED, '1');
        if (typeof api === 'function') {
            api('/api/onboarding/complete', { method: 'POST' }).catch(function () {});
        }
    }

    // ── Render ────────────────────────────────────────────────────────────

    function _renderHeader() {
        var total = _steps.length;
        var idx   = _currentStep;
        var pct   = total > 0 ? Math.round(((idx) / total) * 100) : 0;
        var step  = _steps[idx];
        _headerEl.innerHTML =
            '<div class="wiz-progress-bar-wrap">' +
                '<div class="wiz-progress-label" id="onboarding-wizard-title">' +
                    'Passo ' + (idx + 1) + ' de ' + total + ': ' + (step ? step.title : '') +
                '</div>' +
                '<div class="wiz-progress-track">' +
                    '<div class="wiz-progress-fill" role="progressbar"' +
                    ' aria-valuenow="' + (idx + 1) + '" aria-valuemin="1" aria-valuemax="' + total + '"' +
                    ' style="width:' + pct + '%"></div>' +
                '</div>' +
            '</div>' +
            '<button class="wiz-skip-btn" aria-label="Pular onboarding por agora">' +
                'Pular' +
            '</button>';
        _headerEl.querySelector('.wiz-skip-btn').addEventListener('click', _skipOrClose);
    }

    function _renderCurrent() {
        if (!_steps.length) return;
        _renderHeader();
        var step = _steps[_currentStep];
        _bodyEl.innerHTML = '';
        var nav = { next: _next, prev: _prev };
        step.render(_bodyEl, _state, nav);
        if (step.onEnter) step.onEnter(_state);
        // Move focus to dialog
        setTimeout(function () { _dialogEl.focus(); }, 50);
    }

    // ── Navigation ─────────────────────────────────────────────────────────

    function _next() {
        var step = _steps[_currentStep];
        if (step && step.validate && !step.validate(_state)) {
            if (window.hermesToast) {
                window.hermesToast.error('Complete os campos obrigatorios primeiro.');
            }
            return;
        }
        if (step && step.onExit) step.onExit(_state);
        _currentStep++;
        _saveState();
        if (_currentStep >= _steps.length) {
            _complete();
            return;
        }
        _renderCurrent();
    }

    function _prev() {
        if (_currentStep <= 0) return;
        _currentStep--;
        _saveState();
        _renderCurrent();
    }

    function _skipOrClose() {
        localStorage.setItem(LS_SKIPPED, '1');
        _saveState();
        _close();
    }

    function _complete() {
        _markCompleted();
        _close();
        if (window.hermesToast) {
            window.hermesToast.success('Configuracao concluida! Pressione ? para ver atalhos de teclado.');
        }
    }

    // ── Open / Close ──────────────────────────────────────────────────────

    function _open_wizard(opts) {
        opts = opts || {};
        _build();
        _lastFocus = document.activeElement;

        function _show(saved) {
            if (opts.resume && saved) {
                _state = saved.state || {};
                _currentStep = typeof saved.last_step === 'number' ? saved.last_step
                             : typeof saved.lastStep === 'number' ? saved.lastStep : 0;
            } else {
                _state = {};
                _currentStep = opts.startStep || 0;
            }
            _currentStep = Math.min(_currentStep, Math.max(0, _steps.length - 1));
            _open = true;
            _overlayEl.classList.add('wiz-open');
            _renderCurrent();
        }

        if (opts.resume) {
            _loadSavedState(_show);
        } else {
            _show(null);
        }
    }

    function _close() {
        _open = false;
        if (_overlayEl) _overlayEl.classList.remove('wiz-open');
        if (_lastFocus && _lastFocus.focus) {
            setTimeout(function () { _lastFocus.focus(); }, 50);
        }
    }

    // ── Public API ────────────────────────────────────────────────────────

    function register(step) {
        _steps.push(step);
    }

    window.HermesOnboardingWizard = {
        register: register,
        open: _open_wizard,
        close: _close,
        skip: _skipOrClose,
        next: _next,
        prev: _prev,
        complete: _complete,
        getState: function () { return _state; },
        setState: function (key, val) { _state[key] = val; },
        saveState: _saveState,
        isOpen: function () { return _open; },
    };

    // Auto-init once DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _build);
    } else {
        _build();
    }
})();
