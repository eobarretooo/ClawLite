from __future__ import annotations
import argparse
import atexit
import sys
import time

from clawlite.auth import PROVIDERS, auth_login, auth_logout, auth_status
from clawlite.core.agent import run_task
from clawlite.core.memory import add_note, search_notes
from clawlite.runtime.session_memory import (
    compact_daily_memory,
    ensure_memory_layout,
    memory_hits_to_json,
    save_session_summary,
    semantic_search_memory,
    startup_context,
)
from clawlite.runtime.secret_store import load_dotenv, load_vault_json
from clawlite.runtime.conversation_cron import (
    add_cron_job,
    format_cron_jobs_table,
    format_cron_run_results,
    init_cron_db,
    list_cron_jobs,
    remove_cron_job,
    run_cron_jobs,
)
from clawlite.runtime.doctor import run_doctor
from clawlite.runtime.status import runtime_status
from clawlite.runtime.workspace import init_workspace
from clawlite.runtime.channels import channel_template
from clawlite.runtime.models import model_status, set_model_fallback
from clawlite.runtime.battery import get_battery_mode, set_battery_mode
from clawlite.runtime.multiagent import (
    bind_agent,
    create_agent,
    format_agents_table,
    format_bindings_table,
    format_workers_table,
    init_db,
    list_agent_bindings,
    list_agents,
    list_workers,
    recover_workers,
    start_worker,
    stop_worker,
    task_status,
    upsert_worker,
    worker_loop,
)
from clawlite.runtime.telegram_multiagent import dispatch_local
from clawlite.runtime.reddit import (
    auth_url as reddit_auth_url,
    exchange_code as reddit_exchange_code,
    monitor_mentions_once as reddit_monitor_mentions_once,
    post_milestone as reddit_post_milestone,
    reddit_status,
)
from clawlite.runtime.learning import get_stats as learning_get_stats
from clawlite.runtime.preferences import get_preferences
from clawlite.skills.marketplace import (
    DEFAULT_DOWNLOAD_BASE_URL,
    DEFAULT_INDEX_URL,
    SkillMarketplaceError,
    install_skill,
    publish_skill,
    schedule_auto_update,
    search_skills,
    update_skills,
)
from clawlite.mcp import add_server, install_template, list_servers, remove_server, search_marketplace


def cmd_doctor() -> int:
    print(run_doctor())
    return 0


def _fail(message: str) -> None:
    print(f"❌ {message}")
    raise SystemExit(1)


def _exc_message(exc: Exception) -> str:
    msg = str(exc).strip()
    return msg or exc.__class__.__name__


def _run_gateway_cli(host: str | None, port: int | None) -> None:
    try:
        from clawlite.gateway.server import run_gateway
    except ModuleNotFoundError as exc:
        missing = str(getattr(exc, "name", "") or "")
        if missing in {"fastapi", "uvicorn"}:
            _fail(
                "Dependências do gateway ausentes (fastapi/uvicorn). "
                "No Termux: pkg install rust clang && ~/.clawlite/venv/bin/pip install fastapi uvicorn; "
                "no Linux: pip install fastapi uvicorn."
            )
        _fail(f"Falha ao carregar gateway: {_exc_message(exc)}")
    except Exception as exc:
        _fail(f"Falha ao carregar gateway: {_exc_message(exc)}")

    try:
        run_gateway(host, port)
    except SystemExit:
        raise
    except Exception as exc:
        _fail(f"Falha ao iniciar gateway: {_exc_message(exc)}")


