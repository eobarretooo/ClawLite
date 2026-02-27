#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
from pathlib import Path


def run_git(args: list[str], repo_root: Path, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} falhou: {proc.stderr.strip()}")
    return (proc.stdout or "").strip()


def get_default_branch(repo_root: Path) -> str:
    branch = run_git(["symbolic-ref", "--short", "HEAD"], repo_root, check=False)
    return branch or "main"


def get_openclaw_head(upstream_url: str) -> str:
    proc = subprocess.run(
        ["git", "ls-remote", upstream_url, "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return f"ERRO: {proc.stderr.strip() or 'falha ao consultar remoto'}"
    return (proc.stdout.strip().split("\t")[0] if proc.stdout.strip() else "desconhecido")


def build_report(repo_root: Path, upstream_url: str, days: int) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    branch = get_default_branch(repo_root)
    local_head = run_git(["rev-parse", "HEAD"], repo_root)
    status = run_git(["status", "--short"], repo_root, check=False) or "(limpo)"
    shortlog = run_git(
        [
            "log",
            f"--since={days}.days",
            "--pretty=format:- %h %ad %s (%an)",
            "--date=short",
            "--",
            ".",
        ],
        repo_root,
        check=False,
    ) or "- Nenhum commit local no período."
    openclaw_head = get_openclaw_head(upstream_url)

    return "\n".join(
        [
            "# SYNC_REPORT",
            "",
            f"- Gerado em (UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- Branch local: `{branch}`",
            f"- HEAD local: `{local_head}`",
            f"- OpenClaw upstream: `{upstream_url}`",
            f"- HEAD upstream (remoto): `{openclaw_head}`",
            "",
            "## Resumo",
            "",
            "Este relatório automatiza a fotografia semanal de sincronização entre o estado atual do ClawLite e a referência upstream do OpenClaw.",
            "",
            "## Alterações locais recentes",
            "",
            shortlog,
            "",
            "## Estado do working tree",
            "",
            "```text",
            status,
            "```",
            "",
            "## Próximos passos sugeridos",
            "",
            "- Revisar divergências de arquitetura e roadmap com base no HEAD upstream.",
            "- Priorizar backports/ajustes com maior impacto para paridade funcional.",
            "- Atualizar este relatório automaticamente toda semana (workflow agendado).",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera SYNC_REPORT.md com status semanal de sync")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Raiz do repositório ClawLite",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("SYNC_REPORT.md"),
        help="Caminho de saída do relatório",
    )
    parser.add_argument(
        "--upstream-url",
        default="https://github.com/openclaw/openclaw.git",
        help="Repositório upstream OpenClaw",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Janela de dias para o resumo de commits locais",
    )
    parser.add_argument("--dry-run", action="store_true", help="Não grava arquivo, só imprime preview")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output = args.output if args.output.is_absolute() else (repo_root / args.output)

    report = build_report(repo_root=repo_root, upstream_url=args.upstream_url, days=max(1, args.days))

    if args.dry_run:
        print(report)
        return

    output.write_text(report + "\n", encoding="utf-8")
    print(f"Relatório atualizado em: {output}")


if __name__ == "__main__":
    main()
