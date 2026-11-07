# Prior Work: Graphs of Specialized Models/Agents — Experts vs. Generalist, Routing, Topology, Decomposition, Failure Modes

Verification note: items marked **[verified]** were read from the paper's arXiv abstract or HTML full text during this session (Oct 2026). Items marked **[recall]** come from the researcher's prior knowledge of the paper; the arXiv IDs are believed correct, but the numbers were not re-checked this session and should be spot-checked before they are quoted in a final deliverable.

## Q1. Many specialized experts vs. one generalist: MoE vs. mixtures of LoRAs, and what the number and granularity of experts does

### Takeaway
Libraries of LoRA experts with routing give modest but consistent gains over a single shared adapter, and only when experts are grouped at a moderate level of granularity. In the Arrow/MBC paper, about 10 clustered experts beat 256 per-task "private" experts, and the gap over one shared LoRA is only about 1-2 accuracy points. Very fine-grained experts (one per task) usually need a good router to beat a single generalist adapter. In agent ensembles, "more diverse models" is also not automatically better: repeated sampling from the single best model (Self-MoA) beats mixing different models.

### Cited Findings
- **Arrow / MBC ("Towards Modular LLMs by Building and Reusing a Library of LoRAs", Ostapenko et al. 2024) [verified]:** model-based clustering (MBC) groups the 256 FLAN training tasks by the similarity of their LoRA parameters. Arrow is a zero-shot, training-free router: it builds one SVD prototype per expert per layer and routes each token at each layer with top-k (k=4) selection. — [arXiv 2405.11157](https://arxiv.org/html/2405.11157v1)
- **Granularity result (key for "atomicity") [verified]:** mean zero-shot accuracy on 10 held-out tasks, Phi-2 / Mistral:
  - Base model: 63.8 / 59.5
  - One shared LoRA: 65.5 / 63.1
  - 256 private (one-per-task) LoRAs with uniform merging (μ): 64.8 / 61.9
  - 256 private LoRAs with Arrow routing: 66.6 / 64.4
  - 10 MBC clusters with μ: 67.1 / 64.6
  - 10 MBC clusters with Arrow: 67.4 / 63.9

  Ten clusters was chosen because it gave the best validation loss and downstream accuracy in a cluster-count sweep (Fig. 4 of the paper). Fine-grained experts merged naively did *worse* than one shared adapter, and routing was what rescued them. — [arXiv 2405.11157](https://arxiv.org/html/2405.11157v1)
- **Arrow vs. μ on held-out SNI-12 tasks (Rouge-L) [verified]:**
  - On the private (per-task) library, Arrow beat μ by more than 10 points with Mistral (46.9 vs 36.4).
  - On the MBC library, μ beat Arrow (Phi-2: 44.4 vs 36.7).
  - Takeaway: routing matters most when experts are narrow; with coarse experts, simple averaging can win. — [arXiv 2405.11157](https://arxiv.org/html/2405.11157v1)
- **Arrow vs. oracle [verified]:** upstream, Arrow "almost matches" oracle routing for the private library. The paper reports no latency figures for Arrow, only that its SVD prototypes are cheap to compute. — [arXiv 2405.11157](https://arxiv.org/html/2405.11157v1)
- **MBC compute split [verified]:** 40% of training steps train the private LoRAs used for clustering; the remaining 60% train one adapter per cluster. — [arXiv 2405.11157](https://arxiv.org/html/2405.11157v1)
- **LoraHub (Huang et al. 2023) [recall]:** gradient-free composition of LoRAs trained on FLAN tasks. A small subset (about 20) is sampled and their weights are combined using a few examples. On BIG-Bench Hard it roughly matches few-shot in-context learning while using fewer inference tokens, with high variance across sampled subsets. — [arXiv 2307.13269](https://arxiv.org/abs/2307.13269)
- **MoLE, "Mixture of LoRA Experts" (Wu et al., ICLR 2024) [recall]:** learns a per-layer gating over a fixed set of trained LoRAs. It outperforms linear arithmetic merging of LoRAs in NLP and vision-language settings. — [arXiv 2404.13628](https://arxiv.org/abs/2404.13628)
- **X-LoRA (Buehler & Buehler 2024) [recall]:** a dense, token- and layer-wise scaling over frozen LoRA experts that uses hidden states to set the mixing weights. It is demonstrated on scientific and materials domains. — [arXiv 2402.07148](https://arxiv.org/abs/2402.07148)
- **PHATGOOSE (Muqeeth et al., ICML 2024) [recall]:** each contributor trains a sigmoid gate post hoc for its own PEFT module; routing then happens per token and per layer with no further joint training. It beats merging and retrieval-based routing for zero-shot generalization, and sometimes matches explicit multitask training. — [arXiv 2402.05859](https://arxiv.org/abs/2402.05859)
- **Branch-Train-Merge (Li et al. 2022) [recall]:** trains independent domain "expert LMs" (ELMs) in parallel, then ensembles or parameter-averages them. Compute-matched, ELM ensembles beat a dense GPT-style baseline in perplexity, and gains grow with the number of domains. — [arXiv 2208.03306](https://arxiv.org/abs/2208.03306)
- **Branch-Train-MiX (Sukhbaatar et al. 2024) [recall]:** branches Llama-2-7B into math, code and Wikipedia experts, then merges their FFNs into MoE layers with a learned router plus a short MoE fine-tune. It gives a better accuracy/compute trade-off than BTM and sparse upcycling. — [arXiv 2403.07816](https://arxiv.org/abs/2403.07816)
- **Model merging background [recall]:**
  - Task arithmetic: [2212.04089](https://arxiv.org/abs/2212.04089)
  - TIES-Merging, which resolves sign conflicts: [2306.01708](https://arxiv.org/abs/2306.01708)
  - DARE: [2311.03099](https://arxiv.org/abs/2311.03099)
  - "What Matters for Model Merging at Scale" (Yadav et al. 2024) reports that merging works better with larger, instruction-tuned base models and can tolerate more experts at larger scale. Merging many experts into small models degrades more. — [arXiv 2410.03617](https://arxiv.org/abs/2410.03617)
- **Mixture-of-Agents (Wang et al. 2024) [verified]:** layered architecture in which each agent reads the previous layer's outputs. An open-source-only MoA scored 65.1% on AlpacaEval 2.0 vs. 57.5% for GPT-4o. — [arXiv 2406.04692](https://arxiv.org/abs/2406.04692)
- **Self-MoA (Li et al. 2025) [verified]:** aggregating outputs of only the single top model beats mixing different LLMs: +6.6% on AlpacaEval 2.0 and +3.8% on average across MMLU, CRUX and MATH. MoA is sensitive to output quality, and mixing models often lowers average quality. — [arXiv 2502.00674](https://arxiv.org/abs/2502.00674)
- **"More Agents Is All You Need" (Li et al., TMLR 2024) [recall]:** plain sampling-and-voting over N instances of the same model scales accuracy with N. Gains are larger for harder tasks and are orthogonal to CoT and debate. They report Llama2-13B ensembles reaching Llama2-70B-level accuracy on some tasks. — [arXiv 2402.05120](https://arxiv.org/abs/2402.05120)

### Inferences
- Expert granularity behaves like an inverted U. One generalist adapter is too coarse, one-per-task experts are too fine without a strong router, and a moderate number of clustered experts (about 10 from 256 tasks) was best. An "atomicity" sweep should therefore vary the number of experts on a log scale (1, 4, 10, 32, 256), cross it with the routing method (uniform, learned, Arrow, oracle), and report held-out-task accuracy.
- The Self-MoA result suggests a strong control arm: N samples from the single best model (with voting or aggregation), compute-matched against a heterogeneous expert graph.

### Gaps
- I could not verify a 2025-2026 study that systematically sweeps the number of LoRA experts against task accuracy beyond Arrow's Fig. 4. Exact sweep values were not in the text.
- Latency of token-level LoRA routing (Arrow, PHATGOOSE, X-LoRA) is not reported in the sources checked. Per-token multi-LoRA serving overhead needs other sources, such as S-LoRA or Punica.

## Q2. Model routing (RouteLLM, FrugalGPT, Hybrid LLM): router methods, accuracy, and router overhead

### Takeaway
Routers between a strong and a weak model typically cut strong-model calls by about 1.4-3.7x at a fixed quality target. Gains are much larger on open-ended chat (MT-Bench) than on knowledge or maths benchmarks, and routers trained on out-of-domain preference data can be near random on MMLU and GSM8K until in-domain labels are added. Router overhead is negligible: cheap routers serve about 40-150 requests/s on one GPU for about $3-5 per million requests.

### Cited Findings
- **RouteLLM router families [verified]:**
  - Similarity-weighted (SW) Bradley-Terry ranking over embedding-kNN neighbors (no training)
  - Matrix factorization
  - BERT-base classifier
  - Llama-3-8B causal-LM classifier

  All are trained on Chatbot Arena preference data plus augmentation. — [arXiv 2406.18665](https://arxiv.org/html/2406.18665v4)
- **RouteLLM metrics [verified]:**
  - APGR (average performance gap recovered between the weak and strong model, integrated over cost levels)
  - CPT(x%), the minimum percentage of strong-model calls needed to recover x% of the gap — [arXiv 2406.18665](https://arxiv.org/html/2406.18665v4)
- **RouteLLM best-router cost savings [verified]:**
  - MT-Bench: 3.66x at CPT(50%), 2.49x at CPT(80%)
  - MMLU: 1.41x / 1.14x
  - GSM8K: 1.49x / 1.27x — [arXiv 2406.18665](https://arxiv.org/html/2406.18665v4)
- **RouteLLM training data matters [verified]:** Arena-only routers were near or below random on MMLU (-11.8% to +4.9% APGR vs. random) and on GSM8K. Adding about 1,500 golden-labeled MMLU samples lifted APGR to about 0.57-0.60. Adding GPT-4-judge-labeled data raised MT-Bench matrix-factorization APGR to 0.802 (+60.4% over random). — [arXiv 2406.18665](https://arxiv.org/html/2406.18665v4)
- **RouteLLM router overhead (Table 7) [verified]:**

  | Router | Cost per million requests | Requests/s |
  |---|---|---|
  | SW ranking | $39.26 | 2.9 |
  | Matrix factorization | $3.32 | 155 |
  | BERT | $3.19 | 69.6 |
  | Causal LLM | $5.23 | 42.5 |

  Even the costliest router adds at most 0.4% to GPT-4 generation cost. — [arXiv 2406.18665](https://arxiv.org/html/2406.18665v4)
- **RouteLLM vs. commercial routers [verified]:** the matrix-factorization and causal-LLM routers matched Martian and Unify AI quality with up to 40% fewer GPT-4 calls. Routers also kept their performance when the strong/weak model pair was swapped at test time. — [arXiv 2406.18665](https://arxiv.org/html/2406.18665v4)
- **FrugalGPT (Chen et al. 2023) [recall]:** an LLM cascade with a learned answer-quality scorer that decides whether to stop or escalate. It matches the best single LLM (GPT-4) with up to 98% cost reduction, or improves accuracy by about 4% at equal cost, on the evaluated datasets. — [arXiv 2305.05176](https://arxiv.org/abs/2305.05176)
- **Hybrid LLM (Ding et al., ICLR 2024) [recall]:** a BERT-style router predicts the quality gap between a small and a large model, with a tunable threshold. It reports up to about 40% fewer calls to the large model with no drop in response quality. — [arXiv 2404.14618](https://arxiv.org/abs/2404.14618)
- **RouterBench (Hu et al. 2024) [recall]:** a benchmark and dataset of more than 405k inference outcomes across many LLMs for evaluating routers on a cost-quality plane. — [arXiv 2403.12031](https://arxiv.org/abs/2403.12031)

### Inferences
- Reusable designs:
  - Report the cost-quality Pareto curve, APGR and CPT(50/80%) for every router in the graph.
  - Report router requests/s and cost per million requests.
  - Report the router-vs-random baseline. RouteLLM shows routers can be at or below random out of domain.
- Router candidates map directly onto the plan: SW-ranking/kNN over embeddings, a BERT-type classifier, matrix factorization, and a small-LM classifier. Matrix factorization and BERT were the cheapest and fastest.

### Gaps
- I did not verify 2025-2026 router follow-ups (e.g., RL-trained routers such as "Router-R1", or multi-model routers over more than 2 models). These should be searched separately.
- There is no direct measurement here of router *misclassification* rate as classification accuracy. RouteLLM reports only gap-recovery metrics.

## Q3. Multi-agent graph topologies: which won, on what tasks, and at what token cost

### Takeaway
- Learned or pruned sparse graphs (AgentPrune, G-Designer) match or beat dense complete-graph and debate setups while cutting tokens by about 30-90%.
- Among fixed topologies, denser or irregular graphs beat chains and trees on reasoning tasks (MacNet), but the winner is task-dependent: chain for step-by-step software, tree or star for constrained generation.
- Scaling the number of agents follows a logistic curve that saturates. MacNet found 16 nodes a reasonable choice and saturation around 100.

### Cited Findings
- **MacNet setup (Qian et al., ICLR 2025) [verified]:** DAG-structured collaboration networks on GPT-3.5 with Chain, Star, Tree, Mesh, Layer and Random topologies. Benchmarks: MMLU, HumanEval, SRDD (software) and CommonGen-Hard. — [arXiv 2406.07155](https://arxiv.org/html/2406.07155)
- **MacNet quality averages (Table 1) [verified]:**

  | Topology | Avg. quality |
  |---|---|
  | Random (irregular) | 0.6522 |
  | Mesh | 0.6316 |
  | Star | 0.6267 |
  | Chain | 0.6078 |
  | Tree | 0.6015 |
  | Layer | 0.5629 |
  | CoT baseline | 0.5757 |
  | AgentVerse | 0.5805 |

  Per-task winners:
  - MMLU: Random (0.688)
  - SRDD: Chain (0.806)
  - CommonGen-Hard: Tree (0.772)
  - HumanEval: the AgentVerse baseline (0.726). Chain scored only 0.372, below CoT's 0.610. — [arXiv 2406.07155](https://arxiv.org/html/2406.07155)
- **MacNet structural findings [verified]:**
  - Density: mesh > tree > chain.
  - Irregular topologies used about 51.9% less time than mesh.
  - Star beats deeper trees at equal density.
  - Divergent topologies beat convergent ones, and reversing edges hurts.
  - Removing agent profiles costs 3.67%. — [arXiv 2406.07155](https://arxiv.org/html/2406.07155)
- **MacNet "collaborative scaling law" [verified]:**
  - Node count was scaled from 2^0 to 2^6 (over a thousand agents in a mesh). Quality follows a sigmoid in log(|V|), and collaborative emergence appears earlier than neural emergence.
  - 2^4 = 16 nodes was called "a reasonable choice", and most topologies saturate at about 100 agents.
  - Token length grew 7.51x from 1 to 16 nodes.
  - Without memory control, context grows O(n²); passing only final artifacts rather than full dialogue makes it O(n).
  - Majority voting alone added only 0.9% and plateaued at about 8 agents. AgentVerse hit context explosion beyond about 30 agents. — [arXiv 2406.07155](https://arxiv.org/html/2406.07155)
- **G-Designer (Zhang et al. 2024) [verified]:** a graph neural network designs a task-adaptive communication graph per query. Five GPT-4 agents, average across MMLU, GSM8K, MultiArith, SVAMP, AQuA and HumanEval:
  - G-Designer: 89.84
  - GPTSwarm: 87.32
  - LLM-Debate: 87.01
  - Complete graph: 86.55
  - DyLAN: 85.64
  - AutoGen: 85.58
  - Random graph: 84.58
  - Tree: 83.42
  - Chain: 82.92
  - Star: 82.07

  It was best on 5 of 6 benchmarks; PHP, a single-agent method, won GSM8K. — [arXiv 2410.11782](https://arxiv.org/html/2410.11782)
- **G-Designer cost and scale [verified]:**
  - GSM8K total tokens: 8.5M vs. complete graph 9.8M, GPTSwarm 14M, DyLAN 22M.
  - The headline claims "up to 95.33%" token reduction on HumanEval, but the paper elsewhere says "up to 92.24%". These internal figures are inconsistent.
  - Under agent adversarial attack, accuracy dropped only 0.3 points on MMLU (84.5 to 84.2) and 2.5 points on GSM8K.
  - Scaling 5, 10 and 20 agents (gpt-3.5, MMLU) gave 73.2, 74.5 and 77.8. At 20 agents it used about 6% of GPTSwarm's prompt tokens. — [arXiv 2410.11782](https://arxiv.org/html/2410.11782)
- **AgentPrune (Zhang et al., ICLR 2025) [verified]:**
  - It models multi-agent communication as a spatial-temporal graph, learns a differentiable edge mask for a few rounds (policy gradient plus a low-rank penalty), then prunes once.
  - It matches state-of-the-art topologies at about $5.6 vs. $43.7.
  - Plugged into AutoGen and GPTSwarm, it cut tokens by 28.1-72.8%; on GPTSwarm GSM8K it cut prompt tokens 60.6% while improving accuracy 0.84%.
  - Preliminary finding: randomly removing 10-30% of edges in a 4-agent gpt-3.5 MMLU system sometimes *improved* accuracy (up to +2.83%), evidence of communication redundancy.
  - Five-agent GPT-4 average across six benchmarks: about 88.4-89.7, vs. baselines from 82.07 (star) to 87.02 (PHP). — [arXiv 2410.02506](https://arxiv.org/html/2410.02506)
- **GPTSwarm (Zhuge et al., ICML 2024) [recall]:** agents are computational graphs of operations (nodes) and communication (edges). Prompts are optimized at node level and edges via REINFORCE over edge probabilities; evaluated on MMLU, Mini Crosswords, HumanEval and GAIA. — [arXiv 2402.16823](https://arxiv.org/abs/2402.16823)
- **DyLAN (Liu et al. 2023) [recall]:** a dynamic multi-layer agent network with inference-time agent selection and early stopping. An unsupervised "Agent Importance Score" selects the team. — [arXiv 2310.02170](https://arxiv.org/abs/2310.02170)
- **Multi-agent debate (Du et al. 2023) [recall]:** multiple instances debate over rounds, improving GSM8K and arithmetic accuracy and factuality. Later analyses (e.g., Smit et al., "Should we be going MAD?") found debate often does not beat self-consistency or ensembling at equal compute and is sensitive to hyperparameters. — [Du et al., arXiv 2305.14325](https://arxiv.org/abs/2305.14325); [Smit et al., arXiv 2311.17371](https://arxiv.org/abs/2311.17371)
- **"Towards a Science of Scaling Agent Systems" (Kim et al., Google, v3 Apr 2026) [verified, abstract only]:**
  - 260 configurations across 6 agentic benchmarks and 3 LLM families. Architectures: single-agent, Independent, Centralized, Decentralized and Hybrid multi-agent.
  - Multi-agent ranged from +80.8% on decomposable financial reasoning to -70.0% on sequential planning.
  - Returns diminish once the single-agent baseline is already strong ("capability saturation"), and tool-heavy tasks pay a multi-agent overhead.
  - Architectures without centralized verification propagate errors more.
  - A predictive model chose the best architecture for 87% of held-out configurations (cross-validated R² 0.37-0.41). — [arXiv 2512.08296](https://arxiv.org/abs/2512.08296)

### Inferences
- Reusable experimental grid:
  - Fixed topologies: chain, star, tree, mesh, layered, random.
  - Learned or pruned graphs.
  - Agent count of 1, 2, 4, 8, 16, 32 (fit a logistic curve in log N).
  - Metrics per configuration: accuracy, total prompt and completion tokens, dollar cost, wall-clock time, and accuracy under one adversarial or faulty agent.
- The Kim et al. result is the strongest 2026 evidence that the task's decomposability, not the topology itself, predicts whether a graph helps. Atomicity experiments should label tasks as parallelizable vs. sequential.
- Since random edge pruning can improve accuracy, sparse graphs should be the default, with dense graphs treated as an ablation.

### Gaps
- MacNet's absolute token costs per topology were not given, beyond the 7.51x growth and the O(n²) vs. O(n) analysis.
- Kim et al.'s numeric error-amplification factors and saturation threshold appear only in the full text, which was not read.
- Most topology papers use GPT-3.5 or GPT-4 agents. I found no verified topology study using sub-10B SLM agents.

## Q4. Hierarchical decomposition with small models: does a decomposed small-model pipeline beat a single larger model?

### Takeaway
Decomposition reliably helps compositional and length-generalization tasks (Least-to-Most, DecomP). Pipelines that split planning, tool-calling and summarization into separate small models have beaten a single same-size model and sometimes larger ones. NVIDIA's 2025 position paper argues that 40-70% of LLM calls in real agent frameworks could go to fine-tuned SLMs, but that is a qualitative estimate, not a measured benchmark result.

### Cited Findings
- **NVIDIA "Small Language Models are the Future of Agentic AI" (Belcak et al. 2025) [verified]:** a position paper.
  - Serving a 7B SLM is claimed to be 10-30x cheaper than a 70-175B LLM in latency, energy and FLOPs.
  - Estimated share of calls replaceable by SLMs: MetaGPT about 60%, Open Operator about 40%, Cradle about 70%.
  - SLMs are defined pragmatically as models that fit on consumer devices (in practice under about 10B as of 2025).
  - Heterogeneous systems are proposed for when broad conversational ability is needed. — [arXiv 2506.02153](https://arxiv.org/html/2506.02153)
- **NVIDIA LLM-to-SLM conversion algorithm [verified]:**
  1. Log agent calls securely.
  2. Curate the data and remove PII.
  3. Cluster tasks without supervision to find recurring tasks.
  4. Select candidate SLMs.
  5. Fine-tune them (LoRA/QLoRA or distillation), with 10k-100k examples as a rule of thumb.
  6. Iteratively retrain the SLMs *and the router*.

  Step 3 parallels MBC clustering in Arrow. — [arXiv 2506.02153](https://arxiv.org/html/2506.02153)
- **Agent-Oriented Planning (ICLR 2025) [verified, abstract]:** a meta-agent decomposes queries and assigns sub-tasks to agents under three principles (solvability, completeness, non-redundancy). A reward model scores the plan and a feedback loop revises it. It reports gains over single-agent and other multi-agent planning baselines (no numbers in the abstract). — [arXiv 2410.02189](https://arxiv.org/abs/2410.02189)
- **HuggingGPT (Shen et al., NeurIPS 2023) [recall]:** an LLM controller performs four stages: task planning, model selection (from Hugging Face model descriptions), execution, and response generation. The controller LLM's planning quality was the bottleneck, and the paper notes latency and cost from multiple LLM calls. — [arXiv 2303.17580](https://arxiv.org/abs/2303.17580)
- **Least-to-Most prompting (Zhou et al., ICLR 2023) [recall]:** decompose a problem, then solve the sub-problems sequentially. On SCAN length split it reached about 99.7% accuracy with 14 exemplars vs. about 16% for chain-of-thought (code-davinci-002). — [arXiv 2205.10625](https://arxiv.org/abs/2205.10625)
- **Decomposed Prompting / DecomP (Khot et al., ICLR 2023) [recall]:** a decomposer prompt delegates to modular sub-task handlers (prompts, symbolic functions or retrieval), each of which can be optimized or replaced separately. It outperforms CoT on symbolic manipulation, long-context and multi-hop QA. — [arXiv 2210.02406](https://arxiv.org/abs/2210.02406)
- **α-UMi, "Small LLMs Are Weak Tool Learners: A Multi-LLM Agent" (Shen et al. 2024) [recall]:** splits tool use into planner, caller and summarizer small LLMs (7B/13B), each fine-tuned. It outperforms a single-LLM agent of the same size on tool-use benchmarks such as ToolBench. This is a direct example of a decomposed small-model pipeline beating a monolithic one. — [arXiv 2401.07324](https://arxiv.org/abs/2401.07324)

### Inferences
- The strongest experimental design to reuse is α-UMi-style role decomposition with per-role fine-tuned SLMs, compared against (a) one SLM fine-tuned on all roles, (b) a larger single model, and (c) the decomposed pipeline with an oracle planner. Arm (c) isolates manager error.
- NVIDIA's 40-70% figures are qualitative estimates. Quote them as claims, not benchmark results.

### Gaps
- I did not verify, this session, specific 2025-2026 benchmark results where a graph of SLMs beats a single frontier model end to end. This needs a targeted search.
- HuggingGPT's quantitative planning-accuracy numbers were not re-checked.

## Q5. Known failure modes and mitigations

### Takeaway
Multi-agent systems often show minimal gains over single agents. Their failures cluster into system design, inter-agent misalignment and missing verification. Errors compound on sequential tasks (down to -70% vs. single-agent in Kim et al.), and centralized verification, sparse or pruned communication, and memory control are the best-supported mitigations.

### Cited Findings
- **MAST, "Why Do Multi-Agent LLM Systems Fail?" (Cemri et al. 2025) [verified, abstract]:** more than 1,600 annotated traces from 7 frameworks. The taxonomy has 14 failure modes in 3 categories (system design issues, inter-agent misalignment, task verification), with inter-annotator kappa = 0.88. An LLM-as-judge annotator is released. Multi-agent systems often show "minimal performance gains" on popular benchmarks. — [arXiv 2503.13657](https://arxiv.org/abs/2503.13657)
- **Error propagation and decomposability [verified]:** architectures without centralized verification propagate errors more. Sequential planning tasks degraded by up to 70%, and tool-heavy tasks pay coordination overhead. — [arXiv 2512.08296](https://arxiv.org/abs/2512.08296)
- **Communication overhead [verified]:** context grows O(n²) without memory control (MacNet), and AgentVerse suffered context explosion beyond about 30 agents. — [arXiv 2406.07155](https://arxiv.org/html/2406.07155). Redundant edges can be pruned with equal or better accuracy and 28-73% fewer tokens. — [arXiv 2410.02506](https://arxiv.org/html/2410.02506)
- **Faulty or adversarial agents [verified]:** under adversarial agents, chain and complete-graph setups dropped up to 11.0%, while G-Designer dropped 0.3% (MMLU). — [arXiv 2410.11782](https://arxiv.org/html/2410.11782)
- **Router misclassification [verified]:** routers trained on out-of-domain data can perform at or below random (MMLU and GSM8K in RouteLLM). Fixing this required in-domain labeled or LLM-judged data. — [arXiv 2406.18665](https://arxiv.org/html/2406.18665v4)
- **Quality dilution [verified]:** mixing weaker models into an aggregator lowers average output quality (Self-MoA). — [arXiv 2502.00674](https://arxiv.org/abs/2502.00674)
- **Compounding on compositional tasks [recall]:** "Faith and Fate" (Dziri et al., NeurIPS 2023) shows transformer accuracy decays sharply with compositional depth (e.g., multi-digit multiplication). Errors early in a computation graph propagate. — [arXiv 2305.18654](https://arxiv.org/abs/2305.18654)

### Inferences
- Mitigations to build in:
  - A centralized verifier node.
  - Passing final artifacts only, rather than full transcripts.
  - Learned or pruned sparse edges.
  - Router confidence thresholds with escalation to a larger model (FrugalGPT/Hybrid-LLM style cascades).
  - Reward-model checking of the manager's decomposition (AOP).
- Instrument every run with MAST failure labels, using the released LLM judge, so failure-mode rates can be compared across graph configurations.
- Error compounding can be estimated directly: per-node accuracy p over depth d predicts roughly p^d end-to-end. Compare that prediction with observed accuracy to test whether verification nodes break the compounding.

### Gaps
- MAST per-mode percentages and quantitative mitigation results were not available from the abstract.
- I found no verified study that measures manager-decomposition error rates separately from executor error rates for SLM-based pipelines.

## Q6. Granularity and specialization: number and narrowness of experts vs. accuracy (maps to "atomicity")

### Takeaway
The best direct evidence (Arrow/MBC) shows an intermediate granularity optimum: 10 clustered experts beat both 1 shared and 256 per-task experts. In agent graphs, MacNet and G-Designer show accuracy increasing sub-linearly or logistically with agent count. No verified study yet sweeps expert narrowness for SLM agent graphs specifically.

### Cited Findings
- 1 shared LoRA (65.5) < 256 private LoRAs with Arrow (66.6) < 10 MBC clusters (67.1-67.4), on Phi-2 zero-shot. Naive merging of 256 fine-grained experts (64.8) is worse than one shared LoRA. — [arXiv 2405.11157](https://arxiv.org/html/2405.11157v1)
- Agent-count scaling is logistic in log N, with saturation around 100 agents and 16 as a practical choice. — [arXiv 2406.07155](https://arxiv.org/html/2406.07155)
- G-Designer accuracy rose 73.2, 74.5 and 77.8 for 5, 10 and 20 agents. — [arXiv 2410.11782](https://arxiv.org/html/2410.11782)
- Majority voting plateaus at about 8 agents (MacNet). — [arXiv 2406.07155](https://arxiv.org/html/2406.07155). Sampling-and-voting keeps scaling on harder tasks [recall]. — [arXiv 2402.05120](https://arxiv.org/abs/2402.05120)
- BTM [recall]: gains grow as the number of domain experts increases under a fixed compute budget. — [arXiv 2208.03306](https://arxiv.org/abs/2208.03306)

### Inferences
- Atomicity experiment template:
  - Hold total training data and compute fixed.
  - Partition tasks into K experts with K ∈ {1, 2, 4, 10, 32, all-tasks}, using either semantic clustering or parameter-similarity (MBC) clustering.
  - Route with {uniform, classifier, kNN, Arrow, oracle}.
  - Report held-in and held-out accuracy, router accuracy, end-to-end latency and tokens.
  - Expect a U-shaped optimum, and expect the router to matter more as K grows.

### Gaps
- Full cluster-count sweep values for Fig. 4 of the Arrow paper were not extractable from the text.
- No verified 2025-2026 papers were found on expert-granularity sweeps for multi-agent SLM graphs. A dedicated search is recommended.
