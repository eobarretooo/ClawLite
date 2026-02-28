from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any, Iterator

from clawlite.config.settings import load_config
from clawlite.core.tools import exec_cmd, read_file, write_file
from clawlite.runtime.notifications import create_notification
from clawlite.runtime.offline import (
    OllamaExecutionError,
    ProviderExecutionError,
    run_with_offline_fallback,
    run_with_offline_fallback_stream,
)
from clawlite.runtime.learning import record_task, get_retry_strategy
from clawlite.runtime.preferences import build_preference_prefix
from clawlite.runtime.session_memory import (
    append_daily_log,
    bootstrap_prompt_once,
    compact_daily_memory,
    semantic_search_memory,
    startup_context_text,
)
from clawlite.runtime.system_prompt import build_system_prompt
from clawlite.core.bootstrap import BootstrapManager

MAX_RETRIES = 3
ATTEMPT_TIMEOUT_S = float(os.getenv("CLAWLITE_ATTEMPT_TIMEOUT_S", "90"))
RETRY_BACKOFF_BASE_S = 0.5


def _build_tools_prompt() -> str:
    return """
[Ferramentas Disponíveis]
Você possui acesso às seguintes ferramentas locais. Se precisar usá-las, responda **APENAS** com um bloco JSON neste formato (e nada mais):
{"tool_call": {"name": "NOME_DA_FERRAMENTA", "arguments": {"arg1": "valor"}}}

Ferramentas:
1. {"name": "exec_cmd", "description": "Executa um comando no terminal", "arguments": {"command": "string"}}
2. {"name": "read_file", "description": "Lê um arquivo do disco", "arguments": {"path": "string"}}
3. {"name": "write_file", "description": "Escreve conteúdo em um arquivo", "arguments": {"path": "string", "content": "string"}}

Para interagir com web, utilize as ferramentas de `browser_`:
4. {"name": "browser_goto", "description": "Abre uma URL no navegador e retorna um snapshot (texto + IDs)", "arguments": {"url": "string"}}
5. {"name": "browser_click", "description": "Clica em um elemento pelo seu claw-id", "arguments": {"cid": "string"}}
6. {"name": "browser_fill", "description": "Preenche um elemento com texto pelo seu claw-id", "arguments": {"cid": "string", "text": "string"}}
7. {"name": "browser_read", "description": "Tira um novo snapshot da DOM atual mostrando IDs atualizados", "arguments": {}}
8. {"name": "browser_press", "description": "Pressiona uma tecla especial (ex: Enter, Escape, Tab)", "arguments": {"key": "string"}}
"""

def _execute_local_tool(name: str, args: dict[str, Any]) -> str:
    try:
        if name == "exec_cmd":
            code, out, err = exec_cmd(str(args.get("command", "")))
            return f"Exit code {code}\nSTDOUT:\n{out}\nSTDERR:\n{err}"
        elif name == "read_file":
            return read_file(str(args.get("path", "")))
        elif name == "write_file":
            write_file(str(args.get("path", "")), str(args.get("content", "")))
            return "Arquivo escrito com sucesso."
        
        # Tools de Navegador Automático via Playwright
        elif name.startswith("browser_"):
            from clawlite.runtime.browser_manager import get_browser_manager
            bm = get_browser_manager()
            if name == "browser_goto":
                res = bm.goto(str(args.get("url", "")))
                return f"{res}\n{bm.get_snapshot()}"
            elif name == "browser_click":
                res = bm.click(str(args.get("cid", "")))
                return f"{res}\n{bm.get_snapshot()}"
            elif name == "browser_fill":
                res = bm.fill(str(args.get("cid", "")), str(args.get("text", "")))
                return f"{res}\n{bm.get_snapshot()}"
            elif name == "browser_press":
                res = bm.press(str(args.get("key", "")))
                return f"{res}\n{bm.get_snapshot()}"
            elif name == "browser_read":
                return bm.get_snapshot()
            else:
                return f"Erro: ferramenta browser '{name}' não mapeada."
                
        else:
            return f"Erro: ferramenta '{name}' não existe."
    except Exception as exc:
        return f"Erro ao executar a ferramenta: {exc}"

