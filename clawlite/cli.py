from __future__ import annotations
import argparse
import platform
import shutil
import sys
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

    gw = sub.add_parser("gateway")
    gw.add_argument("--host", default=None)
    gw.add_argument("--port", type=int, default=None)

    args = p.parse_args()

    if args.cmd == "doctor":
        raise SystemExit(cmd_doctor())
    if args.cmd == "run":
        print(run_task(args.prompt))
        return
    if args.cmd == "onboarding":
        run_onboarding()
        return
    if args.cmd == "gateway":
        run_gateway(args.host, args.port)
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
