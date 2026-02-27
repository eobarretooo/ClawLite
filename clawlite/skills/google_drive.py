"""Skill Google Drive — gerenciamento de arquivos no Google Drive.

Suporta listar, buscar, upload e download de arquivos via Google Drive API v3.
Requer credenciais OAuth2 configuradas.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SKILL_NAME = "google-drive"
SKILL_DESCRIPTION = "Gerenciar arquivos no Google Drive"

# Paths de config
_CONFIG_DIR = Path(os.environ.get("CLAWLITE_CONFIG_DIR", Path.home() / ".config" / "clawlite"))
_TOKEN_FILE = _CONFIG_DIR / "gdrive_token.json"


def _load_token() -> dict[str, str] | None:
    """Carrega token OAuth2 salvo."""
    if _TOKEN_FILE.exists():
        try:
            data = json.loads(_TOKEN_FILE.read_text())
            if data.get("access_token"):
                return data
        except (json.JSONDecodeError, KeyError):
            pass
    return None


def _save_token(token_data: dict) -> None:
    """Salva token OAuth2."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _TOKEN_FILE.write_text(json.dumps(token_data, indent=2))


def _api_request(url: str, method: str = "GET", data: bytes | None = None,
                 headers: dict | None = None, timeout: int = 30) -> dict | bytes:
    """Faz requisição autenticada à API do Google Drive."""
    token = _load_token()
    if not token:
        raise PermissionError(
            "Token do Google Drive não configurado. "
            "Configure via: clawlite configure → Google Drive, ou "
            "coloque o token em ~/.config/clawlite/gdrive_token.json"
        )

    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token['access_token']}")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
            if "application/json" in content_type:
                return json.loads(raw.decode())
            return raw
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise PermissionError("Token expirado ou inválido. Reconfigure a autenticação do Google Drive.") from exc
        body = exc.read().decode() if exc.fp else ""
        raise RuntimeError(f"Erro HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Falha de conexão com Google Drive API: {exc}") from exc


def gdrive_list(query: str = "", page_size: int = 20) -> list[dict[str, Any]]:
    """Lista arquivos no Google Drive.

    Args:
        query: Query no formato da API (ex: "mimeType='application/pdf'").
               Se vazio, lista os mais recentes.
        page_size: Número máximo de resultados.
    """
    params = {
        "pageSize": str(page_size),
        "fields": "files(id,name,mimeType,size,modifiedTime,webViewLink)",
        "orderBy": "modifiedTime desc",
    }
    if query:
        params["q"] = query

    url = f"https://www.googleapis.com/drive/v3/files?{urllib.parse.urlencode(params)}"
    try:
        resp = _api_request(url)
        if isinstance(resp, dict):
            return resp.get("files", [])
        return []
    except (PermissionError, ConnectionError, RuntimeError) as exc:
        return [{"error": str(exc)}]


def gdrive_search(name: str) -> list[dict[str, Any]]:
    """Busca arquivos por nome no Google Drive.

    Args:
        name: Nome (ou parte) do arquivo para buscar.
    """
    if not name:
        return [{"error": "Nome de busca não pode ser vazio."}]
    query = f"name contains '{name}' and trashed = false"
    return gdrive_list(query=query)


def gdrive_upload(path: str, folder_id: str = "") -> dict[str, Any]:
    """Faz upload de um arquivo local para o Google Drive.

    Args:
        path: Caminho do arquivo local.
        folder_id: ID da pasta de destino (opcional, raiz se vazio).
    """
    filepath = Path(path)
    if not filepath.exists():
        return {"error": f"Arquivo não encontrado: {path}"}

    # Metadados
    metadata: dict[str, Any] = {"name": filepath.name}
    if folder_id:
        metadata["parents"] = [folder_id]

    # Upload simples (para arquivos pequenos < 5MB)
    file_size = filepath.stat().st_size
    if file_size > 5 * 1024 * 1024:
        return {"error": f"Arquivo muito grande ({file_size} bytes). Upload simples suporta até 5MB."}

    boundary = "clawlite_boundary_2026"
    body_parts = []
    body_parts.append(f"--{boundary}\r\n")
    body_parts.append("Content-Type: application/json; charset=UTF-8\r\n\r\n")
    body_parts.append(json.dumps(metadata) + "\r\n")
    body_parts.append(f"--{boundary}\r\n")
    body_parts.append("Content-Type: application/octet-stream\r\n\r\n")

    header_bytes = "".join(body_parts).encode()
    file_bytes = filepath.read_bytes()
    footer_bytes = f"\r\n--{boundary}--".encode()
    full_body = header_bytes + file_bytes + footer_bytes

    url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,webViewLink"
    try:
        resp = _api_request(url, method="POST", data=full_body,
                            headers={"Content-Type": f"multipart/related; boundary={boundary}"}, timeout=60)
        if isinstance(resp, dict):
            return resp
        return {"status": "upload concluído"}
    except (PermissionError, ConnectionError, RuntimeError) as exc:
        return {"error": str(exc)}


