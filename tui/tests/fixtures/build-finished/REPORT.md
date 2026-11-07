# back-of-house tool

**FALLBACK UI: no generated frontend worked, so this ships the plain reference UI. Not a model result.**

## Brief

**What:** A back-of-house tool where a restaurant owner tracks inventory items, suppliers and supplier invoices

**Look:** Clean and practical, high contrast, easy to read in a busy kitchen

## What was built

Entities in the plan: inventory_item, supplier, supplier_invoice.
Each has a table, a REST API and a section in the UI, with list and create by title.

## Frontend rounds

- Round 0: the build failed
  - Build errors: src/App.tsx(94,30): error TS2345: Argument of type '{ message: string; status: number; }' is not assignable
- Round 1: the build failed
  - Build errors: src/App.tsx(17,66): error TS2304: Cannot find name 'ApiError'.

## Whole-stack journey

Sign up, create a row, reload, sign out, sign back in, and find the row: **passed**.

## Run

- Engine: `modal`
- Estimated cost: $0.58
