---
name: debrief
description: Review the exchange that just happened — how the agent worked, where it guessed, what it got wrong, and what to carry forward — as a one-page report with a decision-path diagram. Use when the user says "/debrief", "debrief this", "review that exchange", "how did you get there", or asks for a walkthrough of the work just done.
---

# Debrief

Turn the exchange that just finished into a review a person can learn from.

The unit is a **decision node**, not a tool call: each node is one claim, coloured by
how well the log backs it. The report is `report.md` plus `figure.svg` — a timeline with
the goals across the top, time running left to right, and every unverified claim hanging
below as a branch. Both are generated from a `debrief.json` you write after reading the
digest.

Scope is fixed: **the current session, the last exchange, invoked at the end of it.**
Do not review other sessions, and do not page back through earlier exchanges unless the
user explicitly asks for one.

## Steps

### 1. Extract the digest

```bash
python3 -I ~/.claude/skills/debrief/scripts/extract.py
```

Writes `debrief/<session>/` with `digest.md`, `events.jsonl`, `meta.json`.

Flags, only if the user asked for something other than the default:
`--prompt "<substring>"` picks an earlier exchange; `--session <id>` / `--file <path>`
point elsewhere; `--out <dir>` changes the output directory.

Read `digest.md`. If it is long, read `meta.json` first for the signal counts.

### 2. State the frame

Before the phases, answer three questions a reader asks first. They are required — the
report is unreadable without them, because the nodes below only say *how* the work went,
never *what it was* or *whether it worked*.

- **`ask`** — what was requested, quoted from the prompt that opened the exchange. Not a
  paraphrase: the reader needs to judge whether the work that followed matched the ask.
- **`delivered`** — what exists now that did not exist before. Name the artifact in plain
  words: "a skill at `~/.claude/skills/debrief` — SKILL.md, two scripts, a colour
  reference". For a question, it is the answer. For a fix, the patch and what it changed.
  **Say whether it was actually built**, not merely planned.
- **`checked`** — what was run to verify the deliverable, at what scope, and what that
  does *not* cover. "Extract and render run end to end on a real exchange; the /debrief
  invocation itself never exercised." Never leave this implicit — a reader who has to
  infer "tested" from a node about the extractor has been failed by the report.
- **`outcome_status`** — one of `verified` / `assumed` / `unobserved`, assigned by the
  same rule as any node, but about the whole deliverable: was the thing as a whole ever
  exercised?
- **`goals`** — what the work was *for*, one line each. Give a goal an **`"at"`**
  timestamp only when the log shows the moment it was achieved — normally the `t` of the
  verified node that closed it. A goal with `at` becomes a **milestone** on the axis: a
  neutral white tile on a stalk, carrying only its status glyph — deliberately not a
  status-coloured tile, so a goal cannot be mistaken for an action below the line. A goal
  without `at` is listed as *no moment in the log* rather than placed at a guessed
  position. Never invent a timestamp to make the row look tidy. The digest's "declared goals"
  section carries the agent's own plan, verbatim; use those items when they exist rather
  than inventing your own. Give each a status by the same rule as a node: `verified` when
  the events show it was achieved, `assumed` when the agent marked it done and nothing
  confirms it, `contradicted` when the work abandoned or refuted it, `unobserved` when it
  was never attempted. **A plan item marked "completed" is the agent's claim, not
  evidence** — that distinction is the reason this section exists.

This is not build-specific. Every exchange has an intent, a result, and a level of
verification; a research exchange answers a question (verified against sources, or
not), a debugging exchange lands a fix (verified by the failing test, or not). Naming
the frame is what lets a reader tell a finished piece of work from a promising pile of
parts — and the goals are what let them tell which actions mattered.

### 3. Find the decisions

Read the whole digest before writing anything. Then identify:

- **Phases** — three to seven stages of the work. A phase is a stretch that answered one
  question or produced one artifact, not a sequence of commands.
- **Nodes** — the claims that the outcome rests on, two to five per phase. The figure
  shows at most three per phase (it favours `contradicted`, `unobserved`, then
  `assumed`); every node you write appears in the report's table, so detail is never
  lost, only demoted. Prefer the moments where the work turned over the moments where
  it was busy: a probe that retired an unknown, a choice between alternatives (record it
  as a **gate** — see below), a failure, a recovery, a judgment call with an alternative
  that was rejected.

Skip: file reads that revealed nothing, formatting, retries of the same failing command
(count them as one node), and anything you cannot tie to a claim.

### 4. Assign status — the only judgement that matters

One node is one claim. Ask: **does the log back this claim?**

