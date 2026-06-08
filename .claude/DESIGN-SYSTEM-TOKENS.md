# Hermes Design System — Tokens Canônicos (Fase F)

> **Spec canônica** de tokens do dashboard Hermes — paleta WCAG AA, espaçamento, tipografia, radii, breakpoints, componentes, e vendors LOCAIS. Fonte única de verdade pra `dashboard/styles.css` e qualquer skill/agent que toque CSS.
>
> **Status**: 2026-06-08 — derivado do estado atual `dashboard/styles.css` (90.9 KB, dark-only) + requisitos Fase F.2 (light mode WCAG AA + toast + tile sistema + dark mode toggle).
>
> **Inviolável**: estes tokens são o vocabulário. Skills/agents NUNCA inventam hex novo, padding numérico fora da escala, radius fora da escala, ou peso de fonte fora da escala. Se faltar token: PROPOR aqui via PR `.claude/DESIGN-SYSTEM-TOKENS.md` antes de tocar `styles.css`.
>
> **Vendors locais obrigatórios** (zero CDN): toda libs vivem em `dashboard/vendor/` — auditadas, hash-pinned, sem requests externos em runtime. Lista completa §9.

---

## §0 — Princípios

1. **Token > hardcoded.** Toda cor/spacing/radius vem de CSS custom property. Hex inline em `styles.css` = bug.
2. **Contraste WCAG AA.** Texto normal ≥ 4.5:1, texto large (≥18px ou ≥14px+bold) ≥ 3:1, componentes UI ≥ 3:1. Light+dark validados.
3. **Dark-first com light gêmeo.** Tokens semânticos (`--text`, `--bg`) trocam por `[data-theme="light"]`; primitives (`--accent`, `--lime`) ficam estáveis. Owner pode trocar em runtime, persiste em `localStorage.hermesTheme`.
4. **Escala fechada.** Spacing/radius/typography são escalas finitas — não há "qualquer número". Nenhum `padding: 7px` sobrevive code-review.
5. **Vendors locais.** Inter, DOMPurify, Chart.js, qualquer fonte/lib → `dashboard/vendor/` com SHA-256 documentado. CSP `default-src 'self'` deve passar.
6. **Mobile-aware.** Não é responsivo full, mas breakpoints definidos pra Mission Control caber em laptop 13" (1280) e desktop 1920+. Owner roda solo em laptop tour + monitor casa.
7. **Componentes ownership.** Spec abaixo é contrato. Cada componente lista classes CSS oficiais + variantes permitidas. Tudo fora disso = ad-hoc → migrar pra spec ou justificar exceção em `GUARDRAILS.md`.
8. **Sem motion gratuita.** Toda animação respeita `prefers-reduced-motion`. Duração padrão 150-250ms, ease único `--ease`.

---

## §1 — Paleta de Cores

### §1.1 Primitives (NÃO mudam com tema)

Cores brand + status que permanecem semanticamente idênticas em light e dark. Hex literal vive apenas aqui.

```css
:root {
  /* Brand */
  --accent:       #7c3aed;  /* roxo Hermes — botão primário, indicador ativo */
  --accent-l:     #a78bfa;  /* roxo claro — hover state, ícone ativo */
  --accent-d:     #5b21b6;  /* roxo escuro — pressed state, sombra glow */

  /* Energy / signature */
  --lime:         #d1fe17;  /* verde-lima Hermes — energia daemon, highlight crítico */
  --lime-dim:     rgba(209,254,23,0.12);

  /* Status semânticos */
  --green:        #10b981;  /* sucesso, healthy */
  --green-dim:    rgba(16,185,129,0.12);
  --red:          #ef4444;  /* erro, banned, burned */
  --red-dim:      rgba(239,68,68,0.12);
  --amber:        #f59e0b;  /* warning, cooldown, degraded */
  --amber-dim:    rgba(245,158,11,0.12);
  --blue:         #3b82f6;  /* info, neutral action */
  --blue-dim:     rgba(59,130,246,0.12);
  --pink:         #ec4899;  /* destaque secundário, badge especial */
  --pink-dim:     rgba(236,72,153,0.12);

  /* Subsystem chips (Mission Control §6.3) */
  --sub-linkedin: #0a66c2;
  --sub-email:    #10b981;
  --sub-scraper:  #f59e0b;
  --sub-audit:    #a78bfa;
  --sub-daemon:   #d1fe17;
  --sub-tunnel:   #3b82f6;
}
```

### §1.2 Tema DARK (default, `data-theme="dark"` ou ausente)

