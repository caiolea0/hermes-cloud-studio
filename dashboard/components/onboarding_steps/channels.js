/* UX-RM-F3-A — Onboarding Step 3: Channel Config
 * Inline config widgets for LinkedIn (LI_AT), Email (SMTP), WhatsApp, Telegram.
 * POST /api/channels/configure {channel, config}
 * GET  /api/channels/{channel}/test → 200 or 501
 * LI_AT field is password-type + masked. Never logs raw secrets.
 */
(function () {
    'use strict';

    var CHANNELS = [
        {
            id: 'linkedin',
            label: 'LinkedIn',
            icon: 'LI',
            fields: [
                { key: 'li_at', label: 'Cookie LI_AT', type: 'password', hint: 'Extraia do Chrome: DevTools → Application → Cookies → li_at' },
            ],
        },
        {
            id: 'email',
            label: 'Email (SMTP)',
            icon: '@',
            fields: [
                { key: 'smtp_host',  label: 'SMTP Host',  type: 'text',     hint: 'ex: smtp.gmail.com' },
                { key: 'smtp_port',  label: 'Porta',      type: 'text',     hint: '587 (TLS) ou 465 (SSL)' },
                { key: 'smtp_user',  label: 'Email',      type: 'text',     hint: 'seu@email.com' },
                { key: 'smtp_pass',  label: 'App Password', type: 'password', hint: 'Senha de app Gmail ou equivalente' },
            ],
        },
        {
            id: 'whatsapp',
            label: 'WhatsApp (Z-API)',
            icon: 'WA',
            fields: [
                { key: 'zapi_instance', label: 'Instance ID', type: 'text',     hint: 'Dashboard Z-API → Instance ID' },
                { key: 'zapi_token',    label: 'Token',       type: 'password', hint: 'Dashboard Z-API → Security Token' },
            ],
        },
        {
            id: 'telegram',
            label: 'Telegram',
            icon: 'TG',
            fields: [
                { key: 'bot_token', label: 'Bot Token',  type: 'password', hint: '@BotFather → /newbot → token' },
                { key: 'chat_id',   label: 'Chat ID',    type: 'text',     hint: 'Use @userinfobot para obter seu chat_id' },
            ],
        },
    ];

    function _escHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    var channelsStep = {
        id: 'channels',
        title: 'Configurar Canais',

        render: function (container, state, nav) {
            var html =
                '<h2 class="wiz-h1">Canais de Outreach</h2>' +
                '<p class="wiz-lead">Configure ao menos LinkedIn para iniciar o warmup. Os outros canais podem ser configurados depois.</p>' +
                '<div id="wiz-channels-list">' +
                CHANNELS.map(function (ch) {
                    var configKey = 'ch_' + ch.id + '_ok';
                    var isOk = state[configKey];
                    return (
                        '<div class="wiz-channel-section" data-ch="' + ch.id + '">' +
                            '<div class="wiz-channel-header" role="button" tabindex="0"' +
                            ' aria-expanded="false" aria-controls="wiz-ch-body-' + ch.id + '">' +
                                '<div class="wiz-channel-title">' +
                                    '<span aria-hidden="true" style="font-size: var(--text-xs);font-weight:700;color:var(--text-3)">' + ch.icon + '</span>' +
                                    ' ' + _escHtml(ch.label) +
                                '</div>' +
                                '<span class="wiz-channel-badge' + (isOk ? ' wiz-badge-ok' : '') + '">' +
                                    (isOk ? 'Configurado' : 'Opcional') +
                                '</span>' +
                            '</div>' +
                            '<div class="wiz-channel-body" id="wiz-ch-body-' + ch.id + '" aria-hidden="true">' +
                                ch.fields.map(function (f) {
                                    return (
                                        '<div class="wiz-field">' +
                                            '<label for="wiz-ch-' + ch.id + '-' + f.key + '">' + _escHtml(f.label) + '</label>' +
                                            '<input id="wiz-ch-' + ch.id + '-' + f.key + '"' +
                                            ' type="' + f.type + '"' +
                                            ' data-ch="' + ch.id + '" data-key="' + f.key + '"' +
                                            ' autocomplete="' + (f.type === 'password' ? 'current-password' : 'off') + '"' +
                                            ' placeholder="">' +
                                            '<span class="wiz-field-hint">' + _escHtml(f.hint) + '</span>' +
                                        '</div>'
                                    );
                                }).join('') +
                                '<div class="wiz-save-row">' +
                                    '<button class="wiz-test-btn" data-ch="' + ch.id + '">' +
                                        'Testar conexao' +
                                    '</button>' +
                                    '<button class="btn-primary" style="font-size: var(--text-sm);padding:7px 14px" data-save-ch="' + ch.id + '">' +
                                        'Salvar' +
                                    '</button>' +
                                    '<span class="wiz-ch-status" id="wiz-ch-status-' + ch.id + '" aria-live="polite" style="font-size: var(--text-xxs);color:var(--text-3)"></span>' +
                                '</div>' +
                            '</div>' +
                        '</div>'
                    );
                }).join('') +
                '</div>' +

                '<div class="wiz-actions">' +
                    '<button class="btn-ghost" id="wiz-ch-prev" aria-label="Voltar para Profile">&larr; Voltar</button>' +
                    '<button class="btn-primary" id="wiz-ch-finish" aria-label="Concluir configuracao">Concluir</button>' +
                '</div>';

            container.innerHTML = html;

            // Toggle channel sections
            container.querySelectorAll('.wiz-channel-header').forEach(function (hdr) {
                function _toggle() {
                    var body = hdr.nextElementSibling;
                    var isOpen = body.classList.contains('wiz-channel-open');
                    body.classList.toggle('wiz-channel-open', !isOpen);
                    body.setAttribute('aria-hidden', isOpen ? 'true' : 'false');
                    hdr.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
                }
                hdr.addEventListener('click', _toggle);
                hdr.addEventListener('keydown', function (e) {
                    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); _toggle(); }
                });
            });

            // Save channel
            container.querySelectorAll('[data-save-ch]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var chId = btn.dataset.saveCh;
                    var config = {};
                    container.querySelectorAll('input[data-ch="' + chId + '"]').forEach(function (inp) {
                        if (inp.value.trim()) config[inp.dataset.key] = inp.value.trim();
                    });
                    var statusEl = document.getElementById('wiz-ch-status-' + chId);
                    statusEl.textContent = 'Salvando...';
                    statusEl.style.color = 'var(--text-3)';
                    btn.disabled = true;

                    var doSave = typeof api === 'function' ? api : function (path, opts) {
                        return fetch(path, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts))
                            .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
                    };

                    doSave('/api/channels/configure', {
                        method: 'POST',
                        body: JSON.stringify({ channel: chId, config: config }),
                        headers: { 'Content-Type': 'application/json' },
                    }).then(function () {
                        state['ch_' + chId + '_ok'] = true;
                        statusEl.textContent = 'Salvo!';
                        statusEl.style.color = 'var(--green)';
                        // Update badge
                        var badge = container.querySelector('[data-ch="' + chId + '"] .wiz-channel-badge');
                        if (badge) { badge.textContent = 'Configurado'; badge.classList.add('wiz-badge-ok'); }
                        if (window.HermesOnboardingWizard) window.HermesOnboardingWizard.saveState();
                        btn.disabled = false;
                    }).catch(function (err) {
                        statusEl.textContent = 'Erro: ' + (err.message || 'falhou');
                        statusEl.style.color = 'var(--red)';
                        btn.disabled = false;
                    });
                });
            });

            // Test channel
            container.querySelectorAll('.wiz-test-btn').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var chId = btn.dataset.ch;
                    var statusEl = document.getElementById('wiz-ch-status-' + chId);
                    statusEl.textContent = 'Testando...';
                    statusEl.style.color = 'var(--text-3)';

                    var doFetch = typeof api === 'function' ? api : function (path) { return fetch(path); };
                    doFetch('/api/channels/' + chId + '/test').then(function () {
                        statusEl.textContent = 'Conexao OK';
                        statusEl.style.color = 'var(--green)';
                    }).catch(function (err) {
                        var msg = err && err.status === 501 ? 'Nao configurado ainda (501)' : 'Falhou: ' + (err.message || err);
                        statusEl.textContent = msg;
                        statusEl.style.color = 'var(--text-3)';
                    });
                });
            });

            container.querySelector('#wiz-ch-prev').addEventListener('click', function () { nav.prev(); });
            container.querySelector('#wiz-ch-finish').addEventListener('click', function () { nav.next(); });
        },

        validate: function () { return true; },
    };

    if (window.HermesOnboardingWizard) {
        window.HermesOnboardingWizard.register(channelsStep);
    }
    window._OnboardingStepChannels = channelsStep;
})();
