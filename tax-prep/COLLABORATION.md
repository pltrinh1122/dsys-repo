# tax-prep collaboration protocol

Two sessions share this repo. This file is the contract between them.

## Roles

- **Architect session** (Muse main chat): designs, codes, and verifies the
  `tax-prep` package. Works with **synthetic fixtures only**. Never sees,
  asks for, or receives real taxpayer documents, SSNs, or account numbers.
- **Workstation session** (Claude Code on Peter's Linux workstation):
  operates the agent against the **real** ~100 documents locally: runs
  `ingest`, drives the `review` UI, runs `carryforward`, and reports
  discrepancies back through Peter.

## The golden rule

Real taxpayer material never leaves the workstation. Concretely:

- Never commit anything under `tax-prep/data/` (gitignored: documents,
  OCR text, the JSONL store).
- Never paste real document content, SSNs, or dollar amounts from real
  returns into commit messages, chat with the Architect session, or issues.
- Discrepancy reports travel as *shapes*, not values: "W-2 box 1 regex
  missed a `$` prefix on one employer format" — never the actual numbers.

## Branch discipline

- Both sessions work on the same branch (currently `build/half1`).
- Architect lands code + specs + tests via commits; Workstation pulls.
- Workstation does not commit code changes. If it finds a bug, it reports
  the shape through Peter; Architect fixes and commits.
- Operational notes (local paths, run logs) stay on the workstation,
  never in the repo.

## Verification split

- Architect verifies with synthetic fixtures (`pytest`, golden cases).
- Workstation verifies operation on real data (counts reconcile,
  review queue drains, carryforward inputs match validated docs).
- A real-data discrepancy is a bug report against the synthetic suite:
  Architect adds a synthetic fixture reproducing the *shape* and fixes it.

## Push

Pushing to origin is Peter's separate explicit call (single-use device
flow). The Workstation session pulls only after a push it was told about.
