/* UX-RM-F3-A — Onboarding Step 2: LinkedIn Profile Setup Checklist
 * Requires at least 4 of 8 items checked to proceed.
 * State keys: photo_done, headline_done, about_done, experience_done,
 *             skills_done, location_done, connects_done, posts_done
 */
(function () {
    'use strict';

    var ITEMS = [
        { id: 'photo',      label: 'Foto de perfil (headshot profissional)' },
        { id: 'headline',   label: 'Headline 100 chars (nicho B2B Cuiaba)' },
        { id: 'about',      label: 'Sobre: 1500-2000 caracteres' },
        { id: 'experience', label: 'Experiencia: 1-2 entradas' },
        { id: 'skills',     label: 'Skills: 5-10 endorsements' },
        { id: 'location',   label: 'Localizacao: Cuiaba, MT, Brasil' },
        { id: 'connects',   label: 'Conexoes 50+ seed (5/dia x 10 dias)' },
        { id: 'posts',      label: 'Posts organicos 2-4 (Dia 7-14)' },
    ];
    var MIN_DONE = 4;

    var profileStep = {
        id: 'profile',
        title: 'Perfil LinkedIn',

        render: function (container, state, nav) {
            var doneCount = ITEMS.filter(function (i) { return state[i.id + '_done']; }).length;

            container.innerHTML =
                '<h2 class="wiz-h1">Configuracao de Perfil (~10 dias manual)</h2>' +
                '<p class="wiz-lead">Marque cada item conforme completar no LinkedIn. Minimo ' + MIN_DONE + ' itens para continuar.</p>' +

                '<ul class="wiz-checklist" role="list" aria-label="Checklist de perfil LinkedIn">' +
                ITEMS.map(function (item) {
                    var key = item.id + '_done';
                    var checked = state[key] ? 'checked' : '';
                    return (
                        '<li role="listitem">' +
                            '<label>' +
                                '<input type="checkbox" data-key="' + key + '" ' + checked + ' aria-label="' + item.label + '">' +
                                '<span class="check-icon" aria-hidden="true"></span>' +
                                '<span class="check-label">' + item.label + '</span>' +
                            '</label>' +
                        '</li>'
                    );
                }).join('') +
                '</ul>' +

                '<details class="wiz-help">' +
                    '<summary>Ver playbook completo de 14 dias</summary>' +
                    '<div class="wiz-playbook">' +
                        '<p><strong>Dia 0-2:</strong> Foto + capa + headline + sobre + experiencia + skills + localizacao.</p>' +
                        '<p><strong>Dia 3-12:</strong> 5 convites/dia das 9h-19h BRT. 50% com mensagem personalizada, 50% sem.</p>' +
                        '<p><strong>Dia 7-14:</strong> 2-4 posts organicos (intro/insight/caso). 5-10 likes/dia + 2-3 comentarios com valor.</p>' +
                        '<p><strong>Dia 14:</strong> Extrair cookie LI_AT + iniciar warmup automatico.</p>' +
                    '</div>' +
                '</details>' +

                '<div class="wiz-actions">' +
                    '<button class="btn-ghost" id="wiz-profile-prev" aria-label="Voltar para Welcome">&larr; Voltar</button>' +
                    '<button class="btn-primary" id="wiz-profile-next"' +
                    ' aria-disabled="' + (doneCount < MIN_DONE ? 'true' : 'false') + '"' +
                    ' aria-label="Avancar para Channel Config">Proximo &rarr;</button>' +
                '</div>';

            var nextBtn = container.querySelector('#wiz-profile-next');

            function _updateNextBtn() {
                var count = ITEMS.filter(function (i) { return state[i.id + '_done']; }).length;
                var blocked = count < MIN_DONE;
                nextBtn.setAttribute('aria-disabled', blocked ? 'true' : 'false');
                nextBtn.style.opacity = blocked ? '0.4' : '';
                nextBtn.style.cursor = blocked ? 'not-allowed' : '';
                nextBtn.title = blocked ? 'Marque pelo menos ' + MIN_DONE + ' itens para continuar' : '';
            }

            container.querySelectorAll('input[type=checkbox]').forEach(function (el) {
                el.addEventListener('change', function (e) {
                    state[e.target.dataset.key] = e.target.checked;
                    _updateNextBtn();
                    if (window.HermesOnboardingWizard) {
                        window.HermesOnboardingWizard.saveState();
                    }
                });
            });

            container.querySelector('#wiz-profile-prev').addEventListener('click', function () { nav.prev(); });
            container.querySelector('#wiz-profile-next').addEventListener('click', function () {
                if (nextBtn.getAttribute('aria-disabled') === 'true') return;
                nav.next();
            });
        },

        validate: function (state) {
            var count = ITEMS.filter(function (i) { return state[i.id + '_done']; }).length;
            return count >= MIN_DONE;
        },
    };

    if (window.HermesOnboardingWizard) {
        window.HermesOnboardingWizard.register(profileStep);
    }
    window._OnboardingStepProfile = profileStep;
    window._OnboardingProfileMinDone = MIN_DONE;
    window._OnboardingProfileItems = ITEMS;
})();
