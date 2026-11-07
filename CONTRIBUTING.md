# Working in Minverva

Minverva is the main repository. It started as a snapshot of `NOVA-SLM/nova-hacks` branch
`free-compute-ui` @ `6bbc9da` (tag `import/nova-hacks-2026-11-07`); nova-hacks is read-only history now.

## Branches

`main` is always green. Nobody pushes to it directly after the import; everything lands through a PR.

Name branches `<area>/<topic>`, lowercase, hyphens:

| area | covers |
|---|---|
| `slm` | contracts, domains, pipeline, manager, llm clients, cli |
| `arch` | `slm/arch/` architecture experiments |
| `bench` | `slm/bench/` project generator, gold artifacts, scoring |
| `train` | `slm/train/`, `notebooks/`, Modal training apps |
| `eval` | `evaluation/` harness and benchmark tasks |
| `ui` | `slm/ui/` web workbench and `slm code` |
| `tui` | `tui/` ratatui monitor |
| `docs` | README, docs/, PLAN.md, EXPERIMENTS.md |
| `ci` | `.github/` |

Examples: `train/spec-auth-lora`, `arch/repair-round`, `tui/elo-table`. One topic per branch; delete
it after merge.

## Commits

`<area>: <what changed, imperative>`, same areas as above, e.g. `bench: add hard difficulty knob`.
The body says why, and quotes any numbers it produced. Agent commits end with the
`Co-Authored-By:` trailer.

## Pull requests

- Target `main`, fill in the template, keep CI green (`python` and `tui` workflows).
- Squash-merge, so `main` reads as one commit per change and `git log --oneline` is the changelog.
- Anything that spends money (Modal, hosted models) puts the $ figure in the PR body.

## Results

`out/` is ignored. When an experiment produces numbers worth keeping, commit a short write-up to
`docs/results/YYYY-MM-DD-<topic>.md` (command, commit SHA, table, $ spent) and link it from
`docs/STATUS.md`. That's how results stay findable.

## Agents

`tasks/PROTOCOL.md` still describes path ownership and code rules. Its git section (nova-hacks
branch names, never touching `main`) is replaced by this file. `docs/LAYERS.md` explains how the
code got here; read it before changing anything that crosses layers.
