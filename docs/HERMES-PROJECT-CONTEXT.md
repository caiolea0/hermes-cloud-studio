# Hermes Project — Contexto Completo para Claude Code

## Visão Geral

Este documento contém todas as decisões, arquitetura, credenciais e próximos passos do projeto Hermes — um sistema de automação de LinkedIn com agente autônomo, dashboard pessoal e integração com Claude Code.

O dono do projeto é Caio Leão (@Hapuxul no Telegram), localizado em Cuiabá, MT, Brasil.

---

## Infraestrutura Atual (já configurada)

### Google Cloud VM
- **Nome:** hermes-vm
- **Tipo:** e2-standard-4 (4 vCPU, 16 GB RAM)
- **SO:** Ubuntu 24.04 LTS (x86/64)
- **Disco:** 30 GB SSD (precisa expandir para 100 GB)
- **IP estático:** 136.115.74.69
- **Região:** us-central1-a (Iowa)
- **Custo:** ~$100.84/mês (coberto pelo trial de R$1.703 / $300 por 90 dias)
- **SSH user:** hermes-gcp
- **SSH key:** ed25519 em C:\Users\cleao\.ssh\id_ed25519
- **Conexão:** `ssh -i $env:USERPROFILE\.ssh\id_ed25519 hermes-gcp@136.115.74.69`

### Software instalado na VM
- Docker 29.5.2
- Ollama com Qwen3 14B (9.3 GB, ~5-8 tok/s em CPU)
- Node.js 22.22.2
- tmux 3.4
- Python 3.11.15 (via uv)
- Hermes Agent v0.14.0 em ~/.hermes/hermes-agent/
- Playwright + Chromium (instalado anteriormente, pode ser reaproveitado)
- ripgrep, ffmpeg

### Hermes Agent — Configuração
- **Versão:** v0.14.0 (2026.5.16)
- **Provider ativo:** OpenRouter
- **Modelo ativo:** nvidia/nemotron-3-super-120b-a12b:free
- **Gateway Telegram:** rodando via systemd (user service com linger)
- **Config:** ~/.hermes/config.yaml
- **Env:** ~/.hermes/.env
- **Skills:** ~/.hermes/skills/
- **85 skills ativas** out-of-the-box

### Credenciais
- **OpenRouter API Key:** (ver `.env` — variável `OPENROUTER_API_KEY`)
- **Telegram Bot Token:** (ver `.env` — variável `TELEGRAM_BOT_TOKEN`)
- **Telegram Chat ID (Caio):** (ver `.env` — variável `TELEGRAM_CHAT_ID`)
- **LinkedIn Cookie (li_at):** (renovar periodicamente, armazenar em `.env` ou session file)

### Computador Local (Caio)
- **SO:** Windows
- **User:** cleao (C:\Users\cleao)
- **Claude Code:** disponível (assinatura ativa)
- **Computador fica ligado:** sim, pode rodar scripts em background

---

## Arquitetura do Sistema

### Três camadas

```
CAMADA 1 — SEU COMPUTADOR (Dashboard + Claude Code)
├── Dashboard web local (React) → interface visual
├── Claude Code → criação, análise, polimento de conteúdo
├── Script Python bridge → Telegram ↔ Claude Code (sem API)
└── Acesso via celular: Cloudflare Tunnel (grátis) ou Remote Control

CAMADA 2 — HERMES NA VM (Execução 24/7)
├── Hermes Agent v0.14.0 → agente autônomo com auto-aprendizado
├── OpenRouter (modelos gratuitos) → inteligência cloud
├── Ollama local (Qwen3 14B, 8B) → fallback e decisões rápidas
├── Playwright + Chromium → automação LinkedIn
├── Cron scheduler → rotinas agendadas
├── Telegram gateway → comunicação com o Caio
├── Skills system → auto-criação e melhoria
├── Memory system → conhecimento persistente
└── API Bridge (FastAPI) → serve dados para o Dashboard

CAMADA 3 — OUTPUTS
├── LinkedIn → posts, conexões, prospecção
├── Telegram → aprovações, alertas, relatórios
└── SQLite → histórico, resultados, métricas
```

### Fluxo de comunicação

```
Dashboard (PC) ←→ API Bridge (VM) ←→ Hermes Agent (VM)
                                        ↕
Claude Code (PC) ←→ SSH ←→ VM filesystem (/pendente/, /aprovado/)
                                        ↕
Telegram (celular) ←→ Hermes Gateway (VM)
                                        ↕
                                    LinkedIn
```

---

## TAREFA 1: Rotação de Modelos

### Estratégia definida

