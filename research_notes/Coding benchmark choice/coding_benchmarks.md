# Coding benchmark choice (research as of 2026-10-28)

Confidence legend: [V] = read on a primary page (GitHub/arXiv/vendor) this session; [S] = seen only in a search-result summary or third-party aggregator; [U] = not verified / from memory. Aggregator numbers (benchlm, anotherwrapper, morphllm, etc.) change often and frequently mix settings. Re-check anything you will put on a slide.

## 1. Landscape

| Benchmark | Task type | Size | License | Contamination control | Harness / cloud |
|---|---|---|---|---|---|
| LiveCodeBench (LCB) | Competitive-programming function/stdin programs (LeetCode, AtCoder, Codeforces); also test-output prediction, code execution | release_v6 = 1055 problems (v1 400, v2 511, v3 612, v4 713, v5 880, v6 1055; May 2023 to Apr 2025) [V] | MIT (code) [V] | Per-problem release dates; `--start_date/--end_date` in compute_scores lets you score only problems after a model's cutoff [V]. Official board default window reportedly Aug 2024-May 2025 (454 problems) [S] | `lcb_runner` pip/python, runs generated code in subprocess sandboxes, no Docker needed [V for runner, U for sandbox details]. No v7 / 2026 release found [S]. |
| LiveCodeBench Pro | Hard contest problems (Codeforces/ICPC/IOI), 584 problems, June 2025 [S] | 584 | U | Collected pre-solution | Too hard for sub-4B models (frontier ~0% on hard) [S] |
| SWE-bench Verified | Repo-level issue patch (Python, 12 repos) | 500 | MIT (U) | None; widely reported as contaminated/saturated; one source says OpenAI stopped reporting it Feb 2026 [S, single source] | `swebench` harness, Docker; `--modal true` with `pip install swebench[modal]` and `--parallelism` [V: swebench.com/SWE-bench/guides/evaluation]. sb-cli also available [V] |
| SWE-bench Lite | Repo-level patch | 300 | MIT (U) | None (2023-24 data) | same harness; docs use `--max_workers 8` locally, `--parallelism 10` on Modal [V] |
| SWE-bench Multimodal | Repo-level, JS + images | ~517 dev/test [U] | U | none | Not suited to text-only 0.6B-4B |
| SWE-bench Live (Microsoft) | Repo-level patch, monthly refreshed from new GitHub issues. Python splits `lite`/`verified` (frozen) and `full` (+50 verified issues/month); MultiLang 1,077 instances/431 repos/8 langs (update 21 Aug 2026); Windows 66 instances (8 Mar 2026) [V: github.com/microsoft/SWE-bench-Live]. Python data last updated 08/2025 as of Sep 2025 README [V]; Lite ~300, Verified ~500 [U, page did not state sizes] | see left | MIT repo; dataset license not stated [V] | Live updates, date windows | Per-instance Docker images, run locally via `python -m evaluation.evaluation`; no cloud harness mentioned [V]. Leaderboard page (swe-bench-live.github.io) failed to load, scores [U] |
| SWE-bench Pro (Scale AI) | Repo-level, long-horizon, Python/Go/TS/JS, 41 repos | 1,865 total; 731 public [S] | U (some copyleft repos in public set; held-out + commercial splits) | Copyleft public set, private held-out/commercial | Harbor dataset exists (hub.harborframework.com) [S]. Top public ~45.9% (Opus 4.5, Mar 2026) to 59.1% (GPT-5.4 xhigh, Jun 2026) [S] |
| SWE-bench Multilingual | Repo-level, 9 langs | 300 | U | none | swebench harness [S]. Top 76-89% depending on source [S] |
| SWE-rebench (Nebius) | Repo-level, continuously harvested tasks, decontaminated monthly windows | rolling, hundreds per window [U] | U | Date-windowed | Own fork of harness (github.com/SWE-rebench/SWE-bench-fork) [S]. Original paper: Qwen3-32B 13.7% (no-think) on Mar-Apr 2025 window [S]. Site fetch failed |
| Terminal-Bench 2.0 | Agentic shell tasks in containers | 89 tasks [S] | Apache-2.0 [U] | Curated hard tasks | Harbor harness with cloud sandboxes (Daytona documented; Modal not confirmed) [S]. GPT-OSS-20B 3.1% [S]. Sub-4B near zero [U] |
| BigCodeBench | Function-level with 139 libraries, tool-like calls | 1,140 full; 148 Hard [S] | Apache-2.0 [U] | Static (2024), some contamination risk | `bigcodebench` pip, Docker/remote evaluator [S/U] |
| Aider Polyglot | Whole-repo-edit exercises, 6 langs (Exercism) | 225 [U] | Apache-2.0 [U] | Static, widely saturated by frontier | Aider benchmark requires Docker [U]. Sub-8B scores single digits [U] |
| HumanEval+ / MBPP+ (EvalPlus) | Function-level | 164 / 378 [U] | Apache-2.0 [U] | Static, heavily contaminated, saturated | `evalplus` pip, pure python, minutes to run [U] |

