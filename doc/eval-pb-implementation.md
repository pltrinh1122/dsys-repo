# Implementation: `/eval-pb` execution procedure

**Status: ratified** — DR-CMD-015, 2026-09-20. Implements the validation routine declared in `doc/slash-commands/eval-pb.md` (Check dimensions as ratified through DR-CMD-009). Amended DR-CMD-020 (worked reference named; no dimension changed). Design counterpart: `doc/eval-pb-design.md` (ratified DR-CMD-015 — provenance and reasoning live there, per DR-CMD-010).

## 0. Execution model

`/eval-pb` is executed by the ambient agent in the invoking chat session. "Execution" means the agent performs this procedure: parse, resolve, admit, per-dimension validation, report. Steps marked `[mechanical]` are exact operations. Steps marked `[judgment]` require the agent's reasoning, reported with reasons and normative citations, never bare verdicts. Steps marked `[mechanical format, judgment content]` have a mechanical format — the template is followed exactly — and judgment content — every finding carries reasons and citations, never bare verdicts. The agent never writes to the candidate, the repo, or any record store during execution. Deviations are reported, never repaired: repair is a mutation matter for `/pb-decide`.

## 1. Parse the invocation `[mechanical]`

Input line: `/eval-pb {matter}`.

1. Empty matter → refuse back with the usage line, no report: `usage: /eval-pb {matter}` — where `{matter}` is a playbook candidate: a procedure claiming the playbook form, given as a `/name`, a repo-relative path, or inline text.
2. Non-empty matter → CANDIDATE-SRC = the matter text, trimmed.

## 2. Resolve the candidate `[mechanical]`

1. If CANDIDATE-SRC is a `/name` (starts with `/`, contains no spaces) → resolve to `doc/slash-commands/<name>.md`. If it is a repo-relative path → resolve as given. Read the file. Record the resolved path and the commit the bytes came from (`git rev-parse HEAD` for working-tree reads — flagged as working tree[, clean|modified]).
2. Otherwise the candidate is the inline text itself; record the source as `inline`.
3. A failed read → refuse back (`unresolvable candidate: <matter>`), no report.

## 3. Admission `[judgment]`

The agent verifies, not classifies: is the matter actually a playbook candidate?

Comparability threshold: the matter must present a procedure *claiming the playbook form* — decision machinery: something that frames matters, enumerates options, gates them, and drives toward disposition (or claims to). Markers: named decision roles (proposer/disposer or equivalent), verdict/disposition production, conditional or gated flow.

Below the threshold → refuse back with redirect, no report: `/eval-rb` for run-books (sequential procedures), `/eval-meta` for general matters (claims, specs, transcripts).

A playbook-adjacent non-playbook (procedure undefined, shape incomplete — e.g., a binding without a procedure, a decision checklist with no gates) → admitted, but the only available overall verdict is "not evaluable against the definition" (§5).

The admission outcome is reported in one line at the top of the report (§6), with its reason.

## 4. Per-dimension validation `[judgment]`