| Status | Glyph | When |
|---|---|---|
| `verified` | ✓ | A tool result, measurement, or code read in the log supports it |
| `assumed` | ⚠ | The agent stated or acted on it; nothing in the log tests it |
| `contradicted` | ✕ | An observation in the log disagrees with it |
| `unobserved` | ∅ | No evidence either way — including what was never attempted |

Rules that decide the hard cases:

- **A failure is usually `verified`, not `contradicted`.** A probe returning "7 works, 8
  doesn't" established a fact. Reserve `contradicted` for the moment reality disagreed
  with something the agent believed — a pipeline that "works" throwing an exception.
- **A guess is `assumed` even when a later measurement proves it right.** The claim was a
  guess at the time it was made; that the measurement came afterwards is the lesson. Note
  the ordering in the evidence column ("chosen 4 min before the measurement").
- **A subagent's finding is `assumed` in this report** until the parent observed it
  itself. Another model saying it verified something is not verification.
- **Absence has no output.** If a path was never tested, make it a node with `unobserved`
  and say what would have tested it. This is usually the most valuable row in the table.

#### How to word a node

A node is an **event in the work**, written for someone who has not read the code. The
test: *could a reader retell this exchange from the figure alone?* If they need to have
seen the source to parse the claim, rewrite it.

- **Bad:** "The probe-before-edit signal fires on the parallelization exchange" — names an
  internal detector; unreadable to anyone who hasn't read `extract.py`.
- **Good:** "Tried the detector on an old exchange; it found nothing — the match was
  case-sensitive" — says what was attempted, what came back, and why it was wrong.
- **Bad:** "A fabricated quote is rejected and named" — passive, and "named" hides the point.
- **Good:** "Planted a fake quote to test the guard; it refused to render and pointed at
  the node."
- **Bad:** "Capping the figure at three nodes per phase loses nothing" — code-review voice.
- **Good:** "Cut the diagram to three nodes per phase; the report table still lists all 13."

Rules of thumb:

- **Start with the agent's action**, not the code's behaviour: *tried, checked, assumed,
  guessed, fixed, told, cut, read*. Passive voice ("is rejected", "is capped") hides who
  did what and is the most common tell.
- **Introduce any tool-specific term in plain words** at first use: "the probe detector
  (a check for measurements taken before the first edit)". If the term takes more than a
  clause to explain, it belongs in the evidence column, not the claim.
- **Never put an identifier in a claim** — `snake_case`, `camelCase`, `something()`, a
  file path, a CSS property. The renderer lints for these; treat a warning as a bug.
- **Put the cause in the claim, the receipt in the evidence.** "…because the match was
  case-sensitive" belongs in the claim; "returned None" is the evidence that says so.
- **Aim for under ~90 characters.** The figure clips at 120.

### 5. Write the rationale for each phase

One or two sentences on **why the phase existed at all** — the question it was there to
retire, or the risk it was there to bound. Not a summary of what happened.

- If the agent said it before acting, quote it: `"why_source": "quoted"`, and put the
  earliest verbatim statement in `"quote"`. Quote text that appears in the transcript,
  character for character.
- Otherwise `"why_source": "inferred"` and write it in your own words. Never dress a
  reconstruction as a quote.

### 6. Write `debrief.json`

Write it to the same directory as the digest. Shape:

```json
{
  "title": "Building the debrief skill",
  "ask": "the user's request, quoted from the prompt that opened the exchange",
  "delivered": "a skill at ~/.claude/skills/debrief — SKILL.md, extract.py, render.py",
  "checked": "extract and render run end to end on a real exchange; the /debrief invocation never exercised",
  "outcome_status": "assumed",
  "goals": [
    {"goal": "Build a skill named /debrief for the current session", "status": "verified", "at": "16:50:13"},
    {"goal": "Test it end to end on a real exchange", "status": "assumed"}
  ],
  "headline": "Two or three sentences a reader keeps: what was asked, what it cost, what to remember.",
  "phases": [
    {
      "name": "Retire the unknown",
      "why": "the provider's concurrency limit was unknown and decides the design",
      "why_source": "quoted",
      "quote": "it's a 30-second test",
      "nodes": [
        {
          "claim": "7 concurrent requests succeed; 2.1s vs ~14s serial",
          "status": "verified",
          "evidence": "probe output 07:53:36",
          "trigger": "the provider's rate limit was unknown",
          "task": "Find the provider's concurrency limit",
          "quote": "ok=7/7",
          "t": "07:53:09",
          "gate": {
            "question": "How many workers to run?",
            "options": [
              {"text": "8, the burst that was measured", "verdict": "chosen", "source": "quoted"},
              {"text": "16, for headroom", "verdict": "rejected",
               "why": "never measured above 8", "source": "inferred"}
            ]
          }
        }
      ]
    }
  ],
  "lessons": [
    {"text": "Measure the burst before choosing the worker count, not after.", "node": "Workers = 6 / 4"}
  ],
  "open": ["Never killed a worker mid-burst to prove the other checkpoints survive."],
  "agents": [
    {"name": "domain-expert", "back": "05:32:36", "finding": "premium normalised by the Monday horizon", "status": "assumed"},
    {"name": "systems-architect", "back": "05:32:48", "finding": "replay poisons the store", "status": "assumed"}
  ],
  "dispatch": "Dispatch 4 reviews · four calls in one message",
  "consolidate": "Consolidate + challenge 6 findings"
}
```

