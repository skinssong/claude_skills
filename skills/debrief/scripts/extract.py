#!/usr/bin/env python3
"""Extract a compact digest of the last exchange from a Claude Code transcript.

Deterministic. No model calls. Reads the session JSONL, slices from the last
real user prompt to the end, drops the bulk (base64 blobs, attachments, full
tool outputs), and emits:

  <out>/events.jsonl   one JSON object per kept event, in order
  <out>/digest.md      the same events as readable text, for the analyst pass
  <out>/meta.json      window, timings, signal counts

Usage:
  python3 extract.py                 # current session, last exchange
  python3 extract.py --session <id>
  python3 extract.py --file <path>
  python3 extract.py --out <dir>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"

# Entry types that never carry reasoning or actions worth reviewing.
DROP_TYPES = {"api-request-blob", "api-request", "api-request-shape",
              "attachment", "last-prompt", "custom-title", "agent-name",
              "mode", "atis-latch", "queue-operation", "file-history-snapshot",
              "file-history-delta", "cost-state"}

THINK_CHARS = 900
TEXT_CHARS = 700
TOOL_IN_CHARS = 500
RESULT_CHARS = 400


def die(msg: str) -> None:
    print(f"debrief: {msg}", file=sys.stderr)
    raise SystemExit(1)


def encode_cwd(path: str) -> str:
    """Claude Code stores projects under munged cwd: /a/b_c -> -a-b-c."""
    return "-" + re.sub(r"[^A-Za-z0-9]+", "-", path.strip("/")).strip("-")


def find_transcript(session: str | None, file: str | None, cwd: str) -> Path:
    if file:
        p = Path(file).expanduser()
        if not p.exists():
            die(f"no transcript at {p}")
        return p

    session = session or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if session:
        # The session id is unique on disk, so don't rely on the cwd mapping —
        # it fails when the skill runs from a subdirectory of the project.
        hits = list(PROJECTS.glob(f"*/{session}.jsonl"))
        if hits:
            return max(hits, key=lambda p: p.stat().st_mtime)
        die(f"no transcript for session {session} under {PROJECTS}")

    proj = PROJECTS / encode_cwd(cwd)
    if not proj.is_dir():
        die(f"no transcript directory for {cwd} (looked in {proj})")
    files = sorted(proj.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not files:
        die(f"no transcripts in {proj}")
    return files[-1]


def is_debrief_invocation(entry: dict) -> bool:
    """The `/debrief ...` command turn that started this run."""
    if entry.get("type") != "user":
        return False
    c = (entry.get("message") or {}).get("content")
    return isinstance(c, str) and "<command-name>/debrief" in c


def is_real_prompt(entry: dict) -> bool:
    """A user turn typed by a person, not an injected reminder or a task card."""
    if entry.get("type") != "user":
        return False
    msg = entry.get("message") or {}
    if isinstance(msg.get("content"), list):
        return False  # tool_result carriers are lists
    text = msg.get("content")
    if not isinstance(text, str) or not text.strip():
        return False
    if entry.get("promptSource") == "system":
        return False
    head = text.lstrip()
    if "<command-name>" in text:
        return False  # slash-command turn (e.g. /debrief itself)
    if head.startswith("<system-reminder") or head.startswith("<task-notification"):
        return False
    if head.startswith("<scheduled-task") or head.startswith("<side-sessions-event"):
        return False
    # Hand-backs from subagents arrive as user strings; they are not prompts.
    if head.startswith("Another Claude session sent a message"):
        return False
    return True


def blocks(entry: dict):
    msg = entry.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def clip(s: str, n: int) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def load(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") in DROP_TYPES:
                continue
            if d.get("isSidechain"):
                continue  # subagent work is summarised by its hand-back
            rows.append(d)
    return rows


def slice_exchange(rows: list[dict], match: str | None = None) -> tuple[list[dict], str]:
    """From the chosen real prompt to the next one. Returns (window, prompt text).

    Default is the last prompt (window runs to the end). `match` selects an
    earlier exchange by a substring of its prompt text and cuts at the next
    real prompt, so the window is exactly one exchange.
    """
    prompts = [i for i, d in enumerate(rows) if is_real_prompt(d)]
    if not prompts:
        die(f"no user prompt found{' matching ' + repr(match) if match else ''}")

    if not match:
        start = prompts[-1]
        end = len(rows)
    else:
        chosen = [i for i in prompts
                  if match.lower() in rows[i]["message"]["content"].lower()]
        if not chosen:
            die(f"no user prompt matching {match!r}")
        start = chosen[-1]
        later = [i for i in prompts if i > start]
        end = later[0] if later else len(rows)

    # The /debrief turn belongs to the review, not to the exchange being reviewed.
    for i in range(start + 1, len(rows)):
        if is_debrief_invocation(rows[i]):
            end = min(end, i)
            break

    return rows[start:end], rows[start]["message"]["content"]


def ts(entry: dict) -> str:
    t = entry.get("timestamp") or ""
    return t[11:19] if len(t) > 19 else ""


def _looks_failed(s: str) -> bool:
    """Conservative failure test.

    Grepping for "error" flags every file read that happens to contain the
    word, which is most of them. Only count signals that mean a command
    actually failed.
    """
    if "Traceback (most recent call last)" in s:
        return True
    if s.startswith("Error:") or s.startswith("error:"):
        return True
    for line in s.splitlines():
        line = line.strip()
        if line.startswith(("FAILED", "FAIL ", "AssertionError", "E   ")):
            return True
        # A bare exception line: NameError: ..., ValueError: ...
        if len(line) < 160 and line[:1].isupper() and "Error:" in line:
            for exc in ("Error:", "Exception:"):
                k = line.find(exc)
                if k > 0 and line[:k].replace("_", "").isalnum():
                    return True
        if "exit code" in line.lower() and "non-zero" in line.lower():
            return True
    return False


def event_stream(window: list[dict]) -> list[dict]:
    """Flatten the window into {t, kind, ...} records, pairing tools to results."""
    out: list[dict] = []
    pending: dict[str, int] = {}  # tool_use id -> index in out

    for d in window:
        t = ts(d)
        kind = d.get("type")

        if kind == "user" and is_real_prompt(d):
            out.append({"t": t, "kind": "prompt",
                        "text": clip(d["message"]["content"], TEXT_CHARS * 2)})
            continue

        if kind == "system":
            sub = d.get("subtype")
            if sub in ("api_error", "compact_boundary"):
                err = d.get("error") or {}
                out.append({"t": t, "kind": "system", "subtype": sub,
                            "text": clip(err.get("message", "") or sub, 200)})
            continue

        if kind == "assistant":
            for b in blocks(d):
                bt = b.get("type")
                if bt == "thinking" and (b.get("thinking") or "").strip():
                    out.append({"t": t, "kind": "thinking",
                                "text": clip(b["thinking"], THINK_CHARS)})
                elif bt == "text" and (b.get("text") or "").strip():
                    out.append({"t": t, "kind": "say",
                                "text": clip(b["text"], TEXT_CHARS)})
                elif bt == "tool_use":
                    inp = b.get("input") or {}
                    label = (inp.get("description") or inp.get("command")
                             or inp.get("file_path") or inp.get("skill")
                             or inp.get("pattern") or inp.get("url") or "")
                    out.append({"t": t, "kind": "tool", "id": b.get("id"),
                                "name": b.get("name"),
                                "label": clip(str(label), TOOL_IN_CHARS),
                                "input": inp})
                    pending[b.get("id")] = len(out) - 1
            continue

        if kind == "user":
            for b in blocks(d):
                if b.get("type") != "tool_result":
                    continue
                idx = pending.get(b.get("tool_use_id"))
                if idx is None:
                    continue
                cc = b.get("content")
                s = cc if isinstance(cc, str) else json.dumps(cc)
                err = bool(b.get("is_error")) or _looks_failed(s)
                out.append({"t": t, "kind": "result", "of": idx, "error": err,
                            "bytes": len(s), "text": clip(s, RESULT_CHARS)})
    return out


def plan_history(window: list[dict]) -> list[dict]:
    """The agent's own declared plan, revision by revision.

    Plan items are the closest thing to goals in the transcript: written before
    the work, and updated as it goes. The tool that renders them must not treat
    a self-reported "completed" as evidence — only as a claim.
    """
    plans: list[dict] = []
    current: list[dict] = []
    for d in window:
        if d.get("type") != "assistant":
            continue
        for b in blocks(d):
            if b.get("type") != "tool_use":
                continue
            if b.get("name") != "mcp__ccd_turn__update_plan":
                continue
            inp = b.get("input") or {}
            t = ts(d)
            if "items" in inp:
                current = [{"goal": str(i.get("content", "")).strip(),
                            "status": str(i.get("status", "")).strip() or "pending"}
                           for i in inp["items"] if i.get("content")]
                plans.append({"t": t, "revision": True,
                              "items": [dict(i) for i in current]})
                continue
            # advance / start / done mutate statuses in place.
            done = set(inp.get("done") or [])
            start = inp.get("start")
            advance = bool(inp.get("advance"))
            for n, item in enumerate(current, 1):
                if n in done:
                    item["status"] = "completed"
                elif advance and item["status"] == "in_progress":
                    item["status"] = "completed"
            if start and 1 <= start <= len(current):
                current[start - 1]["status"] = "in_progress"
            if advance:
                nxt = next((i for i, it in enumerate(current)
                            if it["status"] == "pending"), None)
                if nxt is not None:
                    current[nxt]["status"] = "in_progress"
            if (done or start or advance) and current:
                plans.append({"t": t, "revision": False,
                              "items": [dict(i) for i in current]})
    return plans


def signals(events: list[dict], prompt: str) -> dict:
    """Cheap, mechanical facts. The analyst pass uses these; it doesn't invent them."""
    tools = [e for e in events if e["kind"] == "tool"]
    matters = [e for e in events if e["kind"] == "result" and e["error"]]

    # Retry loops: the same command text emitted 2+ times.
    seen: dict[str, int] = {}
    for e in tools:
        if e["name"] != "Bash":
            continue
        cmd = str((e.get("input") or {}).get("command", ""))[:160]
        if cmd:
            seen[cmd] = seen.get(cmd, 0) + 1
    retries = [k for k, n in seen.items() if n >= 2]

    # Probe-then-edit: a measurement run before any edit to a project file.
    # A cheap unknown-retirement pattern, worth showing even when small.
    probe = None
    first_edit = next((i for i, e in enumerate(tools)
                       if e["name"] in ("Edit", "Write")
                       and "/tmp" not in str(e["label"])), None)
    if first_edit is not None:
        for e in tools[:first_edit]:
            label = (e["label"] or "").lower()
            if e["name"] == "Bash" and any(k in label for k in
                                           ("probe", "measure", "bench")):
                probe = e["label"]
                break

    launches = [e for e in tools if e["name"] == "Agent"]
    parallel = False
    if launches:
        # Two launches within 10 seconds is concurrency, not sequential delegation.
        times = [e["t"] for e in launches]
        parallel = len(times) >= 2 and _within(times[0], times[1], 10)

    return {
        "events": len(events),
        "tool_calls": len(tools),
        "tool_names": _counts(e["name"] for e in tools),
        "thinking_blocks": sum(1 for e in events if e["kind"] == "thinking"),
        "errors": [{"t": e["t"], "text": e["text"]} for e in matters],
        "retries": retries,
        "probe_before_edit": probe,
        "agent_launches": len(launches),
        "agents_parallel": parallel,
        "agents": [{"t": e["t"], "label": e["label"]} for e in launches],
        "prompt": clip(prompt, 400),
    }