O Hermes deve usar diferentes modelos para diferentes tipos de tarefa:

| Tipo de tarefa | Modelo | Provider | Motivo |
|---|---|---|---|
| Posts LinkedIn, mensagens personalizadas | deepseek/deepseek-v4-flash:free | OpenRouter | Melhor qualidade escrita, 1M contexto |
| Comentários, resumos rápidos | minimax/minimax-m2.5:free | OpenRouter | Libera quota do DeepSeek |
| Análise de imagens/screenshots | google/gemma-4-31b-it:free | OpenRouter | Único gratuito com vision |
| Classificação de perfis, sim/não | qwen3:8b | Ollama local | Ilimitado, rápido para decisões |
| Fallback geral | qwen3:14b | Ollama local | Quando limites cloud forem atingidos |
| Modelo padrão para chat | nvidia/nemotron-3-super-120b-a12b:free | OpenRouter | Atualmente ativo, bom equilíbrio |

### Limites gratuitos OpenRouter
- 20 requisições/minuto por modelo
- 200 requisições/dia por modelo
- Com rotação entre 3 modelos = ~600 req/dia efetivas

### O que precisa ser implementado
- Baixar qwen3:8b no Ollama (`ollama pull qwen3:8b`)
- Configurar auxiliary models no Hermes
- Criar skills que especifiquem qual modelo usar por tipo de tarefa

---

## TAREFA 2: Skills de LinkedIn

### Skills que precisam ser criadas

1. **linkedin-post-generator** — Gera posts profissionais em português brasileiro
   - Input: tema, tom desejado, público-alvo
   - Output: post formatado com emojis moderados e 3 hashtags
   - Modelo: deepseek-v4-flash:free

2. **linkedin-profile-researcher** — Pesquisa e analisa perfis de targets
   - Input: filtros (cargo, empresa, localização, setor)
   - Output: lista de perfis com score de relevância
   - Modelo: qwen3:8b (local, para volume)
   - Usa Playwright para navegar no LinkedIn

3. **linkedin-connection-sender** — Envia convites de conexão personalizados
   - Input: perfil da pessoa + contexto
   - Output: mensagem personalizada + envio automático
   - Modelo: deepseek-v4-flash:free (para personalização)
   - Limites: máx 20-30 convites/dia

4. **linkedin-engagement** — Curte e comenta posts de targets
   - Input: lista de targets prioritários
   - Output: ações executadas + relatório
   - Modelo: minimax-m2.5:free (para comentários)

5. **linkedin-trend-monitor** — Monitora tendências do setor
   - Input: palavras-chave, setor
   - Output: resumo de tendências + sugestões de posts
   - Modelo: deepseek-v4-flash:free

6. **weekly-mission-planner** — Configura missões semanais
   - Input: tema da semana + objetivos
   - Output: plano de ações distribuído nos 7 dias
   - Modelo: nemotron (padrão)

### Segurança no LinkedIn
- Máximo 20-30 convites por dia
- Intervalos humanos entre ações (30s a 2min aleatório)
- Sem padrões repetitivos
- Cookie li_at precisa ser renovado periodicamente (~30-60 dias)
- Começar em modo laboratório (sem ações reais) antes de produção

---

## TAREFA 3: Expandir Disco da VM

### Situação atual
- 30 GB total, 18 GB usados, 11 GB livres (64%)
- Qwen3 14B ocupa 9.3 GB
- Hermes + dependências ocupam ~5 GB

### Ação necessária
- Expandir disco para 100 GB pelo Google Cloud Console
- Passos: Compute Engine → Discos → hermes-vm → Editar → 100 GB → Salvar
- Na VM depois: `sudo growpart /dev/sda 2 && sudo resize2fs /dev/sda2` (ou equivalente)
- Custo adicional: ~$7/mês (coberto pelo trial)

### Benefício
- Espaço para mais modelos Ollama (Qwen3 8B, Phi-4-mini)
- Espaço para banco de dados, logs, cache do Playwright
- Margem confortável para operação contínua

---

## TAREFA 4: Dashboard (Interface Visual)

### Conceito
App React que roda local no browser do Caio, conecta na VM via API Bridge (FastAPI).
Acessível do celular via Cloudflare Tunnel (grátis).

### Módulos do Dashboard

1. **Painel de Atividade** — Timeline de tudo que o Hermes fez
   - Posts publicados, perfis visitados, conexões enviadas, skills criadas
   - Atualização em tempo real via WebSocket

2. **Painel de Conteúdo** — Gestão de posts
   - Rascunhos pendentes para revisão
   - Editor inline para ajustes
   - Botões: aprovar, editar, rejeitar, regenerar
   - Agenda de publicação (calendário visual)