def _run_task_with_timeout(prompt: str, timeout_s: float) -> tuple[str, dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=1) as executor:
        fut = executor.submit(run_task_with_meta, prompt)
        try:
            return fut.result(timeout=timeout_s)
        except FutureTimeout:
            return (
                f"Timeout: execução excedeu {timeout_s:.0f}s",
                {
                    "mode": "error",
                    "reason": "attempt-timeout",
                    "model": "n/a",
                    "error": f"timeout>{timeout_s}s",
                    "error_type": "timeout",
                },
            )


def run_task_with_meta(prompt: str) -> tuple[str, dict[str, Any]]:
    if prompt.lower().startswith("resuma o diretório"):
        code, out, err = exec_cmd("ls -la")
        if code == 0:
            return (
                f"Diretório atual:\n{out[:3000]}",
                {"mode": "local-tool", "reason": "directory-summary", "model": "local/exec_cmd"},
            )
        return (
            f"Falha ao listar diretório: {err}",
            {"mode": "error", "reason": "local-tool-failed", "model": "local/exec_cmd"},
        )

    cfg = load_config()
    requested_model = str(cfg.get("model", "openai/gpt-4o-mini"))
    try:
        output, meta = run_with_offline_fallback(prompt, cfg)
    except ProviderExecutionError as exc:
        create_notification(
            event="provider_failed",
            message=f"Falha no provedor remoto: {exc}",
            priority="high",
            dedupe_key=f"provider_failed:{exc}",
            dedupe_window_seconds=300,
        )
        return (
            f"Falha no provedor remoto: {exc}",
            {
                "mode": "error",
                "reason": "provider-failed",
                "model": requested_model,
                "error": str(exc),
            },
        )
    except OllamaExecutionError as exc:
        create_notification(
            event="ollama_failed",
            message=f"Falha no fallback Ollama: {exc}",
            priority="high",
            dedupe_key=f"ollama_failed:{exc}",
            dedupe_window_seconds=300,
        )
        return (
            f"Falha no fallback Ollama: {exc}",
            {
                "mode": "error",
                "reason": "ollama-failed",
                "model": requested_model,
                "error": str(exc),
            },
        )

    if meta.get("mode") == "offline-fallback":
        create_notification(
            event="offline_fallback",
            message=f"Fallback automático para {meta.get('model')}",
            priority="normal",
            dedupe_key=f"offline_fallback:{meta.get('reason')}:{meta.get('model')}",
            dedupe_window_seconds=300,
            metadata=meta,
        )
    return output, meta


def run_task_stream_with_meta(prompt: str) -> tuple[Iterator[str], dict[str, Any]]:
    """
    Versão em formato Streaming (generator) do core agent.
    Yields chunks of text as they arrive from the LLM.
    """
    if prompt.lower().startswith("resuma o diretório"):
        code, out, err = exec_cmd("ls -la")
        def _mock_stream() -> Iterator[str]:
            if code == 0:
                yield f"Diretório atual:\n{out[:3000]}"
            else:
                yield f"Falha ao listar diretório: {err}"
                
        if code == 0:
            return _mock_stream(), {"mode": "local-tool", "reason": "directory-summary", "model": "local/exec_cmd"}
        return _mock_stream(), {"mode": "error", "reason": "local-tool-failed", "model": "local/exec_cmd"}

    cfg = load_config()
    requested_model = str(cfg.get("model", "openai/gpt-4o-mini"))
    try:
        out_stream, meta = run_with_offline_fallback_stream(prompt, cfg)
    except ProviderExecutionError as exc:
        create_notification(
            event="provider_failed",
            message=f"Falha no provedor remoto (stream): {exc}",
            priority="high",
            dedupe_key=f"provider_failed:{exc}",
            dedupe_window_seconds=300,
        )
        def _err_stream() -> Iterator[str]:
            yield f"Falha no provedor remoto: {exc}"
            
        return _err_stream(), {
            "mode": "error",
            "reason": "provider-failed",
            "model": requested_model,
            "error": str(exc),
        }
    except OllamaExecutionError as exc:
        create_notification(
            event="ollama_failed",
            message=f"Falha no fallback Ollama (stream): {exc}",
            priority="high",
            dedupe_key=f"ollama_failed:{exc}",
            dedupe_window_seconds=300,
        )
        def _err_stream() -> Iterator[str]:
            yield f"Falha no fallback Ollama: {exc}"
            
        return _err_stream(), {
            "mode": "error",
            "reason": "ollama-failed",
            "model": requested_model,
            "error": str(exc),
        }

    if meta.get("mode") == "offline-fallback":
        create_notification(
            event="offline_fallback",
            message=f"Fallback automático para {meta.get('model')}",
            priority="normal",
            dedupe_key=f"offline_fallback:{meta.get('reason')}:{meta.get('model')}",
            dedupe_window_seconds=300,
            metadata=meta,
        )
    return out_stream, meta


