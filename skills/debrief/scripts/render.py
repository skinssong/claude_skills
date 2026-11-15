#!/usr/bin/env python3
"""Render a debrief.json into report.md and mermaid figures.

Validates before it renders: every quote must exist verbatim in the transcript
text. If one doesn't, the run fails — a plausible-sounding sentence that the
agent never said is the failure mode this whole artifact exists to avoid.

Usage:
  python3 render.py --input debrief.json --transcript <session>.jsonl \
                    --out <dir> [--events <events.jsonl>]

debrief.json shape:
{
  "title": "one line",
  "headline": "one or two sentences a reader keeps",
  "phases": [
    {"name": "...",
     "why": "...",                 # what the phase was for
     "why_source": "quoted|inferred",
     "quote": "verbatim text",     # required when why_source == quoted
     "nodes": [
       {"claim": "...",
        "status": "verified|assumed|contradicted|unobserved",
        "evidence": "...",         # short, optional
        "quote": "verbatim",       # optional; validated if present
        "t": "07:53:09"}           # optional timestamp
     ]}
  ],
  "lessons": [{"text": "...", "node": "claim text or phase name"}],
  "open": ["what was never tested"]
}
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

# Renderers run under `python3 -I`, which ignores PYTHONPATH and the script's
# directory on sys.path. Load the sibling module explicitly.
_here = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("figure", _here / "figure.py")
figure_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(figure_mod)


GLYPH = {"verified": "✓", "assumed": "?", "contradicted": "✕", "unobserved": "∅"}
CLASS = {"verified": "verified", "assumed": "assumed",
         "contradicted": "contradicted", "unobserved": "unobserved"}

CLASSDEFS = """\
  classDef verified fill:#e3ecf7,stroke:#2a78d6,stroke-width:1.5px,color:#0b0b0b
  classDef assumed fill:#f6eedd,stroke:#c98500,stroke-width:1.5px,color:#0b0b0b
  classDef contradicted fill:#f7e5e4,stroke:#d03b3b,stroke-width:1.5px,color:#0b0b0b
  classDef unobserved fill:#fcfcfb,stroke:#898781,stroke-width:1.5px,stroke-dasharray:5 3,color:#52514e
  classDef why fill:transparent,stroke:none,color:#52514e
  classDef neutral fill:#fcfcfb,stroke:#52514e,stroke-width:1.5px,color:#0b0b0b"""


def die(msg: str) -> None:
    print(f"debrief: {msg}", file=sys.stderr)
    raise SystemExit(1)


def norm(s: str) -> str:
    """Whitespace-insensitive comparison form."""
    s = s.replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("—", "-").replace("–", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


def transcript_text(path: Path) -> str:
    """All readable text from the transcript, for quote validation."""
    parts: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = d.get("message") or {}
            c = msg.get("content")
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, list):
                for b in c:
                    if not isinstance(b, dict):
                        continue
                    for key in ("text", "thinking"):
                        if isinstance(b.get(key), str):
                            parts.append(b[key])
                    if b.get("type") == "tool_use":
                        parts.append(json.dumps(b.get("input") or {},
                                                ensure_ascii=False))
                    if b.get("type") == "tool_result":
                        cc = b.get("content")
                        parts.append(cc if isinstance(cc, str) else json.dumps(cc))
    return "\n".join(parts)


def check_quotes(data: dict, corpus: str) -> list[str]:
    hay = norm(corpus)
    bad: list[str] = []
    for ph in data.get("phases", []):
        if ph.get("why_source") == "quoted":
            q = ph.get("quote")
            if not q:
                bad.append(f"phase {ph.get('name')!r}: why_source=quoted but no quote")
            elif norm(q) not in hay:
                bad.append(f"phase {ph.get('name')!r}: quote not found — {q[:80]!r}")
        for n in ph.get("nodes", []):
            q = n.get("quote")
            if q and norm(q) not in hay:
                bad.append(f"node {n.get('claim','')[:50]!r}: quote not found — {q[:80]!r}")
    return bad


