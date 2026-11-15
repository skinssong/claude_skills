---
name: mermaid
description: Draw a diagram as an image, not source — render Mermaid syntax to SVG, PNG or PDF with the mermaid MCP server. Use when the user asks for a diagram, flowchart, sequence diagram, state machine, or a picture of how something flows, connects or is structured.
---

# Mermaid

Turn a description into a diagram file. The deliverable is an image the user can open, not a
code block: when the `mermaid` MCP server is available, every diagram you are asked for is
rendered and shown, and the source is printed only when they ask for it.

## Steps

1. **Write the diagram** in Mermaid syntax — `flowchart`, `sequenceDiagram`, `stateDiagram-v2`,
   `erDiagram`, `classDiagram`, `gantt`, `mindmap`. Pick the shape that matches the question:
   a flow reads as a flowchart, an interaction as a sequence, structure as a class or ER
   diagram.

2. **Render it** with the `mermaid` MCP tool `render_diagram`:

   - `syntax` — the diagram definition.
   - `format` — `svg` by default. `pdf` for print; `drawio` only for flowcharts that must
     be edited by hand. `png` **only if the server can produce it**: the bundled
     mermaid-cli 12 rejects the `width` flag the server passes, so a PNG render fails with
     `unknown option '-w'` — write the SVG and rasterise it locally (headless Chrome at
     `--force-device-scale-factor=2` is enough) instead of retrying.
   - `output_path` — an absolute path inside the user's project. Never leave the only copy
     in a temp directory.
   - `theme` — `default`, `dark`, `neutral` or `forest`; `background` — a CSS colour. Leave
     them at the defaults unless the diagram must match a document's palette.

3. **Confirm the file exists** and is non-trivial in size, then show it with the file-send
   tool. If the render returns an error, the message usually names the offending line —
   fix the syntax and render again rather than falling back to source.

4. **Say one sentence about what the diagram shows**, then stop. Do not paste the source
   under the image; it duplicates the picture in a worse format.

## Where to write

- Documentation lives next to the document it belongs to — `docs/`, the project root, or
  whatever folder the user names.
- Use a descriptive file name (`payment-flow.svg`, not `diagram1.svg`).
- When the diagram will be embedded in a README or Markdown page, write `svg`; it stays
  sharp at any size and is a few kilobytes.

## Drawing rules

- **A diagram earns its place by removing words.** If the same information fits in three
  sentences, write the sentences.
- **One idea per node.** Labels are phrases, not paragraphs; break long ones with `<br/>`.
- **Order the eye**: left to right for processes, top to bottom for hierarchies.
- **Colour sparingly.** Use `classDef` for at most three roles (input, decision, output)
  and keep the theme's text colour.
- **No legend inside the diagram** when the labels already say what things are.
- **Get the structure right before dressing it** — nodes and edges first, then classes
  and themes.

## When the server is missing

The renderer is an MCP server (`mermaid-render-mcp`, MIT), not part of this folder. Install
it once:

```bash
claude mcp add mermaid -- npx -y mermaid-render-mcp
```

The first run downloads headless Chromium (~150 MB). Without the server, write the Mermaid
source to a `.mmd` file, tell the user the diagram is ready as source, and give them the
install command — never silently skip the image.
