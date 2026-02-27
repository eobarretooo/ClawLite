from __future__ import annotations
import argparse
import platform
import shutil
import sys

from clawlite.auth import PROVIDERS, auth_login, auth_logout, auth_status
from clawlite.core.agent import run_task
from clawlite.core.memory import add_note, search_notes
from clawlite.runtime.doctor import run_doctor
from clawlite.runtime.workspace import init_workspace
from clawlite.runtime.channels import channel_template
from clawlite.runtime.models import model_status, set_model_fallback
from clawlite.runtime.multiagent import (
    format_workers_table,
    init_db,
    list_workers,
    recover_workers,
    start_worker,
    stop_worker,
    task_status,
    upsert_worker,
    worker_loop,
)
from clawlite.runtime.telegram_multiagent import dispatch_local


def cmd_doctor() -> int:
    print(run_doctor())
    return 0


def main() -> None:
    p = argparse.ArgumentParser(prog="clawlite")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("run")
    r.add_argument("prompt")

    m = sub.add_parser("memory")
    msub = m.add_subparsers(dest="mcmd")
    ma = msub.add_parser("add")
    ma.add_argument("text")
    ms = msub.add_parser("search")
    ms.add_argument("query")

    sub.add_parser("doctor")
    sub.add_parser("onboarding")
    sub.add_parser("configure")

    ws = sub.add_parser("workspace")
    ws_sub = ws.add_subparsers(dest="wcmd")
    ws_init = ws_sub.add_parser("init")
    ws_init.add_argument("--path", default=None)

    ch = sub.add_parser("channels")
    ch_sub = ch.add_subparsers(dest="ccmd")
    ch_t = ch_sub.add_parser("template")
    ch_t.add_argument("name", choices=["telegram", "telegram-multiagent", "discord", "whatsapp"])

    ag = sub.add_parser("agents")
    ag_sub = ag.add_subparsers(dest="agcmd")

    ag_reg = ag_sub.add_parser("register")
    ag_reg.add_argument("--channel", default="telegram")
    ag_reg.add_argument("--chat-id", required=True)
    ag_reg.add_argument("--thread-id", default="")
    ag_reg.add_argument("--label", required=True)
    ag_reg.add_argument("--cmd", dest="command_template", required=True, help="command template, ex: clawlite run \"{text}\"")

    ag_start = ag_sub.add_parser("start")
    ag_start.add_argument("worker_id", type=int)

    ag_stop = ag_sub.add_parser("stop")
    ag_stop.add_argument("worker_id", type=int)

    ag_sub.add_parser("list")
    ag_sub.add_parser("recover")

    ag_worker = ag_sub.add_parser("worker")
    ag_worker.add_argument("--worker-id", type=int, required=True)

    ag_t = ag_sub.add_parser("tasks")
    ag_t.add_argument("--limit", type=int, default=20)

    tg = ag_sub.add_parser("telegram-dispatch")
    tg.add_argument("--config", required=True)
    tg.add_argument("--chat-id", required=True)
    tg.add_argument("--thread-id", default="")
    tg.add_argument("--label", default=None)
    tg.add_argument("text")

    md = sub.add_parser("model")
    md_sub = md.add_subparsers(dest="mocmd")
    md_sub.add_parser("status")
    md_f = md_sub.add_parser("set-fallback")
    md_f.add_argument("models", nargs="+")

    gw = sub.add_parser("gateway")
    gw.add_argument("--host", default=None)
    gw.add_argument("--port", type=int, default=None)

    auth = sub.add_parser("auth")
    auth_sub = auth.add_subparsers(dest="acmd")
    login = auth_sub.add_parser("login")
    login.add_argument("provider", choices=list(PROVIDERS.keys()))
    auth_sub.add_parser("status")
    logout = auth_sub.add_parser("logout")
    logout.add_argument("provider", choices=list(PROVIDERS.keys()))

    args = p.parse_args()

    if args.cmd == "doctor":
        raise SystemExit(cmd_doctor())
    if args.cmd == "run":
        print(run_task(args.prompt))
        return
    if args.cmd == "onboarding":
        from clawlite.onboarding import run_onboarding

        run_onboarding()
        return
    if args.cmd == "configure":
        from clawlite.configure_menu import run_configure_menu

        run_configure_menu()
        return
    if args.cmd == "gateway":
        from clawlite.gateway.server import run_gateway

        run_gateway(args.host, args.port)
        return
    if args.cmd == "auth":
        if args.acmd == "login":
            ok, msg = auth_login(args.provider)
            print(("✅ " if ok else "❌ ") + msg)
            return
        if args.acmd == "status":
            for row in auth_status():
                print(f"- {row['provider']}: {'logged-in' if row['logged_in'] else 'not logged'}")
            return
        if args.acmd == "logout":
            done = auth_logout(args.provider)
            print("✅ logout" if done else "ℹ️ already logged out")
            return

    if args.cmd == "workspace" and args.wcmd == "init":
        path = init_workspace(args.path)
        print(f"✅ Workspace inicializado em: {path}")
        return

    if args.cmd == "channels" and args.ccmd == "template":
        print(channel_template(args.name))
        return

    if args.cmd == "model" and args.mocmd == "status":
        print(model_status())
        return

    if args.cmd == "model" and args.mocmd == "set-fallback":
        set_model_fallback(args.models)
        print("✅ model fallback atualizado")
        return

    if args.cmd == "agents":
        init_db()
        if args.agcmd in {"list", "start", "tasks", "telegram-dispatch"}:
            recover_workers()

        if args.agcmd == "register":
            worker_id = upsert_worker(args.channel, args.chat_id, args.thread_id, args.label, args.command_template)
            print(f"✅ worker registrado: {worker_id}")
            return

        if args.agcmd == "start":
            pid = start_worker(args.worker_id)
            print(f"✅ worker {args.worker_id} em execução (pid={pid})")
            return

        if args.agcmd == "stop":
            stop_worker(args.worker_id)
            print(f"✅ worker {args.worker_id} parado")
            return

        if args.agcmd == "list":
            print(format_workers_table(list_workers()))
            return

        if args.agcmd == "recover":
            restarted = recover_workers()
            print("✅ recover concluído; reiniciados:", restarted if restarted else "nenhum")
            return

        if args.agcmd == "worker":
            worker_loop(args.worker_id)
            return

        if args.agcmd == "tasks":
            print(task_status(args.limit))
            return

        if args.agcmd == "telegram-dispatch":
            task_id = dispatch_local(args.config, args.chat_id, args.text, args.thread_id, args.label)
            print(f"✅ task enfileirada: {task_id}")
            return

    if args.cmd == "memory":
        if args.mcmd == "add":
            add_note(args.text)
            print("ok")
            return
        if args.mcmd == "search":
            for i in search_notes(args.query):
                print("-", i)
            return

    p.print_help()


if __name__ == "__main__":
    main()
