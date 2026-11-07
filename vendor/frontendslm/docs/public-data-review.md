# Public data review

Checked 2026-11-07. This is a discovery record, not a training-data manifest. No third-party corpus was downloaded or used for training.

| Candidate | What the inspected primary source establishes | Current project decision |
|---|---|---|
| [UI-Bench paper, version 3](https://arxiv.org/html/2508.20410v3) | Uses blinded expert pairwise judgments with randomized placement and full-page inspection. It releases prompts and links a leaderboard, while its conclusion says the rated generated sites will be released later. | Useful evaluation methodology. A downloadable, licensed corpus pairing the sites with individual preference labels was not verified. Do not claim those labels are available for our training or calibration. |
| [DesignBench repository](https://github.com/WebPAI/DesignBench) and [linked dataset page](https://huggingface.co/datasets/whale99/DesignBench) | Describes 900 samples for generation, editing, and repair across several frameworks. The inspected repository root lists no license file; the dataset page has no dataset card. The page reports 1.12 GB of files even though its viewer says empty. | Potential future external benchmark. Explicit dataset permissions and suitability for preference calibration remain unverified. The unsupported viewer does not establish that the files are absent. |

The original notification-preferences pilot avoids this external provenance gap, but still lacks human verification. Its intended descriptors are author-supplied candidate labels, not measured user perception. Automated functionality results cannot supply that missing judgment.

Evaluation briefs, generated benchmark outputs, original candidate families, and any future accepted training data must remain separately tracked. A benchmark's public availability alone does not make it an appropriate training source.
