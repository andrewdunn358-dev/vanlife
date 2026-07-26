#!/usr/bin/env python3
"""
Serve the site and rebuild it whenever something changes.

Saves the build-then-serve-then-stop-then-rebuild loop. Edit a record or
a stylesheet, reload the browser, see it.

    python3 scripts/serve.py            # http://localhost:24712
    python3 scripts/serve.py --port 0   # any free port

Watches data/sites, scripts and site-assets. Stdlib only, so it runs on
DSM's Python without installing anything. Ctrl-C to stop.
"""
import argparse
import functools
import http.server
import os
import socketserver
import subprocess
import sys
import threading
import time

WATCH = ["data/sites", "scripts", "site-assets"]
IGNORE = (".pyc", "~", ".swp", ".tmp")


def fingerprint(paths):
    """Cheap change detection: every file's size and mtime."""
    out = {}
    for p in paths:
        if not os.path.isdir(p):
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if not d.startswith((".", "__"))]
            for f in files:
                if f.startswith(".") or f.endswith(IGNORE):
                    continue
                fp = os.path.join(root, f)
                try:
                    s = os.stat(fp)
                    out[fp] = (s.st_mtime, s.st_size)
                except OSError:
                    pass
    return out


def build():
    r = subprocess.run([sys.executable, "scripts/build_site.py"],
                       capture_output=True, text=True)
    if r.returncode:
        print("\n  BUILD FAILED")
        print("  " + (r.stderr.strip().replace("\n", "\n  ") or "no output"))
        return False
    tail = [l for l in r.stdout.strip().split("\n") if l.strip()]
    print("  " + (tail[-2] if len(tail) > 1 else tail[-1] if tail else "built"))
    return True


def watcher(interval, stop):
    last = fingerprint(WATCH)
    while not stop.is_set():
        time.sleep(interval)
        now = fingerprint(WATCH)
        if now == last:
            continue
        changed = [f for f in set(now) | set(last) if now.get(f) != last.get(f)]
        last = now
        name = os.path.basename(changed[0]) if changed else "?"
        extra = f" and {len(changed) - 1} more" if len(changed) > 1 else ""
        print(f"\n  changed: {name}{extra}")
        build()


class Quiet(http.server.SimpleHTTPRequestHandler):
    """Serves from an explicit directory.

    SimpleHTTPRequestHandler resolves paths against the process working
    directory at request time, not at construction, so chdir-ing back after
    binding silently serves the wrong tree. The directory argument pins it.
    """

    def log_message(self, fmt, *args):
        # 404s are worth seeing; successful requests are not
        if args and str(args[1]).startswith(("4", "5")):
            sys.stderr.write(f"  {args[1]} {args[0].split()[1]}\n")

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=24712,
                    help="default 24712. Use 0 to let the OS pick a free one.")
    ap.add_argument("--dir", default="site")
    ap.add_argument("--interval", type=float, default=1.0)
    args = ap.parse_args()

    if not os.path.exists("scripts/build_site.py"):
        sys.exit("Run this from the project root.")

    print("building...")
    build()

    if not os.path.isdir(args.dir):
        sys.exit(f"No {args.dir}/ - the build must have failed.")

    root = os.path.abspath(args.dir)
    handler = functools.partial(Quiet, directory=root)
    socketserver.TCPServer.allow_reuse_address = True
    try:
        httpd = socketserver.TCPServer(("", args.port), handler)
    except OSError as e:
        sys.exit(f"Could not bind port {args.port}: {e}\nTry --port 0.")
    port = httpd.server_address[1]

    stop = threading.Event()
    threading.Thread(target=watcher, args=(args.interval, stop), daemon=True).start()

    print(f"\n  http://localhost:{port}")
    print(f"  watching {', '.join(WATCH)} - edit and reload\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        stop.set()
        httpd.server_close()


if __name__ == "__main__":
    main()
