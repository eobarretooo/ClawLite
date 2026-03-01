from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

HEARTBEAT_OK = "HEARTBEAT_OK"
DEFAULT_INTERVAL_S = 1800  # 30 minutos


def _is_effectively_empty(content: str) -> bool:
    """Retorna True se o conteúdo é vazio ou tem apenas linhas em branco / comentários (#)."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return False
    return True


class HeartbeatLoop:
    """Loop de heartbeat baseado em HEARTBEAT.md do workspace.

    Roda em thread daemon — inicia junto ao gateway e para quando o processo encerra.

    Fluxo por ciclo:
      1. Lê HEARTBEAT.md; se vazio/só comentários → silêncio
      2. Injeta conteúdo no agente via run_task_with_learning()
      3. Se resposta == "HEARTBEAT_OK" → silêncio
      4. Outra resposta → cria notificação (canal configurado)
      5. Salva memory/heartbeat-state.json
    """

    def __init__(
        self,
        workspace_path: str | Path | None = None,
        interval_s: int = DEFAULT_INTERVAL_S,
        proactive_callback: Callable[[str], None] | None = None,
    ) -> None:
        root = (
            Path(workspace_path).expanduser()
            if workspace_path
            else Path.home() / ".clawlite" / "workspace"
        )
        self._heartbeat_file = root / "HEARTBEAT.md"
        self._state_file = root / "memory" / "heartbeat-state.json"
        self.interval_s = interval_s
        self._stop_event = threading.Event()
        self._proactive_callback = proactive_callback

    # ------------------------------------------------------------------
    # Estado persistido
    # ------------------------------------------------------------------

    def _load_state(self) -> dict[str, Any]:
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"last_run": None, "last_result": None, "runs_today": 0}

    def _save_state(self, last_result: str, runs_today: int) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "last_result": last_result,
            "runs_today": runs_today,
        }
        self._state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _today_str(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _runs_today(self, state: dict[str, Any]) -> int:
        """Retorna o contador de runs de hoje, zerado se o último run foi ontem ou antes."""
        last_run: str = state.get("last_run") or ""
        if last_run[:10] == self._today_str():
            return int(state.get("runs_today", 0)) + 1
        return 1

    # ------------------------------------------------------------------
    # Ciclo único
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        raw = str(text or "").strip()
        if raw.startswith("```"):
            raw = raw.removeprefix("```json").removeprefix("```").strip()
            if raw.endswith("```"):
                raw = raw[:-3].strip()
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None

    def _decide_action(self, content: str) -> tuple[str, str, str]:
        """Fase 1: decide skip/run com resposta estruturada."""
        from clawlite.core.agent import run_task_with_learning

        prompt = (
            "Você é o planejador de heartbeat. Responda APENAS em JSON com este formato:\n"
            '{"action":"skip|run","tasks":"resumo curto das tarefas quando action=run"}\n\n'
            "Regras:\n"
            "- use action=skip quando não houver trabalho acionável agora;\n"
            "- use action=run apenas quando houver ação proativa imediata.\n\n"
            f"[HEARTBEAT_MD]\n{content}"
        )
        decision_raw = run_task_with_learning(prompt, skill="heartbeat-decision", session_id="heartbeat")
        payload = self._extract_json(decision_raw)
        if payload:
            action = str(payload.get("action", "skip")).strip().lower()
            if action not in {"skip", "run"}:
                action = "skip"
            tasks = str(payload.get("tasks", "")).strip()
            return action, tasks, decision_raw

        # Compatibilidade com fluxo legado baseado em token.
        if decision_raw.strip() == HEARTBEAT_OK:
            return "skip", "", HEARTBEAT_OK
        return "run", decision_raw.strip(), decision_raw

    def _run_once(self) -> None:
        if not self._heartbeat_file.exists():
            logger.debug("heartbeat: HEARTBEAT.md não encontrado, pulando ciclo")
            return

        content = self._heartbeat_file.read_text(encoding="utf-8")
        if _is_effectively_empty(content):
            logger.debug("heartbeat: HEARTBEAT.md vazio/comentários, silêncio")
            return

        logger.info("heartbeat: disparando agente com conteúdo de HEARTBEAT.md")
        try:
            action, tasks, decision_raw = self._decide_action(content)
        except Exception as exc:
            logger.warning("heartbeat: erro ao chamar agente — %s", exc)
            return

        if action == "skip":
            response_clean = HEARTBEAT_OK if str(decision_raw).strip() == HEARTBEAT_OK else "HEARTBEAT_SKIP"
            state = self._load_state()
            runs_today = self._runs_today(state)
            self._save_state(response_clean, runs_today)
            logger.info("heartbeat: decisão=skip — silêncio")
            return

        try:
            from clawlite.core.agent import run_task_with_learning  # import tardio: evita circular

            execution_prompt = tasks.strip() or content
            response = run_task_with_learning(execution_prompt, skill="heartbeat", session_id="heartbeat")
        except Exception as exc:
            logger.warning("heartbeat: erro na fase de execução — %s", exc)
            return

        response_clean = response.strip() or "HEARTBEAT_RUN_EMPTY"
        # trunca para o state (limite legível)
        last_result = response_clean if len(response_clean) <= 200 else response_clean[:197] + "..."

        state = self._load_state()
        runs_today = self._runs_today(state)
        self._save_state(last_result, runs_today)

        if response_clean == HEARTBEAT_OK:
            logger.info("heartbeat: HEARTBEAT_OK — silêncio")
            return

        logger.info("heartbeat: resposta não-OK, criando notificação")
        try:
            from clawlite.runtime.notifications import create_notification
            create_notification(
                event="heartbeat.response",
                message=response_clean[:500],
                priority="normal",
                dedupe_key=f"heartbeat:{self._today_str()}:{abs(hash(response_clean)) % 100_000}",
                dedupe_window_seconds=300,
            )
        except Exception as exc:
            logger.warning("heartbeat: erro ao criar notificação — %s", exc)

        self._send_proactive(response_clean)

    def _send_proactive(self, message: str) -> None:
        callback = self._proactive_callback
        if callback is not None:
            try:
                callback(message)
                return
            except Exception as exc:
                logger.warning("heartbeat: falha no callback proativo — %s", exc)
        self._send_telegram_proactive(message)

    def _send_telegram_proactive(self, message: str) -> None:
        try:
            from clawlite.channels.telegram_runtime import send_telegram_text_sync
            from clawlite.config.settings import load_config
        except Exception:
            return

        try:
            cfg = load_config()
            channels = cfg.get("channels", {}) if isinstance(cfg, dict) else {}
            tg = channels.get("telegram", {}) if isinstance(channels, dict) else {}
            if not isinstance(tg, dict):
                return

            token = str(tg.get("token", "")).strip()
            chat_id = str(tg.get("chat_id") or tg.get("chatId") or "").strip()
            if not token or not chat_id:
                return

            text = f"[heartbeat] {message}".strip()
            send_telegram_text_sync(
                token=token,
                chat_id=chat_id,
                text=text,
            )
        except Exception as exc:
            logger.warning("heartbeat: falha ao enviar alerta Telegram — %s", exc)

    # ------------------------------------------------------------------
    # Controle do loop
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Bloqueia em loop — chamar em thread daemon."""
        logger.info("heartbeat: loop iniciado (interval=%ds)", self.interval_s)
        while not self._stop_event.is_set():
            try:
                self._run_once()
            except Exception as exc:
                logger.warning("heartbeat: exceção não tratada em _run_once — %s", exc)
            self._stop_event.wait(self.interval_s)
        logger.info("heartbeat: loop encerrado")

    def stop(self) -> None:
        """Sinaliza o loop para parar na próxima oportunidade."""
        self._stop_event.set()


