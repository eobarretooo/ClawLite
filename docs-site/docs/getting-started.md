# Começando em 1 minuto

## Instalação (1 comando)

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

## 1) Diagnóstico inicial

```bash
clawlite doctor
```

## 2) Onboarding wizard (primeira execução)

```bash
clawlite onboarding
```

No onboarding você já configura tudo de forma guiada:
- modelo
- canais (Telegram/WhatsApp/Discord)
- skills
- gateway
- segurança
- voz por canal (STT/TTS)

## 3) Configure estilo OpenClaw (ajustes finos)

```bash
clawlite configure
```

## 4) Runtime local: status + start

```bash
clawlite status
clawlite start --host 0.0.0.0 --port 8787
```

> `clawlite start` e `clawlite gateway` sobem o servidor gateway local.

## 5) Primeira tarefa

```bash
clawlite run "Resuma a pasta atual"
```

## Extras úteis

```bash
# aprendizado local
clawlite stats --period week

# integração Reddit
clawlite reddit status
```
