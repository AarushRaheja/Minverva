# Exact numeric audit regression

Audit 2.1 closes a demonstrated false pass: a deliberately incorrect quantity display showed 11, 12 and 13 while the required values were 1, 2 and 3. The old substring assertions accepted every workflow on desktop and mobile. Exact assertions rejected the incorrect display, and the correct reference passed both assertion modes.

| Fixture | Substring checks | Exact checks |
|---|---|---|
| Correct quantity | Pass | Pass |
| Incorrect prefixed quantity | Pass (false pass) | Fail as expected |

All four variants compiled and rendered successfully in network-blocked Modal sandboxes. Their accessibility, overflow and runtime checks passed. The strengthened assertions—not an unrelated build or scanner failure—rejected the mutation.

Numeric quantity and cart-count targets now use `expect_text_exact`, which applies Playwright's whitespace-normalized text equality. Other text checks retain their original substring behavior. Both successful and failed text assertions save a separate observed-text sample, bounded to 20 strings of 2,000 characters with an explicit truncation flag. The sample is taken after the assertion; it is not a claim of continuous state stability.

This changes the expanded audit protocol. Historical baseline and repair scores remain frozen and cannot be relabeled as exact numeric verification. New results must record audit 2.1. The six-case Thinking Critic comparison uses the original frozen audit 2.0 evidence and is unaffected.

The sources are original assistant-authored harness fixtures, not model-generated improvements or human-reviewed training data. The experiment is complete; Modal app `ap-xi6Ack1TTwRV10ACfyBZZk` is stopped with zero tasks. Local validation: 57 tests, Ruff and JavaScript syntax checks pass.
