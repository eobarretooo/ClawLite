#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time

from clawlite.runtime.reddit import monitor_mentions_once


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=int, default=3600)
    args = p.parse_args()
    while True:
        try:
            result = monitor_mentions_once()
            print(f"checked={len(result['checked_subreddits'])} new={result['new_mentions']}")
        except Exception as e:
            print("monitor error:", e)
        time.sleep(max(60, args.interval))


if __name__ == "__main__":
    main()
