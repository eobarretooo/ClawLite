# ⚡ Início Rápido

Fluxo mínimo para subir o ClawLite localmente.

## 1) Instalação

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

## 2) Gerar workspace inicial

```bash
clawlite onboard
```

## 3) Configurar provider

```bash
export CLAWLITE_MODEL="gemini/gemini-2.5-flash"
export CLAWLITE_LITELLM_API_KEY="<sua-chave>"
```

## 4) Iniciar gateway

```bash
clawlite start --host 127.0.0.1 --port 8787
```

## 5) Testar chat

```bash
curl -sS http://127.0.0.1:8787/v1/chat \
  -H 'content-type: application/json' \
  -d '{"session_id":"cli:quickstart","text":"quem voce e?"}'
```

➡️ Próxima página: [Comandos CLI](/comandos-cli)
