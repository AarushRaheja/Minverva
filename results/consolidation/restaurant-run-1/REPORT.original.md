# back-of-house tool

**FALLBACK UI: no generated frontend worked, so this ships the plain reference UI. Not a model result.**

no generated UI worked, so the plain reference UI shipped

## Brief

**What:** A back-of-house tool where a restaurant owner tracks inventory items, suppliers and supplier invoices

**Look:** Clean and practical, high contrast, easy to read in a busy kitchen

## What was built

Entities in the plan: inventory_item, supplier, supplier_invoice.
Each has a table, a REST API and a section in the UI, with list and create by title. **Compare this with the brief:** anything else it asks for was not built.

## Frontend rounds

- Round 0: audit failed: build_pass, complete_render, interaction_pass, no_overflow, no_serious_a11y, nonempty, release_eligible, complete_state_measurements, state_accessibility_pass, state_overflow_pass, audit_pass
- Round 1: audit failed: build_pass, complete_render, interaction_pass, no_overflow, no_serious_a11y, nonempty, release_eligible, complete_state_measurements, state_accessibility_pass, state_overflow_pass, audit_pass

## Whole-stack journey

Sign up, create a row, reload, sign out, sign back in, and find the row: **passed**.

## Not checked by anything here

- Whether the design is good: nothing automated measures that.
- Whether every visible control does what its label says, beyond the tested flows.
- Security review of the generated code.

## Run

- Engine: `modal`
- Estimated cost: $0.58
- Round-by-round evidence: `frontend/`