def gdrive_download(file_id: str, dest: str = ".") -> dict[str, Any]:
    """Faz download de um arquivo do Google Drive.

    Args:
        file_id: ID do arquivo no Drive.
        dest: Caminho de destino (diretório ou arquivo).
    """
    if not file_id:
        return {"error": "file_id não pode ser vazio."}

    # Busca metadados para pegar o nome
    try:
        meta_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?fields=name,mimeType,size"
        meta = _api_request(meta_url)
        if not isinstance(meta, dict):
            return {"error": "Resposta inesperada ao buscar metadados."}
        filename = meta.get("name", file_id)
    except (PermissionError, ConnectionError, RuntimeError) as exc:
        return {"error": str(exc)}

    # Download
    try:
        dl_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
        content = _api_request(dl_url, timeout=120)

        dest_path = Path(dest)
        if dest_path.is_dir():
            dest_path = dest_path / filename
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, bytes):
            dest_path.write_bytes(content)
        else:
            dest_path.write_text(json.dumps(content))

        return {"file": str(dest_path), "size": dest_path.stat().st_size, "name": filename}
    except (PermissionError, ConnectionError, RuntimeError) as exc:
        return {"error": str(exc)}


def run(command: str = "") -> str:
    """Ponto de entrada compatível com o registry do ClawLite."""
    if not command:
        token = _load_token()
        if token:
            return f"✅ {SKILL_NAME} configurada. Use: list, search <nome>, upload <path>, download <file_id> [dest]"
        return "⚠️ Google Drive não configurado. Configure o token OAuth em ~/.config/clawlite/gdrive_token.json"

    parts = command.strip().split(None, 2)
    cmd = parts[0].lower()
    arg1 = parts[1] if len(parts) > 1 else ""
    arg2 = parts[2] if len(parts) > 2 else ""

    if cmd == "list":
        files = gdrive_list(query=arg1)
        if files and "error" in files[0]:
            return files[0]["error"]
        if not files:
            return "Nenhum arquivo encontrado."
        lines = [f"- {f['name']} ({f.get('mimeType','?')}) — {f.get('webViewLink','')}" for f in files]
        return "Arquivos:\n" + "\n".join(lines)

    elif cmd == "search":
        if not arg1:
            return "Uso: search <nome>"
        files = gdrive_search(arg1)
        if files and "error" in files[0]:
            return files[0]["error"]
        if not files:
            return "Nenhum arquivo encontrado."
        lines = [f"- {f['name']} (id: {f['id']})" for f in files]
        return "Resultados:\n" + "\n".join(lines)

    elif cmd == "upload":
        if not arg1:
            return "Uso: upload <caminho_do_arquivo>"
        result = gdrive_upload(arg1, folder_id=arg2)
        if "error" in result:
            return f"❌ {result['error']}"
        return f"✅ Upload concluído: {result.get('name','')} (id: {result.get('id','')})"

    elif cmd == "download":
        if not arg1:
            return "Uso: download <file_id> [destino]"
        result = gdrive_download(arg1, dest=arg2 or ".")
        if "error" in result:
            return f"❌ {result['error']}"
        return f"✅ Baixado: {result['file']} ({result['size']} bytes)"

    else:
        return f"Comando desconhecido: {cmd}. Use: list, search, upload, download"
