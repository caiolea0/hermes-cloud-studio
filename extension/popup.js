function fmtTime(ts) {
    if (!ts) return '—';
    const d = new Date(ts);
    return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function renderStatus(resp) {
    const hasEl = document.getElementById('has-cookie');
    const lastEl = document.getElementById('last-sync');
    const stEl = document.getElementById('status');
    const trigEl = document.getElementById('trigger');

    hasEl.innerHTML = resp.hasCookie
        ? '<span class="dot ok"></span>sim'
        : '<span class="dot err"></span>não';

    const s = resp.status;
    if (!s) {
        lastEl.textContent = 'nunca';
        stEl.innerHTML = '<span class="dot warn"></span>pendente';
        trigEl.textContent = '—';
        return;
    }
    lastEl.textContent = fmtTime(s.ts);
    trigEl.textContent = s.trigger || '—';

    // Account type
    const atEl = document.getElementById('account-type');
    if (atEl) {
        const at = resp.accountType;
        if (!at) {
            atEl.innerHTML = '<span class="dot warn"></span>aguardando';
        } else if (at.ok) {
            atEl.innerHTML = '<span class="dot ok"></span>' + (at.type || '—').toUpperCase();
        } else {
            atEl.innerHTML = '<span class="dot err"></span>' + (at.type || 'erro');
        }
    }
    if (s.ok && s.rotated) {
        stEl.innerHTML = '<span class="dot ok"></span>rotacionado';
    } else if (s.ok && s.unchanged) {
        stEl.innerHTML = '<span class="dot ok"></span>sem mudança';
    } else if (s.ok) {
        stEl.innerHTML = '<span class="dot ok"></span>ok';
    } else {
        stEl.innerHTML = '<span class="dot err"></span>' + (s.reason || 'erro');
    }
}

function load() {
    chrome.runtime.sendMessage({ action: 'status' }, renderStatus);
}

document.getElementById('sync-btn').addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'sync' }, () => setTimeout(load, 500));
});

load();