Newest 2026 items seen: SWE-bench Pro Verified (arXiv 2609.08149, [S]); SWE-bench-Live MultiLang/Windows (above [V]); Terminal-Bench 2.0 + Harbor (late 2025, [S]). Nothing newer than release_v6 for LCB found.

## 2. Reference numbers (small models)

### LiveCodeBench (best fit)
- Qwen3 tech report (arXiv 2505.09388, [V via arxiv.org/html]): LCB v5 thinking: 0.6B 12.3, 1.7B 33.2, 4B 54.2, 8B 57.5. Non-thinking: 0.6B 3.6, 1.7B 11.6, 4B 21.3, 8B 22.8. (One search summary claimed 4B non-thinking = 54.2; the html read says that is thinking. Use the html read.) Report's LCB v5 window is 2024.10-2025.02 [U].
- DeepCoder-1.5B-Preview: LCB v5 25.1 (base R1-distill-1.5B 16.9), HumanEval+ 73.0, Codeforces 963 [S, HF model card agentica-org/DeepCoder-1.5B-Preview]. 
- Frontier for context: official board top o4-mini-high 80.2% on 454-problem window [S, one article]; vendor claims ~91-93% [S, unverified settings].
- Caveat: Qwen3 thinking mode needs 10k-30k+ token outputs per problem. That dominates cost and breaks the "parallel small specialists" latency story. Non-thinking numbers (1.7B 11.6) are the fair baseline for a non-thinking pipeline.

### SWE-bench family
- SWE-agent-LM-7B (SWE-smith, Qwen2.5-Coder-7B): 15.2% Verified, 11.7% Lite; 32B: 40.2% Verified, 30.7% Lite [S via arXiv 2504.21798 search summary]. SWE-Gym-32B: 20.6 Verified, 15.3 Lite [S].
- SWE-Mirror-LM-7B 22.8% Verified (OpenHands) [S, secondary README].
- Agentless (GPT-4o): 32.0% Lite at ~$0.70/instance (27.33% in earlier version at $0.34) [S, arXiv 2407.01489]. No published Agentless result with a sub-8B model found [U].
- Sub-4B on SWE-bench Verified/Lite: nothing credible found. Expected 0-5% for 0.6B/1.7B [U, my estimate]. Non-zero is realistic only for 7B+ trained on thousands of trajectories.
- 32B fine-tunes now 50-60% Verified (OpenSWE-32B 59.8%) [S, arXiv 2603.13023]; frontier ~80% Verified, 46-59% Pro [S].

### Other
- MapCoder-Lite (arXiv 2509.17489, Qwen-based ~7B-class with role LoRAs): HumanEval 82.93 vs MapCoder 70.73, MBPP 84.63 vs 67.51 [S, search summary; PDF unreadable]. Backbone and sizes [U].

## 3. Decomposability
- Function-level / contest (LCB, HumanEval, MBPP): plan/restate -> write examples/tests -> helper functions -> assemble -> self-test/debug. Published: MapCoder (4 agents; GPT-4 scale) [S]; MapCoder-Lite distills 4 roles into one small LLM with role LoRAs, which is almost your architecture (specialist LoRAs on one base) [S]; AgentCoder (programmer/test-designer/executor) and CodeCoT [U, not checked this session]. Caveat: LCB stdin problems are mostly monolithic; a DAG buys little parallelism, mostly a sequential pipeline (plan -> code -> test -> repair). Parallelism shows up in sampling many candidates and generating tests in parallel.
- SWE-bench: Agentless stages (localize file -> function -> edit lines; sample N patches; generate reproduction tests; rerank) map directly onto specialist adapters, and candidate patches / tests run in parallel [S]. But each stage needs long-context repo reading (thousands of tokens); a 0.6B-1.7B model will likely localize poorly.
- SWE-smith / SWE-Gym show small models only reach 15-20% Verified even with thousands of trajectories and 7B+ coder bases [S].

