"""
Módulo utilitário para execução segura de subprocessos nas skills do ClawLite.

Todas as skills devem usar safe_run() em vez de subprocess.run(shell=True)
para evitar vulnerabilidades de command injection.
"""
from __future__ import annotations

import shlex
import shutil
import subprocess
from typing import Optional


def safe_run(
    args: list[str],
    *,
    timeout: int = 30,
    cwd: Optional[str] = None,
) -> str:
    """Executa um comando de forma segura (sem shell=True).

    Args:
        args: Lista de argumentos do comando (ex: ["docker", "ps", "-a"])
        timeout: Timeout em segundos (default: 30)
        cwd: Diretório de trabalho opcional

    Returns:
        stdout do comando ou mensagem de erro
    """
    if not args:
        return "Nenhum comando especificado."

    executable = args[0]
    if not shutil.which(executable):
        return f"Comando '{executable}' não encontrado. Verifique se está instalado."

    try:
        proc = subprocess.run(
            args,
            shell=False,
            text=True,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
        )
        if proc.returncode != 0:
            return proc.stderr.strip() or f"Comando falhou (código {proc.returncode})"
        return proc.stdout.strip() or "Comando executado com sucesso."
    except subprocess.TimeoutExpired:
        return f"Comando excedeu o timeout de {timeout}s."
    except OSError as exc:
        return f"Erro ao executar comando: {exc}"


def parse_command(command: str) -> list[str]:
    """Faz parse seguro de uma string de comando em lista de argumentos.

    Usa shlex.split() para tratar aspas e escapes corretamente,
    sem invocar o shell.

    Args:
        command: String do comando (ex: 'docker ps -a')

    Returns:
        Lista de argumentos parseados
    """
    try:
        return shlex.split(command)
    except ValueError as exc:
        raise ValueError(f"Comando inválido: {exc}") from exc


def require_bin(name: str) -> Optional[str]:
    """Verifica se um binário está disponível no PATH.

    Returns:
        None se encontrado, mensagem de erro se não
    """
    if not shutil.which(name):
        return f"Dependência '{name}' não encontrada. Instale antes de usar."
    return None
