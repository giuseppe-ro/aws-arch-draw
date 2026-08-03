# aws-arch-draw

A skill for **opencode** that turns a project's AWS deployment code into a
clean architecture diagram (`.drawio`, viewable in draw.io) — with AWS icons,
left-to-right data flow, color-coded edges, and boxes for external systems.

## What it does

Given a project that deploys AWS infrastructure (SQS, SNS, Lambda, DynamoDB,
EventBridge, …), the skill:

1. Discovers the real architecture from your **terraform deployment code**
   (authoritative) or the project's **graphify** knowledge graph.
2. Draws the diagram as a `.drawio` file you can open in draw.io.

## Accuracy guarantee

The diagram is never a guess. Before anything is saved, the generated model is
checked against ground truth (your terraform or graphify output):

- no invented resources or connections,
- no missing trigger/write/stream edges,
- names and types match your deployment exactly.

If the model drifts from reality, the render is **refused** — nothing wrong is
ever written to disk. You edit the *model*, not the XML.

## Prerequisites

- **graphify** — see https://github.com/Graphify-Labs/graphify
- **draw.io** — see the draw.io MCP: https://github.com/jgraph/drawio-mcp/blob/main/mcp-tool-server/README.md

## Usage

Run in a project directory with a `deploy/` terraform folder (or a
`graphify-out/`):

```
/aws-arch-draw
```

Output: `docs/<dirname>-architecture.drawio`.

### Subcommands

| Command | What it does |
|---------|--------------|
| `/aws-arch-draw re-render` | Re-render the diagram from the current model (no re-discovery). |
| `/aws-arch-draw regenerate` | Re-run discovery, report any drift vs the model, then re-render. |
| `/aws-arch-draw ignore-resource <name>` | Stop showing a resource type (e.g. `sqs dlq`). |
| `/aws-arch-draw enable-resource <name>` | Start showing a resource type again. |
| `/aws-arch-draw help` | Show usage. |

## How to adjust the diagram

The diagram is generated from a model file at
`graphify-out/architecture-model.json`. To change the title, external system
names, or add a downstream consumer, edit that file and run
`/aws-arch-draw re-render`. The layout, colors, and routing are computed
automatically — you never hand-edit coordinates or the `.drawio` XML.

## Where to go deeper

- `skill/aws-arch-draw/README.md` — full technical reference: model schema, discovery rules,
  validation contract, and how `scripts/render.py` + `scripts/tf_parser.py`
  work.
- `skill/SKILL.md` — the skill definition loaded by opencode.
