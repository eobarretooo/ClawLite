from __future__ import annotations
import argparse
import platform
import shutil
import sys

from clawlite.auth import PROVIDERS, auth_login, auth_logout, auth_status
from clawlite.configure_menu import run_configure_menu
from clawlite.core.agent import run_task
from clawlite.core.memory import add_note, search_notes
from clawlite.onboarding import run_onboarding
from clawlite.gateway.server import run_gateway


def cmd_doctor() -> int:
    print("ClawLite Doctor")
    print("python:", sys.version.split()[0])
    print("platform:", platform.platform())
    print("git:", "ok" if shutil.which("git") else "missing")
    print("curl:", "ok" if shutil.which("curl") else "missing")
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
        run_onboarding()
        return
    if args.cmd == "configure":
        run_configure_menu()
        return
    if args.cmd == "gateway":
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
