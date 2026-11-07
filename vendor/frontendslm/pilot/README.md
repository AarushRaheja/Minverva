# Original review candidates

`notification-preferences.tsx` is an original assistant-authored local-state interface. It is separate from the 50 evaluation briefs and their model outputs. It is not a 4B model result or an accepted training example. A subsequent [human visual review](../reports/human-review-v1.md) rates this reference 4/5; its scope must not be generalized to model quality or manually tested behavior.

`scripts/prepare_review_pilot.py` renders the working candidate and three deliberate mutations on Modal. The working candidate passed the full measured audit; the missing-save, low-contrast, and mobile-overflow variants failed their intended groups. `scripts/package_review_pilot.py` produces a static review page, screenshots, source ZIPs, raw evidence links, provenance, and checksums in `artifacts/original-review-pilot-v1`.

The review page asks for spontaneous descriptors before revealing the author's intended direction, then records visual quality, primary-action clarity, first intended action, comments, and whether the reviewer personally tried the interactions. Screenshot inspection must not be reported as manual interaction testing. Exported reviews stay local, include the source checksum, and remain `submitted_for_validation` with `training_eligible: false`.

Before any training acceptance:

1. A human verifies or corrects the brief, source/render correspondence, design labels and behavior claims.
2. Review provenance identifies the actual reviewer and exact source version; changed source requires renewed review.
3. Source permissions and duplicates are checked. Every variant in this family stays in the same split.
4. Working examples and intentionally broken Critic examples are assigned distinct roles. Broken code must not become an Architect target.
5. A separate versioned dataset manifest records accepted examples. None currently exists.

The supplied blueprint explicitly orders “Human verification and correction” before “Versioned training dataset.” No review or training approval has been inferred from automated test success.

Use `scripts/import_human_review.py <submitted-json>` to validate a feedback submission against its exact source and saved packet hashes. The importer preserves raw data under `artifacts/human-reviews`, adds a scoped observation to the preference profile, and keeps training eligibility separate. The original packet's zero-review count describes its creation-time snapshot; the current review index records later submissions.

## Original revision candidates

`scripts/prepare_revision_candidates.py` derives three review candidates from the saved controlled defects and the working reference. It verifies the original artifact checksums, exact intended failure groups and full passing reference audit before exporting complete corrected components, reviewable code diffs, and evidence hashes. Open `artifacts/original-revision-candidates-v1/review.html` to inspect them.

These are assistant-authored controlled repairs, not successful 4B-model trajectories. They share one corrected implementation and one design family. All remain unassigned to splits, unreviewed and ineligible for training; they must never be counted as three independent designs or mixed with evaluation outputs.