`agents` is optional. Include it only when the exchange dispatched **two or more**
subagents; it produces a second figure with one lane per agent. Its rules:

- A subagent's finding defaults to `assumed` — the parent didn't observe it, it received
  a message from another model. Only mark one `verified` if the parent then checked it
  itself in this exchange.
- Put the return time in `back`. Concurrency is only legible if the reader can see that
  lane 3 finished before lane 1.
- If two agents disagreed, the challenged one becomes `contradicted` at the node where
  the parent adjudicated, and the adjudication belongs in the consolidate label (e.g.
  "0 survived · 4 downgraded · 2 refuted").

#### The trigger: what made the agent act

Every node can carry a `"trigger"` — the observation or question that caused the action,
in one clause. It prints as *because …* above the claim, in muted text, so the figure
answers "why did it look there?" without a second diagram.

- **Take it from the log, not from plausibility.** The trigger for a fix is almost always
  the preceding result: the error string, the implausible number, the test that failed.
  `"because the digest printed '8 errors' for an exchange the agent knew had one"`.
- **A trigger that is a claim of its own is still a claim.** "The user asked" is
  verifiable from the prompt. "It realised X was wrong" is usually reconstruction — if
  nothing in the log says so, leave the trigger out rather than narrate motive.
- **Not every node needs one.** Verified nodes on the main path often just follow. Use
  it where the reader would otherwise ask "what made it do that?" — failures, detours,
  and the first action of a phase.

#### Grouping attempts at the same thing

When several nodes are attempts at **one** objective — a guess that failed, the fix that
failed, the third try that worked — give them the same `task` string. The figure then
draws one ladder instead of three loose red dots, in time order, ending in an outcome:

```
try 1 · ✕ guessed the folder-name rule wrong              17:06:12
try 2 · ✕ fixed it; next run died on a missing import   17:07:28
try 3 · ✓ ran with no arguments, found the session      17:08:09 — resolved
```

Rules:

- **Group only real attempts at one objective.** Same goal restated, or the same
  operation retried against the same target. Three unrelated failures that happen to be
  red are not a ladder; grouping them invents a narrative the log doesn't contain.
- **Attempts read as `try N`, phases as `1 ·`, milestones carry no number.** Three sequences on one figure that all start at 1 will be read as one sequence; the labels keep them apart.
- **The last node decides the outcome.** `verified` → *resolved*. `contradicted` with
  `"abandoned": true` → *abandoned*. `contradicted` or `unobserved` with no later success
  → *unresolved*. That word is the honest answer to "did it ever work?", and it is what
  the ladder exists to show.
- **Say when the goal was dropped.** If the work moved on without solving it, set
  `"abandoned": true` on the last node — that is a fact worth seeing, not a failure to
  hide.
- **Every failure needs an ending.** A `contradicted` node on its own reads as a dead end
  and leaves the reader wondering what happened next. If the work recovered *and the log
  shows it*, add the resolving node to the same task — the re-run, the passing test. If
  the recovery happened later or outside this exchange, put a short `"outcome"` on the
  node instead: `"outcome": "fixed in the next exchange"`, `"still unverified"`,
  `"dropped"`. The figure and the table both print it after an em dash.

`quote` on a node is optional. When present it is checked against the transcript and the
render fails if it is not there verbatim. Use it on nodes that carry the lesson.

#### Decision gates

Some moments are not observations but **forks**: two or more options were on the table
and one was taken. They are invisible in a list of actions — the reader sees what ran,
never what was not — so give the node a `gate`:

