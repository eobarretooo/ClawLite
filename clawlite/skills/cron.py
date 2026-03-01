"""Skill Cron — agendamento de tarefas periódicas integrado ao conversation_cron runtime.

Permite criar, listar, remover e executar cron jobs programaticamente,
com integração ao sistema de notificação do ClawLite.
"""
from __future__ import annotations

import json
from typing import Any

SKILL_NAME = "cron"
SKILL_DESCRIPTION = "Agendar tarefas periódicas"

# Intervalos pré-definidos comuns (para conveniência)
INTERVAL_PRESETS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "6h": 21600,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}


def _parse_interval(expression: str) -> int:
    """Converte expressão de intervalo para segundos.

    Aceita presets ('1h', '30m', '1d') ou número direto de segundos.
    """
    normalized = expression.strip().lower()
    if normalized in INTERVAL_PRESETS:
        return INTERVAL_PRESETS[normalized]
    try:
        val = int(normalized)
        if val <= 0:
            raise ValueError
        return val
    except ValueError:
        raise ValueError(
            f"Intervalo inválido: '{expression}'. "
            f"Use presets ({', '.join(INTERVAL_PRESETS.keys())}) ou número de segundos."
        )


def cron_add(expression: str, task: str, channel: str = "telegram",
             chat_id: str = "", label: str = "default", name: str = "") -> dict[str, Any]:
    """Adiciona um cron job.

    Args:
        expression: Intervalo (ex: '1h', '30m', '1d', ou segundos).
        task: Texto/comando a executar periodicamente.
        channel: Canal de destino (padrão: telegram).
        chat_id: ID do chat de destino.
        label: Label para agrupar jobs.
        name: Nome identificador do job. Se vazio, usa os primeiros 30 chars da task.
    """
    from clawlite.runtime.conversation_cron import add_cron_job

    try:
        interval = _parse_interval(expression)
    except ValueError as exc:
        return {"error": str(exc)}

    if not task:
        return {"error": "Tarefa não pode ser vazia."}

    job_name = name or task[:30].replace("\n", " ")

    try:
        job_id = add_cron_job(
            channel=channel,
            chat_id=chat_id,
            thread_id="",
            label=label,
            name=job_name,
            text=task,
            interval_seconds=interval,
        )
        return {
            "id": job_id,
            "name": job_name,
            "interval": expression,
            "interval_seconds": interval,
            "channel": channel,
            "status": "criado",
        }
    except Exception as exc:
        return {"error": f"Falha ao criar cron job: {exc}"}


def cron_list(channel: str | None = None, label: str | None = None) -> list[dict[str, Any]]:
    """Lista cron jobs cadastrados.

    Args:
        channel: Filtrar por canal (opcional).
        label: Filtrar por label (opcional).
    """
    from clawlite.runtime.conversation_cron import list_cron_jobs

    try:
        jobs = list_cron_jobs(channel=channel, label=label)
        return [
            {
                "id": j.id,
                "name": j.name,
                "text": j.text[:100],
                "interval_seconds": j.interval_seconds,
                "channel": j.channel,
                "chat_id": j.chat_id,
                "label": j.label,
                "enabled": bool(j.enabled),
                "last_run_at": j.last_run_at,
                "next_run_at": j.next_run_at,
                "last_result": j.last_result,
            }
            for j in jobs
        ]
    except Exception as exc:
        return [{"error": f"Falha ao listar cron jobs: {exc}"}]


def cron_remove(job_id: int) -> dict[str, Any]:
    """Remove um cron job pelo ID.

    Args:
        job_id: ID do job a remover.
    """
    from clawlite.runtime.conversation_cron import remove_cron_job

    try:
        removed = remove_cron_job(int(job_id))
        if removed:
            return {"id": job_id, "status": "removido"}
        return {"error": f"Job #{job_id} não encontrado."}
    except Exception as exc:
        return {"error": f"Falha ao remover job: {exc}"}


def cron_run_now(job_id: int) -> dict[str, Any]:
    """Executa um cron job imediatamente (fora do ciclo normal).

    Args:
        job_id: ID do job a executar.
    """
    from clawlite.runtime.conversation_cron import run_cron_jobs

    try:
        results = run_cron_jobs(job_id=int(job_id))
        if not results:
            return {"error": f"Job #{job_id} não encontrado ou desabilitado."}
        r = results[0]
        return {
            "job_id": r.job_id,
            "status": r.status,
            "task_id": r.task_id,
            "message": r.message,
        }
    except Exception as exc:
        return {"error": f"Falha ao executar job: {exc}"}


def cron_status() -> dict[str, Any]:
    """Retorna status geral do sistema de cron."""
    from clawlite.runtime.conversation_cron import list_cron_jobs

    try:
        jobs = list_cron_jobs()
        enabled = [j for j in jobs if j.enabled]
        return {
            "total_jobs": len(jobs),
            "enabled_jobs": len(enabled),
            "disabled_jobs": len(jobs) - len(enabled),
            "presets_available": list(INTERVAL_PRESETS.keys()),
        }
    except Exception as exc:
        return {"error": f"Falha ao obter status: {exc}"}


def run(command: str = "") -> str:
    """Ponto de entrada compatível com o registry do ClawLite."""
    if not command:
        status = cron_status()
        if "error" in status:
            return f"❌ {status['error']}"
        return (
            f"✅ Cron: {status['total_jobs']} jobs ({status['enabled_jobs']} ativos). "
            f"Use: list, add <intervalo> <tarefa>, remove <id>, run <id>, status"
        )

    parts = command.strip().split(None, 2)
    cmd = parts[0].lower()
    arg1 = parts[1] if len(parts) > 1 else ""
    arg2 = parts[2] if len(parts) > 2 else ""

    if cmd == "status":
        return json.dumps(cron_status(), ensure_ascii=False, indent=2)

    elif cmd == "list":
        jobs = cron_list()
        if jobs and "error" in jobs[0]:
            return jobs[0]["error"]
        if not jobs:
            return "Nenhum cron job cadastrado."
        lines = []
        for j in jobs:
            status = "✅" if j["enabled"] else "⏸️"
            lines.append(f"{status} #{j['id']} {j['name']} — cada {j['interval_seconds']}s ({j['channel']})")
        return "\n".join(lines)

    elif cmd == "add":
        if not arg1 or not arg2:
            return f"Uso: add <intervalo> <tarefa>\nIntervalos: {', '.join(INTERVAL_PRESETS.keys())} ou segundos"
        result = cron_add(arg1, arg2)
        if "error" in result:
            return f"❌ {result['error']}"
        return f"✅ Job #{result['id']} criado: '{result['name']}' a cada {result['interval']}."

    elif cmd == "remove":
        if not arg1:
            return "Uso: remove <id>"
        try:
            job_id = int(arg1)
        except ValueError:
            return "❌ ID inválido. Use um número inteiro."
        result = cron_remove(job_id)
        if "error" in result:
            return f"❌ {result['error']}"
        return f"✅ Job #{result['id']} removido."

    elif cmd == "run":
        if not arg1:
            return "Uso: run <id>"
        try:
            job_id = int(arg1)
        except ValueError:
            return "❌ ID inválido. Use um número inteiro."
        result = cron_run_now(job_id)
        if "error" in result:
            return f"❌ {result['error']}"
        return f"✅ Job #{result['job_id']} executado: {result['status']} (task: {result.get('task_id', '-')})"

    else:
        return f"Comando desconhecido: {cmd}. Use: list, add, remove, run, status"
