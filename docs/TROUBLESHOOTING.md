# Troubleshooting

## 1) `IndentationError` ao carregar skills (`aws`, `ssh`, `supabase`)

**Sintoma**
- Erro de sintaxe ao importar módulos em `clawlite/skills/*.py`.

**Causa comum**
- Bloco `if` sem indentação no `return`.

**Solução**
```bash
python -m compileall -q clawlite/skills
```
- Se houver erro, ajuste a indentação e rode novamente até ficar sem saída.

## 2) `❌ Falha no comando 'agents': worker <id> não encontrado`

**Causa comum**
- O worker ainda não foi registrado no banco local.

**Solução**
```bash
clawlite agents register --channel telegram --chat-id 123 --label geral --cmd 'clawlite run "{text}"'
clawlite agents list
clawlite agents start <id>
```

## 3) `❌ Falha no comando 'cron': interval_seconds deve ser maior que 0`

**Causa comum**
- `--every-seconds` foi enviado com `0` ou valor negativo.

**Solução**
```bash
clawlite cron add --channel telegram --chat-id 123 --label geral --name heartbeat --text "ping" --every-seconds 60
```

## 4) `❌ Falha no comando 'skill': ...`

**Causa comum**
- Manifesto inválido, host de download não permitido, slug inválido ou pacote ausente.

**Solução**
- Verifique os parâmetros `--index-url`, `--allow-host`, `--manifest-path`, `--allow-file-urls`.
- Para publicação local:
```bash
clawlite skill publish ./minha-skill --version 1.0.0 --slug minha-skill
```

## 5) Mensagens de `auth` em estado não autenticado

**Sintoma**
- `clawlite auth status` exibe `não autenticado`.
- `clawlite auth logout <provider>` pode informar que já estava desconectado.

**Solução**
```bash
clawlite auth login openai
clawlite auth status
```

## 6) `battery` aplicado mas com comportamento inesperado

**Diagnóstico**
```bash
clawlite battery status
```

**Solução**
```bash
clawlite battery set --enabled true --throttle-seconds 8
```
- Use valores positivos para `--throttle-seconds`.

## 7) Dashboard/Gateway retorna erro de autorização

**Sintoma**
- `401 Missing bearer token` ou `403 Invalid token`.

**Solução**
- Use o token salvo em `~/.clawlite/config.json` (`gateway.token`).
- Envie header:
```text
Authorization: Bearer <token>
```

## 8) Provedor remoto falha por token ausente (OpenAI/Anthropic/OpenRouter)

**Sintoma**
- Erros como `token ausente para provedor remoto 'openai'`.

**Solução**
1. Defina o token por variável de ambiente (prioridade mais alta):
```bash
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export OPENROUTER_API_KEY="..."
```
2. Ou configure via `clawlite auth login <provider>` para salvar no arquivo de config.

**Observações**
- Precedência de token: variável de ambiente → token salvo na config.
- Timeout remoto pode ser ajustado com `CLAWLITE_REMOTE_TIMEOUT` (segundos).
