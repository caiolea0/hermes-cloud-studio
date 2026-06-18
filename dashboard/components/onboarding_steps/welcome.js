/* UX-RM-F3-A — Onboarding Step 1: Welcome
 * Registers with HermesOnboardingWizard when script loads.
 * Dependency: onboarding_wizard.js must load first.
 */
(function () {
    'use strict';

    var welcomeStep = {
        id: 'welcome',
        title: 'Bem-vindo ao Hermes',

        render: function (container, state, nav) {
            container.innerHTML =
                '<div class="wiz-welcome">' +
                    '<h2 class="wiz-h1">Bem-vindo ao Hermes Cloud Studio</h2>' +
                    '<p class="wiz-lead">Automacao B2B para prospecção em Cuiabá-MT — do first-contact ao follow-up.</p>' +

                    '<div class="wiz-value-grid" role="list">' +
                        '<div class="wiz-value" role="listitem">' +
                            '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">' +
                                '<path d="M10 2l2.4 5H17l-3.9 2.8 1.4 5.2L10 12l-4.5 3L7 9.8 3 7h4.6z"/>' +
                            '</svg>' +
                            '<h3>AI Brain</h3>' +
                            '<p>Cmd+K palette + Brain streaming. Pressione / para perguntar.</p>' +
                        '</div>' +
                        '<div class="wiz-value" role="listitem">' +
                            '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">' +
                                '<path d="M10 2l1.9 3.8L16 6.9l-3 2.9.7 4.1L10 12l-3.7 1.9.7-4.1L4 7l4.1-.3z"/>' +
                                '<circle cx="10" cy="10" r="8"/><path d="M7 10l2 2 4-4"/>' +
                            '</svg>' +
                            '<h3>Cobaia Segura</h3>' +
                            '<p>Warmup 14 dias + auto-quarentena + panic button.</p>' +
                        '</div>' +
                        '<div class="wiz-value" role="listitem">' +
                            '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">' +
                                '<rect x="3" y="10" width="3" height="7" rx="0.5"/>' +
                                '<rect x="8.5" y="6" width="3" height="11" rx="0.5"/>' +
                                '<rect x="14" y="3" width="3" height="14" rx="0.5"/>' +
                            '</svg>' +
                            '<h3>Observabilidade</h3>' +
                            '<p>Cada acao logada + replayavel + alertas Telegram.</p>' +
                        '</div>' +
                    '</div>' +

                    '<p class="wiz-disclosure">Vamos levar ~5 minutos para configurar sua conta. Voce pode pular e retomar depois.</p>' +

                    '<div class="wiz-actions">' +
                        '<span class="wiz-min-note">~5 min</span>' +
                        '<button class="btn-primary" id="wiz-welcome-next" aria-label="Comecar configuracao">Comecar &rarr;</button>' +
                    '</div>' +
                '</div>';

            container.querySelector('#wiz-welcome-next').addEventListener('click', function () {
                nav.next();
            });
        },

        validate: function () { return true; },
    };

    // Safe registration (wizard may not be loaded yet in test environments)
    if (window.HermesOnboardingWizard) {
        window.HermesOnboardingWizard.register(welcomeStep);
    }
    // Export for direct testing
    window._OnboardingStepWelcome = welcomeStep;
})();
