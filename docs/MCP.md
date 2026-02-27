# MCP no ClawLite (PT-BR)

Este guia resume o suporte MCP (Model Context Protocol) no ClawLite.

## 1) Cliente MCP (config local)

Arquivo de configuração:

- `~/.clawlite/mcp.json`

Formato:

```json
{
  "servers": {
    "filesystem": "npx -y @modelcontextprotocol/server-filesystem ~/",
    "github": "npx -y @modelcontextprotocol/server-github"
  }
}
```

Comandos CLI:

```bash
clawlite mcp add <nome> <url-ou-comando>
clawlite mcp list
clawlite mcp remove <nome>
```

Validações implementadas:

- `nome`: minúsculo, números e `.-_`
- `url/comando`: aceita `http(s)`, `ws(s)` e comandos iniciando com `npx`, `uvx`, `python`, `node`
- persistência robusta: cria `~/.clawlite/mcp.json` automaticamente quando necessário

## 2) Server MCP no Gateway

Endpoint MCP JSON-RPC:

- `POST /mcp` (mesma porta do gateway)

Autenticação:

- Bearer token igual ao dashboard/gateway

Métodos MCP suportados:

- `initialize`
- `notifications/initialized`
- `ping`
- `tools/list`
- `tools/call`

As tools retornadas em `tools/list` são baseadas no registry de skills do ClawLite (`skill.<slug>`).

## 3) Skills via MCP

Cada skill vira uma tool MCP com:

- `name`: `skill.<slug>`
- `description`: descrição do registry
- `inputSchema`: objeto JSON com `command`/`prompt`

Execução via MCP:

- método: `tools/call`
- parâmetro: `name="skill.<slug>"`
- argumentos: `{"command": "..."}`

Erros retornam mensagens em PT-BR (JSON-RPC error).

## 4) Marketplace MCP

Integração com catálogo oficial:

- Fonte: `https://github.com/modelcontextprotocol/servers` (README oficial)

Comandos:

```bash
clawlite mcp search [query]
clawlite mcp install filesystem
clawlite mcp install github
```

`install` inicial registra templates conhecidos no `mcp.json` (sem instalar binários automaticamente).

## 5) Dashboard MCP

No `dashboard.html`, seção **MCP** permite:

- listar servidores configurados e status simples
- adicionar/remover servidores
- buscar catálogo MCP
- instalação rápida de templates `filesystem` e `github`

A UI consome endpoints REST abaixo.

## 6) API REST de suporte

Todos exigem Bearer token:

- `GET /api/mcp/config`
- `GET /api/mcp/list`
- `POST /api/mcp/add`
- `POST /api/mcp/remove`
- `GET /api/mcp/search?q=...`
- `POST /api/mcp/install`
- `GET /api/mcp/status`

## 7) Teste rápido manual

1. Subir gateway:

```bash
clawlite start --port 8787
```

2. Configurar via CLI:

```bash
clawlite mcp add local https://example.com/mcp
clawlite mcp list
```

3. Testar handshake MCP (ajuste TOKEN):

```bash
curl -s -X POST http://127.0.0.1:8787/mcp \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
```

4. Abrir dashboard e usar seção MCP.