3. **Painel de Prospecção** — Gestão de targets
   - Cards com foto, cargo, empresa, score
   - Filtros visuais por setor, cargo, localização
   - Ações: conectar, ignorar, salvar
   - Histórico de interações

4. **Painel de Missões** — Planejamento semanal
   - Calendário semanal com drag & drop
   - Templates de missão (recrutadores, marketing, C-level)
   - Cada missão configura: filtros de busca + volume + modelo a usar

5. **Painel de Skills** — Visualização das skills do Hermes
   - Lista com nome, descrição, vezes usada, última melhoria
   - Ativar/desativar skills
   - Ver histórico de auto-melhorias

6. **Painel de Memória** — O que o Hermes aprendeu
   - Sobre o Caio, sobre targets, sobre o mercado
   - Editar, corrigir, limpar

7. **Chat Claude Code** — Campo de texto que executa claude -p no PC
   - Para trabalho criativo que precisa do Claude
   - Respostas formatadas em HTML

### Stack técnica do Dashboard
- **Frontend:** React + Tailwind + shadcn/ui
- **Backend (API Bridge):** FastAPI (Python) rodando na VM
- **Comunicação:** REST + WebSocket
- **Autenticação:** Token simples (JWT ou API key)
- **Acesso mobile:** Cloudflare Tunnel (grátis, HTTPS automático)

### API Bridge — Endpoints necessários

```
GET  /api/activity          — Timeline de atividades
GET  /api/content/pending   — Posts pendentes
POST /api/content/approve   — Aprovar post
POST /api/content/reject    — Rejeitar post
GET  /api/prospects          — Lista de perfis encontrados
POST /api/prospects/connect  — Aprovar conexão
GET  /api/missions           — Missões configuradas
POST /api/missions           — Criar nova missão
GET  /api/skills             — Lista de skills
POST /api/skills/toggle      — Ativar/desativar skill
GET  /api/memory             — Memórias do Hermes
GET  /api/hermes/status      — Status do agente
POST /api/hermes/command     — Enviar comando ao Hermes
WS   /api/ws                — WebSocket para atualizações em tempo real
```

---

## TAREFA 5: Sistema Claude Code via Telegram (PC ligado)

### Arquitetura
Script Python no PC do Caio que:
1. Escuta mensagens no Telegram (bot secundário ou mesmo bot)
2. Executa `claude -p "mensagem"` no terminal
3. Captura o output
4. Envia de volta no Telegram formatado em Markdown

### Limitações
- PC precisa estar ligado
- Respostas do Claude são texto (sem imagens/diagramas)
- Mensagens longas (>4096 chars) precisam ser quebradas
- Não é em tempo real — Claude Code pode levar 10-60 segundos

### Alternativa para mobile
- Dashboard web via Cloudflare Tunnel (melhor experiência)
- Claude Code Remote Control (acesso pelo browser do celular)

---

## Ordem de Execução Sugerida

### Fase 1 — Infraestrutura (fazer agora)
1. Expandir disco para 100 GB
2. Baixar qwen3:8b no Ollama
3. Configurar rotação de modelos no Hermes

### Fase 2 — Skills de LinkedIn (fazer agora)
1. Criar skill de geração de posts
2. Criar skill de pesquisa de perfis (modo laboratório)
3. Criar skill de missão semanal
4. Testar tudo via Telegram

### Fase 3 — API Bridge (Claude Code constrói)
1. FastAPI na VM com endpoints básicos
2. Autenticação com token
3. Lê dados do Hermes (skills, memória, logs)
4. WebSocket para updates em tempo real

### Fase 4 — Dashboard (Claude Code constrói)
1. React app no PC do Caio
2. Conecta na API Bridge
3. Painel de atividade primeiro (mais simples)
4. Depois: conteúdo, prospecção, missões

### Fase 5 — Integração completa
1. Cloudflare Tunnel para acesso mobile
2. Sistema Claude Code via Telegram
3. Refinamento contínuo

---

## Como usar este documento no Claude Code

Abra o Claude Code e diga:

```
Leia o arquivo HERMES-PROJECT-CONTEXT.md que está nesta pasta.
Ele contém toda a arquitetura e decisões do meu projeto Hermes.
Conecte via SSH na VM hermes-gcp@136.115.74.69 e comece pela
Fase 1: expandir o disco, baixar qwen3:8b, e configurar a
rotação de modelos.
```

O Claude Code terá todo o contexto necessário para executar qualquer fase do projeto.