For each of the ten check dimensions (§4.1–§4.10), produce one finding: **conforms** / **deviates** (with the normative clause cited) / **undefined-against** (the dimension does not apply to this candidate's kind — stated, never silent). Every finding carries one line of reasoning and at least one citation to the normative definition: `doc/glossary.md` "Playbook (decision-making)", `doc/dyad-architecture-doc.md` §8.2 (§8.3 for records), or a ratified DecisionRecord. Never bare verdicts.

**Worked reference (DR-CMD-020):** `doc/dsys-mutation-playbook-spec.md` — the ratified second playbook (§8.4); `/eval-pb` run 2026-09-21 returned conforms (10/10). The agent may consult it to ground judgment calls (e.g., what G1-precision gates look like in practice). Consultative only: every finding still cites the normative definition per above; the reference is never a substitute standard and adds no comparative axis (DR-CMD-011 stands).

1. **DoD conditionals, not sequences.** Does the candidate drive matters via definition-of-done conditionals (entry trigger + exit condition, condition-triggered, re-entrant — §8.2, I-4), or via ordered steps? Ordered steps → deviates (cited: glossary "not a sequence").
2. **Explicit admission/kill gates.** Are entry gates and kill/merge gates named, each with its failure routing? Admission without kill, or gates that name no reason on failure → deviates (cited: §8.2 START/STOP).
3. **Disposition modes each with their own DoD.** Does the candidate enumerate its disposition modes — its analog of §8.2's ratify | authorize | set_standing | overrule | triage — each with a definition of done? A mode without its DoD → deviates (cited: §8.2 disposition modes).
4. **Proposer ≠ disposer.** Are proposing and disposing separated, with disposition requiring the disposer's act? Self-disposition, or disposition on the proposer's authority alone → deviates (cited: §8.2 KEEP).
5. **Records writable only on disposition.** Are persistent records (DecisionRecords or the candidate's analog) writable only as the product of a disposition? Records writable mid-deliberation, or dispositions that write no record → deviates (cited: §8.3).
6. **Plane discipline.** Is the candidate a procedure the operator *follows*, not a node commanded — with sequencing left to run-books? Command-nodes or embedded sequencing → deviates (cited: glossary).
7. **Exercise declared (DR-CMD-009).** Does the candidate cite at least one executed run (transcript or record ref) exercising the admit and kill paths? Absent → deviates (cited: DR-CMD-009). Presence checked only — run *quality* is disposition's judgment (G5), never the validator's.
8. **Trigger declared (DR-CMD-009).** Does the candidate state when it applies and name the non-trigger cases where it does not? Absent → deviates (cited: DR-CMD-009).
9. **Output format specified (DR-CMD-009).** Is the record/report shape the candidate produces defined (template or schema cited), not left to per-run invention? Absent → deviates (cited: DR-CMD-009).
10. **Gates at G1 precision (DR-CMD-009).** Are the admission/kill gates stated precisely enough to *fail* — i.e., could a matter observably fail them? A gate no matter could fail is decoration → deviates (cited: DR-CMD-009).

Dimensions 7–10 are declaration-presence checks per DR-CMD-009: the validator checks that the declaration exists and is cited, never whether the cited evidence is good.

## 5. Overall verdict `[judgment]`

- **conforms**: every applicable dimension conforms (undefined-against dimensions recorded, not penalized).
- **deviates (cited)**: one or more dimensions deviate; each cited.
- **not evaluable against the definition**: the §3 second branch — playbook-adjacent, shape incomplete.

## 6. Report `[mechanical format, judgment content]`

Byte-exact template. Refused matters get no report (§2, §3); the admission line therefore shows only the admitted outcomes.

```text
/eval-pb report
Candidate: <matter> -> <resolved source> @ <commit> [(working tree[, clean|modified]) | inline]
Admission: <admitted: <reason> | not evaluable: <reason>>

Findings:
1. DoD conditionals: <conforms | deviates: <clause> | undefined-against: <reason>> — <one-line reason>
2. Admission/kill gates: <...> — <one-line reason>
3. Disposition modes: <...> — <one-line reason>
4. Proposer/disposer: <...> — <one-line reason>
5. Records on disposition: <...> — <one-line reason>
6. Plane discipline: <...> — <one-line reason>
7. Exercise declared: <...> — <one-line reason>
8. Trigger declared: <...> — <one-line reason>
9. Output format: <...> — <one-line reason>
10. Gate precision: <...> — <one-line reason>

Overall: <conforms | deviates (cited) | not evaluable against the definition>
```

Pre-delivery checklist: admission line present; every dimension carries a finding; every deviates cites its clause; no bare verdicts; deviations reported, never repaired.

## 7. Worked example

2026-09-20: executed in-chat by the ambient agent — `/eval-pb` applied to its own validation routine (the Check dimensions + Admission + Output of `doc/slash-commands/eval-pb.md`). Admission: playbook-adjacent non-playbook — Kind is slash-command, and the disposition machinery is absent by declared design (Boundaries 3–4: evaluation is not decision) — → overall verdict **not evaluable against the definition**. Per-dimension: 4, 5, 6 conform; 1 deviates (the routine is sequential: admit → check → report); 2 deviates (admission gate present, no kill branch); 3 undefined-against (no disposition by design). Note: this run predates DR-CMD-009 — dimensions 7–10 did not exist; the routine's exercise declaration would now be checked under dimension 7.

## Glossary

- **candidate** — the playbook candidate under validation: CANDIDATE-SRC resolved (§2).
- **matter** — the text supplied to `/eval-pb` in chat.
- **admission** — the §3 gate: verifies the matter is actually a playbook candidate; verifies, never classifies.
- **dimension** — one of the ten check dimensions (§4.1–§4.10).
- **conforms / deviates / undefined-against** — the finding scale (§4, §5). Deviates always cites its normative clause; undefined-against states its reason.
- **normative clause** — the cited requirement: glossary "Playbook (decision-making)", `doc/dyad-architecture-doc.md` §8.2/§8.3, or a ratified DecisionRecord (e.g., DR-CMD-009).
- **comparability threshold** — the §3 bar: a procedure claiming the playbook form (decision machinery: framing, options, gates, disposition). Below it, redirect.
- **declaration-presence** — the DR-CMD-009 check regime: the validator checks that a declaration exists and is cited, never its quality.
