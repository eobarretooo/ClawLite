
# ClawLite ✨

<!-- Um assistente autônomo portátil e runtime-first para Linux. -->

ClawLite é um **assistente autônomo portátil e runtime-first** projetado para Linux, focado em operações via CLI e gateway. Ele oferece um ambiente robusto para agentes inteligentes, com um conjunto de funcionalidades que incluem roteamento de inferência multi-provedor, um subsistema de memória avançado e serviços de agendamento.

---

## 🚀 Visão Geral

ClawLite é o coração de um sistema de agente Python, centrado na operação via linha de comando (CLI) e um gateway eficiente. Ele não depende de uma interface de usuário gráfica (dashboard), servindo um ponto de entrada HTML estático mínimo para visibilidade dos endpoints. Sua arquitetura modular e extensível permite a criação de agentes autônomos com capacidades de memória, agendamento e interação com diversos canais.

### Principais Funcionalidades:

*   **Gateway FastAPI**: Oferece endpoints `/v1/*` e aliases de compatibilidade `/api/*` para interação flexível.
*   **Pontos de Entrada de Chat**: Suporte a WebSocket e HTTP para comunicação de chat.
*   **Serviços de Agendamento**: Inclui cron, heartbeat e supervisão para automação e monitoramento.
*   **Roteamento de Inferência Multi-provedor**: Gerencia o roteamento e o ciclo de vida de autenticação de provedores de inferência.
*   **Subsistema de Memória Avançado**: Diagnósticos, versionamento, ramificação e ajuste de qualidade para uma memória de agente inteligente.

---

## 🛠️ Tecnologias Utilizadas

*   **Python 3.10+**: Linguagem de programação principal.
*   **FastAPI**: Framework web para o gateway de alta performance.
*   **WebSocket**: Para comunicação de chat em tempo real.
*   **CLI (Command Line Interface)**: Para interação e controle do agente.
*   **Litellm**: Para roteamento de inferência multi-provedor.

---

## 🏗️ Arquitetura

A arquitetura do ClawLite é modular e bem definida, com os seguintes componentes principais:

```text
clawlite/
├── core/         # engine, prompt, memory, skills, subagent
├── tools/        # tool abc, registry, and built-in tools
├── bus/          # events and async queue
├── channels/     # manager + channels (full telegram, other adapters)
├── gateway/      # FastAPI + WebSocket
├── scheduler/    # cron + heartbeat
├── providers/    # litellm/custom/codex/transcription
├── session/      # JSONL store per session
├── config/       # schema + loader
├── workspace/    # loader + identity templates
├── skills/       # built-in markdown skills (SKILL.md)
├── cli/          # start/run/onboard/cron commands
└── utils/        # shared helpers
```

**Fluxo Principal:**

1.  A mensagem entra via `channels` ou `gateway`.
2.  `core.engine` constrói o prompt (workspace + memória + histórico + skills).
3.  O provedor responde; se houver chamadas de ferramentas, `tools.registry` as executa.
4.  A resposta final é entregue primeiro; a persistência (`session.store` append + `core.memory` consolidate) é executada em modo de melhor esforço e registra falhas de armazenamento degradadas sem abortar a execução.
5.  `scheduler.cron` e `scheduler.heartbeat` acionam execuções proativas.

---

## ⚡ Quickstart

**Pré-requisito:** Python 3.10+

Siga os passos abaixo para colocar o ClawLite em funcionamento rapidamente:

1.  **Instalar localmente:**

    ```bash
    pip install -e .
    ```

2.  **Gerar templates de workspace / baseline de onboarding:**

    ```bash
    clawlite onboard
    # variante interativa:
    clawlite onboard --wizard
    ```

3.  **Configurar provedor (exemplo):**

    ```bash
    export CLAWLITE_MODEL="gemini/gemini-2.5-flash"
    export CLAWLITE_LITELLM_API_KEY="<sua-chave>"
    ```

4.  **Iniciar o gateway:**

    ```bash
    clawlite start --host 127.0.0.1 --port 8787
    # alias:
    clawlite gateway --host 127.0.0.1 --port 8787
    ```

5.  **Enviar uma requisição de chat:**

    ```bash
    curl -sS http://127.0.0.1:8787/v1/chat \
      -H 'content-type: application/json' \
      -d '{"session_id":"cli:quickstart","text":"hello"}'
    ```

    *Se o modo de autenticação for necessário, inclua o token do portador (cabeçalho ou parâmetro de consulta, conforme a configuração).* 

---

## ⚙️ Comandos CLI Essenciais

### Provedor e Validação:

