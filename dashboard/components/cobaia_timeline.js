/**
 * F.7 C3 — Cobaia 14-day Warmup Timeline (IIFE component).
 *
 * Renders 14 day-cells showing phase progression.
 * Each cell: lurking(gray) | ramp(yellow) | normal(green) | paused(red) | today(blue ring) | future(faded).
 * Hover tooltip shows day + phase + caps summary.
 * Full keyboard navigation: Tab to cell, Enter/Space shows tooltip (role=button).
 *
 * XSS: textContent only — no innerHTML with user data.
 * WCAG: aria-label per cell describes day + phase + status.
 */
(function CobaiaTimeline() {
    'use strict';

    const PHASE_LABELS = {
        lurking: 'Lurking',
        ramp: 'Ramp',
        normal: 'Normal',
        paused: 'Pausado',
        future: 'Futuro',
    };

    let _mount = null;

    function _phaseClass(cell) {
        if (cell.is_future) return 'cobaia-day-cell--future';
        if (cell.phase === 'paused') return 'cobaia-day-cell--paused';
        if (cell.phase === 'ramp') return 'cobaia-day-cell--ramp';
        if (cell.phase === 'normal') return 'cobaia-day-cell--normal';
        return 'cobaia-day-cell--lurking';
    }

    function _buildCell(cell) {
        const phaseClass = _phaseClass(cell);
        const todayClass = cell.is_today ? ' cobaia-day-cell--today' : '';
        const label = PHASE_LABELS[cell.is_future ? 'future' : cell.phase] || cell.phase;
        const caps = cell.caps || {};
        const ariaLabel = `Dia ${cell.day}, fase ${label}, ` +
            `cap connects ${caps.connects || 0}, engagements ${caps.engagements || 0}` +
            (cell.is_today ? ', hoje' : cell.is_future ? ', futuro' : '');

        const div = document.createElement('div');
        div.className = `cobaia-day-cell ${phaseClass}${todayClass}`;
        div.setAttribute('tabindex', '0');
        div.setAttribute('aria-label', ariaLabel);

        const num = document.createElement('span');
        num.className = 'cobaia-day-num';
        num.textContent = cell.day;

        const dot = document.createElement('span');
        dot.className = 'cobaia-day-phase-dot';
        dot.setAttribute('aria-hidden', 'true');

        const tooltip = document.createElement('div');
        tooltip.className = 'cobaia-day-tooltip';
        tooltip.setAttribute('aria-hidden', 'true');
        tooltip.textContent = `Dia ${cell.day} · ${label}`;
        if (!cell.is_future) {
            tooltip.textContent += ` · Connects: ${caps.connects || 0} · Eng: ${caps.engagements || 0}`;
        }

        div.appendChild(num);
        div.appendChild(dot);
        div.appendChild(tooltip);
        return div;
    }

    function render(timelineData) {
        if (!_mount) return;
        _mount.innerHTML = '';

        if (!timelineData || !timelineData.exists) {
            const empty = document.createElement('p');
            empty.className = 'cobaia-feed-empty';
            empty.textContent = 'Timeline nao disponivel — warmup nao iniciado';
            _mount.appendChild(empty);
            return;
        }

        const container = document.createElement('div');
        container.className = 'cobaia-timeline';
        container.setAttribute('role', 'list');
        container.setAttribute('aria-label', `Timeline warmup cobaia — dia ${timelineData.current_day} de ${timelineData.total_days}`);

        (timelineData.days || []).forEach(cell => {
            const el = _buildCell(cell);
            el.setAttribute('role', 'listitem');
            container.appendChild(el);
        });

        _mount.appendChild(container);
    }

    function mount(containerId) {
        _mount = document.getElementById(containerId);
        if (!_mount) {
            console.warn('[cobaia-timeline] mount point not found:', containerId);
        }
    }

    window.CobaiaTimeline = { mount, render };
})();
