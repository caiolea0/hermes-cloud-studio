# Hermes 2.0 — Design State (UI/UX v2)
**Atualizado**: 2026-06-21
**Status**: idioma visual v2 (minimalismo robusto) APROVADO pelo owner (tom). Telas-âncora geradas e validadas. Pendente: 3 telas restantes + integração ao dashboard real.

> Ponto de retomada do trabalho de UI/UX. Ler junto com `HERMES-2.0-UIUX-PLAN.md` (plano mestre de UI) e as memórias agentmemory (`hermes-2.0-uiux-visao`, `design-language-v2-minimalismo-robusto`, `hermes-2.0-design-v2-escalado`).

---

## 1. Idioma visual v2 — Minimalismo Robusto (LEIS, aprovadas)

O owner reprovou um primeiro lote de mockups "maximalistas" (muita cor/glow/seções/texto). O idioma correto, aprovado na esteira:

1. **Minimalista mas robusto** — calma visual, muito respiro, 1 foco por tela. Poder mantido, revelado sob demanda.
2. **Cor escassa e harmônica** — base neutra dark (NÃO roxo saturado de fundo), 1 acento (roxo `#7c3aed`) cirúrgico; status (warm=oportunidade, cool=consolidado, good=potencial) só com significado; glow sutil.
3. **Zero jargão** — tudo em PT de operador leigo. "SEO"→"aparecer no Google"; "adversarial report"→"por que o concorrente ganha"; cada ação diz o que FAZ + tooltip.
4. **Progressive disclosure** — tela limpa por padrão; hover-expand / drawers revelam detalhe (pedido explícito do owner: "mousehover com expansão de componentes").
5. **Fluido, não seções empilhadas de texto** — dashboard/ferramenta, não landing page.
6. **Reduced-motion safety (CRÍTICO)** — owner tem `prefers-reduced-motion` ATIVO. Conteúdo SEMPRE visível; `opacity:0`+animação de entrada SÓ sob `@media(prefers-reduced-motion:no-preference)`. Valores (barras, números) inline na base; animação só enhancement. Ver `lsn_28da11acc5f4311c`.
7. **Dados reais quando implementado** — nada mockup; solid=medido, translúcido=projetado.

---

## 2. Artefatos (em `.claude/design-mockups/`)

| Arquivo | O quê | Estado |
|---|---|---|
| `design-system-v2.css` | **CSS canônico — fonte da verdade do idioma**. Tokens OKLCH, `.top/.nav/.chip/.glance/.card/.act/.ring/.disc/.reveal/.toast`, reduced-motion safety embutida | ✅ canônico |
| `02b-esteira-v2.html` | Esteira de leads — **golden reference aprovada** (cards, hover-expand, count-up, FLIP, filtro-reverso) | ✅ aprovada |
| `cmd-v2.html` | Command Center ("Central") — agentes limpos, hover revela função | ✅ validado |
| `map-v2.html` | Mapa de varredura — **SVG auto-contido** (zonas por situação, sem WebGL/CDN/tiles), clicável + filtro | ✅ validado |
| `dossier-v2.html` | Dossiê de venda — BLUF + anel de gap | ✅ validado |
| `competitors-v2.html` | Concorrência — "você vs líder", viz CSS puro, CTAs | ✅ validado |
| `agent-v2.html` | Agente ("Caçador de negócios") — o que faz em PT, ações claras | ✅ validado |
| `myday-v2.html` | Meu dia — jornada fluida (bug de scrollytelling consertado) | ✅ validado |
| `hero-v2.html` | Início / lobby — visão geral calma + oportunidades quentes + atalhos | ✅ validado |
| `onboarding-v2.html` | Primeiro uso — varrer 1º bairro + como a máquina funciona (visual) | ✅ validado |
| `action-dispatch-v2.html` | Formas de comandar — ⌘K, menu radial, arrastar, deslizar-confirmar | ✅ validado |
| `index.html` | Galeria v2 (10 cards) | ✅ |
| `00-hero..11-design-system` (v1) | Lote maximalista REPROVADO — manter só como referência de estrutura/dados, NÃO de tom | ⚠️ reprovado |

**Validação** (via preview eval sob `prefers-reduced-motion: reduce = true`): todas as 7 telas v2 → `hiddenBig=0` (conteúdo sempre visível), zero erro de console, PT puro, herdam o CSS canônico.

---

## 3. Decisões de UI já tomadas
- Stack: **vanilla JS** (sem React) — todas as libs (MapLibre, ECharts, etc) são framework-agnostic; rings/gauges = CSS puro. React só island opcional se necessário. (Ver `HERMES-2.0-UIUX-PLAN.md §6.)
- 8 decisões abertas do UIUX-PLAN: defaults adotados (dock+⌘K nav, graph+gauge agentes, vanilla+GSAP dossiê, Contabo nginx basemap, número-único+toggle, Cuiabá-only launch, slide-to-confirm). Reconfirmar ao integrar.

## 4. Bugs/lições desta sessão
- **reduced-motion** → conteúdo invisível (cards sumiram, my-day não abria). Regra na §1.6. Lição `lsn_28da11acc5f4311c`.
- **deck.gl@9 + h3-js** versão incompatível → loop infinito de erro (H3HexagonLayer). Mapa v2 usa MapLibre puro, sem H3HexagonLayer.
- **`preview_screenshot` trava** neste ambiente Windows (até página leve). Validar via `preview_eval` (console + DOM); owner vê via navegador `http://localhost:55050`.

## 5. Próximos passos do design (quando retomar)
1. ✅ **CONCLUÍDO** — 10 telas v2 completas e validadas sob reduced-motion (lista §2).
2. Refinar conforme feedback do owner no conjunto (iterativo).
3. Integrar o idioma v2 ao **dashboard real** (`dashboard/`) — hoje é vanilla JS + tokens.css/light.css (F.2.4). O `design-system-v2.css` deve convergir com/substituir os tokens conforme o redesign.
4. Conectar as telas aos dados reais quando o **motor de diagnóstico** (H2-F1..F4) existir.

> **Sequenciamento acordado**: design = blueprint → **fundação na VPS** (H2-F0 docker + Tailscale + auto-deploy, ver `HERMES-2.0-ACCESS-DEPLOY.md`) → **motor** (F1-F4 crescendo na VPS) → **frontend real** (passo 3+4). Ver memória `sequenciamento-fundacao-antes-motor`.

## Como retomar o design numa nova sessão
1. `preview_start` config `design-mockups` (launch.json) → abrir `http://localhost:55050`.
2. Ler este doc + `HERMES-2.0-UIUX-PLAN.md` + memórias `design-language-v2-*`.
3. Lei inviolável: validar QUALQUER tela sob `prefers-reduced-motion: reduce` (conteúdo sempre visível) antes de aprovar.