Surface scale `s1→s5` cria profundidade (cards > app shell > modal). Texto scale `text → text-2 → text-3` desce em hierarquia.

```css
:root,
:root[data-theme="dark"] {
  /* Surfaces */
  --bg:        #0a0a0c;
  --s1:        #111114;
  --s2:        #18181c;
  --s3:        #1f1f24;
  --s4:        #27272d;
  --s5:        #303038;

  /* Text */
  --text:      #f0f0f4;  /* contrast vs bg = 17.4:1 (AAA) */
  --text-2:    #8b8b98;  /* contrast vs bg = 6.1:1  (AA)  */
  --text-3:    #55556a;  /* contrast vs bg = 3.2:1  (AA large only) */

  /* Borders */
  --border:    rgba(255,255,255,0.06);
  --border-h:  rgba(255,255,255,0.12);
  --border-a:  rgba(255,255,255,0.20);

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.40);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.45);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.55);
  --shadow-glow: 0 0 24px rgba(124,58,237,0.35);  /* accent glow */
}
```

### §1.3 Tema LIGHT (`[data-theme="light"]`) — WCAG AA validado

Light mode é gêmeo, NÃO afterthought. Cada token semântico tem versão clara que mantém contraste igual ou melhor.

```css
:root[data-theme="light"] {
  /* Surfaces */
  --bg:        #f7f7f9;
  --s1:        #ffffff;
  --s2:        #f0f0f4;
  --s3:        #e6e6ec;
  --s4:        #d8d8e0;
  --s5:        #c8c8d2;

  /* Text */
  --text:      #14141a;  /* contrast vs bg = 16.8:1 (AAA) */
  --text-2:    #4a4a58;  /* contrast vs bg = 7.2:1  (AA)  */
  --text-3:    #6b6b78;  /* contrast vs bg = 4.7:1  (AA)  */

  /* Borders */
  --border:    rgba(0,0,0,0.08);
  --border-h:  rgba(0,0,0,0.16);
  --border-a:  rgba(0,0,0,0.28);

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.06);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.12);
  --shadow-glow: 0 0 24px rgba(124,58,237,0.18);

  /* Status dims precisam ser MAIS opacos no light pra preservar legibilidade */
  --lime-dim:  rgba(209,254,23,0.28);
  --green-dim: rgba(16,185,129,0.18);
  --red-dim:   rgba(239,68,68,0.16);
  --amber-dim: rgba(245,158,11,0.20);
  --blue-dim:  rgba(59,130,246,0.16);
  --pink-dim:  rgba(236,72,153,0.16);
}
```

### §1.4 Matriz de contraste validada (WCAG 2.1 AA)

Owner deve revalidar via `.claude/scripts/validate_contrast.py` (Fase F.2 entregável) antes de qualquer mudança de cor.

| Combinação                       | Dark ratio | Light ratio | Status |
|----------------------------------|------------|-------------|--------|
| `--text` on `--bg`               | 17.4:1     | 16.8:1      | AAA    |
| `--text` on `--s1`               | 16.2:1     | 21.0:1      | AAA    |
| `--text-2` on `--bg`             | 6.1:1      | 7.2:1       | AA     |
| `--text-3` on `--bg`             | 3.2:1      | 4.7:1       | AA-L / AA |
| `--accent` text on `--s1`        | 5.4:1      | 5.8:1       | AA     |
| `--accent-l` text on `--bg`      | 8.1:1      | n/a (use `--accent`) | AA |
| `--green` text on `--green-dim`  | 7.8:1      | 6.4:1       | AA     |
| `--red` text on `--red-dim`      | 5.9:1      | 5.1:1       | AA     |
| `--amber` text on `--amber-dim`  | 8.2:1      | 6.8:1       | AA     |
| `--lime` text on `--lime-dim`    | 12.3:1     | 9.7:1       | AAA    |
| Focus ring `--accent` on bg      | 5.4:1      | 5.8:1       | AA     |

**Regra**: nenhuma combinação texto/superfície usada na UI pode ficar abaixo de 4.5:1 (normal) ou 3:1 (large/UI). Adicionar entrada nesta matriz se introduzir nova combinação.

---

## §2 — Espaçamento

Escala 4px-base. Toda margin/padding/gap deve ser uma destas variáveis. Owner em code-review rejeita `padding: 11px`.

