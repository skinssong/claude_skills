#!/usr/bin/env python3
"""Draw the debrief figure: time on the x-axis, deviations as branches.

A reader's first question is "what was it trying to do, and where did it go
sideways". A horizontal spine answers both — position is time, a branch is a
departure from the plan, and the dots on the line are what held. A vertical
box stack answers neither, which is why this replaced the mermaid flowchart.

No dependencies. Deterministic: same debrief.json, same SVG.
"""
from __future__ import annotations

from datetime import datetime

W = 1560
PAD_L, PAD_R = 172, 28
LANE_H = 60
CHAR_W = 6.9

COL = {
    "verified": ("#2a78d6", "#e3ecf7", "#0b0b0b"),
    "assumed": ("#c98500", "#f6eedd", "#0b0b0b"),
    "contradicted": ("#d03b3b", "#f7e5e4", "#0b0b0b"),
    "unobserved": ("#898781", "#fcfcfb", "#52514e"),
}
GLYPH = {"verified": "✓", "assumed": "?", "contradicted": "✕", "unobserved": "∅"}
INK, MUTED, HAIR = "#0b0b0b", "#52514e", "#c3c2b7"
# Milestones and other structure: neutral ink, never a status hue.
NEUTRAL = ("#52514e", "#fcfcfb", "#0b0b0b")


def _secs(t) -> int | None:
    try:
        p = datetime.strptime(str(t or "").strip(), "%H:%M:%S")
        return p.hour * 3600 + p.minute * 60 + p.second
    except ValueError:
        return None