def run_task(prompt: str) -> str:
    return run_task_with_learning(prompt)


def run_task_with_learning(prompt: str, skill: str = "", session_id: str = "") -> str:
    """Executa task com aprendizado contínuo: preferências, histórico e auto-retry."""
    # Injetar preferências + contexto de memória de sessão
    base_system = build_system_prompt()
    prefix = build_preference_prefix()
    startup_ctx = startup_context_text()
    bootstrap_mgr = BootstrapManager()
    bootstrap_txt = bootstrap_mgr.get_prompt() if bootstrap_mgr.should_run() else ""
    mem_hits = semantic_search_memory(prompt, max_results=3)
    mem_snippets = "\n".join([f"- {h.snippet}" for h in mem_hits])

    context_prefix_parts = []
    if base_system.strip():
        context_prefix_parts.append("[System Prompt]\n" + base_system[:3200])
    if bootstrap_txt.strip():
        context_prefix_parts.append("[Bootstrap Inicial]\n" + bootstrap_txt[:2000])
    if startup_ctx.strip():
        context_prefix_parts.append("[Contexto de Sessão]\n" + startup_ctx[:2200])
    if mem_snippets.strip():
        context_prefix_parts.append("[Memória Relevante]\n" + mem_snippets[:1200])
    if prefix.strip():
        context_prefix_parts.append(prefix)

    if session_id:
        from clawlite.runtime.session_memory import read_recent_session_messages
        recent = read_recent_session_messages(session_id, limit=6)
        if recent:
            chat_hist = []
            for m in recent:
                r = m.get("role", "info")
                t = (m.get("text") or "").strip()
                if t:
                    chat_hist.append(f"{r.capitalize()}: {t}")
            
            if chat_hist:
                context_prefix_parts.append("[Histórico Recente da Conversa Atual]\n" + "\n\n".join(chat_hist))

    context_prefix_parts.append(_build_tools_prompt())
    context_prefix = "\n\n".join(context_prefix_parts).strip()
    enriched_prompt = f"{context_prefix}\n\n[Pedido]\n{prompt}" if context_prefix else prompt

    append_daily_log(f"Task iniciada (skill={skill or 'n/a'}): {prompt[:220]}", category="task-start")

    attempt = 0
    current_prompt = enriched_prompt
    last_output = ""
    last_meta: dict[str, Any] = {}

    # O loop principal suporta retries e até 3 steps de Tool Calling
    tool_steps = 0
    MAX_TOOL_STEPS = 3

    while attempt <= MAX_RETRIES:
        t0 = time.time()
        output, meta = _run_task_with_timeout(current_prompt, ATTEMPT_TIMEOUT_S)
        duration = time.time() - t0

        is_error = meta.get("mode") == "error"
        result = "fail" if is_error else "success"
        err_reason = str(meta.get("reason") or meta.get("error_type") or "")
        
        # Interceptar Tool Call
        if not is_error and output.strip().startswith('{"tool_call":') and tool_steps < MAX_TOOL_STEPS:
            import json
            try:
                tc = json.loads(output.strip())["tool_call"]
                tool_res = _execute_local_tool(tc["name"], tc.get("arguments", {}))
                tool_steps += 1
                
                # Alimenta o loop novamente com o resultado da tool
                current_prompt = f"{current_prompt}\n\n[Sua resposta anterior]\n{output}\n\n[Resultado da Ferramenta]\n{tool_res}"
                continue
            except Exception as e:
                # Se falhar o parse do JSON, alimentamos o erro de volta
                current_prompt = f"{current_prompt}\n\n[Sua resposta anterior]\n{output}\n\n[Erro do Sistema]\nJSON inválido para tool_call: {e}"
                tool_steps += 1
                continue

        record_task(
            prompt=prompt,
            result=result,
            duration_s=duration,
            model=meta.get("model", ""),
            tokens=meta.get("tokens", 0),
            skill=skill,
            retry_count=attempt,
            error_type=err_reason,
            error_message=str(meta.get("error") or "") or output[:240],
        )

        append_daily_log(
            f"Task {result} (tentativa={attempt + 1}/{MAX_RETRIES + 1}, skill={skill or 'n/a'}, duração={duration:.2f}s, motivo={err_reason or 'n/a'}): {prompt[:140]}",
            category="task-result",
        )

        if not is_error:
            compact_daily_memory()
            bootstrap_mgr.complete()  # apaga BOOTSTRAP.md após primeira resposta bem-sucedida
            if meta.get("mode") == "offline-fallback":
                return f"[offline:{meta.get('reason')} -> {meta.get('model')}]\n{output}"
            return output

        last_output = output
        last_meta = meta
        attempt += 1

        retry_prompt = get_retry_strategy(prompt, attempt)
        if retry_prompt is None:
            break

        create_notification(
            event="task_retry",
            message=f"Retry {attempt}/{MAX_RETRIES} para task (skill={skill or 'n/a'})",
            priority="normal",
            dedupe_key=f"task_retry:{skill}:{err_reason}:{attempt}",
            dedupe_window_seconds=30,
            metadata={"attempt": attempt, "reason": err_reason, "skill": skill},
        )

        time.sleep(RETRY_BACKOFF_BASE_S * (2 ** (attempt - 1)))
        current_prompt = f"{context_prefix}\n\n{retry_prompt}" if context_prefix else retry_prompt

    compact_daily_memory()
    create_notification(
        event="task_retry_exhausted",
        message=f"Task falhou após {MAX_RETRIES + 1} tentativas (skill={skill or 'n/a'})",
        priority="high",
        dedupe_key=f"task_retry_exhausted:{skill}:{str(last_meta.get('reason', ''))[:40]}",
        dedupe_window_seconds=120,
        metadata={"skill": skill, "last_reason": last_meta.get("reason", "")},
    )
    if last_meta.get("mode") == "offline-fallback":
        return f"[offline:{last_meta.get('reason')} -> {last_meta.get('model')}]\n{last_output}"
    return last_output