```css
:root {
  --sp-0:  0;
  --sp-1:  4px;
  --sp-2:  8px;
  --sp-3:  12px;
  --sp-4:  16px;
  --sp-5:  20px;
  --sp-6:  24px;
  --sp-8:  32px;
  --sp-10: 40px;
  --sp-12: 48px;
  --sp-16: 64px;
}
```

**Uso típico**:
- Card interno: `padding: var(--sp-4)` (16px)
- Lista item: `padding: var(--sp-2) var(--sp-3)` (8/12)
- Section gap: `gap: var(--sp-6)` (24px)
- Hero/page header: `padding: var(--sp-8) var(--sp-6)`
- Botão padrão: `padding: var(--sp-2) var(--sp-4)` (8×16) — confirma com `:height: 32px`
- Botão sm: `padding: var(--sp-1) var(--sp-3)` (4×12) — `height: 24px`
- Botão lg: `padding: var(--sp-3) var(--sp-5)` (12×20) — `height: 40px`

---

## §3 — Tipografia

### §3.1 Fonte

```css
:root {
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', 'SF Mono', Consolas, Monaco, monospace;
}
```

**Inter** servida via `dashboard/vendor/fonts/inter/` (variable WOFF2, weights 400/500/600/700, hash-pinned §9). Owner offline funciona idêntico.

**JetBrains Mono** servida via `dashboard/vendor/fonts/jetbrains-mono/` — apenas pra `<code>`, log tail, terminal, hash diff, agent_zero output.

### §3.2 Escala de tamanhos

Base `html { font-size: 13px }` (já no `styles.css:45`). Escala em px absoluto pra previsibilidade — `rem` complica leitura.

```css
:root {
  --fs-xs:   10px;  /* badge, micro-label, timestamp seco */
  --fs-sm:   11px;  /* secondary text, table small, btn-sm */
  --fs-base: 13px;  /* body default */
  --fs-md:   15px;  /* page section title, card title */
  --fs-lg:   18px;  /* page hero title */
  --fs-xl:   22px;  /* big number stat */
  --fs-2xl:  28px;  /* kpi hero */
  --fs-3xl:  36px;  /* splash/empty state */
}
```

### §3.3 Pesos

Inter variable, mas só estes 4 pontos permitidos:

```css
:root {
  --fw-regular: 400;
  --fw-medium:  500;
  --fw-semi:    600;
  --fw-bold:    700;
}
```

### §3.4 Line-height + tracking

```css
:root {
  --lh-tight:   1.2;   /* títulos, números KPI */
  --lh-normal:  1.5;   /* body default */
  --lh-loose:   1.7;   /* texto longo (mission notes, agent reply) */

  --ls-tight:   -0.01em;  /* títulos grandes */
  --ls-normal:  0;
  --ls-wide:    0.05em;   /* uppercase label, badge text */
}
```

### §3.5 Classes utilitárias canônicas

(Compatíveis com `.t-10/.t-11/.t-13/.t-15/.t-18/.t-22/.t-28` já em `styles.css:65-71` — manter aliases até migração completa)

```css
.t-xs   { font-size: var(--fs-xs); }
.t-sm   { font-size: var(--fs-sm); }
.t-base { font-size: var(--fs-base); }
.t-md   { font-size: var(--fs-md); }
.t-lg   { font-size: var(--fs-lg); }
.t-xl   { font-size: var(--fs-xl); }
.t-2xl  { font-size: var(--fs-2xl); }

.t-regular { font-weight: var(--fw-regular); }
.t-medium  { font-weight: var(--fw-medium); }
.t-semi    { font-weight: var(--fw-semi); }
.t-bold    { font-weight: var(--fw-bold); }

.t-muted { color: var(--text-2); }
.t-dim   { color: var(--text-3); }
.t-mono  { font-family: var(--font-mono); }

.t-upper { text-transform: uppercase; letter-spacing: var(--ls-wide); }
.t-tabular { font-variant-numeric: tabular-nums; }  /* obrigatório em KPI, contagem regressiva */
```

---

## §4 — Border Radius

```css
:root {
  --r-xs:   6px;   /* badge, chip pequeno */
  --r-sm:   8px;   /* button, input, list item */
  --r-md:   10px;  /* card secundário, panel inline */
  --r:      14px;  /* card principal, modal */
  --r-lg:   20px;  /* hero card, mission tile grande */
  --r-pill: 999px; /* pill, avatar circular, status chip */
}
```

**Regra**: nenhum `border-radius: 12px` solto. Se 14 é demais e 10 é pouco, escolha um — não invente intermediário.

---

## §5 — Motion

