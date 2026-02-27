# Integração Reddit (ClawLite)

## Recursos entregues

- Post de milestone para subreddits alvo:
  - r/selfhosted
  - r/Python
  - r/AIAssistants
  - r/termux
- Monitor de menções ao ClawLite (comentários) com sugestão de resposta enviada no Telegram para aprovação.
- OAuth Reddit com persistência de `refresh_token` no `~/.clawlite/config.json`.

## Configuração OAuth (passo a passo)

1. Acesse: https://www.reddit.com/prefs/apps
2. Clique em **create app**
3. Tipo: **script**
4. Defina:
   - name: `ClawLite`
   - redirect uri: `http://127.0.0.1:8788/reddit/callback`
5. Salve e copie:
   - `client_id`
   - `client_secret`

Preencha no `~/.clawlite/config.json`:

```json
"reddit": {
  "enabled": true,
  "client_id": "...",
  "client_secret": "...",
  "redirect_uri": "http://127.0.0.1:8788/reddit/callback",
  "refresh_token": "",
  "subreddits": ["selfhosted", "Python", "AIAssistants", "termux"],
  "notify_chat_id": "1850513297"
}
```

6. Gere URL OAuth:

```bash
clawlite reddit auth-url
```

7. Abra no navegador, autorize, copie o `code` da URL de callback.

8. Troque code por token:

```bash
clawlite reddit exchange-code "SEU_CODE"
```

## Comandos

```bash
clawlite reddit status
clawlite reddit post-milestone --title "ClawLite v0.4.1" --text "..."
clawlite reddit monitor-once
```

Monitor de hora em hora:

```bash
python3 scripts/reddit_monitor_hourly.py --interval 3600
```

## Aprovação antes de responder

As menções detectadas são enviadas no Telegram com sugestão de resposta.
A resposta só deve ser publicada após aprovação do usuário.