```json
{
  "claim": "How should the current session be identified?",
  "status": "verified",
  "t": "17:09:17",
  "gate": {
    "question": "How should the current session be identified?",
    "options": [
      {"text": "Ask the environment for the session id",
       "verdict": "chosen", "why": "the id is authoritative", "source": "quoted"},
      {"text": "Take the newest file in the project folder",
       "verdict": "rejected", "why": "it picked a different session", "source": "inferred"}
    ],
    "depends_on": "Guessed the folder-name rule wrong"
  }
}
```

The figure gives the node a neutral diamond on the spine — a choice is structure,
whatever was chosen — and a box listing what was weighed: the chosen option in ink, the
rejected ones struck through in muted grey. Rejected options are **never status-coloured**;
they were declined, not disproved.

Rules:

- **Only draw a gate the log supports.** Both options must appear in the log — the agent
  stating the alternative, trying it and backing out, or the user naming it. If you are
  reconstructing the road not taken from hindsight, do not make it a gate.
- **`verdict`** is `chosen` or `rejected`, nothing else. Always give exactly one `chosen`.
- **`source`** says whether the option and its reason are in the log (`quoted`) or your
  reconstruction (`inferred`). The report prints this beside every option; an inferred
  alternative presented as fact is the failure this field exists to prevent.
- **`depends_on`** names the claim that forced the gate — the failed probe, the surprise.
  Match the first ~50 characters of that node's `claim`; the figure draws a thin dashed
  curve from it to the diamond. Use it only when the log shows the dependency, not when
  the two merely happen to be adjacent.
- **The gate node still has a `status`**, and it is about the decision: `verified` when
  later work confirmed the chosen path, `assumed` when the choice was taken on faith and
  never tested.
- **`question` is optional when the claim already asks it.** Keep the claim under about
  90 characters; the long what-and-why belongs in the options, not the question.
- **One gate per fork.** If a phase weighed the same trade-off twice, it is two gates only
  if the second weighing used new information; otherwise it was one decision.

### 7. Render

```bash
python3 -I ~/.claude/skills/debrief/scripts/render.py \
  --input debrief/<session>/debrief.json \
  --transcript <transcript path from meta.json> \
  --meta debrief/<session>/meta.json \
  --out debrief/<session>
```

This validates every quote and writes `report.md`, `figure.svg` (the timeline the report
embeds) and `figure.mmd` (a mermaid rendition, kept for editing).

**Optional `--trace`** adds `trace.html`: the same exchange in the vendored
trajectory-tree viewer — every turn, tool call, parameter and result, with zoom, pan and
clickable evidence. Use it when the user wants to inspect the actual calls rather than
read the review, or asks "show me what actually ran". It costs a few seconds and a
multi-megabyte file, so it is off by default; it is also runnable on its own:
`scripts/trace.py --transcript <path> --out <debrief dir>`. It needs Node on PATH and a
one-time install of the viewer (37 MB, kept outside the skill):

```sh
git clone --depth 1 https://github.com/goatliamia/trajectory-tree.git ~/.local/share/debrief/trajectory-tree
npm ci --prefix ~/.local/share/debrief/trajectory-tree/plugin/portable-tools --ignore-scripts
```

If it is not installed the script prints those two commands and exits — the report is
already written by then, so a missing viewer never costs you the debrief.

Open `trace.html` either by double-clicking it, or with `--serve`, which prints a
`http://127.0.0.1:<port>/trace.html` URL. **Prefer `--serve` when the page will be read
inside an app pane**: it is a 3 MB document and some in-app previews refuse it from
`file://` while a localhost URL always works. The server stops when the command is
interrupted.

### 8. Answer

`figure.svg` is generated directly by the renderer — no separate step. Open it to check
it reads, then reply with:

1. **What was asked and what was delivered, and whether it was checked** — one sentence,
   with the outcome status. A reader must never have to infer "built" or "tested".
2. Attach `report.md` and `figure.svg` with the file-send tool. Markdown depends on the
   sibling image; send both together so the link resolves.
3. The three or four things worth carrying forward — the lessons, not a retelling.
4. What was never tested, if anything was.

Keep the reply short. The report holds the detail; the reply is the debrief.

## Voice

Write like a reviewer, not a narrator. "It probed before designing" is narration. "It
probed because the limit was unknown, and that 30 seconds is why the design held" is a
review. Prefer the specific number, the timestamp, and the quote over the adjective.

Do not be flattering. The most useful rows are usually the ones where the agent was
wrong, guessed, or never looked. Say so plainly — the point of the artifact is that the
next exchange goes better, which only works if this one is described accurately.

## References

- `reference/colour-scheme.md` — the palette, glyphs, and the rules for what colour may
  and may not encode. Read before changing colours or adding a fifth state.
