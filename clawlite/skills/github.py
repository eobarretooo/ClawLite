"""Skill GitHub — automação de repos, issues, PRs e CI via `gh` CLI.

Usa o GitHub CLI (`gh`) já autenticado para interagir com repositórios.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

SKILL_NAME = "github"
SKILL_DESCRIPTION = "Automação de issues, PRs e repositórios via gh CLI"


def _gh_available() -> bool:
    """Verifica se o gh CLI está instalado."""
    return shutil.which("gh") is not None


def _run_gh(*args: str, timeout: int = 30) -> dict[str, Any]:
    """Executa um comando gh e retorna resultado estruturado."""
    if not _gh_available():
        return {"error": "gh CLI não está instalado. Instale em https://cli.github.com/"}

    cmd = ["gh"] + list(args)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            return {"error": proc.stderr.strip() or f"gh retornou código {proc.returncode}"}
        output = proc.stdout.strip()
        # Tenta parsear JSON
        try:
            return {"data": json.loads(output)}
        except (json.JSONDecodeError, ValueError):
            return {"data": output}
    except subprocess.TimeoutExpired:
        return {"error": f"Timeout ({timeout}s) ao executar: {' '.join(cmd)}"}
    except Exception as exc:
        return {"error": str(exc)}


def gh_repos(limit: int = 30) -> list[dict] | str:
    """Lista repositórios do usuário autenticado.

    Args:
        limit: Número máximo de repos para listar.
    """
    result = _run_gh("repo", "list", "--json", "name,description,visibility,updatedAt", "--limit", str(limit))
    if "error" in result:
        return result["error"]
    return result["data"] if isinstance(result["data"], list) else result["data"]


def gh_issues(repo: str, state: str = "open", limit: int = 30) -> list[dict] | str:
    """Lista issues de um repositório.

    Args:
        repo: Repositório no formato owner/repo.
        state: Estado das issues (open, closed, all).
        limit: Número máximo de issues.
    """
    result = _run_gh("issue", "list", "--repo", repo, "--state", state,
                     "--json", "number,title,state,author,labels,createdAt", "--limit", str(limit))
    if "error" in result:
        return result["error"]
    return result["data"] if isinstance(result["data"], list) else result["data"]


def gh_create_issue(repo: str, title: str, body: str = "") -> dict | str:
    """Cria uma issue em um repositório.

    Args:
        repo: Repositório no formato owner/repo.
        title: Título da issue.
        body: Corpo/descrição da issue.
    """
    if not title:
        return "Título da issue não pode ser vazio."
    args = ["issue", "create", "--repo", repo, "--title", title]
    if body:
        args.extend(["--body", body])
    result = _run_gh(*args)
    if "error" in result:
        return result["error"]
    return result["data"]


def gh_create_pr(repo: str, title: str, body: str = "", branch: str = "", base: str = "main") -> dict | str:
    """Cria um Pull Request.

    Args:
        repo: Repositório no formato owner/repo.
        title: Título do PR.
        body: Descrição do PR.
        branch: Branch de origem (head). Se vazio, usa a branch atual.
        base: Branch de destino (padrão: main).
    """
    if not title:
        return "Título do PR não pode ser vazio."
    args = ["pr", "create", "--repo", repo, "--title", title, "--base", base]
    if body:
        args.extend(["--body", body])
    if branch:
        args.extend(["--head", branch])
    result = _run_gh(*args)
    if "error" in result:
        return result["error"]
    return result["data"]


def gh_ci_status(repo: str, limit: int = 10) -> list[dict] | str:
    """Verifica status de CI/CD (workflow runs) de um repositório.

    Args:
        repo: Repositório no formato owner/repo.
        limit: Número máximo de runs.
    """
    result = _run_gh("run", "list", "--repo", repo,
                     "--json", "databaseId,displayTitle,status,conclusion,headBranch,createdAt",
                     "--limit", str(limit))
    if "error" in result:
        return result["error"]
    return result["data"] if isinstance(result["data"], list) else result["data"]


def run(command: str = "") -> str:
    """Ponto de entrada compatível com o registry do ClawLite."""
    if not command:
        if not _gh_available():
            return "❌ gh CLI não encontrado. Instale em https://cli.github.com/"
        return f"✅ {SKILL_NAME} pronta. Use: repos, issues <repo>, create-issue <repo> <title>, create-pr <repo> <title>, ci <repo>"

    parts = command.strip().split(None, 2)
    cmd = parts[0].lower()
    arg1 = parts[1] if len(parts) > 1 else ""
    arg2 = parts[2] if len(parts) > 2 else ""

    if cmd == "repos":
        data = gh_repos()
        if isinstance(data, str):
            return data
        lines = [f"- {r['name']} ({r.get('visibility','?')}) — {r.get('description','')}" for r in data]
        return "Repositórios:\n" + "\n".join(lines) if lines else "Nenhum repositório encontrado."

    elif cmd == "issues":
        if not arg1:
            return "Uso: issues <owner/repo>"
        data = gh_issues(arg1)
        if isinstance(data, str):
            return data
        if not data:
            return "Nenhuma issue aberta."
        lines = [f"#{i['number']} {i['title']} [{i['state']}]" for i in data]
        return "\n".join(lines)

    elif cmd == "create-issue":
        if not arg1:
            return "Uso: create-issue <owner/repo> <título>"
        return str(gh_create_issue(arg1, arg2 or "Nova issue"))

    elif cmd == "create-pr":
        if not arg1:
            return "Uso: create-pr <owner/repo> <título>"
        return str(gh_create_pr(arg1, arg2 or "Novo PR"))

    elif cmd in ("ci", "ci-status"):
        if not arg1:
            return "Uso: ci <owner/repo>"
        data = gh_ci_status(arg1)
        if isinstance(data, str):
            return data
        if not data:
            return "Nenhum workflow run encontrado."
        lines = [f"#{r['databaseId']} {r['displayTitle']} — {r['status']}/{r.get('conclusion','?')} ({r['headBranch']})" for r in data]
        return "\n".join(lines)

    else:
        # Fallback: executa comando gh direto
        proc = subprocess.run(command, shell=True, text=True, capture_output=True)
        if proc.returncode != 0:
            return proc.stderr.strip() or "Erro ao executar comando gh."
        return proc.stdout.strip()


def info() -> str:
    """Retorna informações da skill para o agente."""
    return (
        "# GitHub Skill\n"
        "Use `gh` CLI para interagir com GitHub.\n"
        "## Comandos: repos, issues <repo>, create-issue <repo> <title>, create-pr <repo> <title>, ci <repo>\n"
        "## Funções: gh_repos(), gh_issues(repo), gh_create_issue(repo, title, body), gh_create_pr(repo, title, body, branch), gh_ci_status(repo)"
    )