def _clock(s: int) -> str:
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _wrap(s: str, chars: int, max_lines: int) -> list[str]:
    words, lines, cur = (s or "").split(), [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if len(cand) > chars and cur:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                cur = ""
                break
        else:
            cur = cand
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines or [""]


def _box(x: float, y: float, lines: list[str], stroke: str, fill: str, ink: str,
         pre: list[str] | None = None):
    pre = pre or []
    allw = max([len(l) for l in lines] + [len(l) for l in pre] or [0])
    w = max(allw * CHAR_W + 16, 90)
    h = 14 * len(lines) + 12 * len(pre) + 11
    out = [f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="4" '
           f'fill="{fill}" stroke="{stroke}" stroke-width="1"/>']
    ry = y + 14
    for l in pre:
        out.append(f'<text x="{x+8:.0f}" y="{ry:.0f}" font-size="9" fill="{MUTED}">'
                   f'{_esc(l)}</text>')
        ry += 12
    for l in lines:
        out.append(f'<text x="{x+8:.0f}" y="{ry+1:.0f}" font-size="10.5" '
                   f'fill="{ink}">{_esc(l)}</text>')
        ry += 14
    return out, w, h


def render(debrief: dict) -> str:
    """Return the figure as an SVG document."""
    phases = debrief.get("phases", [])
    goals = debrief.get("goals", [])

    stamps = sorted(s for s in (_secs(n.get("t")) for ph in phases
                                for n in ph.get("nodes", [])) if s is not None)
    t0, t1 = (stamps[0], stamps[-1]) if len(stamps) >= 2 else (0, 1)
    span = max(1, t1 - t0)
    x0, x1 = PAD_L, W - PAD_R

    def px(t, frac: float) -> float:
        f = (t - t0) / span if t is not None else frac
        return x0 + max(0.0, min(1.0, f)) * (x1 - x0)

    body: list[str] = []
    y = 24.0

    # Milestones: a goal that the log timestamps earns a station on the axis.
    # Goals without a verified moment are listed separately rather than placed
    # at a guessed position — an unearned marker would be the exact failure the
    # colour scheme exists to avoid.
    milestones = [(g, _secs(g.get("at"))) for g in goals]
    milestones = [(g, t) for g, t in milestones if t is not None]
    unplaced = [g for g in goals if _secs(g.get("at")) is None]

    # Place them first (placement only depends on x), so the headroom above the
    # axis can be sized to the rows actually used.
    ms_placements = []
    ms_rows = [-1e9, -1e9, -1e9]
    for gi, (g, t) in enumerate(milestones, 1):
        label = g.get("goal", "")
        lines = _wrap(label, 28, 2)
        w = max(len(l) for l in lines) * CHAR_W + 14
        h = 13 * len(lines) + 9
        mx = px(t, 0)
        bx = min(max(mx - w / 2, x0), x1 - w)
        row = next((i for i, e in enumerate(ms_rows) if bx > e + 8), None)
        if row is None:
            row = min(range(len(ms_rows)), key=lambda i: ms_rows[i])
        ms_rows[row] = bx + w
        ms_placements.append((g, mx, bx, w, h, row, lines))
    ms_head = 0
    if ms_placements:
        tallest = max(pl[4] for pl in ms_placements)
        ms_head = 160 + (max(pl[5] for pl in ms_placements) + 1) * (tallest + 10)

    # ---- axis -------------------------------------------------------------
    axis_y = y + 48 + ms_head
    body.append(f'<text x="16" y="{axis_y+4:.0f}" font-size="11" fill="{MUTED}">time</text>')
    for k in range(5):
        tx = x0 + k * (x1 - x0) / 4
        body.append(f'<line x1="{tx:.0f}" y1="{axis_y-26:.0f}" x2="{tx:.0f}" '
                    f'y2="{axis_y+6:.0f}" stroke="{HAIR}" stroke-width="1"/>')
        body.append(f'<text x="{tx:.0f}" y="{axis_y+20:.0f}" font-size="10" fill="{MUTED}" '
                    f'text-anchor="middle">{_clock(t0 + int(k * span / 4))}</text>')
    body.append(f'<line x1="{x0}" y1="{axis_y:.0f}" x2="{x1}" y2="{axis_y:.0f}" '
                f'stroke="{HAIR}" stroke-width="2"/>')

    # ---- milestones drawn ---------------------------------------------------
    for g, mx, bx, w, h, row, lines in ms_placements:
        st = g.get("status", "unobserved")
        # A milestone is structure, not a claim: neutral ink, never a status
        # hue. Only the glyph carries the outcome, so a goal tile cannot be
        # mistaken for an action below the line.
        stroke, fill, ink = NEUTRAL
        by = axis_y - 132 - row * (h + 10)
        body.append(f'<path d="M{mx:.0f},{axis_y-7:.0f} L{mx+5:.0f},{axis_y+1:.0f} '
                    f'L{mx:.0f},{axis_y+9:.0f} L{mx-5:.0f},{axis_y+1:.0f} Z" '
                    f'fill="#ffffff" stroke="{stroke}" stroke-width="1.6"/>')
        body.append(f'<line x1="{mx:.0f}" y1="{axis_y-8:.0f}" x2="{mx:.0f}" '
                    f'y2="{by+h:.0f}" stroke="{stroke}" stroke-width="1" opacity="0.5"/>')
        body.append(f'<rect x="{bx:.0f}" y="{by:.0f}" width="{w:.0f}" height="{h:.0f}" '
                    f'rx="3" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
        for li, l in enumerate(lines):
            body.append(f'<text x="{bx+7:.0f}" y="{by+12+li*12:.0f}" font-size="9.5" '
                        f'fill="{ink}">{GLYPH[st] + " " if li == 0 else ""}'
                        f'{_esc(l)}</text>')

    if unplaced:
        for gi, g in enumerate(unplaced, 1):
            st = g.get("status", "unobserved")
            body.append(f'<text x="{x0 - 150:.0f}" y="{axis_y + 40 + (gi-1)*13:.0f}" '
                        f'font-size="9" fill="{MUTED}">{GLYPH[st]} '
                        f'{_esc(g.get("goal", "")[:38])} (no moment in the log)</text>')

    # ---- phases on the spine ----------------------------------------------
    n = max(1, len(phases))
    row_right = [-1e9, -1e9, -1e9]
    for pi, ph in enumerate(phases, 1):
        ts = [t for t in (_secs(x.get("t")) for x in ph.get("nodes", [])) if t is not None]
        xa = px(min(ts), (pi - 1) / n) if ts else px(None, (pi - 1) / n)
        xb = px(max(ts), pi / n) if ts else px(None, pi / n)
        xb = max(xb, xa + 60)
        body.append(f'<rect x="{xa:.0f}" y="{axis_y-4:.0f}" width="{xb-xa:.0f}" height="8" '
                    f'rx="3" fill="{MUTED}" opacity="0.28"/>')
        lines = _wrap(f'{pi} · {ph.get("name", "")}', 26, 2)
        label_w = max(len(l) for l in lines) * CHAR_W * 0.95
        cx = (xa + xb) / 2
        label_row = next((i for i, e in enumerate(row_right) if cx - label_w / 2 > e + 6), None)
        if label_row is None:
            label_row = min(range(3), key=lambda i: row_right[i])
        row_right[label_row] = cx + label_w / 2
        base = axis_y - 34 - label_row * 26
        for li, l in enumerate(lines):
            body.append(f'<text x="{cx:.0f}" y="{base+li*12:.0f}" font-size="10.5" '
                        f'text-anchor="middle" fill="{MUTED}">{_esc(l)}</text>')

    # ---- nodes and branches -----------------------------------------------
    # Nodes sharing a `task` value are attempts at the same thing. They render
    # as one ladder hanging from the spine, in time order, so a failure is
    # followed by what came of the next attempt — not left as a lone red dot.
    nodes = [(pi, nd) for pi, ph in enumerate(phases, 1) for nd in ph.get("nodes", [])]
    # A gate is a fork on the spine, not a deviation, so it is kept out of the
    # branch lanes and placed first: its box gets a top lane near the axis and
    # the branches stack below it.
    gate_nodes = [(pi, nd) for pi, nd in nodes if nd.get("gate")]
    plain = [(pi, nd) for pi, nd in nodes if not nd.get("gate")]
    groups: dict[str, list[tuple[int, dict]]] = {}
    singles: list[tuple[int, dict]] = []
    for item in plain:
        task = (item[1].get("task") or "").strip()
        if task:
            groups.setdefault(task, []).append(item)
        else:
            singles.append(item)

    branch_y0 = axis_y + 42
    total_nodes = max(1, len(plain))
    lane_end = [x0 - 10] * 6
    lane_h = [0.0] * 6
    lanes_used: list[int] = []
    items: list[dict] = []

    def lane_for(bx: float, w: float, h: float) -> int:
        lane = next((i for i, e in enumerate(lane_end) if e <= bx - 18), None)
        if lane is None:
            lane = min(range(len(lane_end)), key=lambda i: lane_end[i])
        lane_end[lane] = bx + w
        lane_h[lane] = max(lane_h[lane], h)
        if lane not in lanes_used:
            lanes_used.append(lane)
        return lane

    # ---- decision gates (placed first: top lanes) -------------------------
    # A gate is a fork: one option taken, others dropped. It gets a neutral
    # diamond on the spine and a box listing what was weighed. The rejected
    # options are never status-coloured — they were declined, not disproved.
    gate_marks: list[dict] = []
    for pi, nd in gate_nodes:
        g = nd["gate"]
        mx = px(_secs(nd.get("t")), 0.5)
        rows = []
        glyph = GLYPH.get(nd.get("status", "unobserved"), "∅")
        q = f'{glyph} {g.get("question", "") or nd.get("claim", "")}'
        rows.append({"lines": _wrap(q, 54, 3), "kind": "question"})
        for opt in g.get("options", []):
            verdict = (opt.get("verdict") or "").strip()
            glyph = "✓" if verdict == "chosen" else "✕"
            text = f"{glyph} {opt.get('text','')}"
            why = (opt.get("why") or "").strip()
            if why:
                text += f" — {why}"
            rows.append({"lines": _wrap(text, 54, 3), "kind": verdict or "rejected"})
        w = max(max(len(l) for l in r["lines"]) for r in rows) * CHAR_W + 30
        h = sum(14 * len(r["lines"]) + 8 for r in rows) + 6
        bx = min(max(mx - w / 2, x0 + 4), x1 - w)
        gate_marks.append({"mx": mx, "bx": bx, "w": w, "h": h, "rows": rows,
                           "status": nd.get("status", "unobserved"),
                           "lane": lane_for(bx, w, h)})

    # ---- attempts ladders -------------------------------------------------
    for task, chain in groups.items():
        chain.sort(key=lambda it: _secs(it[1].get("t")) or 0)
        xa = px(_secs(chain[0][1].get("t")), 0.3)
        xb = px(_secs(chain[-1][1].get("t")), 0.35)

        rows = []
        for gi, (pi, nd) in enumerate(chain, 1):
            st = nd.get("status", "unobserved")
            stroke, fill, ink = COL[st]
            outcome = ""
            if gi == len(chain):
                if st == "verified":
                    outcome = "resolved"
                elif nd.get("abandoned"):
                    outcome = "abandoned"
                elif st == "contradicted":
                    outcome = "unresolved"
            text = f'try {gi} · {GLYPH[st]} {nd.get("claim", "")}' + (
                f' — {outcome}' if outcome else "")
            trig = (nd.get("trigger") or "").strip()
            rows.append({"lines": _wrap(text, 52, 3), "stroke": stroke, "fill": fill,
                         "ink": ink, "t": nd.get("t", ""),
                         "pre": _wrap(f"because {trig}", 52, 2) if trig else []})

        w = max(max([len(l) for r in rows for l in r["lines"] + r["pre"]] or [0]) * CHAR_W + 34, 200)
        h = sum(14 * len(r["lines"]) + 12 * len(r["pre"]) + (26 if r["t"] else 16) for r in rows)
        bx = min(max(xa + 14, x0 + 4), x1 - w)
        items.append({"kind": "ladder", "bx": bx, "w": w, "h": h, "rows": rows,
                      "xa": xa, "xb": max(xb, xa + 10),
                      "lane": lane_for(bx, w, h)})

    # ---- single nodes -----------------------------------------------------
    for k, (pi, nd) in enumerate(singles):
        st = nd.get("status", "unobserved")
        stroke, fill, ink = COL[st]
        nx = px(_secs(nd.get("t")), (k + 0.5) / total_nodes)
        if st == "verified":
            items.append({"kind": "dot", "nx": nx, "status": st})
            continue

        outcome = (nd.get("outcome") or "").strip()
        text = f'{GLYPH[st]} {nd.get("claim", "")}' + (f' — {outcome}' if outcome else "")
        lines = _wrap(text, 40, 3)
        trig = (nd.get("trigger") or "").strip()
        pre = _wrap(f"because {trig}", 44, 2) if trig else []
        w = max([len(l) for l in lines] + [len(l) for l in pre] + [0]) * CHAR_W + 16
        h = 14 * len(lines) + 12 * len(pre) + 11
        bx = min(max(nx + 12, x0 + 4), x1 - w)
        items.append({"kind": "branch", "bx": bx, "w": w, "h": h, "nx": nx,
                      "lines": lines, "pre": pre, "status": st, "stroke": stroke,
                      "fill": fill, "ink": ink, "lane": lane_for(bx, w, h)})

    # Lane offsets from the tallest item in each lane, so a three-row ladder
    # does not run into the row below it.
    lane_y = {}
    cur = branch_y0
    for lane in sorted(lanes_used):
        lane_y[lane] = cur
        cur += lane_h[lane] + 14
    bottom = cur - 14 if lanes_used else branch_y0

    for it in items:
        if it["kind"] == "dot":
            st = it["status"]
            stroke, fill, _ = COL[st]
            body.append(f'<circle cx="{it["nx"]:.0f}" cy="{axis_y:.0f}" r="6" '
                        f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
            continue

        by = lane_y[it["lane"]]
        if it["kind"] == "ladder":
            xa, xb = it["xa"], it["xb"]
            body.append(f'<path d="M{xa:.0f},{axis_y+8:.0f} L{xa:.0f},{axis_y+18:.0f} '
                        f'L{xb:.0f},{axis_y+18:.0f} L{xb:.0f},{axis_y+8:.0f}" fill="none" '
                        f'stroke="{MUTED}" stroke-width="1"/>')
            bx, w = it["bx"], it["w"]
            rail_x = bx + 6
            body.append(f'<line x1="{rail_x:.0f}" y1="{axis_y+18:.0f}" x2="{rail_x:.0f}" '
                        f'y2="{by + it["h"]:.0f}" stroke="{HAIR}" stroke-width="1"/>')
            ry = by
            for i, r in enumerate(it["rows"]):
                h = 14 * len(r["lines"]) + 12 * len(r["pre"]) + (22 if r["t"] else 12)
                sw = 1.6 if i == len(it["rows"]) - 1 else 1
                body.append(f'<rect x="{bx:.0f}" y="{ry:.0f}" width="{w:.0f}" height="{h:.0f}" '
                            f'rx="4" fill="{r["fill"]}" stroke="{r["stroke"]}" '
                            f'stroke-width="{sw}"/>')
                py = ry + 13
                for l in r["pre"]:
                    body.append(f'<text x="{bx+22:.0f}" y="{py:.0f}" font-size="9" '
                                f'fill="{MUTED}">{_esc(l)}</text>')
                    py += 12
                for li, l in enumerate(r["lines"]):
                    body.append(f'<text x="{bx+22:.0f}" y="{py+1+li*14:.0f}" '
                                f'font-size="10.5" fill="{r["ink"]}">{_esc(l)}</text>')
                if r["t"]:
                    body.append(f'<text x="{bx+22:.0f}" '
                                f'y="{ry+13+12*len(r["pre"])+14*len(r["lines"]):.0f}" '
                                f'font-size="9" fill="{MUTED}">{_esc(r["t"])}</text>')
                body.append(f'<circle cx="{rail_x:.0f}" cy="{ry+9:.0f}" r="3" '
                            f'fill="{r["stroke"]}"/>')
                ry += h + 4
            continue

        # branch
        st = it["status"]
        nx, bx, w = it["nx"], it["bx"], it["w"]
        body.append(f'<path d="M{nx:.0f},{axis_y+6:.0f} L{nx:.0f},{by-6:.0f} '
                    f'L{bx:.0f},{by-6:.0f}" fill="none" stroke="{it["stroke"]}" '
                    f'stroke-width="1.4"'
                    f'{" stroke-dasharray=\"4 3\"" if st == "unobserved" else ""}/>')
        b, _, _ = _box(bx, by, it["lines"], it["stroke"], it["fill"], it["ink"],
                       pre=it.get("pre"))
        body += b

    y = bottom + 8

    # ---- gates drawn ------------------------------------------------------
    ms_x = [pl[1] for pl in ms_placements]
    for gm in gate_marks:
        mx, bx, w, h = gm["mx"], gm["bx"], gm["w"], gm["h"]
        by = lane_y[gm["lane"]]
        # A milestone station sits on the same spine; when one is close, drop
        # the diamond below the axis so the two do not read as one marker.
        cy = axis_y + (11 if any(abs(mx - m) < 13 for m in ms_x) else 0)
        # neutral diamond: a choice is structure, whatever was chosen
        body.append(f'<path d="M{mx:.0f},{cy-8:.0f} L{mx+8:.0f},{cy:.0f} '
                    f'L{mx:.0f},{cy+8:.0f} L{mx-8:.0f},{cy:.0f} Z" '
                    f'fill="#ffffff" stroke="{MUTED}" stroke-width="1.8"/>')
        body.append(f'<line x1="{mx:.0f}" y1="{cy+8:.0f}" x2="{mx:.0f}" '
                    f'y2="{by-6:.0f}" stroke="{HAIR}" stroke-width="1"/>')
        body.append(f'<path d="M{mx:.0f},{by-6:.0f} L{bx:.0f},{by-6:.0f}" '
                    f'fill="none" stroke="{HAIR}" stroke-width="1"/>')
        body.append(f'<rect x="{bx:.0f}" y="{by:.0f}" width="{w:.0f}" height="{h:.0f}" '
                    f'rx="4" fill="#ffffff" stroke="{MUTED}" stroke-width="1" '
                    f'stroke-dasharray="1 0"/>')
        ry = by + 6
        for r in gm["rows"]:
            if r["kind"] == "question":
                ink, weight, deco = MUTED, "600", ""
            elif r["kind"] == "chosen":
                ink, weight, deco = INK, "500", ""
            else:
                ink, weight, deco = MUTED, "400", ' text-decoration="line-through"'
            for li, l in enumerate(r["lines"]):
                body.append(f'<text x="{bx+10:.0f}" y="{ry+11+li*14:.0f}" '
                            f'font-size="10" font-weight="{weight}" fill="{ink}"'
                            f'{deco}>{_esc(l)}</text>')
            ry += 14 * len(r["lines"]) + 8

    # depends_on arcs: a thin curve from the observation consumed to the gate.
    # Resolved against every node, so a gate can hang off a ladder row too.
    node_x = {}
    for k, (pi, nd) in enumerate(nodes):
        if nd.get("gate"):
            continue
        nx = px(_secs(nd.get("t")), (k + 0.5) / max(1, len(nodes)))
        node_x.setdefault((nd.get("claim") or "")[:50], nx)
    for pi, nd in gate_nodes:
        dep = ((nd.get("gate") or {}).get("depends_on") or "").strip()
        if not dep:
            continue
        src = next((x for c, x in node_x.items() if c.startswith(dep[:50])), None)
        if src is None:
            continue
        mx = px(_secs(nd.get("t")), 0.5)
        mid = (src + mx) / 2
        body.append(f'<path d="M{src:.0f},{axis_y-8:.0f} Q{mid:.0f},{axis_y-26:.0f} '
                    f'{mx-9:.0f},{axis_y-3:.0f}" fill="none" stroke="{MUTED}" '
                    f'stroke-width="1" stroke-opacity="0.6" stroke-dasharray="4 3"/>')

    # ---- delivered ---------------------------------------------------------
    if debrief.get("delivered"):
        st = debrief.get("outcome_status", "unobserved")
        stroke, fill, ink = COL[st]
        lines = _wrap(f'{GLYPH[st]} Delivered — {debrief["delivered"]}', 96, 2)
        body.append(f'<line x1="{x0}" y1="{y:.0f}" x2="{x1}" y2="{y:.0f}" '
                    f'stroke="{HAIR}" stroke-width="1" stroke-dasharray="6 6"/>')
        b, w, h = _box(x0, y + 12, lines, stroke, fill, ink)
        body += b
        y += 12 + h

    height = int(y + 26)
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" '
        f'viewBox="0 0 {W} {height}" style="max-width:100%;height:auto" '
        f'font-family="system-ui,-apple-system,sans-serif">',
        f'<rect width="{W}" height="{height}" fill="#fcfcfb"/>',
        *body, "</svg>"])
