#!/usr/bin/env python3
"""Start one local service, then open its dedicated application window."""
import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

from app import BASE, SERVICE, runtime_dir


def running(state):
    try:
        data = json.loads(state.read_text())
        url = data["url"]
        if not url.startswith("http://127.0.0.1:") or data.get("app") != str(BASE):
            return None
        with urllib.request.urlopen(url + "/api/health", timeout=1) as resp:
            return url if json.load(resp).get("service") == SERVICE else None
    except (OSError, ValueError, KeyError):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--task")
    parser.add_argument('--skill')
    parser.add_argument('--source')
    parser.add_argument('--slug')
    args = parser.parse_args()
    run = runtime_dir()
    with (run / "launch.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = run / "state.json"
        url = running(state)
        if not url:
            with (run / "app.log").open("a") as log:
                subprocess.Popen([sys.executable, str(BASE / "app.py")], cwd=BASE,
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            for _ in range(70):
                time.sleep(0.1)
                url = running(state)
                if url:
                    break
        if not url:
            raise SystemExit(f"技能小站未能启动，请查看 {run / 'app.log'}")
    print(url, flush=True)
    if args.no_open:
        return
    params = {}
    if args.task: params['job'] = args.task
    if args.skill: params['skill'] = args.skill
    if args.source and args.slug: params.update(source=args.source,slug=args.slug)
    if params: url += '/?'+urllib.parse.urlencode(params)
    browser = next((shutil.which(name) for name in ("google-chrome", "chromium", "chromium-browser") if shutil.which(name)), None)
    if browser:
        subprocess.Popen([browser, f"--app={url}", "--class=skill-station", "--window-size=1260,880"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    else:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


if __name__ == "__main__":
    main()
