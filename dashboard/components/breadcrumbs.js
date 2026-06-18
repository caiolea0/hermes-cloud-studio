/* UX-RM-F2-A — Breadcrumb Bar component
 * Renders: Dashboard › Group › Page trail in .breadcrumb-bar
 * Called by navigate() on every page switch.
 */
(function () {
    const PAGE_TO_GROUP = {
        control: 'operations', cobaia: 'operations',
        'pipeline-studio': 'operations', tasks: 'operations',
        prospects: 'outreach', proposals: 'outreach', audit: 'outreach', linkedin: 'outreach',
        skills: 'intelligence', 'skill-proposals': 'intelligence', lab: 'intelligence', memory: 'intelligence',
        claude: 'devtools', 'mcp-gateway': 'devtools',
    };

    const GROUP_LABELS = {
        operations: 'Operations', outreach: 'Outreach',
        intelligence: 'Intelligence', devtools: 'Dev Tools',
    };

    const PAGE_TITLES = {
        dashboard: 'Dashboard', control: 'Control', cobaia: 'Cobaia',
        'pipeline-studio': 'Pipeline Studio', tasks: 'Daily Queue',
        prospects: 'Prospects', proposals: 'Propostas', audit: 'Auditoria',
        linkedin: 'LinkedIn', skills: 'Skills', 'skill-proposals': 'Skill Proposals',
        lab: 'Lab', memory: 'Memoria', missions: 'Missions',
        claude: 'AI Terminal', 'mcp-gateway': 'MCP Gateway', observability: 'Observability',
    };

    function escHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    class HermesBreadcrumbs {
        mount(containerId) {
            this._el = document.getElementById(containerId);
        }

        update(groupId, pageId) {
            if (!this._el) this._el = document.getElementById('breadcrumb-mount');
            if (!this._el) return;
            const group = groupId && GROUP_LABELS[groupId];
            const pageTitle = PAGE_TITLES[pageId] || pageId;

            if (!group) {
                this._el.innerHTML = '';
                return;
            }

            this._el.innerHTML =
                '<ol class="breadcrumb-ol" aria-label="Breadcrumb">' +
                '<li><a href="#dashboard" class="bc-link" onclick="navigate(\'dashboard\');return false;">Dashboard</a></li>' +
                '<li aria-hidden="true" class="bc-sep">›</li>' +
                '<li><button class="bc-link" onclick="toggleNavGroup(\'' + escHtml(groupId) + '\')">' + escHtml(group) + '</button></li>' +
                '<li aria-hidden="true" class="bc-sep">›</li>' +
                '<li aria-current="page" class="bc-current">' + escHtml(pageTitle) + '</li>' +
                '</ol>';
        }
    }

    window.HermesBreadcrumbs = new HermesBreadcrumbs();
})();