def main() -> None:
    # bootstrap de segredos (.env + vault local opcional)
    load_dotenv()
    load_vault_json()

    _started_at = time.time()
    _raw_cmd = " ".join(sys.argv[1:]).strip() or "help"

    def _autosave_session_summary() -> None:
        try:
            elapsed = time.time() - _started_at
            save_session_summary(
                f"Sessão CLI encerrada: `{_raw_cmd}` em {elapsed:.1f}s",
                important=False,
            )
        except Exception:
            pass

    atexit.register(_autosave_session_summary)

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

    mm_init = msub.add_parser("init")
    mm_init.add_argument("--path", default=None)

    mm_ctx = msub.add_parser("context")
    mm_ctx.add_argument("--path", default=None)

    mm_sem = msub.add_parser("semantic-search")
    mm_sem.add_argument("query")
    mm_sem.add_argument("--max-results", type=int, default=5)
    mm_sem.add_argument("--path", default=None)

    mm_compact = msub.add_parser("compact")
    mm_compact.add_argument("--max-daily-files", type=int, default=21)
    mm_compact.add_argument("--path", default=None)

    mm_sum = msub.add_parser("save-session")
    mm_sum.add_argument("summary")
    mm_sum.add_argument("--not-important", action="store_true")
    mm_sum.add_argument("--path", default=None)

    sub.add_parser("doctor")
    sub.add_parser("status")
    sub.add_parser("onboarding")
    sub.add_parser("configure")

    start = sub.add_parser("start")
    start.add_argument("--host", default=None)
    start.add_argument("--port", type=int, default=None)

    ws = sub.add_parser("workspace")
    ws_sub = ws.add_subparsers(dest="wcmd")
    ws_init = ws_sub.add_parser("init")
    ws_init.add_argument("--path", default=None)

    ch = sub.add_parser("channels")
    ch_sub = ch.add_subparsers(dest="ccmd")
    ch_t = ch_sub.add_parser("template")
    ch_t.add_argument("name", choices=["telegram", "telegram-multiagent", "slack", "discord", "whatsapp", "teams"])

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

    ag_create = ag_sub.add_parser("create")
    ag_create.add_argument("name")
    ag_create.add_argument("--channel", required=True, choices=["telegram", "slack", "discord", "whatsapp", "teams"])
    ag_create.add_argument("--token", default="")
    ag_create.add_argument("--account", default="")
    ag_create.add_argument("--personality", default="")
    ag_create.add_argument("--role", default="")
    ag_create.add_argument("--tag", action="append", default=[])
    ag_create.add_argument("--orchestrator", action="store_true")

    ag_sub.add_parser("list")

    ag_bind = ag_sub.add_parser("bind")
    ag_bind.add_argument("agent")
    ag_bind.add_argument("--channel", required=True, choices=["telegram", "slack", "discord", "whatsapp", "teams"])
    ag_bind.add_argument("--account", required=True)

    ag_sub.add_parser("bindings")
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

    cr = sub.add_parser("cron")
    cr_sub = cr.add_subparsers(dest="crcmd")

    cr_list = cr_sub.add_parser("list")
    cr_list.add_argument("--channel", default=None)
    cr_list.add_argument("--chat-id", default=None)
    cr_list.add_argument("--thread-id", default=None)
    cr_list.add_argument("--label", default=None)

    cr_add = cr_sub.add_parser("add")
    cr_add.add_argument("--channel", default="telegram")
    cr_add.add_argument("--chat-id", required=True)
    cr_add.add_argument("--thread-id", default="")
    cr_add.add_argument("--label", required=True)
    cr_add.add_argument("--name", required=True)
    cr_add.add_argument("--text", required=True)
    cr_add.add_argument("--every-seconds", type=int, required=True)
    cr_add.add_argument("--disabled", action="store_true")

    cr_rm = cr_sub.add_parser("remove")
    cr_rm.add_argument("job_id", type=int)

    cr_run = cr_sub.add_parser("run")
    cr_run.add_argument("--job-id", type=int, default=None)
    cr_run.add_argument("--all", action="store_true")

    bt = sub.add_parser("battery")
    bt_sub = bt.add_subparsers(dest="bacmd")
    bt_sub.add_parser("status")
    bt_set = bt_sub.add_parser("set")
    bt_set.add_argument("--enabled", choices=["true", "false"], default=None)
    bt_set.add_argument("--throttle-seconds", type=float, default=None)

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

    sk = sub.add_parser("skill")
    sk_sub = sk.add_subparsers(dest="scmd")

    sk_install = sk_sub.add_parser("install")
    sk_install.add_argument("slug")
    sk_install.add_argument("--index-url", default=DEFAULT_INDEX_URL)
    sk_install.add_argument("--allow-host", action="append", default=[])
    sk_install.add_argument("--install-dir", default=None)
    sk_install.add_argument("--manifest-path", default=None)
    sk_install.add_argument("--force", action="store_true")
    sk_install.add_argument("--allow-file-urls", action="store_true")

    sk_update = sk_sub.add_parser("update")
    sk_update.add_argument("slugs", nargs="*")
    sk_update.add_argument("--index-url", default=DEFAULT_INDEX_URL)
    sk_update.add_argument("--allow-host", action="append", default=[])
    sk_update.add_argument("--install-dir", default=None)
    sk_update.add_argument("--manifest-path", default=None)
    sk_update.add_argument("--force", action="store_true")
    sk_update.add_argument("--dry-run", action="store_true")
    sk_update.add_argument("--allow-file-urls", action="store_true")

    sk_publish = sk_sub.add_parser("publish")
    sk_publish.add_argument("source_dir")
    sk_publish.add_argument("--version", required=True)
    sk_publish.add_argument("--slug", default=None)
    sk_publish.add_argument("--description", default="")
    sk_publish.add_argument("--category", default="general")
    sk_publish.add_argument("--status", default="stable", choices=["stable", "beta", "experimental", "deprecated"])
    sk_publish.add_argument("--tag", action="append", default=[])
    sk_publish.add_argument("--install-hint", default="")
    sk_publish.add_argument("--hub-dir", default=None)
    sk_publish.add_argument("--manifest-path", default=None)
    sk_publish.add_argument("--download-base-url", default=DEFAULT_DOWNLOAD_BASE_URL)

    sk_search = sk_sub.add_parser("search")
    sk_search.add_argument("query", nargs="?", default="")
    sk_search.add_argument("--index-url", default=DEFAULT_INDEX_URL)
    sk_search.add_argument("--allow-host", action="append", default=[])
    sk_search.add_argument("--manifest-path", default=None)
    sk_search.add_argument("--category", default=None)
    sk_search.add_argument("--status", default=None, choices=["stable", "beta", "experimental", "deprecated"])
    sk_search.add_argument("--allow-file-urls", action="store_true")

    sk_autoupdate = sk_sub.add_parser("auto-update")
    sk_autoupdate.add_argument("--index-url", default=DEFAULT_INDEX_URL)
    sk_autoupdate.add_argument("--allow-host", action="append", default=[])
    sk_autoupdate.add_argument("--install-dir", default=None)
    sk_autoupdate.add_argument("--manifest-path", default=None)
    sk_autoupdate.add_argument("--strict", action="store_true")
    sk_autoupdate.add_argument("--dry-run", action="store_true")
    sk_autoupdate.add_argument("--apply", action="store_true")
    sk_autoupdate.add_argument("--allow-file-urls", action="store_true")
    sk_autoupdate.add_argument("--schedule-seconds", type=int, default=None)

    mcp = sub.add_parser("mcp")
    mcp_sub = mcp.add_subparsers(dest="mcpcmd")
    mcp_add = mcp_sub.add_parser("add")
    mcp_add.add_argument("name")
    mcp_add.add_argument("url")
    mcp_sub.add_parser("list")
    mcp_rm = mcp_sub.add_parser("remove")
    mcp_rm.add_argument("name")
    mcp_search = mcp_sub.add_parser("search")
    mcp_search.add_argument("query", nargs="?", default="")
    mcp_install = mcp_sub.add_parser("install")
    mcp_install.add_argument("name")

    st = sub.add_parser("stats")
    st.add_argument("--period", choices=["today", "week", "month", "all"], default="all")
    st.add_argument("--skill", default=None)

    rd = sub.add_parser("reddit")
    rd_sub = rd.add_subparsers(dest="rdcmd")

    rd_sub.add_parser("status")
    rd_auth = rd_sub.add_parser("auth-url")
    rd_auth.add_argument("--scopes", default="identity submit read history")
    rd_ex = rd_sub.add_parser("exchange-code")
    rd_ex.add_argument("code")

    rd_post = rd_sub.add_parser("post-milestone")
    rd_post.add_argument("--title", required=True)
    rd_post.add_argument("--text", required=True)
    rd_post.add_argument("--subs", nargs="*", default=[])

    rd_sub.add_parser("monitor-once")

    args = p.parse_args()

    if args.cmd == "doctor":
        raise SystemExit(cmd_doctor())
    if args.cmd == "status":
        print(runtime_status())
        return
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
    if args.cmd == "start":
        _run_gateway_cli(args.host, args.port)
        return
    if args.cmd == "gateway":
        _run_gateway_cli(args.host, args.port)
        return
    if args.cmd == "auth":
        try:
            if args.acmd == "login":
                ok, msg = auth_login(args.provider)
                print(("✅ " if ok else "❌ ") + msg)
                if not ok:
                    raise SystemExit(1)
                return
            if args.acmd == "status":
                for row in auth_status():
                    status = "autenticado" if row["logged_in"] else "não autenticado"
                    print(f"- {row['provider']} ({row['display']}): {status}")
                return
            if args.acmd == "logout":
                done = auth_logout(args.provider)
                print("✅ Logout realizado." if done else "ℹ️ Provedor já estava desconectado.")
                return
            _fail("Subcomando obrigatório para 'auth'.")
        except SystemExit:
            raise
        except Exception as exc:
            _fail(f"Falha no comando 'auth': {_exc_message(exc)}")

    if args.cmd == "skill":
        try:
            if args.scmd == "install":
                result = install_skill(
                    args.slug,
                    index_url=args.index_url,
                    allow_hosts=args.allow_host,
                    install_dir=args.install_dir,
                    manifest_path=args.manifest_path,
                    force=args.force,
                    allow_file_urls=args.allow_file_urls,
                )
                print(f"✅ skill instalada: {result['slug']}@{result['version']}")
                print(f"caminho: {result['install_path']}")
                print(f"próximo passo: clawlite run \"use {result['slug']} para ...\"")
                print("dica: use `clawlite skill search` para explorar catálogo com filtros")
                return

            if args.scmd == "update":
                result = update_skills(
                    index_url=args.index_url,
                    allow_hosts=args.allow_host,
                    install_dir=args.install_dir,
                    manifest_path=args.manifest_path,
                    slugs=args.slugs,
                    force=args.force,
                    dry_run=args.dry_run,
                    allow_file_urls=args.allow_file_urls,
                )
                for updated in result["updated"]:
                    if updated.get("dry_run"):
                        print(
                            f"🔎 {updated['slug']}: {updated['from_version']} -> {updated['to_version']} (simulação)"
                        )
                    else:
                        print(f"⬆️ {updated['slug']}: {updated.get('from_version', '?')} -> {updated['version']}")
                for skipped in result["skipped"]:
                    print(f"⏭️ {skipped['slug']}: {skipped['reason']}")
                for missing in result["missing"]:
                    print(f"❓ {missing}: não instalada localmente")
                if not result["updated"]:
                    print("ℹ️ Nenhuma skill foi atualizada.")
                return

            if args.scmd == "publish":
                result = publish_skill(
                    args.source_dir,
                    version=args.version,
                    slug=args.slug,
                    description=args.description,
                    category=args.category,
                    status=args.status,
                    tags=args.tag,
                    install_hint=args.install_hint,
                    hub_dir=args.hub_dir,
                    manifest_path=args.manifest_path,
                    download_base_url=args.download_base_url,
                )
                print(f"📦 skill publicada: {result['slug']}@{result['version']}")
                print(f"status/categoria: {result['status']} · {result['category']}")
                print(f"instalação: {result['install_hint']}")
                print(f"pacote: {result['package_path']}")
                print(f"manifesto: {result['manifest_path']}")
                return

            if args.scmd == "search":
                rows = search_skills(
                    index_url=args.index_url,
                    allow_hosts=args.allow_host,
                    manifest_path=args.manifest_path,
                    allow_file_urls=args.allow_file_urls,
                    query=args.query,
                    category=args.category,
                    status=args.status,
                )
                if not rows:
                    print("ℹ️ Nenhuma skill encontrada para os filtros informados.")
                    return
                for row in rows:
                    local_marker = "✅ instalada" if row["installed"] else "⬇️ não instalada"
                    blocked = f" ⛔{row['blocked_reason']}" if row.get("blocked_reason") else ""
                    tags = f" [{', '.join(row['tags'])}]" if row.get("tags") else ""
                    print(
                        f"- {row['slug']}@{row['version']} ({row['status']}/{row['category']}) {local_marker}{blocked}{tags}"
                    )
                    print(f"  {row['description']}")
                    print(f"  instalação: {row['install_hint']}")
                print(f"\nTotal: {len(rows)} skill(s)")
                return

            if args.scmd == "auto-update":
                if args.apply and args.dry_run:
                    _fail("Use apenas um modo: --dry-run ou --apply")
                dry_run = (not args.apply) or args.dry_run
                result = update_skills(
                    index_url=args.index_url,
                    allow_hosts=args.allow_host,
                    install_dir=args.install_dir,
                    manifest_path=args.manifest_path,
                    dry_run=dry_run,
                    allow_file_urls=args.allow_file_urls,
                    strict=args.strict,
                )
                for updated in result["updated"]:
                    if updated.get("dry_run"):
                        print(f"🔎 {updated['slug']}: {updated['from_version']} -> {updated['to_version']} (simulação)")
                    else:
                        print(f"⬆️ {updated['slug']}: {updated.get('from_version', '?')} -> {updated['version']} (updated)")
                for skipped in result["skipped"]:
                    print(f"⏭️ {skipped['slug']}: {skipped['reason']} (skipped)")
                for blocked in result.get("blocked", []):
                    print(f"⛔ {blocked['slug']}: {blocked['reason']} (blocked)")
                for missing in result["missing"]:
                    print(f"❓ {missing}: não instalada localmente")
                if not result["updated"]:
                    print("ℹ️ Nenhuma skill foi atualizada.")

                if args.schedule_seconds is not None:
                    if dry_run:
                        _fail("Agendamento exige --apply")
                    job_id = schedule_auto_update(
                        every_seconds=args.schedule_seconds,
                        index_url=args.index_url,
                        strict=args.strict,
                        allow_hosts=args.allow_host,
                        manifest_path=args.manifest_path,
                        install_dir=args.install_dir,
                        allow_file_urls=args.allow_file_urls,
                    )
                    print(f"🗓️ Auto-update agendado: job_id={job_id} a cada {args.schedule_seconds}s")
                return
            _fail("Subcomando obrigatório para 'skill'.")
        except SkillMarketplaceError as exc:
            _fail(f"Falha no comando 'skill': {_exc_message(exc)}")
        except SystemExit:
            raise
        except Exception as exc:
            _fail(f"Falha no comando 'skill': {_exc_message(exc)}")

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

    if args.cmd == "battery":
        try:
            if args.bacmd == "status":
                mode = get_battery_mode()
                print(f"modo_bateria.ativo: {mode['enabled']}")
                print(f"modo_bateria.intervalo_segundos: {mode['throttle_seconds']}")
                return
            if args.bacmd == "set":
                enabled = None
                if args.enabled is not None:
                    enabled = args.enabled.lower() == "true"
                mode = set_battery_mode(enabled=enabled, throttle_seconds=args.throttle_seconds)
                print("✅ Modo bateria atualizado.")
                print(f"modo_bateria.ativo: {mode['enabled']}")
                print(f"modo_bateria.intervalo_segundos: {mode['throttle_seconds']}")
                return
            _fail("Subcomando obrigatório para 'battery'.")
        except SystemExit:
            raise
        except Exception as exc:
            _fail(f"Falha no comando 'battery': {_exc_message(exc)}")

    if args.cmd == "cron":
        try:
            init_cron_db()
            if args.crcmd == "list":
                rows = list_cron_jobs(args.channel, args.chat_id, args.thread_id, args.label)
                print(format_cron_jobs_table(rows))
                return

            if args.crcmd == "add":
                job_id = add_cron_job(
                    channel=args.channel,
                    chat_id=args.chat_id,
                    thread_id=args.thread_id,
                    label=args.label,
                    name=args.name,
                    text=args.text,
                    interval_seconds=args.every_seconds,
                    enabled=(not args.disabled),
                )
                print(f"✅ Tarefa cron salva: {job_id}")
                return

            if args.crcmd == "remove":
                removed = remove_cron_job(args.job_id)
                if removed:
                    print(f"✅ Tarefa cron removida: {args.job_id}")
                else:
                    _fail(f"Tarefa cron não encontrada: {args.job_id}")
                return

            if args.crcmd == "run":
                rows = run_cron_jobs(job_id=args.job_id, run_all=args.all)
                print(format_cron_run_results(rows))
                return
            _fail("Subcomando obrigatório para 'cron'.")
        except SystemExit:
            raise
        except Exception as exc:
            _fail(f"Falha no comando 'cron': {_exc_message(exc)}")

    if args.cmd == "agents":
        try:
            init_db()
            if args.agcmd in {"start", "tasks", "telegram-dispatch", "workers"}:
                recover_workers()

            if args.agcmd == "create":
                agent_id = create_agent(
                    args.name,
                    channel=args.channel,
                    role=args.role,
                    personality=args.personality,
                    credentials=args.token,
                    account=args.account,
                    orchestrator=args.orchestrator,
                    tags=args.tag,
                )
                print(f"✅ Agente criado: {agent_id}")
                return

            if args.agcmd == "bind":
                agent_id = bind_agent(args.agent, channel=args.channel, account=args.account)
                print(f"✅ Agente vinculado: {args.agent} (id={agent_id})")
                return

            if args.agcmd == "bindings":
                print(format_bindings_table(list_agent_bindings()))
                return

            if args.agcmd == "register":
                worker_id = upsert_worker(args.channel, args.chat_id, args.thread_id, args.label, args.command_template)
                print(f"✅ Worker registrado: {worker_id}")
                return

            if args.agcmd == "start":
                pid = start_worker(args.worker_id)
                print(f"✅ Worker {args.worker_id} em execução (pid={pid})")
                return

            if args.agcmd == "stop":
                stop_worker(args.worker_id)
                print(f"✅ Worker {args.worker_id} parado")
                return

            if args.agcmd == "list":
                print(format_agents_table(list_agents()))
                return

            if args.agcmd == "recover":
                restarted = recover_workers()
                print("✅ Recuperação concluída; reiniciados:", restarted if restarted else "nenhum")
                return

            if args.agcmd == "worker":
                worker_loop(args.worker_id)
                return

            if args.agcmd == "tasks":
                print(task_status(args.limit))
                return

            if args.agcmd == "telegram-dispatch":
                task_id = dispatch_local(args.config, args.chat_id, args.text, args.thread_id, args.label)
                print(f"✅ Tarefa enfileirada: {task_id}")
                return
            _fail("Subcomando obrigatório para 'agents'.")
        except SystemExit:
            raise
        except Exception as exc:
            _fail(f"Falha no comando 'agents': {_exc_message(exc)}")


    if args.cmd == "mcp":
        try:
            if args.mcpcmd == "add":
                row = add_server(args.name, args.url)
                print(f"✅ MCP server adicionado: {row['name']} -> {row['url']}")
                return
            if args.mcpcmd == "list":
                rows = list_servers()
                if not rows:
                    print("ℹ️ Nenhum servidor MCP configurado.")
                    return
                for row in rows:
                    print(f"- {row['name']}: {row['url']}")
                return
            if args.mcpcmd == "remove":
                if remove_server(args.name):
                    print(f"✅ MCP server removido: {args.name}")
                else:
                    _fail(f"Servidor MCP não encontrado: {args.name}")
                return
            if args.mcpcmd == "search":
                rows = search_marketplace(args.query)
                if not rows:
                    print("ℹ️ Nenhum servidor MCP encontrado.")
                    return
                for row in rows:
                    print(f"- {row['name']} ({row.get('source', '-')})")
                    if row.get("description"):
                        print(f"  {row['description']}")
                return
            if args.mcpcmd == "install":
                row = install_template(args.name)
                print(f"✅ MCP template instalado: {row['name']} -> {row['url']}")
                print("dica: use `clawlite mcp list` para validar")
                return
            _fail("Subcomando obrigatório para 'mcp'.")
        except ValueError as exc:
            _fail(f"Falha no comando 'mcp': {_exc_message(exc)}")
        except SystemExit:
            raise
        except Exception as exc:
            _fail(f"Falha no comando 'mcp': {_exc_message(exc)}")

    if args.cmd == "stats":
        try:
            from rich.console import Console
            from rich.table import Table

            console = Console()
            stats = learning_get_stats(period=args.period, skill=args.skill)
            prefs = get_preferences()

            table = Table(title=f"📊 ClawLite Stats ({args.period})", show_lines=True)
            table.add_column("Métrica", style="cyan")
            table.add_column("Valor", style="green")
            table.add_row("Total de tasks", str(stats["total_tasks"]))
            table.add_row("Taxa de sucesso", f"{stats['success_rate']}%")
            table.add_row("Tempo médio", f"{stats['avg_duration_s']}s")
            table.add_row("Total tokens", str(stats["total_tokens"]))
            table.add_row("Streak de acertos", f"🔥 {stats['streak']}")

            if stats["top_skills"]:
                skills_str = ", ".join(f"{s['skill']} ({s['count']})" for s in stats["top_skills"])
                table.add_row("Top skills", skills_str)

            table.add_row("Preferências", str(len(prefs)))
            console.print(table)

            if prefs:
                pt = Table(title="🧠 Preferências aprendidas")
                pt.add_column("#", style="dim")
                pt.add_column("Categoria", style="yellow")
                pt.add_column("Valor", style="white")
                for i, p in enumerate(prefs):
                    pt.add_row(str(i), p.get("category", ""), p.get("value", "")[:60])
                console.print(pt)
        except Exception as exc:
            _fail(f"Falha no comando 'stats': {_exc_message(exc)}")
        return

    if args.cmd == "reddit":
        try:
            if args.rdcmd == "status":
                st = reddit_status()
                print(f"enabled: {st['enabled']}")
                print(f"client_id_configured: {st['client_id']}")
                print(f"client_secret_configured: {st['client_secret']}")
                print(f"refresh_token_configured: {st['refresh_token']}")
                print("subreddits:", ", ".join(st['subreddits']))
                print("redirect_uri:", st['redirect_uri'])
                return
            if args.rdcmd == "auth-url":
                print(reddit_auth_url(args.scopes))
                return
            if args.rdcmd == "exchange-code":
                data = reddit_exchange_code(args.code)
                print("✅ OAuth configurado. refresh_token:", bool(data.get("refresh_token")))
                return
            if args.rdcmd == "post-milestone":
                res = reddit_post_milestone(args.title, args.text, args.subs or None)
                print("✅ Postagem concluída")
                for row in res:
                    print("-", row['subreddit'])
                return
            if args.rdcmd == "monitor-once":
                r = reddit_monitor_mentions_once()
                print(f"checked={len(r['checked_subreddits'])} new_mentions={r['new_mentions']}")
                return
            _fail("Subcomando obrigatório para 'reddit'.")
        except SystemExit:
            raise
        except Exception as exc:
            _fail(f"Falha no comando 'reddit': {_exc_message(exc)}")

    if args.cmd == "memory":
        if args.mcmd == "add":
            add_note(args.text)
            print("ok")
            return
        if args.mcmd == "search":
            for i in search_notes(args.query):
                print("-", i)
            return
        if args.mcmd == "init":
            root = ensure_memory_layout(args.path)
            print(f"✅ workspace de memória pronto: {root}")
            return
        if args.mcmd == "context":
            ctx = startup_context(args.path)
            print("root:", ctx["root"])
            print("files_loaded:")
            for f in ctx["files_loaded"]:
                print("-", f)
            return
        if args.mcmd == "semantic-search":
            hits = semantic_search_memory(args.query, max_results=args.max_results, path=args.path)
            print(memory_hits_to_json(hits))
            return
        if args.mcmd == "compact":
            r = compact_daily_memory(max_daily_files=args.max_daily_files, path=args.path)
            print(f"✅ compactado={r['compacted']} mantidos={r['kept']}")
            return
        if args.mcmd == "save-session":
            save_session_summary(args.summary, important=not args.not_important, path=args.path)
            print("✅ resumo de sessão salvo")
            return

    p.print_help()


if __name__ == "__main__":
    main()