class AsyncHeartbeatLoop:
    """Wrapper assíncrono para rodar heartbeat no loop principal do gateway."""

    def __init__(
        self,
        workspace_path: str | Path | None = None,
        interval_s: int = DEFAULT_INTERVAL_S,
        proactive_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._sync = HeartbeatLoop(
            workspace_path=workspace_path,
            interval_s=interval_s,
            proactive_callback=proactive_callback,
        )
        self.interval_s = max(1, int(interval_s))
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def _run_loop(self) -> None:
        logger.info("heartbeat(async): loop iniciado (interval=%ds)", self.interval_s)
        while not self._stop_event.is_set():
            try:
                await asyncio.to_thread(self._sync._run_once)
            except Exception as exc:
                logger.warning("heartbeat(async): exceção em ciclo — %s", exc)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_s)
            except asyncio.TimeoutError:
                pass
        logger.info("heartbeat(async): loop encerrado")

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="clawlite-heartbeat-async")

    async def stop(self) -> None:
        self._stop_event.set()
        task = self._task
        self._task = None
        if task is not None:
            try:
                await task
            except Exception:
                pass


def start_heartbeat_thread(
    workspace_path: str | Path | None = None,
    interval_s: int = DEFAULT_INTERVAL_S,
    proactive_callback: Callable[[str], None] | None = None,
) -> HeartbeatLoop:
    """Inicia o HeartbeatLoop em thread daemon e retorna a instância para controle."""
    hb = HeartbeatLoop(
        workspace_path=workspace_path,
        interval_s=interval_s,
        proactive_callback=proactive_callback,
    )
    t = threading.Thread(target=hb.start, name="clawlite-heartbeat", daemon=True)
    t.start()
    return hb
