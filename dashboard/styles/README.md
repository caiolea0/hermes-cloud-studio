# Hermes Dashboard — Styles & Design System

Documenta convenção de tokens, procedimento de auditoria WCAG via axe-core, e regras anti-regressão visual. **Leia antes de tocar qualquer CSS.**

## Arquivos

| Arquivo | Papel |
|---|---|
| `tokens.css` | Fonte canônica de TODOS os tokens (color/spacing/radii/typography/shadow/motion). **DARK default.** |
| `light.css` | Overrides `:root[data-theme=light]`. Apenas cores + shadows; spacing/typography herda do default. |
| `../styles.css` | Estilos globais legacy. Migração progressiva pra `var(--*)` — F.2.4e refatora primary surfaces (sidebar/topbar/cards/modals); componentes específicos seguem em PRs futuros. |

## Regra anti-hex-literal

🚫 **NUNCA** introduza hex/rgb/hsl literais em `styles.css`, `components/*.js`, `app.js` ou qualquer arquivo dashboard fora deste diretório `styles/`.

✅ **SEMPRE** use `var(--color-*)`, `var(--space-*)`, `var(--radius-*)`, `var(--text-*)`, `var(--shadow-*)`, `var(--motion-*)`.

Exceção pontual aceitável: border decorativo único ou debug temporário. Comment justificando o motivo é obrigatório (`/* literal: gradient decorativo, não há token equivalente */`).

## Theme switching

FOUC-prevention via inline script no `<head>` ANTES de qualquer `<link rel=stylesheet>`:

```html
<script>
  (function () {
    const t = localStorage.getItem('hermes_theme') || 'auto';
    const dark = t === 'dark' || (t === 'auto' && matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  })();
</script>
```

Toggle runtime:
```js
document.documentElement.setAttribute('data-theme', 'light');
localStorage.setItem('hermes_theme', 'light');
```

## Auditoria WCAG (axe-core)

`dashboard/vendor/axe.min.js` (axe-core 4.10+) é vendor LOCAL — alinha pattern MERGED-019 (DOMPurify local, NÃO CDN runtime). Carregado via `<script src="vendor/axe.min.js" defer>` em `index.html`.

### Procedure manual smoke (DevTools console)

```js
await axe.run().then(r => {
  const violations = r.violations.map(v => ({
    id: v.id,
    impact: v.impact,
    nodes: v.nodes.length,
  }));
  console.table(violations);
  console.log('Contrast violations:', violations.filter(v => v.id === 'color-contrast').length);
});
```

### Gate F.2.4 — done criteria

- **Zero** `color-contrast` violations em 6 runs:
  - `/dashboard#control` light + dark
  - `/dashboard#dashboard` light + dark
  - `/dashboard#prospects` light + dark
- Outras violations (best-practice, ARIA roles) tratadas best-effort, mas não bloqueiam merge inicial.

Se violation `color-contrast` detectada → ajustar valor de cor em `tokens.css` (escurecer `--color-fg` ou aclarar `--color-bg`) ATÉ zero. NÃO aceitar "ligeiramente abaixo 4.5:1, owner não vai notar".

## Screenshot baselines

`.claude/screenshots/baseline/` versionado em git (regression test futuro). 1440×900, 6 PNG (3 páginas × 2 themes):

- `control_dark.png` / `control_light.png`
- `dashboard_dark.png` / `dashboard_light.png`
- `prospects_dark.png` / `prospects_light.png`

Atualize baseline quando refactor visual intencional. PR de refactor inclui baseline novo no mesmo commit.

## Convenção naming (resumo)

| Prefixo | Uso |
|---|---|
| `--color-*` | Cores semânticas (bg/fg/accent/success/warn/error/info/border) |
| `--space-*` | Spacing base 4px (xs=4, sm=8, md=16, lg=24, xl=32, 2xl=48) |
| `--radius-*` | Border radius (sm=4, md=8, lg=12, full=9999) |
| `--text-*` | Font size (xs=11, sm=13, base=14, lg=16, xl=20, 2xl=28) |
| `--font-*` | Font family (sans, mono) |
| `--shadow-*` | Box shadow (sm, md, lg) |
| `--motion-*` | Duration (fast=120ms, base=200ms, slow=400ms) |
| `--ease-*` | Easing curves (out, in-out) |

Adicione novo token apenas se ≥2 lugares precisam — caso contrário use literal pontual com comment.