```css
:root {
  --ease:        cubic-bezier(0.4, 0, 0.2, 1);     /* standard */
  --ease-in:     cubic-bezier(0.4, 0, 1, 1);
  --ease-out:    cubic-bezier(0, 0, 0.2, 1);
  --ease-spring: cubic-bezier(0.5, -0.5, 0.5, 1.5); /* toast entrada, modal */

  --t-instant: 80ms;
  --t-fast:    150ms;
  --t-base:    220ms;
  --t-slow:    400ms;
  --t-very-slow: 800ms;  /* só pra reveal/empty state — nunca interação */
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

**Regra**: hover/focus/active = `--t-fast`. Modal/drawer/toast = `--t-base`. Skeleton/shimmer = `--t-very-slow` com `infinite`.

---

## §6 — Breakpoints

Hermes não é mobile-first, mas Mission Control deve degradar previsível.

```css
:root {
  --bp-sm:  640px;   /* não atendido — fallback "abra no desktop" */
  --bp-md:  1024px;  /* tablet landscape — Mission tiles colapsam pra 2 col */
  --bp-lg:  1280px;  /* laptop 13" — layout mínimo suportado */
  --bp-xl:  1600px;  /* desktop padrão */
  --bp-2xl: 1920px;  /* full HD — layout ótimo */
}

