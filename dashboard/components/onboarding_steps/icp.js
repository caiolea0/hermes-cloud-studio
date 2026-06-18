/* UX-RM-F3-B — Onboarding Step 4: ICP Filters
 * Registers with HermesOnboardingWizard when script loads.
 * Dependency: onboarding_wizard.js must load first.
 *
 * API exposed:
 *   window._OnboardingStepICP — step object
 *   window._OnboardingIcpLoadPreset(id) — load a preset by id, re-renders form
 */
(function () {
    'use strict';

    var _presets = [];
    var _lastContainer = null;
    var _lastState = null;
    var _lastNav = null;

    var SENIORITY_OPTIONS = ['c_level', 'vp', 'director', 'manager'];

    function _escAttr(s) {
        if (!s) return '';
        return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function _safeApi(path, opts) {
        if (typeof api === 'function') {
            return api(path, opts);
        }
        return Promise.reject(new Error('api not available'));
    }

    function _strToArr(val) {
        if (!val) return [];
        return val.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    }

    function _arrToStr(arr) {
        if (!arr || !arr.length) return '';
        return arr.join(', ');
    }

    function _renderPresetCards() {
        if (!_presets.length) {
            return '<p class="wiz-presets-empty">Carregando templates...</p>';
        }
        return '<div class="wiz-presets">' +
            '<p class="wiz-presets-label">Templates recomendados:</p>' +
            '<div class="wiz-preset-grid">' +
            _presets.map(function (p) {
                var hint = p.icp.industries ? p.icp.industries.slice(0, 2).join(', ') : '';
                return '<button class="wiz-preset-card" type="button"' +
                    ' data-preset-id="' + _escAttr(p.id) + '"' +
                    ' aria-label="Carregar preset ' + _escAttr(p.name) + '">' +
                    '<span class="wiz-preset-name">' + _escAttr(p.name) + '</span>' +
                    '<span class="wiz-preset-hint">' + _escAttr(hint) + '</span>' +
                    '</button>';
            }).join('') +
            '</div>' +
            '</div>';
    }

    function _renderSeniorityChecks(selected) {
        selected = selected || [];
        return SENIORITY_OPTIONS.map(function (s) {
            var isChecked = selected.indexOf(s) >= 0;
            var label = s.replace('_', ' ');
            return '<label class="wiz-chip">' +
                '<input type="checkbox" data-key="seniority_levels" value="' + s + '"' +
                (isChecked ? ' checked' : '') +
                ' aria-label="Senioridade ' + label + '">' +
                '<span>' + label + '</span>' +
                '</label>';
        }).join('');
    }

    function _bindFormEvents(container, state) {
        // Text inputs: comma-separated → array
        container.querySelectorAll('input[type=text][data-key]').forEach(function (el) {
            el.addEventListener('change', function () {
                state.icp = state.icp || {};
                state.icp[el.dataset.key] = _strToArr(el.value);
                if (window.HermesOnboardingWizard) window.HermesOnboardingWizard.saveState();
            });
        });

        // Number inputs
        container.querySelectorAll('input[type=number][data-key]').forEach(function (el) {
            el.addEventListener('change', function () {
                state.icp = state.icp || {};
                state.icp[el.dataset.key] = el.value ? parseInt(el.value, 10) : null;
                if (window.HermesOnboardingWizard) window.HermesOnboardingWizard.saveState();
            });
        });

        // Seniority checkboxes
        container.querySelectorAll('input[type=checkbox][data-key=seniority_levels]').forEach(function (el) {
            el.addEventListener('change', function () {
                state.icp = state.icp || {};
                state.icp.seniority_levels = state.icp.seniority_levels || [];
                if (el.checked) {
                    if (state.icp.seniority_levels.indexOf(el.value) < 0) {
                        state.icp.seniority_levels.push(el.value);
                    }
                } else {
                    state.icp.seniority_levels = state.icp.seniority_levels.filter(function (s) {
                        return s !== el.value;
                    });
                }
                if (window.HermesOnboardingWizard) window.HermesOnboardingWizard.saveState();
            });
        });
    }

    function _loadPreset(id) {
        var p = null;
        for (var i = 0; i < _presets.length; i++) {
            if (_presets[i].id === id) { p = _presets[i]; break; }
        }
        if (!p || !_lastState || !_lastContainer) return;
        // Deep-copy preset ICP into state
        _lastState.icp = JSON.parse(JSON.stringify(p.icp));
        if (window.HermesOnboardingWizard) window.HermesOnboardingWizard.saveState();

        // Update form inputs directly (no full re-render, avoids duplicate event listeners)
        var b = _lastContainer;
        var icp = _lastState.icp;

        var el = b.querySelector('#icp-industries');
        if (el) el.value = _arrToStr(icp.industries);
        el = b.querySelector('#icp-titles');
        if (el) el.value = _arrToStr(icp.job_titles);
        el = b.querySelector('#icp-states');
        if (el) el.value = _arrToStr(icp.states);
        el = b.querySelector('#icp-cities');
        if (el) el.value = _arrToStr(icp.cities);
        el = b.querySelector('#icp-size-min');
        if (el) el.value = icp.company_size_min || '';
        el = b.querySelector('#icp-size-max');
        if (el) el.value = icp.company_size_max || '';
        el = b.querySelector('#icp-daily');
        if (el) el.value = icp.max_prospects_per_day || 5;

        b.querySelectorAll('input[type=checkbox][data-key=seniority_levels]').forEach(function (cb) {
            cb.checked = (icp.seniority_levels || []).indexOf(cb.value) >= 0;
        });

        // Open details to reveal filled values
        var details = b.querySelector('.wiz-icp-form');
        if (details) details.open = true;
    }

    window._OnboardingIcpLoadPreset = _loadPreset;

    function _wirePresetCards(container) {
        container.querySelectorAll('.wiz-preset-card[data-preset-id]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                _loadPreset(btn.dataset.presetId);
            });
        });
    }

    var icpStep = {
        id: 'icp',
        title: 'Ideal Customer Profile',

        onEnter: function (state) {
            // Ensure geo default so validate passes once target is set
            if (!state.icp) {
                state.icp = { countries: ['BR'], max_prospects_per_day: 5 };
            }

            // Load presets async — update preset area + wire events on arrival
            _safeApi('/api/icp/presets').then(function (r) {
                if (r && r.presets && r.presets.length) {
                    _presets = r.presets;
                    if (_lastContainer) {
                        var presetEl = _lastContainer.querySelector('.wiz-presets, .wiz-presets-empty');
                        if (presetEl) {
                            var wrapper = document.createElement('div');
                            wrapper.innerHTML = _renderPresetCards();
                            presetEl.parentNode.replaceChild(wrapper.firstChild, presetEl);
                        }
                        // Wire click events on newly inserted cards
                        _wirePresetCards(_lastContainer);
                    }
                }
            }).catch(function () {});

            // Restore saved profile from backend if not in wizard state yet
            var hasData = state.icp && (
                (state.icp.industries && state.icp.industries.length) ||
                (state.icp.job_titles && state.icp.job_titles.length)
            );
            if (!hasData) {
                _safeApi('/api/icp/profile').then(function (r) {
                    if (r && r.data && Object.keys(r.data).length) {
                        state.icp = r.data;
                        if (_lastContainer) {
                            icpStep.render(_lastContainer, state, _lastNav);
                        }
                    }
                }).catch(function () {});
            }
        },

        render: function (container, state, nav) {
            _lastContainer = container;
            _lastState = state;
            _lastNav = nav;

            var icp = state.icp || {};

            container.innerHTML =
                '<h2 class="wiz-h1">Quem voce quer prospectar?</h2>' +
                '<p class="wiz-lead">Define seu Ideal Customer Profile (ICP). ' +
                'Cobaia vai buscar perfis matching estes filtros no LinkedIn.</p>' +

                _renderPresetCards() +

                '<details class="wiz-icp-form"' + (
                    (icp.industries && icp.industries.length) ||
                    (icp.job_titles && icp.job_titles.length) ? ' open' : ''
                ) + '>' +
                '<summary class="wiz-icp-summary">Customizar ICP</summary>' +

                '<fieldset class="wiz-fieldset">' +
                '<legend>Empresa-alvo</legend>' +
                '<div class="wiz-field">' +
                '<label for="icp-industries">Industrias <span class="wiz-req" aria-hidden="true">*</span></label>' +
                '<input type="text" id="icp-industries" data-key="industries"' +
                ' value="' + _escAttr(_arrToStr(icp.industries)) + '"' +
                ' placeholder="Software, Marketing Agency, SaaS..."' +
                ' aria-describedby="icp-industries-hint" aria-required="true">' +
                '<span class="wiz-field-hint" id="icp-industries-hint">Separe por virgula. Ex: SaaS, Marketing</span>' +
                '</div>' +
                '<div class="wiz-row">' +
                '<div class="wiz-field">' +
                '<label for="icp-size-min">Min colaboradores</label>' +
                '<input type="number" id="icp-size-min" data-key="company_size_min"' +
                ' value="' + (icp.company_size_min || '') + '" min="1">' +
                '</div>' +
                '<div class="wiz-field">' +
                '<label for="icp-size-max">Max colaboradores</label>' +
                '<input type="number" id="icp-size-max" data-key="company_size_max"' +
                ' value="' + (icp.company_size_max || '') + '" min="1">' +
                '</div>' +
                '</div>' +
                '</fieldset>' +

                '<fieldset class="wiz-fieldset">' +
                '<legend>Persona-alvo</legend>' +
                '<div class="wiz-field">' +
                '<label for="icp-titles">Cargos <span class="wiz-req" aria-hidden="true">*</span></label>' +
                '<input type="text" id="icp-titles" data-key="job_titles"' +
                ' value="' + _escAttr(_arrToStr(icp.job_titles)) + '"' +
                ' placeholder="Founder, CEO, Marketing Director..."' +
                ' aria-required="true">' +
                '</div>' +
                '<div class="wiz-field">' +
                '<label id="seniority-group-label">Senioridades</label>' +
                '<div class="wiz-checkboxes" role="group" aria-labelledby="seniority-group-label">' +
                _renderSeniorityChecks(icp.seniority_levels) +
                '</div>' +
                '</div>' +
                '</fieldset>' +

                '<fieldset class="wiz-fieldset">' +
                '<legend>Geo</legend>' +
                '<div class="wiz-field">' +
                '<label for="icp-states">Estados BR (UF)</label>' +
                '<input type="text" id="icp-states" data-key="states"' +
                ' value="' + _escAttr(_arrToStr(icp.states)) + '"' +
                ' placeholder="MT, GO, DF, SP">' +
                '</div>' +
                '<div class="wiz-field">' +
                '<label for="icp-cities">Cidades especificas</label>' +
                '<input type="text" id="icp-cities" data-key="cities"' +
                ' value="' + _escAttr(_arrToStr(icp.cities)) + '"' +
                ' placeholder="Cuiaba, Varzea Grande...">' +
                '</div>' +
                '</fieldset>' +

                '<fieldset class="wiz-fieldset">' +
                '<legend>Limites diarios</legend>' +
                '<div class="wiz-field">' +
                '<label for="icp-daily">Max prospects/dia</label>' +
                '<input type="number" id="icp-daily" data-key="max_prospects_per_day"' +
                ' value="' + (icp.max_prospects_per_day || 5) + '" min="1" max="20"' +
                ' aria-describedby="icp-daily-hint">' +
                '<span class="wiz-field-hint" id="icp-daily-hint">LinkedIn safe: 3-5/dia no primeiro mes</span>' +
                '</div>' +
                '</fieldset>' +

                '</details>' +

                '<div class="wiz-actions">' +
                '<button class="btn-ghost" id="wiz-icp-prev" type="button"' +
                ' aria-label="Voltar para configuracao de canais">&larr; Voltar</button>' +
                '<button class="btn-primary" id="wiz-icp-next" type="button"' +
                ' aria-label="Avancar para Pre-Flight">Proximo &rarr;</button>' +
                '</div>';

            // Wire preset cards (cards present at initial render; async-loaded ones wired in onEnter)
            _wirePresetCards(container);

            _bindFormEvents(container, state);

            container.querySelector('#wiz-icp-prev').addEventListener('click', function () { nav.prev(); });
            container.querySelector('#wiz-icp-next').addEventListener('click', function () { nav.next(); });
        },

        onExit: function (state) {
            if (!state.icp) return;
            // Ensure countries default before saving
            if (!state.icp.countries || !state.icp.countries.length) {
                state.icp.countries = ['BR'];
            }
            _safeApi('/api/icp/profile', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(state.icp),
            }).catch(function () {
                if (window.hermesToast) {
                    window.hermesToast.error('Falha ao salvar ICP. Continuar offline.');
                }
            });
        },

        validate: function (state) {
            var icp = state.icp || {};
            var hasTarget = (icp.industries && icp.industries.length) ||
                            (icp.job_titles && icp.job_titles.length);
            var hasGeo = (icp.countries && icp.countries.length) ||
                         (icp.states && icp.states.length) ||
                         (icp.cities && icp.cities.length);
            return !!(hasTarget && hasGeo);
        },
    };

    if (window.HermesOnboardingWizard) {
        window.HermesOnboardingWizard.register(icpStep);
    }
    window._OnboardingStepICP = icpStep;
})();
