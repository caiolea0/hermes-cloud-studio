/* window.hermesToast — API de notificações em PT-BR.
   Reutiliza namespace do 1.x (F.2.4). API: objeto com métodos, NÃO função direta.
   Uso: hermesToast.success('Salvo') / hermesToast.error('Falha') /
        hermesToast.info('Info') / hermesToast.warn('Atenção') */
(function () {
  'use strict';

  let _el = null;
  let _timer = null;

  function _ensure() {
    if (_el) return _el;
    _el = document.createElement('div');
    _el.className = 'toast';
    _el.setAttribute('role', 'status');
    _el.setAttribute('aria-live', 'polite');
    _el.setAttribute('aria-atomic', 'true');
    document.body.appendChild(_el);
    return _el;
  }

  function _show(msg, type) {
    const el = _ensure();

    const icons = {
      success: 'ti-circle-check',
      error: 'ti-circle-x',
      warn: 'ti-alert-triangle',
      info: 'ti-info-circle',
    };
    const iconClass = icons[type] || icons.info;

    // Sanitiza via DOMPurify se disponível, fallback escapeHtml
    const safeMsg = window.DOMPurify
      ? DOMPurify.sanitize(msg, { ALLOWED_TAGS: [] })
      : msg.replace(/[<>&"']/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#39;' }[c]));

    el.innerHTML = `<i class="ti ${iconClass}" aria-hidden="true"></i><span>${safeMsg}</span>`;

    // Cor por tipo via inline (tokens CSS)
    const colors = {
      success: 'var(--good)',
      error: 'var(--danger)',
      warn: 'var(--warm)',
      info: 'var(--accent-2)',
    };
    el.querySelector('i').style.color = colors[type] || colors.info;

    clearTimeout(_timer);
    el.classList.add('show');
    _timer = setTimeout(() => el.classList.remove('show'), 3800);
  }

  window.hermesToast = {
    success: (msg) => _show(msg, 'success'),
    error: (msg) => _show(msg, 'error'),
    warn: (msg) => _show(msg, 'warn'),
    info: (msg) => _show(msg, 'info'),
  };
})();