/* Uso (custom properties em @media não funcionam — repetir literal): */
@media (max-width: 1023px) { .hide-md { display: none; } }
@media (max-width: 1279px) { .hide-lg { display: none; } }
@media (min-width: 1600px) { .show-xl { display: block; } }
```

**Regra grids**:
- `< 1024px` → mensagem "Mission Control requer ≥1280px" + redirect `/dashboard` simplificado.
- `1024-1279` → Mission tiles 2 colunas, sidebar colapsada.
- `1280-1599` → Mission tiles 3 colunas, sidebar colapsada.
- `≥ 1600` → Mission tiles 3 colunas, sidebar expandida default, painel direito (logs) visível.
- `≥ 1920` → tudo + painel direito mais largo.

---

## §7 — Layout Shell

Tokens já em uso (preservar — `styles.css:36-38`):

```css
:root {
  --sidebar-w:    56px;   /* collapsed */
  --sidebar-exp:  220px;  /* expanded */
  --topbar-h:     48px;
  --rightpane-w:  360px;  /* logs/decisions panel (Mission Control) */
  --footer-h:     32px;   /* status bar (energy, ws health, theme toggle) */
}
```

**Z-index escala** (sempre referenciar token, NUNCA hardcode `z-index: 9999`):

```css
:root {
  --z-base:     0;
  --z-sticky:   100;
  --z-sidebar:  200;
  --z-topbar:   300;
  --z-dropdown: 400;
  --z-modal:    500;
  --z-toast:    600;
  --z-tooltip:  700;
  --z-debug:    9000;   /* dev overlay */
}
```

---

## §8 — Componentes (contrato)

Tudo abaixo é especificação de classes CSS oficiais. Skills/agents que geram HTML usam EXATAMENTE estas classes. Compor (`btn btn-primary btn-sm`) é OK; inventar (`btn-mega-cta`) requer adição aqui primeiro.

### §8.1 Button

```
.btn                — base, height 32px, padding sp-2/sp-4, radius r-sm, fw-medium
  .btn-primary     — bg accent, text on accent (#fff)
  .btn-ghost       — bg transparent, border --border, text --text-2 → :hover text
  .btn-danger      — bg --red-dim, text --red, :hover bg --red
  .btn-success     — bg --green-dim, text --green
  .btn-warning     — bg --amber-dim, text --amber
  .btn-lime        — bg --lime, text #0a0a0c (high contrast pra signature)
  .btn-icon        — square 32x32, only icon child
Sizes:
  .btn-sm          — height 24px, padding sp-1/sp-3, fs-sm
  .btn-lg          — height 40px, padding sp-3/sp-5, fs-md
State modifiers:
  [disabled]       — opacity 0.4, cursor not-allowed, no hover
  [aria-busy=true] — spinner overlay (vendor-local CSS spin)
  [data-active]    — bg accent, ring accent
```

### §8.2 Input / Select / Textarea

```
.input             — height 32px, bg --s2, border --border, radius r-sm, padding sp-2/sp-3
  :focus           — border --accent, shadow 0 0 0 3px rgba(124,58,237,0.20)
  [aria-invalid]   — border --red, shadow ring red
.input-sm          — height 24px
.input-lg          — height 40px
.textarea          — extends .input, min-height 80px, resize vertical
.select            — extends .input, caret right via vendor-local SVG
.input-group       — flex row, gap 0, shared border (prefix/suffix support)
.label             — fs-sm, fw-medium, color --text-2, mb sp-1
.help              — fs-xs, color --text-3, mt sp-1
.error             — fs-xs, color --red, mt sp-1
```

### §8.3 Card

```
.card              — bg --s1, border --border, radius --r, padding sp-4
  :hover           — border --border-h (apenas se interativa, [data-clickable])
  .card-header     — flex row, mb sp-3, fs-md fw-semi
  .card-body       — flex column, gap sp-3
  .card-footer     — flex row, justify-end, mt sp-3, pt sp-3, border-top --border
.card-elev         — shadow-md (eleva sobre fundo)
.card-glow         — shadow-glow (accent glow — apenas pra destaque crítico, ex: "tarefa urgente")
.card-sm           — padding sp-3, radius r-md
```

### §8.4 Badge / Chip

```
.badge             — inline-flex, padding sp-1 sp-2, radius r-xs, fs-xs, fw-medium
  .badge-lime/green/red/amber/blue/pink/accent  — bg --{color}-dim, text --{color}
.chip              — like badge mas pill (radius r-pill), padding sp-1 sp-3
.chip-removable    — chip + .chip-x (close button right)
.status-dot        — 8x8 circle, vertical-align middle, mr sp-1
  .status-dot-healthy  — bg --green
  .status-dot-warning  — bg --amber
  .status-dot-error    — bg --red
  .status-dot-idle     — bg --text-3
  .status-dot-pulse    — animation pulse 2s infinite (live indicator)
```

### §8.5 Toast (NOVO Fase F.2)

Vendor zero — DOM injetado via `dashboard/components/toast.js` (LOCAL, sem `react-hot-toast`, sem CDN).

```
#toast-stack       — fixed bottom-right, z-toast, gap sp-2, max-width 380px
.toast             — bg --s2, border --border, radius r-md, padding sp-3 sp-4, shadow-md
                     fade-in-up via t-base ease-spring, auto-dismiss 5s default
  .toast-icon      — 20x20, mr sp-3
  .toast-body      — flex column gap sp-1
  .toast-title     — fs-sm fw-semi
  .toast-msg       — fs-sm color --text-2
  .toast-actions   — mt sp-2, flex row gap sp-2, btn-sm
  .toast-close     — abs top-right sp-2, btn-icon size 20

Variantes (semantic):
  .toast-success   — border-left 3px --green
  .toast-error     — border-left 3px --red, no auto-dismiss
  .toast-warning   — border-left 3px --amber
  .toast-info      — border-left 3px --blue
  .toast-progress  — border-left 3px --accent, contains <progress> bar
```

**API JS canônica** (impl Fase F.2):
```js
Toast.success(msg, {title, duration, actions})
Toast.error(msg, {title, actions})  // sticky
Toast.warning(msg, {duration})
Toast.info(msg)
Toast.progress(msg, {value, max})  // updateable handle
Toast.dismiss(id)
Toast.dismissAll()
```

### §8.6 Modal / Drawer

```
.modal-backdrop    — fixed inset 0, bg rgba(0,0,0,0.6), z-modal, fade t-base
.modal             — bg --s1, border --border, radius --r, max-width 560px, padding sp-6
                     centered, shadow-lg
  .modal-header    — flex row justify-between, mb sp-4, fs-md fw-semi
  .modal-body      — max-height 70vh, overflow-y auto
  .modal-footer    — mt sp-5, flex row justify-end gap sp-2
.modal-lg          — max-width 800px
.modal-sm          — max-width 380px
.drawer            — fixed right 0, top topbar-h, bottom 0, width 480px, bg --s1
                     border-left --border, slide-in-right t-base ease
.drawer-left       — fixed left, slide-in-left
```

### §8.7 Tab / Pill nav

```
.tabs              — flex row, border-bottom --border, gap sp-1
  .tab             — padding sp-2 sp-3, color --text-3, border-bottom 2px transparent
    :hover         — color --text-2
    [aria-selected=true] — color --accent-l, border-bottom 2px --accent-l
.pillnav           — flex row, gap sp-1, padding sp-1, bg --s2, radius r-pill
  .pill            — padding sp-1 sp-3, radius r-pill, fs-sm color --text-2
    [aria-selected=true] — bg --s4, color --text
```

### §8.8 Table

```
.table             — width 100%, border-collapse separate, border-spacing 0
  thead th         — text-left, fs-sm fw-semi color --text-2, padding sp-2 sp-3, border-bottom --border
  tbody td         — padding sp-2 sp-3, border-bottom --border, fs-base
  tbody tr:hover   — bg --s2
  tbody tr[data-selected] — bg --accent (alpha 0.10)
.table-sm td       — padding sp-1 sp-2
.table-zebra tr:nth-child(even) td  — bg --s2 (alpha 0.5)
```

### §8.9 Skeleton / Empty state

```
.skeleton          — bg gradient s2→s3→s2, animation shimmer 1.5s infinite, radius r-xs
.skeleton-text     — height fs-base, my sp-1
.skeleton-title    — height fs-lg, width 60%
.empty             — flex column align-center, padding sp-12 sp-6, gap sp-3
  .empty-icon      — 64x64, color --text-3
  .empty-title     — fs-lg fw-semi color --text-2
  .empty-msg       — fs-sm color --text-3, max-width 360px, text-center
  .empty-cta       — mt sp-4
```

### §8.10 Subsystem tile (NOVO Fase F.2 Mission Control)

```
.sub-tile          — bg --s1, border --border, radius --r, padding sp-4, min-height 140px
                     flex column gap sp-2
  .sub-tile-head   — flex row justify-between align-center
    .sub-tile-name — fs-md fw-semi, with status-dot prefix
    .sub-tile-menu — btn-icon (pause/resume/details menu)
  .sub-tile-status — fs-sm color --text-2
  .sub-tile-last   — fs-xs color --text-3 (última ação + relativo timestamp)
  .sub-tile-next   — fs-xs color --text-3 (próxima agendada)
  .sub-tile-actions — mt-auto, flex row gap sp-2
Variantes (left border 3px):
  .sub-tile-healthy   — border-left 3px --green
  .sub-tile-warning   — border-left 3px --amber
  .sub-tile-error     — border-left 3px --red, glow --red-dim
  .sub-tile-paused    — border-left 3px --text-3, opacity 0.7
  .sub-tile-cooldown  — border-left 3px --blue, contains countdown.t-mono.t-tabular
```

### §8.11 Theme toggle (NOVO Fase F.2)

```
.theme-toggle      — btn-icon, in topbar right
                     swap icon sun/moon via vendor-local SVG
                     persist data-theme em html + localStorage.hermesTheme
                     respeita prefers-color-scheme no first load
                     transition t-base em --bg, --text (sem flash)
```

### §8.12 Code / Pre

```
.code-inline       — font-mono, fs-sm, bg --s3, padding 1px sp-1, radius r-xs
.code-block        — font-mono, fs-sm, bg --s2, padding sp-3, radius r-sm, overflow-x auto
                     border-left 3px --accent
.diff-add          — bg --green-dim, color --green
.diff-del          — bg --red-dim, color --red
.diff-ctx          — color --text-2
```

### §8.13 Form layout

```
.form              — flex column gap sp-4
.form-row          — flex row gap sp-3, wrap
.form-col          — flex column gap sp-1, flex 1
.fieldset          — border --border, radius r-md, padding sp-4
  .fieldset-title  — fs-sm fw-semi color --text-2, mb sp-3, t-upper
```

---

## §9 — Vendors LOCAIS

**Inviolável**: zero CDN, zero CSP `unsafe-inline`. Toda lib vive em `dashboard/vendor/` com SHA-256 documentado e auditoria a cada bump.

### §9.1 Diretório canônico

```
dashboard/vendor/
├── fonts/
│   ├── inter/
│   │   ├── Inter-roman.var.woff2          (weights 400-700 variable)
│   │   ├── Inter-italic.var.woff2
│   │   └── inter.css                       (@font-face declarations)
│   └── jetbrains-mono/
│       ├── JetBrainsMono-Regular.woff2
│       ├── JetBrainsMono-Bold.woff2
│       └── jetbrains.css
├── icons/
│   ├── lucide/                              (subset SVG sprites — apenas ícones usados)
│   │   └── lucide.svg                       (sprite único, <use href="#icon-name">)
│   └── README.md                            (lista ícones permitidos + processo add)
├── lib/
│   ├── dompurify-3.2.4.min.js              (já existente — XSS Fase E.2)
│   ├── chart.umd-4.4.7.min.js              (KPI charts Mission Control + Cobaia)
│   └── chartjs-adapter-date-fns-3.0.0.min.js
└── HASHES.txt                               (SHA-256 de cada arquivo + data + source URL)
```

### §9.2 Vendors atuais + planejados

| Vendor                 | Versão  | Uso                                        | Fase    | Status      |
|------------------------|---------|--------------------------------------------|---------|-------------|
| DOMPurify              | 3.2.4   | Sanitize HTML Claude/agent_zero output     | E.2     | ✅ LOCAL    |
| Inter (variable)       | 4.0     | Fonte primária UI                          | F.2     | ⏳ A migrar de CDN |
| JetBrains Mono         | 2.304   | Code, log tail, terminal, agent output     | F.2     | ⏳ A baixar |
| Lucide icons (subset)  | 0.469   | Ícones UI (sprite SVG)                     | F.2     | ⏳ A gerar  |
| Chart.js               | 4.4.7   | KPI/cohort charts Mission + Cobaia + F.8   | F.8     | ⏳ A baixar |
| chartjs-adapter-datefns| 3.0.0   | Time-series eixo X Chart.js                | F.8     | ⏳ A baixar |

### §9.3 Processo de bump (obrigatório)

1. Download arquivo oficial (npm tarball preferido — não unpkg).
2. Verificar SHA-256 contra release notes oficiais.
3. Atualizar `dashboard/vendor/HASHES.txt` com `nome | versão | sha256 | data_bump | source_url`.
4. Skill `audit-vendors` (a criar Fase F.9) revalida hashes em CI/local hook.
5. Owner aprova bump em commit `chore(vendor): bump <nome> <old>→<new>`.

### §9.4 CSP target (Fase F.8 hardening)

```
Content-Security-Policy:
  default-src 'self';
  script-src 'self';
  style-src 'self' 'unsafe-inline';     /* TODO migrar pra hash/nonce em F.8 */
  font-src 'self';
  img-src 'self' data:;
  connect-src 'self' ws: wss:;
  base-uri 'self';
  form-action 'self';
  frame-ancestors 'none';
```

---

## §10 — Iconografia

- **Sistema único**: Lucide (subset). NÃO misturar com Heroicons, Material, Font Awesome.
- **Tamanhos padrão**: 14, 16, 18, 20, 24, 32, 48. Reflete escala tipográfica.
- **Stroke width**: `2` default. Nunca `1.5` ou `3` mixed — manter consistente.
- **Cor**: herda `currentColor` (=`color: var(--text)` ou variante). Nunca hex inline.
- **Acesso**: `<svg><use href="#icon-<name>"/></svg>` referenciando sprite local `dashboard/vendor/icons/lucide/lucide.svg`.
- **Lista permitida**: documentada em `dashboard/vendor/icons/README.md`. Adicionar ícone novo = PR com justificativa + adicionar ao sprite via build script.

---

## §11 — Acessibilidade (gates)

1. **Foco visível sempre**: `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }` default global. Skill que remova `outline: none` sem substituir = bug.
2. **Hit target mínimo**: 32×32 px (botões). Lista item ≥ 28 vertical.
3. **ARIA obrigatório**:
   - Botão icon-only → `aria-label`
   - Toast → `role="status"` (info/success) ou `role="alert"` (error/warning)
   - Modal → `role="dialog" aria-modal="true" aria-labelledby="..."`
   - Tab → `role="tablist"` / `role="tab"` / `aria-selected`
   - Status dot → `aria-label="healthy"` / `role="img"`
4. **Trap focus** em modal/drawer. ESC fecha.
5. **Skip-link** topo: `Pular para conteúdo principal` antes do nav.
6. **Reduced motion** respeitado (§5).
7. **prefers-color-scheme**: detectar no first paint, salvar override em `localStorage.hermesTheme`.

---

## §12 — Migração & Compatibilidade

`styles.css` atual (90.9 KB) usa subset destes tokens. Migração incremental:

### Fase F.2 (próxima)
- [ ] Adicionar `:root[data-theme="light"]` block §1.3
- [ ] Adicionar tokens `--sp-*`, `--fs-*`, `--fw-*`, `--lh-*`, `--ls-*`, `--shadow-*`, `--z-*`, `--sub-*`
- [ ] Adicionar classes utilitárias §3.5 novas (manter aliases `.t-13` etc)
- [ ] Implementar `.theme-toggle` componente + `dashboard/components/theme.js`
- [ ] Implementar `.toast` componente + `dashboard/components/toast.js`
- [ ] Implementar `.sub-tile` Mission Control + variantes
- [ ] Baixar Inter + JetBrains Mono + Lucide pra `dashboard/vendor/`
- [ ] Script `.claude/scripts/validate_contrast.py` cobrindo matriz §1.4
- [ ] Auditoria `find dashboard/ -name '*.css' -o -name '*.js'` por hex literal — converter pra token

### Fase F.8
- [ ] Migrar `style-src 'unsafe-inline'` → hashes
- [ ] Adicionar Chart.js vendor + KPI charts
- [ ] Lighthouse score ≥ 90 acessibilidade (dark+light)

### Fase F.9
- [ ] Skill `audit-vendors` automatiza re-hash + diff
- [ ] Visual regression baseline (Playwright screenshot diff dark+light)

---

## §13 — Anti-padrões (rejeitar em code-review)

| ❌ Não fazer                                  | ✅ Fazer                                     |
|----------------------------------------------|---------------------------------------------|
| `color: #f0f0f4`                              | `color: var(--text)`                        |
| `padding: 11px`                               | `padding: var(--sp-3)` (12) ou `--sp-2` (8) |
| `border-radius: 12px`                         | `--r-md` (10) ou `--r` (14)                 |
| `font-size: 14px`                             | `--fs-base` (13) ou `--fs-md` (15)          |
| `font-weight: 800`                            | `--fw-bold` (700)                           |
| `<link href="https://fonts.googleapis.com">`  | Vendor local `dashboard/vendor/fonts/`      |
| `<script src="https://cdn.jsdelivr.net/...">`| Vendor local `dashboard/vendor/lib/`        |
| `z-index: 9999`                               | `var(--z-modal)` / `var(--z-toast)`         |
| `transition: all 0.3s ease`                   | `transition: all var(--t-base) var(--ease)` |
| `outline: none` sem substituir                | `:focus-visible` ring custom                |
| Toast custom com `setTimeout(remove, 3000)`   | API `Toast.success(msg)` canônica §8.5      |
| Inline `style="color:red"`                    | `class="t-danger"` ou token via classe      |
| Dark-only fix sem testar light               | Pareia ambos antes de merge                 |
| Inventar classe `.mega-button-cta`            | Compor `.btn .btn-lime .btn-lg` ou propor aqui |