def _counts(xs) -> dict:
    c: dict[str, int] = {}
    for x in xs:
        c[x] = c.get(x, 0) + 1
    return dict(sorted(c.items(), key=lambda kv: -kv[1]))


def _within(a: str, b: str, seconds: int) -> bool:
    try:
        ta = datetime.strptime(a, "%H:%M:%S")
        tb = datetime.strptime(b, "%H:%M:%S")
    except ValueError:
        return False
    return abs((tb - ta).total_seconds()) <= seconds


def render_digest(events: list[dict], meta: dict) -> str:
    plans = meta.get("plans") or []
    lines = [f"# Exchange digest", "",
             f"- window: {meta['start']} → {meta['end']}",
             f"- events kept: {meta['signals']['events']}",
             f"- tool calls: {meta['signals']['tool_calls']} "
             f"({', '.join(f'{k}×{v}' for k, v in meta['signals']['tool_names'].items())})",
             f"- errors observed: {len(meta['signals']['errors'])}",
             ""]
    if plans:
        first = plans[0]
        last = plans[-1]
        lines += ["## The agent's declared goals", "",
                  "*As written by the agent before and during the work. `completed` is the"
                  " agent's own claim, not evidence — check it against the events below.*", ""]
        lines.append(f"First declared at {first['t']}:")
        for i, it in enumerate(first["items"], 1):
            lines.append(f"  {i}. {it['goal']}  ({it['status']})")
        lines.append("")
        if last is not first:
            lines.append(f"Last state at {last['t']}:")
            for i, it in enumerate(last["items"], 1):
                lines.append(f"  {i}. [{it['status']}] {it['goal']}")
            lines.append("")
        changed = [(i, it) for i, it in enumerate(last["items"], 1)
                   if i > len(first["items"]) or
                   it["status"] != first["items"][i - 1]["status"]
                   or it["goal"] != first["items"][i - 1]["goal"]]
        if changed:
            lines += ["Goals added or re-statused after the first plan: "
                      + ", ".join(f"{i} ({it['status']})" for i, it in changed), ""]
        lines.append(f"Plans revised {len(plans)} times.")
        lines.append("")
    if meta["signals"]["probe_before_edit"]:
        lines.append(f"- probe before any edit: `{meta['signals']['probe_before_edit']}`")
    if meta["signals"]["retries"]:
        lines.append(f"- repeated commands: {len(meta['signals']['retries'])}")
    lines.append("")

    for i, e in enumerate(events):
        k = e["kind"]
        t = e["t"]
        if k == "prompt":
            lines.append(f"## [{t}] USER: {e['text']}")
        elif k == "thinking":
            lines.append(f"[{t}] THINK: {e['text']}")
        elif k == "say":
            lines.append(f"[{t}] SAY: {e['text']}")
        elif k == "tool":
            lines.append(f"[{t}] TOOL {e['name']} #{i}: {e['label']}")
        elif k == "result":
            flag = "ERR" if e["error"] else "ok"
            lines.append(f"[{e['t']}]   → {flag} ({e['bytes']}B): {e['text']}")
        elif k == "system":
            lines.append(f"[{t}] SYSTEM {e.get('subtype')}: {e['text']}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", help="session id (default: newest in this cwd)")
    ap.add_argument("--file", help="explicit transcript path")
    ap.add_argument("--prompt", help="review the exchange whose prompt contains this text")
    ap.add_argument("--out", default=None, help="output directory")
    ap.add_argument("--cwd", default=os.getcwd())
    args = ap.parse_args()

    path = find_transcript(args.session, args.file, args.cwd)
    rows = load(path)
    window, prompt = slice_exchange(rows, args.prompt)
    events = event_stream(window)

    stamps = [r.get("timestamp") for r in window if r.get("timestamp")]
    meta = {
        "session": path.stem,
        "transcript": str(path),
        "start": (stamps[0] if stamps else ""),
        "end": (stamps[-1] if stamps else ""),
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "signals": signals(events, prompt),
        "plans": plan_history(window),
    }

    out = Path(args.out).expanduser() if args.out else Path.cwd() / "debrief" / meta["session"]
    out.mkdir(parents=True, exist_ok=True)

    with (out / "events.jsonl").open("w", encoding="utf-8") as fh:
        for e in events:
            e = dict(e)
            e.pop("input", None)  # keep the digest small; label carries the gist
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    (out / "digest.md").write_text(render_digest(events, meta), encoding="utf-8")
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")

    print(f"debrief: {out}/digest.md")
    print(f"debrief: {meta['signals']['events']} events · "
          f"{meta['signals']['tool_calls']} tool calls · "
          f"{len(meta['signals']['errors'])} errors")


if __name__ == "__main__":
    main()