## 4. Cost and time on Modal (estimates, [U] unless noted)
Modal prices [V, modal.com/pricing]: A10 $1.10/h, L4 $0.80/h, L40S $1.95/h, A100-80 $2.50/h, H100 $3.95/h; CPU $0.0000131/core-s, mem $0.00000222/GiB-s; $30/month free on Starter.
- LiveCodeBench: 454-problem window (or v6 1055). vLLM on one L4/A10/L40S. With non-thinking ~1-2k tokens x n=5 samples x ~500 problems = ~5M tokens: a few minutes to <1 GPU-hour per config. Thinking mode with 16-32k tokens: ~10-20x, still a few GPU-hours (<$10). Test execution is CPU-only, seconds per problem, no Docker builds. Realistic total for 10-20 ablation runs: $10-30.
- SWE-bench Lite (300) / Verified (500) on Modal: harness builds per-instance Docker images (base/env/instance layers); Modal option avoids local disk. Eval itself roughly 5-15 CPU-min/instance incl. image build the first time [U]; LLM side for Agentless with small model ~ tens of thousands of tokens per instance, a few GPU-hours. Total perhaps $15-40 for one Lite run plus debugging, but harness debugging eats days. Local Mac cannot do it.
- SWE-bench Live: per-instance Docker, local-only harness [V]; you'd need to port it to Modal sandboxes yourself.
- Terminal-Bench 2.0: needs agent loop with many turns in containers; small models near 0.

## 5. Recommendation

**Primary: LiveCodeBench (release_v6, restricted to the post-cutoff window, e.g. problems dated 2024-08 to 2025-04, or the official 454-problem window), pass@1 with n>=5 samples, code generation scenario, run on Modal with vLLM multi-LoRA.**
Why: date-windowed contamination control (Qwen3 cutoff is before the window, partially; state this honestly), MIT license, pure-Python execution (no Docker), cheap (single-digit GPU-hours per run), fast iteration, and honest same-size published references. Decomposition is a sequential plan -> code -> test -> repair DAG; sell parallelism via sibling tasks (helper functions, unit-test generation, N candidates) and compare against single-model baselines at equal token budget.

Reference scores you will be compared against (LCB v5 unless noted; note windows differ from yours, so re-run baselines yourself on your exact window):
- Qwen3-0.6B: 12.3 (think) / 3.6 (non-think); Qwen3-1.7B: 33.2 / 11.6; Qwen3-4B: 54.2 / 21.3 [V].
- DeepCoder-1.5B: 25.1 [S]. 
Must-do: run plain Qwen3-1.7B and Qwen3-4B on your own window in the same mode as your system (non-thinking and thinking), plus a "same-compute best-of-n + self-test" baseline. Beating non-thinking Qwen3-4B (21.3) with 0.6B/1.7B specialists is a credible, non-strawman headline; matching thinking-mode numbers is hard.
Optionally also report HumanEval+/MBPP+ (EvalPlus, minutes to run) as a sanity check, flagged as contaminated.

**Stretch: SWE-bench Lite (300) via `swebench` harness with `--modal true`, using an Agentless-style pipeline (localize -> repair -> test).** Expect low single digits to ~10% with a <=4B model. Reference: SWE-agent-LM-7B 11.7% Lite / 15.2% Verified; Agentless+GPT-4o 32.0% [S]. Only attempt a 30-50 instance slice, report honestly. If you want contamination control, SWE-bench Live Lite is better in principle but has no cloud harness. Skip SWE-bench Pro, Terminal-Bench, Multimodal, Polyglot (zero-ish for your model sizes or high infra cost).

Unverified items to double-check: SWE-bench Lite/Verified Modal flag behavior in the current `swebench` version (docs say `--modal true`, but run `--help`); SWE-bench-Live leaderboard values and sizes; official LCB leaderboard window; MapCoder-Lite numbers; AgentCoder/CodeCoT results; EvalPlus/Aider/BigCodeBench licenses and sizes; any sub-4B SWE-bench result.

## Sources
- https://github.com/LiveCodeBench/LiveCodeBench
- https://github.com/microsoft/SWE-bench-Live
- https://www.swebench.com/SWE-bench/guides/evaluation/
- https://arxiv.org/html/2505.09388 (Qwen3 report)
- https://modal.com/pricing
- https://huggingface.co/agentica-org/DeepCoder-1.5B-Preview
- https://arxiv.org/pdf/2504.21798 (SWE-smith)
- https://arxiv.org/pdf/2407.01489 (Agentless)
- https://arxiv.org/pdf/2509.17489 (MapCoder-Lite); https://arxiv.org/pdf/2405.11403 (MapCoder)
- https://arxiv.org/pdf/2505.20411 (SWE-rebench)
- https://arxiv.org/pdf/2509.16941 (SWE-bench Pro)
- https://arxiv.org/pdf/2603.13023 (daVinci-Env)
- https://www.tbench.ai/docs/run-terminal-bench-2-0
- https://benchlm.ai/benchmarks/liveCodeBenchV6 , https://www.morphllm.com/swe-bench-pro (aggregators)