def run_task_stream_with_learning(prompt: str, skill: str = "", session_id: str = "") -> Iterator[str]:
    """Executa task e yield chunks. Ideal para websockets/dashboard."""
    base_system = build_system_prompt()
    prefix = build_preference_prefix()
    startup_ctx = startup_context_text()
    bootstrap_mgr = BootstrapManager()
    bootstrap_txt = bootstrap_mgr.get_prompt() if bootstrap_mgr.should_run() else ""
    mem_hits = semantic_search_memory(prompt, max_results=3)
    mem_snippets = "\n".join([f"- {h.snippet}" for h in mem_hits])

    context_prefix_parts = []
    if base_system.strip():
        context_prefix_parts.append("[System Prompt]\n" + base_system[:3200])
    if bootstrap_txt.strip():
        context_prefix_parts.append("[Bootstrap Inicial]\n" + bootstrap_txt[:2000])
    if startup_ctx.strip():
        context_prefix_parts.append("[Contexto de Sessão]\n" + startup_ctx[:2200])
    if mem_snippets.strip():
        context_prefix_parts.append("[Memória Relevante]\n" + mem_snippets[:1200])
    if prefix.strip():
        context_prefix_parts.append(prefix)
    
    if session_id:
        from clawlite.runtime.session_memory import read_recent_session_messages
        recent = read_recent_session_messages(session_id, limit=6)
        if recent:
            chat_hist = []
            for m in recent:
                r = m.get("role", "info")
                t = (m.get("text") or "").strip()
                if t:
                    chat_hist.append(f"{r.capitalize()}: {t}")
            
            if chat_hist:
                context_prefix_parts.append("[Histórico Recente da Conversa Atual]\n" + "\n\n".join(chat_hist))

    context_prefix_parts.append(_build_tools_prompt())
    context_prefix = "\n\n".join(context_prefix_parts).strip()
    enriched_prompt = f"{context_prefix}\n\n[Pedido]\n{prompt}" if context_prefix else prompt

    append_daily_log(f"Task stream iniciada (skill={skill or 'n/a'}): {prompt[:220]}", category="task-start")

    tool_steps = 0
    MAX_TOOL_STEPS = 3
    current_prompt = enriched_prompt

    while tool_steps <= MAX_TOOL_STEPS:
        t0 = time.time()
        out_stream, meta = run_task_stream_with_meta(current_prompt)
        
        is_error = meta.get("mode") == "error"
        err_reason = str(meta.get("reason") or meta.get("error_type") or "")
        
        # Se falhou direto na chamada (ex: sem internet):
        if is_error:
            duration = time.time() - t0
            record_task(
                prompt=prompt,
                result="fail",
                duration_s=duration,
                model=meta.get("model", ""),
                tokens=0,
                skill=skill,
                retry_count=0,
                error_type=err_reason,
                error_message=str(meta.get("error") or ""),
            )
            append_daily_log(
                f"Task stream fail (duração={duration:.2f}s, motivo={err_reason or 'n/a'})", category="task-result"
            )
            yield from out_stream
            return

        # Consumindo o stream com sucesso
        full_output = []
        try:
            if meta.get("mode") == "offline-fallback":
                yield f"[offline:{meta.get('reason')} -> {meta.get('model')}]\n"
                
            for chunk in out_stream:
                full_output.append(chunk)
                yield chunk
                
            output_text = "".join(full_output)
            
            # Interceptar Tool Call
            if output_text.strip().startswith('{"tool_call":') and tool_steps < MAX_TOOL_STEPS:
                import json
                try:
                    tc = json.loads(output_text.strip())["tool_call"]
                    tool_res = _execute_local_tool(tc["name"], tc.get("arguments", {}))
                    tool_steps += 1
                    
                    # Yield separator
                    yield f"\n\n[Executando ferramenta '{tc['name']}'...]\n"
                    
                    current_prompt = f"{current_prompt}\n\n[Sua resposta anterior]\n{output_text}\n\n[Resultado da Ferramenta]\n{tool_res}"
                    continue
                except Exception as e:
                    current_prompt = f"{current_prompt}\n\n[Sua resposta anterior]\n{output_text}\n\n[Erro do Sistema]\nJSON inválido para tool_call: {e}"
                    tool_steps += 1
                    continue
                
            # Finish if no tool call
            compact_daily_memory()
            bootstrap_mgr.complete()
            
            duration = time.time() - t0
            record_task(
                prompt=prompt,
                result="success",
                duration_s=duration,
                model=meta.get("model", ""),
                tokens=len(output_text) // 4,
                skill=skill,
                retry_count=0,
                error_type="",
                error_message="",
            )
            append_daily_log(
                f"Task stream success (duração={duration:.2f}s): {prompt[:140]}", category="task-result"
            )
            return
            
        except Exception as exc:
            duration = time.time() - t0
            record_task(
                prompt=prompt,
                result="fail",
                duration_s=duration,
                model=meta.get("model", ""),
                tokens=0,
                skill=skill,
                retry_count=0,
                error_type="stream-exception",
                error_message=str(exc),
            )
            yield f"\n[Erro durante stream: {exc}]"
            return
