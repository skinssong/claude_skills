#!/usr/bin/env python3
"""Optional: an interactive trace view of the same exchange.

The report answers "what should I learn"; this answers "show me the actual
calls". It runs the vendored trajectory-tree viewer over the transcript and
copies the self-contained HTML next to the report, so the two can be read
side by side.

Off by default: it is a 60 MB dependency and a multi-megabyte output, and most
debriefs are read once. Pass --trace to render.py, or run this directly.

Usage:
  python3 trace.py --transcript <session>.jsonl --out <debrief dir>
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The viewer is 37 MB of JS, so it lives outside the skill directory and is
# installed on demand. Override with DEBRIEF_TRACE_HOME.
TRACE_HOME = Path(os.environ.get("DEBRIEF_TRACE_HOME")
                  or Path.home() / ".local" / "share" / "debrief" / "trajectory-tree")
VIEWER = TRACE_HOME / "scripts" / "trajectory-view.mjs"


def die(msg: str) -> None:
    print(f"debrief: {msg}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--host", default="claude")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--serve", action="store_true",
                    help="serve the result on localhost instead of relying on file://")
    args = ap.parse_args()

    transcript = Path(args.transcript).expanduser().resolve()
    if not transcript.exists():
        die(f"no transcript at {transcript}")
    if not VIEWER.exists():
        die(f"trajectory-tree not installed at {TRACE_HOME}\n"
            f"  git clone --depth 1 https://github.com/goatliamia/trajectory-tree.git {TRACE_HOME}\n"
            f"  npm ci --prefix {TRACE_HOME / 'plugin' / 'portable-tools'} --ignore-scripts")
    node = shutil.which("node")
    if not node:
        die("node not found on PATH (the trace view needs Node 18+, 20+ preferred)")

    proc = subprocess.run(
        [node, str(VIEWER), "--host", args.host, "--file", str(transcript),
         "--lang", args.lang],
        capture_output=True, text=True, timeout=300,
    )
    line = next((l for l in proc.stdout.splitlines() if l.startswith("{")), None)
    if proc.returncode != 0 or not line:
        die(f"trajectory-tree failed:\n{proc.stderr.strip()[:800]}")
    meta = json.loads(line)
    if not meta.get("ok"):
        die(f"trajectory-tree reported failure: {line[:400]}")

    src = Path(meta["output"])
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "trace.html"
    shutil.copyfile(src, dest)
    t = meta.get("totals", {})
    print(f"debrief: {dest}  ({dest.stat().st_size // 1024} KB · "
          f"{t.get('turns','?')} turns · {t.get('calls','?')} calls)")

    if args.serve:
        # A 3+ MB page is slow or blocked in some in-app previews; a localhost
        # URL sidesteps that and matches what the viewer was built for.
        import http.server
        import functools
        import threading
        handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                    directory=str(out))
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"debrief: http://127.0.0.1:{port}/trace.html  (Ctrl-C to stop)")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    else:
        print(f"debrief: open it with:  open \"{dest}\"")


if __name__ == "__main__":
    main()
