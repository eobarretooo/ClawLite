# Quickstart

## 1. Instalar

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

Ou localmente:

```bash
pip install -e .
```

## 2. Onboarding (workspace)

```bash
clawlite onboard
```

Isso gera/atualiza os arquivos de identidade no workspace:
- `IDENTITY.md`
- `SOUL.md`
- `USER.md`
- `AGENTS.md`
- `TOOLS.md`

## 3. Configurar provider

Via variáveis de ambiente:

```bash
export CLAWLITE_MODEL="gemini/gemini-2.5-flash"
export CLAWLITE_LITELLM_API_KEY="<sua-chave>"
```

## 4. Subir gateway

```bash
clawlite start --host 127.0.0.1 --port 8787
```

## 5. Testar chat

```bash
curl -sS http://127.0.0.1:8787/v1/chat \
  -H 'content-type: application/json' \
  -d '{"session_id":"cli:quickstart","text":"quem voce e?"}'
```
