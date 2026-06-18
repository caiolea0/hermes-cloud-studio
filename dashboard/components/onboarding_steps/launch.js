/* UX-RM-F3-B — Onboarding Step 5: Launch Pre-Flight
 * Shows 5 preflight checks and activates cobaia warmup if all green.
 * validate() always returns true — user can complete wizard without launching.
 *
 * API exposed:
 *   window._OnboardingStepLaunch — step object
 *   window._HermesStartWarmup()  — POST start-warmup + complete wizard
 */
(function () {
    'use strict';

    function _escHtml(s) {
        if (!s) return '';
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function _safeApi(path, opts) {
        if (typeof api === 'function') {
            return api(path, opts);
        }
        return Promise.reject(new Error('api not available'));
    }

    // ── Preflight checks ─────────────────────────────────────────────────────

    function _checkProfile() {
        return _safeApi('/api/onboarding/state').then(function (r) {
            var items = (r && r.data && r.data.state) ? r.data.state : {};
            var keys = ['photo', 'headline', 'about', 'experience', 'skills', 'location', 'connects', 'posts'];
            var done = keys.filter(function (k) { return items[k + '_done']; }).length;
            return {
                ok: done >= 4,
                message: done + '/8 itens de perfil completados' + (done >= 4 ? '' : ' (min. 4)'),
            };
        }).catch(function () {
            return { ok: false, message: 'Verificacao de perfil falhou' };
        });
    }

    function _checkChannels() {
        return _safeApi('/api/channels/linkedin/test').then(function (r) {
            return { ok: !!(r && r.ok), message: r && r.ok ? 'LinkedIn LI_AT configurado' : 'LinkedIn nao configurado' };
        }).catch(function (err) {
            var is501 = err && (err.status === 501 || (err.message && err.message.indexOf('501') >= 0));
            return { ok: false, message: is501 ? 'LI_AT nao configurado (passo 3)' : 'Canal LinkedIn indisponivel' };
        });
    }

    function _checkICP() {
        return _safeApi('/api/icp/profile').then(function (r) {
            var icp = (r && r.data) ? r.data : {};
            var hasTarget = (icp.industries && icp.industries.length) ||
                            (icp.job_titles && icp.job_titles.length);
            var hasGeo = (icp.countries && icp.countries.length) ||
                         (icp.states && icp.states.length) ||
                         (icp.cities && icp.cities.length);
            if (!hasTarget || !hasGeo) {
                return { ok: false, message: 'ICP incompleto (industrias ou cargos + geo necessarios)' };
            }
            var target = _escHtml(
                (icp.job_titles || []).slice(0, 2).join(', ') ||
                (icp.industries || []).slice(0, 1).join(', ')
            );
            var geo = _escHtml((icp.states || icp.countries || []).slice(0, 2).join(', '));
            return { ok: true, message: target + ' em ' + geo };
        }).catch(function () {
            return { ok: false, message: 'Verificacao de ICP falhou' };
        });
    }

    function _checkConnections() {
        return _safeApi('/api/linkedin/cobaia/profile-stats').then(function (r) {
            var count = (r && r.connections_count != null) ? r.connections_count : 0;
            return {
                ok: count >= 50,
                message: count + ' conexoes' + (count >= 50 ? ' (OK)' : ' (min. 50 ideal)'),
            };
        }).catch(function () {
            return { ok: false, message: 'Stats indisponiveis (aceitar e continuar)' };
        });
    }

    function _checkHermesHealth() {
        return _safeApi('/api/hermes/status').then(function () {
            return { ok: true, message: 'Backend + WS conectados' };
        }).catch(function () {
            return { ok: false, message: 'Backend offline ou inacessivel' };
        });
    }

    function _gatherPreflightStatus() {
        return Promise.all([
            _checkProfile(),
            _checkChannels(),
            _checkICP(),
            _checkConnections(),
            _checkHermesHealth(),
        ]).then(function (results) {
            return {
                profile:     results[0],
                channels:    results[1],
                icp:         results[2],
                connections: results[3],
                hermes:      results[4],
            };
        }).catch(function () {
            return {
                profile:     { ok: false, message: 'Erro' },
                channels:    { ok: false, message: 'Erro' },
                icp:         { ok: false, message: 'Erro' },
                connections: { ok: false, message: 'Erro' },
                hermes:      { ok: false, message: 'Erro' },
            };
        });
    }

    // ── Render helpers ───────────────────────────────────────────────────────

    function _icon(ok, warn) {
        if (ok) return '<svg class="pf-icon pf-ok" viewBox="0 0 20 20" aria-hidden="true"><path d="M16.7 5.3a1 1 0 0 1 0 1.4l-8 8a1 1 0 0 1-1.4 0l-4-4a1 1 0 1 1 1.4-1.4L8 12.6l7.3-7.3a1 1 0 0 1 1.4 0z"/></svg>';
        if (warn) return '<svg class="pf-icon pf-warn" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2L2 17h16L10 2zm0 3l6 11H4L10 5zm-1 4v3h2V9H9zm0 4v2h2v-2H9z"/></svg>';
        return '<svg class="pf-icon pf-fail" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2a8 8 0 1 0 0 16A8 8 0 0 0 10 2zm1 11H9v-2h2v2zm0-4H9V5h2v4z"/></svg>';
    }

    function _renderItem(pf, key, label, warn) {
        var check = pf[key] || { ok: false, message: '...' };
        var cls = check.ok ? 'ok' : (warn && !check.ok ? 'warn' : 'fail');
        return '<li class="pf-item pf-' + cls + '" role="listitem">' +
            _icon(check.ok, warn && !check.ok) +
            '<div class="pf-detail">' +
            '<h4 class="pf-label">' + label + '</h4>' +
            '<p class="pf-msg">' + (check.message || '') + '</p>' +
            (warn && !check.ok ? '<small class="pf-warn-note">Pode continuar — sera mais conservador.</small>' : '') +
            '</div>' +
            '</li>';
    }

    function _renderPreflightItems(pf) {
        return _renderItem(pf, 'profile',     'LinkedIn Profile completo', false) +
               _renderItem(pf, 'channels',    'Canal LinkedIn configurado', false) +
               _renderItem(pf, 'icp',         'ICP definido',               false) +
               _renderItem(pf, 'connections', 'Conexoes 50+ seed',          true) +
               _renderItem(pf, 'hermes',      'Hermes backend healthy',     false);
    }

    function _renderLoadingItems() {
        var labels = ['LinkedIn Profile completo', 'Canal LinkedIn configurado',
                      'ICP definido', 'Conexoes 50+ seed', 'Hermes backend healthy'];
        return labels.map(function (l) {
            return '<li class="pf-item pf-loading" role="listitem">' +
                '<span class="pf-spinner" aria-hidden="true"></span>' +
                '<div class="pf-detail"><h4 class="pf-label">' + l + '</h4>' +
                '<p class="pf-msg">Verificando...</p></div>' +
                '</li>';
        }).join('');
    }

    function _renderLaunchCta(allGreen) {
        if (allGreen) {
            return '<div class="wiz-launch-ready">' +
                '<p class="wiz-launch-ok">Todos os requisitos OK — pronto pra decolar!</p>' +
                '<p class="wiz-launch-sub">Day 0 lurking comeca agora. Acompanhe em ' +
                '<a href="#cobaia" class="wiz-launch-link">dashboard &rsaquo; Cobaia</a>.</p>' +
                '<button class="btn-primary btn-launch" type="button" id="wiz-warmup-btn"' +
                ' aria-label="Iniciar warmup cobaia automaticamente">' +
                'Iniciar Warmup' +
                '</button>' +
                '</div>';
        }
        return '<div class="wiz-launch-blocked">' +
            '<p class="wiz-launch-warn">Resolva os itens vermelhos antes de iniciar.</p>' +
            '<p class="wiz-launch-sub">Voce pode sair e voltar quando estiver pronto.' +
            ' O wizard salva o progresso automaticamente.</p>' +
            '</div>';
    }

    function _updatePreflightDOM(pf) {
        var list = document.getElementById('wiz-preflight-list');
        if (list) list.innerHTML = _renderPreflightItems(pf);
        var allGreen = pf.profile.ok && pf.channels.ok && pf.icp.ok && pf.hermes.ok;
        var cta = document.getElementById('wiz-launch-cta');
        if (cta) {
            cta.innerHTML = _renderLaunchCta(allGreen);
            // Wire warmup button via addEventListener (no inline onclick)
            var warmupBtn = cta.querySelector('#wiz-warmup-btn');
            if (warmupBtn) {
                warmupBtn.addEventListener('click', function () { _startWarmup(); });
            }
        }
    }

    // ── Warmup action ────────────────────────────────────────────────────────

    function _startWarmup() {
        var btn = document.getElementById('wiz-warmup-btn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Iniciando...';
        }
        _safeApi('/api/linkedin/cobaia/start-warmup', { method: 'POST' })
            .then(function () {
                if (window.hermesToast) window.hermesToast.success('Warmup iniciado! Day 0 lurking ativo.');
                if (window.HermesOnboardingWizard) window.HermesOnboardingWizard.complete();
                if (typeof navigate === 'function') navigate('cobaia');
            })
            .catch(function (e) {
                if (btn) { btn.disabled = false; btn.textContent = 'Iniciar Warmup'; }
                var msg = (e && e.message) ? e.message : 'Erro desconhecido';
                if (window.hermesToast) window.hermesToast.error('Falha ao iniciar warmup: ' + msg);
            });
    }

    window._HermesStartWarmup = _startWarmup;

    // ── Step object ──────────────────────────────────────────────────────────

    var launchStep = {
        id: 'launch',
        title: 'Pre-Flight + Start',

        render: function (container, state, nav) {
            container.innerHTML =
                '<h2 class="wiz-h1">Pre-Flight Cobaia Activation</h2>' +
                '<p class="wiz-lead">Hermes valida todos os requisitos antes de iniciar ' +
                'warmup automatizado. Conexoes podem estar abaixo de 50 — tudo bem, ' +
                'sera mais conservador nos primeiros dias.</p>' +

                '<ul class="wiz-preflight" id="wiz-preflight-list"' +
                ' role="list" aria-label="Status dos pre-requisitos" aria-live="polite">' +
                _renderLoadingItems() +
                '</ul>' +

                '<div id="wiz-launch-cta" aria-live="polite"></div>' +

                '<div class="wiz-actions">' +
                '<button class="btn-ghost" id="wiz-launch-prev" type="button"' +
                ' aria-label="Voltar para ICP Filters">&larr; Voltar</button>' +
                '<button class="btn-secondary" id="wiz-launch-finish" type="button"' +
                ' aria-label="Concluir onboarding sem iniciar warmup">' +
                'Concluir sem iniciar' +
                '</button>' +
                '</div>';

            container.querySelector('#wiz-launch-prev').addEventListener('click', function () { nav.prev(); });
            container.querySelector('#wiz-launch-finish').addEventListener('click', function () {
                if (window.HermesOnboardingWizard) window.HermesOnboardingWizard.complete();
            });

            // Kick off async preflight — updates DOM in-place on completion
            _gatherPreflightStatus().then(function (pf) {
                state.preflight = pf;
                _updatePreflightDOM(pf);
            });
        },

        validate: function () { return true; },
    };

    if (window.HermesOnboardingWizard) {
        window.HermesOnboardingWizard.register(launchStep);
    }
    window._OnboardingStepLaunch = launchStep;
})();
