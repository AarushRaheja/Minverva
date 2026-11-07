# Coding agent evaluation

Measures whether the manager-and-specialists architecture gives a real advantage, under what conditions, at what cost and how reliably. The agent never grades itself: it works in a throwaway folder, and a separate grader then checks what it left behind against tests it couldn't see.

## Commands

```
uv run python -m evaluation doctor                 # what this machine can run
uv run python -m evaluation tasks                  # every task and its review state
uv run python -m evaluation validate               # each task fails on its base, passes with its reference, doesn't flake
uv run python -m evaluation plan <experiment>      # trial count and worst-case cost, runs nothing
uv run python -m evaluation run <experiment>       # resumable; finished trials are skipped
uv run python -m evaluation import-legacy          # bring saved out/arch runs in, runs no model
uv run python -m evaluation report                 # out/eval/reports/report.md
uv run python -m evaluation dashboard              # out/eval/reports/dashboard.html
uv run python -m evaluation export-harbor          # repository tasks in Harbor's format
uv run pytest evaluation/tests
```

Run `controls` first, and again after changing the harness. The nothing-submitted agent must resolve 0% and the reference must resolve 100%, or the report says not to trust it. `run` refuses more than 100 trials or a worst case above $25 without `--yes`, and refuses held-out tasks without `--final`.

## Running on Modal

`functional-gate`, `ablation-prompt-repair` and `final-heldout` run the local model on a Modal GPU. Deploy once with `uv run modal deploy modal_apps/ollama_app.py`, then `uv run python -m evaluation modal-check`. See spend any time with `uv run python -m evaluation spend`.

The limit is in `configs/modal.toml`: $20.85 of app spend counted from 2026-11-01, which is $20 on top of what was already used. It's enforced in three places:

- **Before an experiment:** it won't start if the limit is reached or billing can't be read.
- **Before each trial:** a trial starts only if its whole time limit would still fit.
- **Before each model call:** the bridge refuses calls past the limit, which also stops a running trial. It's recorded as not attempted, and the experiment can resume.

Billing only reports finished hours, so the check assumes up to 1.5 unreported GPU hours. A Modal-side dashboard limit is still worth setting, because this one only covers calls made through the bridge. Other apps in the workspace count toward the cap but aren't stopped by it.

## Layout

| Folder | What it does |
|---|---|
| `core.py` | `Task`, `Budget`, `AgentResult`, and the `CodingAgent` protocol |
| `configs/` | Agent manifests, budgets, experiments, the preregistered decision rules, external benchmarks |
| `adapters/` | Custom agent, controls, conventional tool loop, Claude Code, Harbor agent |
| `benchmarks/` | Task registry, private tasks, project builds, task review, saved-run import, Harbor export |
| `runner/` | Orchestrator, sandbox, limits and measurement, patch capture, trajectory log |
| `evaluators/` | The independent grade, failure labels |
| `analysis/` | Statistics, report, dashboard |

Results go in `out/eval/`, which git ignores. Only `project_build.py`, `custom_agent.py`, `correctness.grade_project` and `legacy.py` touch the `slm` package. The custom agent is run through its own command line.

## How a trial stays honest

- **The starting point is outside the agent's reach.** The baseline sits in a git folder the agent can't write to, so committing or deleting `.git` can't hide a change.
- **Hidden tests aren't reachable.** The sandbox blocks this whole repo, and only the visible tests are copied in.
- **Grading starts clean.** The patch goes onto a fresh copy of the frozen repo and all tests are restored, so editing or deleting tests can't help. Editing an existing test is also flagged.
- **What's measured comes from outside the agent.** Its own claims are never used.
- **Not attempting isn't failing.** `unsupported` and `environment_failure` trials are reported beside the results, never counted as coding failures.
- **Safety is scored separately.** Taking an injected action doesn't change the coding score, so it can't get averaged away.

Submitted code runs in the same process as the tests it is graded by, as in most benchmarks, so a deliberately malicious submission could forge its results. Inspect `patch.diff` for any result that looks too good.

## Known gaps

- **The custom agent can't attempt repository tasks.** It builds new projects from a brief and has no way to read or edit a repo, so those tasks, Terminal-Bench and SWE-bench all come back unsupported.
- **Isolation is `sandbox-exec`, not containers.** `container_image_digest` stays null. Harbor export gives Docker isolation, but needs Docker running and far more disk.
- **Seed tasks aren't independent.** There are 8, against the plan's 100, and they were written by Claude Code, the same tool that's a baseline here. They're marked `independently_reviewed = false` and are all dev tasks, so they can't support a final claim.
- **Other baselines aren't installed.** Codex, OpenHands, mini-SWE-agent, Gemini CLI and Aider need manifests and installing. `tool-loop` is a conventional loop written for this harness, not mini-SWE-agent.
- **Quality checks are partial.** `ruff` runs when installed; Semgrep and CodeQL aren't wired in, and blinded human review needs people.
- **Energy, GPU memory and the local model's memory aren't measured.** Peak memory covers the agent's own process tree only, and the Ollama server is a separate process.
- **Saved runs are partial records.** Imported trials have no cost or trajectory and their provenance says so.
- **Local cost is an assumption.** `$0.12` per hour in the manifests is a placeholder rate, not a measurement.
- **The 500-task allocation isn't here.** Only 89 Terminal-Bench and 60 private are stated in the plan's text; the rest was in a chart that didn't come through.
