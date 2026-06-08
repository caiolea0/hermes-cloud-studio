// Hermes LinkedIn Sync — MV3 service worker
// Captures changes to .linkedin.com / li_at cookie and POSTs to local Hermes server.

const HERMES_URL = 'http://localhost:55000/api/internal/li_at_rotate';
const ACCOUNT_TYPE_URL = 'http://localhost:55000/api/internal/account_type_set';
const LAST_KEY = 'hermes_li_at_last';
const STATUS_KEY = 'hermes_status_last';
const ACCOUNT_TYPE_STATUS_KEY = 'hermes_account_type_status';

async function readCurrentLiAt() {
    return new Promise(resolve => {
        chrome.cookies.get({ url: 'https://www.linkedin.com/', name: 'li_at' }, c => {
            resolve(c?.value || null);
        });
    });
}

async function pushToHermes(value) {
    if (!value) return { ok: false, reason: 'no_cookie' };
    try {
        const r = await fetch(HERMES_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ li_at: value }),
        });
        const data = await r.json().catch(() => ({}));
        return { ok: r.ok && data.ok, status: r.status, body: data };
    } catch (e) {
        return { ok: false, error: e.message };
    }
}

async function syncIfChanged(trigger = 'manual') {
    const cur = await readCurrentLiAt();
    if (!cur) {
        await chrome.storage.local.set({ [STATUS_KEY]: { ok: false, reason: 'no_cookie', ts: Date.now(), trigger } });
        return;
    }
    const { [LAST_KEY]: last } = await chrome.storage.local.get(LAST_KEY);
    if (last === cur) {
        await chrome.storage.local.set({ [STATUS_KEY]: { ok: true, unchanged: true, ts: Date.now(), trigger } });
        return;
    }
    const result = await pushToHermes(cur);
    if (result.ok) {
        await chrome.storage.local.set({
            [LAST_KEY]: cur,
            [STATUS_KEY]: { ok: true, rotated: true, ts: Date.now(), trigger },
        });
        console.log('[Hermes] Cookie rotated successfully', { trigger });
    } else {
        await chrome.storage.local.set({
            [STATUS_KEY]: { ok: false, error: result, ts: Date.now(), trigger },
        });
        console.warn('[Hermes] Rotation failed', result);
    }
}

// 1. On install: do initial sync
chrome.runtime.onInstalled.addListener(() => {
    syncIfChanged('install');
    // 2. Set up an alarm to poll every 30 min (safety net for missed events)
    chrome.alarms.create('hermes-sync', { periodInMinutes: 30 });
});

chrome.runtime.onStartup.addListener(() => {
    syncIfChanged('startup');
    chrome.alarms.create('hermes-sync', { periodInMinutes: 30 });
});

// 3. Real-time: listen for cookie changes
chrome.cookies.onChanged.addListener(info => {
    if (info.removed) return;
    const c = info.cookie;
    if (c.name !== 'li_at') return;
    if (!c.domain.endsWith('linkedin.com')) return;
    syncIfChanged('change');
});

// 4. Alarm fires
chrome.alarms.onAlarm.addListener(a => {
    if (a.name === 'hermes-sync') syncIfChanged('alarm');
});

// 5. Account type detection (from content.js running on linkedin.com)
async function pushAccountType(payload) {
    try {
        const r = await fetch(ACCOUNT_TYPE_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                account_type: payload.type,
                evidence: payload.evidence,
                detected_from: 'extension_content_script',
                page_url: payload.page_url,
            }),
        });
        const data = await r.json().catch(() => ({}));
        await chrome.storage.local.set({
            [ACCOUNT_TYPE_STATUS_KEY]: {
                ok: r.ok && data.ok,
                type: payload.type,
                evidence: payload.evidence,
                ts: Date.now(),
            }
        });
        console.log('[Hermes] account_type detected:', payload.type, payload.evidence);
    } catch (e) {
        console.warn('[Hermes] account_type push failed:', e);
        await chrome.storage.local.set({
            [ACCOUNT_TYPE_STATUS_KEY]: { ok: false, error: e.message, ts: Date.now() }
        });
    }
}

// 6. Manual sync from popup + content-script messages
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.action === 'sync') {
        syncIfChanged('popup').then(() => sendResponse({ ok: true }));
        return true;
    }
    if (msg.action === 'status') {
        chrome.storage.local.get([STATUS_KEY, LAST_KEY, ACCOUNT_TYPE_STATUS_KEY]).then(s => {
            sendResponse({
                status: s[STATUS_KEY] || null,
                hasCookie: !!s[LAST_KEY],
                accountType: s[ACCOUNT_TYPE_STATUS_KEY] || null,
            });
        });
        return true;
    }
    if (msg.action === 'accountTypeDetected') {
        pushAccountType(msg.payload).then(() => sendResponse({ ok: true }));
        return true;
    }
});