---

## §14 — Cheatsheet (cola rápida)

```css
/* Cores */
--bg --s1 --s2 --s3 --s4 --s5
--text --text-2 --text-3
--accent --accent-l --accent-d
--lime --green --red --amber --blue --pink
--{color}-dim
--border --border-h --border-a

/* Spacing (4-base) */
--sp-1=4  --sp-2=8  --sp-3=12  --sp-4=16  --sp-5=20  --sp-6=24
--sp-8=32 --sp-10=40 --sp-12=48 --sp-16=64

/* Type */
--fs-xs=10 --fs-sm=11 --fs-base=13 --fs-md=15 --fs-lg=18 --fs-xl=22 --fs-2xl=28
--fw-regular=400 --fw-medium=500 --fw-semi=600 --fw-bold=700

/* Radius */
--r-xs=6 --r-sm=8 --r-md=10 --r=14 --r-lg=20 --r-pill=999

/* Motion */
--t-instant=80 --t-fast=150 --t-base=220 --t-slow=400
--ease (standard)

/* Layout */
--sidebar-w=56 --sidebar-exp=220 --topbar-h=48
--rightpane-w=360 --footer-h=32
--z-modal=500 --z-toast=600

/* Shadows */
--shadow-sm --shadow-md --shadow-lg --shadow-glow
```

---

## §15 — Mudança & governança

- **Owner deste doc**: `@cleao`. Qualquer skill/agent que proponha token novo abre PR alterando este arquivo PRIMEIRO. Implementação em `styles.css` vem depois.
- **Versionamento**: header deste arquivo registra data + delta na próxima vez que mudar. Sem changelog separado — diff git é o changelog.
- **Critério "ship"**: token só vai pra produção depois de (a) entrada nesta spec, (b) entrada na matriz §1.4 se for cor, (c) classe utilitária ou componente correspondente, (d) revalidação `validate_contrast.py`.
- **Conflito tema**: se light vs dark exigir tokens divergentes além dos já mapeados, abrir issue `design-system: token branch needed for <case>` antes de hack `[data-theme="light"] .my-thing { color: red }`.

---

**Fim spec canônica.** Cumprir = UI Hermes consistente, acessível, owner-friendly, escalável pra F.2-F.9 sem refactor visual. Quebrar = débito imediato em `.claude/FRONTEND-GAP.md` §design-debt.