```bash
clawlite provider status
clawlite provider use openai --model openai/gpt-4.1-mini
clawlite provider set-auth openai --api-key "<key>"
clawlite validate provider
clawlite validate config
clawlite validate preflight --gateway-url http://127.0.0.1:8787
```

### Diagnósticos, Memória, Agendador e Skills:

```bash
clawlite diagnostics --gateway-url http://127.0.0.1:8787
clawlite memory
clawlite memory doctor
clawlite memory quality --gateway-url http://127.0.0.1:8787
clawlite cron add --session-id cli:ops --expression "every 300" --prompt "status"
clawlite heartbeat trigger --gateway-url http://127.0.0.1:8787
clawlite skills list
clawlite skills check
```

---

## 🌐 Endpoints do Gateway (v1 + Aliases de Compatibilidade)

| Método | Endpoint | Notas |
|---|---|---|
| `GET` | `/` | Ponto de entrada mínimo estático do gateway (sem dependência de dashboard) |
| `GET` | `/health` | Snapshot de saúde/prontidão |
| `GET` | `/v1/status` | Status do plano de controle |
| `GET` | `/api/status` | Alias de `/v1/status` |
| `GET` | `/v1/diagnostics` | Snapshot de diagnósticos de runtime |
| `GET` | `/api/diagnostics` | Alias de `/v1/diagnostics` |
| `POST` | `/v1/chat` | Endpoint principal de chat HTTP |
| `POST` | `/api/message` | Alias de `/v1/chat` |
| `GET` | `/api/token` | Diagnósticos de token mascarado |
| `POST` | `/v1/control/heartbeat/trigger` | Aciona o ciclo de heartbeat |
| `POST` | `/v1/cron/add` | Cria um trabalho cron |
| `GET` | `/v1/cron/list` | Lista trabalhos cron por sessão |
| `DELETE` | `/v1/cron/{job_id}` | Remove um trabalho cron |
| `WS` | `/v1/ws` | Chat principal WebSocket |
| `WS` | `/ws` | Alias de `/v1/ws` |

---

## 🧠 Destaques de Memória e Autonomia

*   A recuperação de memória híbrida e o rastreamento de qualidade são integrados aos diagnósticos de runtime e operações CLI.
*   O estado de qualidade da memória persiste a pontuação, avaliação de desvio, recomendações e histórico de ajuste.
*   O loop de ajuste é executado como um componente autônomo de runtime quando habilitado, com comportamento fail-soft, cooldown e limitação de taxa.
*   Playbooks cientes da camada escolhem ações com base na gravidade do desvio e na camada de raciocínio mais fraca.
*   Detalhes de execução específicos da camada são persistidos para auditabilidade (`template_id`, `backfill_limit`, `snapshot_tag`, `action_variant`) juntamente com os campos do playbook.
*   Os diagnósticos expõem mapas de telemetria de ajuste e o contexto da última ação (`actions_by_layer`, `actions_by_playbook`, `actions_by_action`, `action_status_by_layer`, `last_action_metadata`).

---

## 💡 Skills (Habilidades)

ClawLite utiliza **skills em Markdown (`SKILL.md`)** com descoberta automática. As skills são carregadas de fontes como `builtin` (repositório), `user workspace` e `marketplace local`, com uma política de resolução determinística para duplicatas.

### Skills Built-in Atuais:

*   `cron`
*   `memory`
*   `github`
*   `summarize`
*   `skill-creator`
*   `web-search`
*   `weather`
*   `tmux`
*   `hub`
*   `clawhub`

---

## 🧪 Testes e CI

### Verificações Locais:

```bash
pytest -q tests
truff check clawlite/ --select E9,F --ignore F401,F811
bash scripts/smoke_test.sh
clawlite validate preflight --gateway-url http://127.0.0.1:8787
```

### Workflows de CI (`.github/workflows/`):

*   `ci.yml` (matriz pytest, lint, smoke, contrato de autonomia)
*   `coverage.yml` (pytest + cobertura XML)
*   `secret-scan.yml` (gitleaks)

---

## 🤝 Contribuição

Contribuições são **muito bem-vindas**! Para contribuir com o ClawLite, por favor, siga as diretrizes em [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 📝 Licença

Este projeto é distribuído sob a licença [MIT License](LICENSE). Veja o arquivo `LICENSE` para mais detalhes.

---

## 👤 Autores

*   **eobarretooo** - *Desenvolvimento Inicial* - [GitHub](https://github.com/eobarretooo)

---

## 🌟 Agradecimentos

*   A todos os contribuidores e mantenedores do projeto [awesome-readme](https://github.com/matiassingers/awesome-readme) pela inspiração e melhores práticas.
*   À comunidade de código aberto por suas ferramentas e bibliotecas incríveis.
