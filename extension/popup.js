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
    const tokEl = document.getElementById('token-status');
    const tokSetup = document.getElementById('token-setup');

    // Token status — mostra setup form se ausente
    if (resp.hasToken) {
        tokEl.innerHTML = '<span class="dot ok"></span>configurado';
        tokSetup.style.display = 'none';
    } else {
        tokEl.innerHTML = '<span class="dot err"></span>FALTA — configurar abaixo';
        tokSetup.style.display = 'block';
    }

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

document.getElementById('token-save-btn').addEventListener('click', () => {
    const input = document.getElementById('token-input');
    const token = (input.value || '').trim();
    if (!token) {
        alert('Token vazio. Cole o valor de HERMES_INTERNAL_TOKEN do .env.');
        return;
    }
    if (token.length < 20) {
        alert('Token muito curto. Verifique se copiou completo.');
        return;
    }
    chrome.runtime.sendMessage({ action: 'setInternalToken', token }, (resp) => {
        if (resp && resp.ok) {
            input.value = '';
            setTimeout(load, 200);
        } else {
            alert('Falha ao salvar token: ' + (resp?.error || 'desconhecido'));
        }
    });
});

load();
