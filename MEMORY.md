# ClawLite — MEMORY

## Missão
Construir um assistente open source, portátil e poderoso para Linux e Termux, com operação local/online, multi-agente e ecossistema de skills comunitárias.

## Estado atual
- CLI base funcional
- Memória local SQLite
- Tools locais iniciais (read/write/exec)
- Gateway WebSocket com token auth + dashboard + health
- Onboarding interativo inicial

## Roadmap Prioritário (aprovado)

### 🔥 Prioridade Máxima
1. **Multi-agente nativo no Telegram**
   - Objetivo: subagentes persistentes funcionando direto no Telegram (sem depender de Discord)
   - Entregáveis: runtime de agentes persistentes, roteamento por thread/chat, supervisão e recuperação.

### 💪 Poder Real
2. **Auto-update de skills**
   - Detector de novas skills + instalação segura automática (com política de trust).
3. **Modo offline (Ollama)**
   - Fallback automático para modelo local quando sem internet/API.
4. **Voz (Telegram/WhatsApp)**
   - Comandos por áudio (STT) e resposta opcional em TTS.
5. **Cron jobs por conversa**
   - Agendamento contextual por chat (ex.: lembretes diários 08:00).

### 📱 Mobile First
6. **Modo bateria**
   - Redução inteligente de polling/chamadas quando bateria baixa.
7. **Notificações inteligentes**
   - Notificar apenas eventos relevantes (prioridade, urgência, deduplicação).

### 🌍 Comunidade de Skills
8. **Hub de skills no GitHub**
   - Repositório público central para descoberta e contribuição.
9. **CLI de skills publish/install**
   - `clawlite skill publish` / `clawlite skill install`.
10. **Site de skills (estilo skills.sh)**
   - Galeria visual com busca, categorias, ratings e instalação 1 comando.
11. **Marketplace de skills (pagas/gratuitas)**
   - Monetização opcional e distribuição da comunidade.

## Ordem de implementação
P0: item 1
P1: itens 2, 3
P2: itens 5, 9
P3: itens 4, 6, 7
P4: itens 8, 10, 11

## Próximo milestone ativo
- Iniciar P0: arquitetura e MVP de multi-agente nativo no Telegram.