# A claim is read by someone who has not seen the code. These patterns mark a
# claim that leaked an identifier or a file path out of the implementation.
IDENTIFIER_PATTERNS = [
    (re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b"), "snake_case identifier"),
    (re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b"), "camelCase identifier"),
    (re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b"), "CONSTANT_CASE identifier"),
    (re.compile(r"\b\w+\("), "function call"),
    # A real path has a second segment or a file extension. A bare /command is
    # user vocabulary (the reader typed it), so it is allowed.
    (re.compile(r"(?:^|[\s(])/[^\s/]+/[^\s]+|(?:^|[\s(])/[\w.-]*\.[a-z]{2,4}\b"), "file path"),
    (re.compile(r"\b\w+\.(py|json|jsonl|mmd|svg|md|toml|ya?ml|js|ts)\b"), "file name"),
    (re.compile(r"\bviewBox\b|\bclassDef\b|\bjson\b|\bJSON\b"), "format/property name"),
    # Three-part hyphenated compounds are usually internal vocabulary:
    # "probe-before-edit", "read-modify-write". Explain them or move them out.
    (re.compile(r"\b\w+-\w+-\w+\b"), "internal compound term"),
]

PASSIVE = re.compile(r"\b(is|are|was|were|has been|have been)\s+\w+(ed|en)\b", re.I)
GERUND_START = re.compile(r"^[A-Z][a-z]+ing\b")


def lint_claims(data: dict) -> list[str]:
    """Flag claims that only make sense to someone who has read the code."""
    warns: list[str] = []
    for ph in data.get("phases", []):
        for n in ph.get("nodes", []):
            claim = n.get("claim", "")
            for rx, label in IDENTIFIER_PATTERNS:
                m = rx.search(claim)
                if m:
                    warns.append(f"{label} {m.group(0)!r} in claim {claim[:60]!r}")
                    break
            if len(claim) > 120:
                warns.append(f"claim is {len(claim)} chars (clips at 120): {claim[:60]!r}…")
            if PASSIVE.search(claim):
                warns.append(f"passive voice hides the actor: {claim[:60]!r}")
            if GERUND_START.match(claim.strip()):
                warns.append(f"gerund subject reads like a code review: {claim[:60]!r}")
    return warns


CLAIM_CHARS = 120
WHY_CHARS = 150


def clip(s: str, n: int) -> str:
    s = " ".join((s or "").split())
    if len(s) <= n:
        return s
    cut = s[: n - 1]
    if " " in cut[int(n * 0.6):]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:") + "…"


def label(text: str, extra: str | None = None) -> str:
    """Mermaid-safe label: quoted, with <br/> for the second line."""
    text = (text or "").replace('"', "'").strip()
    if extra:
        extra = extra.replace('"', "'").strip()
        return f'"{text}<br/>{extra}"'
    return f'"{text}"'


FIGURE_NODES_PER_PHASE = 3


def figure_nodes(ph: dict) -> list[dict]:
    """Nodes that earn a place in the figure.

    The table in the report carries every node; the figure carries the ones a
    reader should see at a glance. Prefer the instructive statuses, then keep
    the analyst's order.
    """
    nodes = ph.get("nodes", [])
    if len(nodes) <= FIGURE_NODES_PER_PHASE:
        return nodes
    rank = {"contradicted": 0, "unobserved": 1, "assumed": 2, "verified": 3}
    keep = sorted(range(len(nodes)),
                  key=lambda i: (rank.get(nodes[i].get("status"), 9), i)
                  )[:FIGURE_NODES_PER_PHASE]
    return [nodes[i] for i in sorted(keep)]


def build_mermaid(data: dict, parallel: bool) -> str:
    lines = ["%%{init: {\"flowchart\": {\"wrappingWidth\": 190, \"nodeSpacing\": 30, "
             "\"rankSpacing\": 30, \"htmlLabels\": true}} }%%",
             "flowchart TB"]
    # The frame: what was asked, and what came out. A reader should be able to
    # tell what the exchange was for without reading a single phase.
    if data.get("ask"):
        lines.append(f'  A0[{label("Asked — " + clip(data["ask"], 100))}]')
        lines.append("  class A0 neutral")
    # Goals, if the agent declared a plan. Rendered as a row so a reader sees
    # what the work was FOR before seeing the work.
    goals = data.get("goals") or []
    if goals:
        # One node per goal, chained with invisible links so they stack in the
        # order the agent declared them. Without the links mermaid packs them
        # into a grid and the order — part of the meaning — is lost.
        lines.append('  subgraph G["What it set out to do"]')
        lines.append("    direction TB")
        prev = None
        for gi, g in enumerate(goals, 1):
            st = g.get("status", "unobserved")
            glyph = GLYPH.get(st, "∅")
            gid = f"G{gi}"
            lines.append(f"    {gid}[{label(f'{gi}. ' + glyph + ' ' + clip(g.get('goal',''), CLAIM_CHARS))}]")
            lines.append(f"    class {gid} {CLASS.get(st, 'unobserved')}")
            if prev:
                lines.append(f"    {prev} ~~~ {gid}")
            prev = gid
        lines.append("  end")

    node_ids: list[tuple[str, list[str]]] = []  # (phase id, node ids)
    for pi, ph in enumerate(data.get("phases", []), 1):
        pid = f"P{pi}"
        name = (ph.get("name") or f"phase {pi}").replace('"', "'")
        lines.append(f'  subgraph {pid}["{pi} · {name}"]')
        lines.append("    direction LR")
        ids = []
        for ni, n in enumerate(figure_nodes(ph), 1):
            nid = f"N{pi}_{ni}"
            ids.append(nid)
            st = n.get("status", "unobserved")
            glyph = GLYPH.get(st, "∅")
            body = clip(n.get("claim", ""), CLAIM_CHARS)
            gate = n.get("gate") or {}
            chosen = next((o.get("text", "") for o in gate.get("options", [])
                           if (o.get("verdict") or "").strip() == "chosen"), "")
            if chosen:
                body = clip(body + " → " + chosen, CLAIM_CHARS + 40)
            lines.append(f"    {nid}[{label(glyph + ' ' + body)}]")
            lines.append(f"    class {nid} {CLASS.get(st, 'unobserved')}")
        if ph.get("why"):
            wid = f"W{pi}"
            src = ph.get("why_source", "inferred")
            prefix = "Why" if src == "quoted" else "Why (inferred)"
            lines.append(f"    {wid}[{label(prefix + ' — ' + clip(ph['why'], WHY_CHARS))}]")
            lines.append(f"    class {wid} why")
            if ids:
                lines.append(f"    {ids[-1]} ~~~ {wid}")
        lines.append("  end")
        node_ids.append((pid, ids))

    # Chain phases (subgraph-to-subgraph keeps each lane's LR row intact).
    for i in range(len(node_ids) - 1):
        lines.append(f"  {node_ids[i][0]} --> {node_ids[i+1][0]}")

    if data.get("ask") and goals:
        lines.append("  A0 --> G")
    elif data.get("ask") and node_ids:
        lines.append(f"  A0 --> {node_ids[0][0]}")
    if goals and node_ids:
        lines.append(f"  G --> {node_ids[0][0]}")
    if data.get("delivered") and node_ids:
        st = data.get("outcome_status", "unobserved")
        glyph = GLYPH.get(st, "∅")
        body = clip(data["delivered"], 160)
        out_line = f"{glyph} Delivered — {body}"
        lines.append(f'  Z0[{label(out_line)}]')
        lines.append(f"  class Z0 {CLASS.get(st, 'unobserved')}")
        lines.append(f"  {node_ids[-1][0]} --> Z0")

    lines.append(CLASSDEFS)
    return "\n".join(lines)


def build_lanes(data: dict) -> str | None:
    """Optional figure: one lane per subagent, when the exchange used several.

    Only emitted when debrief.json carries an "agents" array. A subagent's
    finding is `assumed` here until the parent verified it — that is the rule,
    so the default status is assumed unless the analyst says otherwise.
    """
    agents = data.get("agents") or []
    if len(agents) < 2:
        return None
    lines = ["%%{init: {\"flowchart\": {\"wrappingWidth\": 210, \"nodeSpacing\": 20, "
             "\"rankSpacing\": 34, \"htmlLabels\": true}} }%%",
             "flowchart TB",
             f'  D0["{data.get("dispatch", "Dispatch")}"]']
    for i, a in enumerate(agents, 1):
        name = (a.get("name") or f"agent {i}").replace('"', "'")
        when = f" · {a['back']}" if a.get("back") else ""
        st = a.get("status", "assumed")
        body = clip(a.get("finding", ""), CLAIM_CHARS)
        lines += [f'  subgraph L{i}["{name}{when}"]', "    direction TB",
                  f"    A{i}[{label(GLYPH.get(st, '?') + ' ' + body)}]",
                  f"    class A{i} {CLASS.get(st, 'assumed')}", "  end",
                  f"  D0 --> L{i}"]
    lines.append(f'  C["{data.get("consolidate", "Consolidate")}"]')
    lines += [f"  L{i} --> C" for i in range(1, len(agents) + 1)]
    lines.append(CLASSDEFS)
    return "\n".join(lines)


REQUIRED = ("ask", "delivered", "checked", "outcome_status")


def check_goals(data: dict, meta: dict) -> list[str]:
    """Warn when the exchange declared a plan but the report has no goals."""
    warns = []
    if (meta.get("plans") or []) and not data.get("goals"):
        warns.append("the agent declared a plan but the report has no `goals` — "
                     "a reader cannot tell what the actions were for")
    for g in data.get("goals") or []:
        if g.get("status") not in GLYPH:
            warns.append(f"goal {g.get('goal','')[:50]!r}: status must be one of "
                         f"{', '.join(GLYPH)}")
    return warns


def check_gates(data: dict) -> list[str]:
    """A gate is a fork: exactly one option taken, the rest set aside."""
    warns: list[str] = []
    for ph in data.get("phases", []):
        for n in ph.get("nodes", []):
            g = n.get("gate")
            if not g:
                continue
            name = n.get("claim", "")[:50]
            opts = g.get("options") or []
            chosen = [o for o in opts
                      if (o.get("verdict") or "").strip() == "chosen"]
            if not opts:
                warns.append(f"gate {name!r}: no options — a fork with one side is a "
                             f"plain node")
            elif len(chosen) != 1:
                warns.append(f"gate {name!r}: expected exactly one option with verdict "
                             f"'chosen', found {len(chosen)}")
            for o in opts:
                v = (o.get("verdict") or "").strip()
                if v not in ("chosen", "rejected"):
                    warns.append(f"gate {name!r}: verdict {v!r} must be 'chosen' or "
                                 f"'rejected'")
    return warns


def check_frame(data: dict) -> list[str]:
    """The report must say what was asked, what exists, and what was run."""
    bad = [f"missing required field {k!r}" for k in REQUIRED if not data.get(k)]
    st = data.get("outcome_status")
    if st and st not in GLYPH:
        bad.append(f"outcome_status {st!r} is not one of {', '.join(GLYPH)}")
    return bad


def render_report(data: dict, meta: dict, mermaid: str) -> str:
    sig = meta.get("signals", {})
    start = (meta.get("start") or "")[11:19]
    end = (meta.get("end") or "")[11:19]
    out = [f"# {data.get('title', 'Exchange debrief')}", "",
           f"*{start} → {end} · {sig.get('tool_calls', '?')} tool calls · "
           f"{len(sig.get('errors', []))} errors · "
           f"{sig.get('thinking_blocks', '?')} reasoning blocks*", "",
           "**Key** — ✓ verified (an observation backs it) · ? assumed (nothing tests it) · "
           "✕ contradicted (an observation disagrees) · ∅ unobserved (no evidence either way)",
           ""]

    st = data.get("outcome_status", "unobserved")
    out += ["| | |", "|---|---|",
            f"| **Asked** | {data.get('ask', '')} |"]
    goals = data.get("goals") or []
    if goals:
        out.append("| **Goals** | " + "<br>".join(
            f"{GLYPH.get(g.get('status'), '∅')} {g.get('goal','')}"
            + (f" · {g['at']}" if g.get("at") else " · *no moment in the log*")
            for g in goals) + " |")
    out += [f"| **Delivered** | {data.get('delivered', '')} |",
            f"| **{GLYPH.get(st, '∅')} Checked** | {data.get('checked', '')} |",
            ""]
    if goals:
        out += ["*A goal marked ? was claimed done by the agent but not observed here;"
                " ∅ was never attempted; ✕ was abandoned or contradicted.*", ""]

    if data.get("headline"):
        out += [data["headline"], ""]

    out += ["![Exchange timeline](figure.svg)", ""]
    out += ["*Time runs left to right; dots on the line held, branches are where the work"
            " deviated, diamonds are forks where one option was taken and the others set"
            " aside. Full claims and evidence are in the tables below.*", ""]

    out += ["## Decisions, phase by phase", ""]
    for pi, ph in enumerate(data.get("phases", []), 1):
        out.append(f"### {pi}. {ph.get('name', '')}")
        out.append("")
        src = ph.get("why_source", "inferred")
        why = ph.get("why", "")
        if src == "quoted" and ph.get("quote"):
            out.append(f"*Why — “{ph['quote']}”*")
        else:
            out.append(f"*Why (inferred) — {why}*")
        out.append("")
        out += ["| | Claim | Evidence |", "|---|---|---|"]
        prev_task = None
        for n in ph.get("nodes", []):
            st = n.get("status", "unobserved")
            claim = n.get("claim", "")
            trig = n.get("trigger")
            if trig:
                claim = f"*because {trig}*<br>{claim}"
            task = n.get("task")
            if task and task != prev_task:
                out.append(f"| | **{task}** | |")
            prev_task = task
            if n.get("outcome"):
                claim += f" — **{n['outcome']}**"
            out.append(f"| {GLYPH.get(st,'∅')} | {claim} | {n.get('evidence','')} |")
            gate = n.get("gate")
            if gate:
                for opt in gate.get("options", []):
                    v = (opt.get("verdict") or "").strip()
                    text = opt.get("text", "")
                    why = (opt.get("why") or "").strip()
                    if v == "chosen":
                        line = f"↳ **chose** {text}"
                        mark = "✓"
                    else:
                        line = f"↳ ~~{text}~~"
                        mark = "✕"
                    if why:
                        line += f" — {why}"
                    src = {"quoted": "stated", "inferred": "*inferred*"}.get(
                        opt.get("source"), opt.get("source") or "")
                    out.append(f"| {mark} | {line} | {src} |")
        out.append("")

    if data.get("lessons"):
        out += ["## What to carry forward", ""]
        for i, l in enumerate(data["lessons"], 1):
            out.append(f"{i}. {l.get('text','')}"
                       + (f" — *{l['node']}*" if l.get("node") else ""))
        out.append("")

    if data.get("open"):
        out += ["## Still open", ""]
        for o in data["open"]:
            out.append(f"- {o}")
        out.append("")

    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="debrief.json")
    ap.add_argument("--transcript", required=True, help="session .jsonl")
    ap.add_argument("--meta", help="meta.json from extract.py")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--trace", action="store_true",
                    help="also render an interactive trace.html of the same exchange")
    args = ap.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    frame = check_frame(data)
    if frame:
        die("report frame is incomplete:\n  " + "\n  ".join(frame))

    meta = {}
    if args.meta and Path(args.meta).exists():
        meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))

    corpus = transcript_text(Path(args.transcript))
    bad = check_quotes(data, corpus)
    if bad:
        die("quote validation failed:\n  " + "\n  ".join(bad))

    warns = lint_claims(data) + check_goals(data, meta) + check_gates(data)
    if warns:
        print("debrief: report warnings:", file=sys.stderr)
        for w in warns:
            print(f"  ! {w}", file=sys.stderr)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    parallel = bool((meta.get("signals") or {}).get("agents_parallel"))
    mmd = build_mermaid(data, parallel)
    (out / "figure.mmd").write_text(mmd + "\n", encoding="utf-8")

    # The timeline is the figure a reader actually looks at: time is position,
    # deviations are branches. The mermaid source stays alongside for editing.
    svg = figure_mod.render(data)
    (out / "figure.svg").write_text(svg, encoding="utf-8")

    lanes = build_lanes(data)
    if lanes:
        (out / "lanes.mmd").write_text(lanes + "\n", encoding="utf-8")

    report_md = render_report(data, meta, mmd)
    (out / "report.md").write_text(report_md, encoding="utf-8")

    print(f"debrief: {out}/report.md    (markdown source)")
    print(f"debrief: {out}/figure.svg    (figure alone)")
    print(f"debrief: {out}/figure.mmd    (editable source)")
    if lanes:
        print(f"debrief: {out}/lanes.mmd")
    print("debrief: quotes verified against the transcript")

    if args.trace:
        import subprocess
        r = subprocess.run([sys.executable, "-I", str(_here / "trace.py"),
                            "--transcript", args.transcript, "--out", str(out)])
        if r.returncode != 0:
            print("debrief: trace view failed; the report above is unaffected",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
