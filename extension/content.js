// Hermes — content script roda em qualquer página linkedin.com
// Detecta account type via DOM real (sem Patchright, sem quota da VM).
// Envia para background.js quando detectar (com cooldown 1h pra evitar spam).
(function() {
    'use strict';

    const LOG = (...args) => console.log('[Hermes ext]', ...args);
    LOG('content script loaded on', location.href);

    function detectAccountType() {
        const evidence = [];
        let type = 'free';

        const allText = (document.body && document.body.innerText || '').toLowerCase();

        // 1. URL — atalho rápido
        if (location.pathname.startsWith('/sales/') ||
            location.hostname.startsWith('sales.')) {
            evidence.push('sales_url');
            type = 'sales_navigator';
        }

        // 2. Link "Sales Navigator" no nav
        const salesLinks = document.querySelectorAll(
            "a[href*='/sales/'], a[href*='sales.linkedin.com'], " +
            "[data-control-name*='sales_navigator'], " +
            "[aria-label*='Sales Navigator']"
        );
        if (salesLinks.length > 0) {
            evidence.push('sales_link');
            type = 'sales_navigator';
        }

        // 3. Premium markers — várias estratégias
        const premiumSelectors = [
            "li-icon[type='premium-app-icon']",
            "li-icon[type='premium-icon']",
            "[data-control-name='premium_branding']",
            "[data-test-app-aware-link*='premium']",
            ".global-nav__premium-cta-link",
            "a[href*='/premium/my-premium']",
            "[aria-label*='Premium account']",
            ".pv-top-card__premium-badge",
            ".premium-icon",
            "img[alt*='Premium']",
            // Sidebar visible to logged-in user
            "a[href*='/premium/products']",
        ];
        const premiumHits = [];
        premiumSelectors.forEach(sel => {
            try {
                const n = document.querySelectorAll(sel).length;
                if (n > 0) premiumHits.push(`${sel}(${n})`);
            } catch (e) { /* invalid selector */ }
        });
        if (premiumHits.length > 0) {
            evidence.push('premium_selectors:' + premiumHits.slice(0, 3).join(','));
            if (type === 'free') type = 'premium';
        }

        // 4. Texto "Premium" + "Seus recursos" (pt-BR) OU "Your Premium" (en) na sidebar/aside
        const sideArea = document.querySelector(
            "aside.scaffold-layout__aside, " +
            ".pv-text-details__left-panel, " +
            ".scaffold-layout__sidebar, " +
            "section.pv-top-card, " +
            ".artdeco-card"
        );
        if (sideArea) {
            const txt = (sideArea.innerText || '').toLowerCase();
            // Strong positives
            if (txt.includes('seus recursos premium') ||
                txt.includes('your premium') ||
                txt.includes('premium account')) {
                evidence.push('sidebar_text_premium_strong');
                if (type === 'free') type = 'premium';
            }
        }

        // 5. Fallback: texto Premium fora de contexto de upsell
        // "Premium" sozinho, mas NÃO "experimentar premium" nem "try premium"
        const hasPremiumBadge = allText.includes('premium') &&
            !allText.match(/experimentar premium|try premium|teste o premium|seja premium|upgrade to premium/);
        // Sidebar/header tem badge "Premium" — visto na screenshot
        const profileBadge = document.querySelector(
            ".pv-text-details__about-this-profile-entrypoint + *, " +
            ".pv-top-card__photo-wrapper + div"
        );
        if (profileBadge && (profileBadge.innerText || '').toLowerCase().includes('premium')) {
            evidence.push('profile_badge_premium');
            if (type === 'free') type = 'premium';
        }

        // 6. /premium/my-premium/ acessível sem redirect = premium
        if (location.pathname.startsWith('/premium/my-premium')) {
            const dashboard = document.querySelector(
                "section[data-test-id='premium-dashboard'], " +
                "h1[class*='premium-dashboard'], " +
                ".pmt-dashboard"
            );
            if (dashboard) {
                evidence.push('my_premium_dashboard_visible');
                if (type === 'free') type = 'premium';
            }
        }

        return { type, evidence };
    }

    const SEND_COOLDOWN_MS = 60 * 60 * 1000;  // 1h

    function maybeSendDetection(trigger) {
        const result = detectAccountType();
        LOG('detected', result, 'trigger=' + trigger);
        chrome.storage.local.get(['hermes_account_type_last', 'hermes_account_type_ts'], (s) => {
            const lastType = s.hermes_account_type_last;
            const lastTs = s.hermes_account_type_ts || 0;
            const ageMs = Date.now() - lastTs;
            // Force send if type changed OR every hour even if same
            const shouldSend = (lastType !== result.type) || (ageMs > SEND_COOLDOWN_MS);
            if (!shouldSend) {
                LOG('skip send — same type & recent (age=' + Math.round(ageMs/60000) + 'min)');
                return;
            }
            LOG('sending to background');
            chrome.runtime.sendMessage({
                action: 'accountTypeDetected',
                payload: { ...result, page_url: location.href }
            }, (resp) => {
                LOG('background ack', resp);
                chrome.storage.local.set({
                    hermes_account_type_last: result.type,
                    hermes_account_type_ts: Date.now(),
                });
            });
        });
    }

    // Roda após 4s do load (LinkedIn lazy-loads)
    setTimeout(() => maybeSendDetection('initial'), 4000);

    // SPA navigation watcher
    let lastUrl = location.href;
    new MutationObserver(() => {
        if (location.href !== lastUrl) {
            lastUrl = location.href;
            LOG('SPA nav to', location.href);
            setTimeout(() => maybeSendDetection('spa_nav'), 3000);
        }
    }).observe(document, { subtree: true, childList: true });
})();
