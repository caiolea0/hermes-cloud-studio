(function () {
    'use strict';

    const PAGE_IDS = [
        'dashboard', 'control', 'cobaia', 'pipeline-studio',
        'tasks', 'prospects', 'proposals', 'audit', 'linkedin',
        'skills', 'skill-proposals', 'lab', 'memory', 'missions',
        'claude', 'mcp-gateway', 'observability',
    ];

    class HermesAxeRunner {
        constructor() {
            this._lastReport = null;
        }

        async _ensureAxe() {
            if (window.axe) return;
            if (window.loadComponent) {
                await window.loadComponent('axe.min', '');
            } else {
                throw new Error('axe.min.js not loaded and loadComponent unavailable');
            }
        }

        async runFullAudit() {
            await this._ensureAxe();
            const results = await window.axe.run(document.body, {
                runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] },
                resultTypes: ['violations'],
            });
            return results.violations;
        }

        async runOnPage(pageId) {
            if (typeof navigate === 'function') navigate(pageId);
            await new Promise(r => setTimeout(r, 800));
            return this.runFullAudit();
        }

        async runAllPages() {
            const report = {};
            for (const p of PAGE_IDS) {
                try {
                    report[p] = await this.runOnPage(p);
                } catch (e) {
                    report[p] = [{ id: 'runner-error', impact: 'critical', help: e.message, nodes: [] }];
                }
            }
            this._lastReport = report;
            return report;
        }

        formatReport(violations) {
            return violations.map(v => ({
                id: v.id,
                impact: v.impact,
                help: v.helpUrl || v.help,
                affected: v.nodes.length,
                html_snippets: v.nodes.slice(0, 3).map(n => n.html),
            }));
        }

        summarize(report) {
            return Object.entries(report).map(([page, violations]) => ({
                page,
                count: violations.length,
                maxImpact: _maxImpact(violations),
            }));
        }

        renderPanel(containerId) {
            const el = document.getElementById(containerId);
            if (!el) return;
            el.innerHTML = `
                <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
                    <h2 style="margin:0;font-size:15px;font-weight:700;color:var(--text-1)">A11y Audit</h2>
                    <button type="button" class="btn btn-ghost btn-sm" id="axe-run-btn">
                        <svg style="width:13px;height:13px"><use href="#i-refresh"/></svg> Run Audit
                    </button>
                    <button type="button" class="btn btn-ghost btn-sm" id="axe-export-btn" style="display:none">
                        Export CSV
                    </button>
                    <span id="axe-status" style="font-size:11px;color:var(--text-3)"></span>
                </div>
                <div id="axe-summary-table"></div>
                <div id="axe-detail-panel" style="display:none;margin-top:16px"></div>
            `;
            document.getElementById('axe-run-btn').addEventListener('click', () => this._runAndRender());
            document.getElementById('axe-export-btn').addEventListener('click', () => this._exportCsv());
        }

        async _runAndRender() {
            const btn = document.getElementById('axe-run-btn');
            const status = document.getElementById('axe-status');
            if (btn) { btn.disabled = true; btn.textContent = 'Running...'; }
            if (status) status.textContent = 'Scanning 17 pages...';
            try {
                const report = await this.runAllPages();
                const summary = this.summarize(report);
                this._renderSummaryTable(summary, report);
                if (status) {
                    const totalViolations = summary.reduce((n, r) => n + r.count, 0);
                    status.textContent = totalViolations === 0
                        ? 'ZERO violations'
                        : `${totalViolations} violation${totalViolations > 1 ? 's' : ''} found`;
                    status.style.color = totalViolations === 0 ? 'var(--green)' : 'var(--red)';
                }
                const exportBtn = document.getElementById('axe-export-btn');
                if (exportBtn) exportBtn.style.display = '';
            } catch (e) {
                if (status) { status.textContent = 'Error: ' + e.message; status.style.color = 'var(--red)'; }
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = 'Run Audit'; }
            }
        }

        _renderSummaryTable(summary, report) {
            const tbody = summary.map(r => `
                <tr style="cursor:pointer" onclick="window.axeRunner._showDetail('${r.page}')">
                    <td style="padding:8px 12px;font-size:12px;font-weight:500">${r.page}</td>
                    <td style="padding:8px 12px;font-size:12px;text-align:center">
                        <span style="color:${r.count === 0 ? 'var(--green)' : 'var(--red)'};font-weight:700">${r.count}</span>
                    </td>
                    <td style="padding:8px 12px;font-size:11px;color:${_impactColor(r.maxImpact)}">${r.maxImpact || 'none'}</td>
                </tr>
            `).join('');
            const table = document.getElementById('axe-summary-table');
            if (table) {
                table.innerHTML = `
                    <table style="width:100%;border-collapse:collapse;font-size:12px">
                        <thead>
                            <tr style="border-bottom:1px solid var(--border)">
                                <th style="padding:8px 12px;text-align:left;color:var(--text-3);font-size:11px">Page</th>
                                <th style="padding:8px 12px;text-align:center;color:var(--text-3);font-size:11px">Violations</th>
                                <th style="padding:8px 12px;text-align:left;color:var(--text-3);font-size:11px">Max Impact</th>
                            </tr>
                        </thead>
                        <tbody>${tbody}</tbody>
                    </table>
                `;
            }
            this._currentReport = report;
        }

        _showDetail(page) {
            const detail = document.getElementById('axe-detail-panel');
            if (!detail || !this._currentReport) return;
            const violations = this._currentReport[page] || [];
            if (!violations.length) {
                detail.style.display = '';
                detail.innerHTML = `<div style="padding:12px;color:var(--green);font-size:12px">No violations on ${page}</div>`;
                return;
            }
            const rows = violations.map(v => `
                <div style="padding:12px;border-bottom:1px solid var(--border)">
                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                        <span style="font-size:11px;font-weight:700;padding:2px 6px;border-radius:3px;background:${_impactBg(v.impact)};color:${_impactColor(v.impact)}">${escapeHtml(v.impact || '')}</span>
                        <code style="font-size:11px;color:var(--text-2)">${escapeHtml(v.id || '')}</code>
                        <a href="${/^https?:\/\//.test(v.helpUrl) ? v.helpUrl : '#'}" target="_blank" rel="noopener" style="font-size:11px;color:var(--accent-l)">${escapeHtml(v.help || v.id || '')}</a>
                    </div>
                    <div style="font-size:11px;color:var(--text-3)">${v.nodes.length} element${v.nodes.length > 1 ? 's' : ''} affected</div>
                    ${v.nodes.slice(0, 2).map(n => `<pre style="font-size:10px;overflow:auto;max-width:100%;padding:6px;background:var(--s2);border-radius:4px;margin-top:4px">${escapeHtml(n.html)}</pre>`).join('')}
                </div>
            `).join('');
            detail.style.display = '';
            detail.innerHTML = `
                <h3 style="font-size:13px;font-weight:600;margin:0 0 12px;color:var(--text-1)">${page} — ${violations.length} violation${violations.length > 1 ? 's' : ''}</h3>
                ${rows}
            `;
        }

        _exportCsv() {
            if (!this._currentReport) return;
            const rows = [['page', 'id', 'impact', 'help', 'affected']];
            for (const [page, violations] of Object.entries(this._currentReport)) {
                for (const v of violations) {
                    rows.push([page, v.id, v.impact, (v.help || '').replace(/,/g, ';'), v.nodes.length]);
                }
            }
            const csv = rows.map(r => r.join(',')).join('\n');
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'hermes-a11y-audit.csv';
            a.click();
            URL.revokeObjectURL(url);
        }
    }

    function _maxImpact(violations) {
        const order = ['critical', 'serious', 'moderate', 'minor'];
        for (const level of order) {
            if (violations.some(v => v.impact === level)) return level;
        }
        return '';
    }

    function _impactColor(impact) {
        return { critical: 'var(--red)', serious: '#f97316', moderate: '#f59e0b', minor: 'var(--text-3)' }[impact] || 'var(--text-3)';
    }

    function _impactBg(impact) {
        return { critical: 'rgba(239,68,68,.15)', serious: 'rgba(249,115,22,.15)', moderate: 'rgba(245,158,11,.15)', minor: 'rgba(255,255,255,.06)' }[impact] || 'rgba(255,255,255,.06)';
    }

    window.HermesAxeRunner = HermesAxeRunner;
    window.axeRunner = new HermesAxeRunner();

    // Adapter for ObservabilityShell tab protocol (render/destroy)
    window.ObservabilityA11y = {
        render() {
            const el = document.getElementById('axe-runner-panel');
            if (!el) return;
            if (!el.dataset.wired) {
                window.axeRunner.renderPanel('axe-runner-panel');
                el.dataset.wired = '1';
            }
        },
        destroy() {},
    };
})();
