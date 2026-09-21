# Implementation: `/eval-rb` execution procedure

**Status: ratified** — DR-CMD-017 (2026-09-20). Implements the validation routine declared in `doc/slash-commands/eval-rb.md` (Check dimensions as declared in the contract; dimensions 7–10 apply the DR-CMD-009 declaration-presence regime — the pattern application ratified in DR-CMD-017; see design §2). Design counterpart: `doc/eval-rb-design.md` (ratified, DR-CMD-017).

## 0. Execution model

`/eval-rb` is executed by the ambient agent in the invoking chat session. "Execution" means the agent performs this procedure: parse, resolve, admit, per-dimension validation, report. Steps marked `[mechanical]` are exact operations. Steps marked `[judgment]` require the agent's reasoning, reported with reasons and normative citations, never bare verdicts. Steps marked `[mechanical format, judgment content]` have a mechanical format — the template is followed exactly — and judgment content — every finding carries reasons and citations, never bare verdicts. The agent never writes to the candidate, the repo, or any record store during execution. Deviations are reported, never repaired: repair is a mutation matter for `/pb-decide`.

## 1. Parse the invocation `[mechanical]`

Input line: `/eval-rb {matter}`.

1. Empty matter → refuse back with the usage line, no report: `usage: /eval-rb {matter}` — where `{matter}` is a run-book candidate: a procedure claiming the run-book form, given as a `/name`, a repo-relative path, or inline text.
2. Non-empty matter → CANDIDATE-SRC = the matter text, trimmed.

## 2. Resolve the candidate `[mechanical]`

1. If CANDIDATE-SRC is a `/name` (starts with `/`, contains no spaces) → resolve to `doc/slash-commands/<name>.md`. If it is a repo-relative path → resolve as given. Read the file. Record the resolved path and the commit the bytes came from (`git rev-parse HEAD` for working-tree reads — flagged as working tree[, clean|modified]).
2. Otherwise the candidate is the inline text itself; record the source as `inline`.
3. A failed read → refuse back (`unresolvable candidate: <matter>`), no report.

## 3. Admission `[judgment]`

The agent verifies, not classifies: is the matter actually a run-book candidate?

Comparability threshold: the matter must present a procedure *claiming the run-book form* — an automaton-plane executable: strictly ordered steps, each step an AST-allowlisted expression (compiled once) invoking a declared tool, zero inference inside, pinned to a shipped release (or claiming to). Markers: named steps in fixed order, tool bindings, guards as expressions, `release_version`, an `AutomatonRun` association.

Below the threshold → refuse back with redirect, no report: `/eval-pb` for playbooks (decision machinery), `/eval-meta` for general matters (claims, specs, transcripts). A merely sequential procedure that is not automaton-plane — e.g., a judgment-stepped ambient-agent procedure — does **not** pass the threshold: sequentiality alone is not the run-book form.

A run-book-adjacent non-run-book (procedure undefined, shape incomplete — e.g., this command's own contract, which validates run-books but is an ambient-agent procedure by declared design; a step list with no tool bindings) → admitted, but the only available overall verdict is "not evaluable against the definition" (§5).

The admission outcome is reported in one line at the top of the report (§6), with its reason.

## 4. Per-dimension validation `[judgment]`

For each of the ten check dimensions (§4.1–§4.10), produce one finding: **conforms** / **deviates** (with the normative clause cited) / **undefined-against** (the dimension does not apply to this candidate's kind — stated, never silent). Every finding carries one line of reasoning and at least one citation to the normative definition: `doc/glossary.md` "Run-book", the RunBook entity (`schema.py`), `doc/automaton-executor-spec.md`, or a ratified DecisionRecord. Never bare verdicts.

1. **Strictly sequential steps.** Does the candidate drive execution via ordered steps (fixed positions, advancing step to step), or via conditionals and gates? Conditional/gated flow → deviates (cited: glossary "strictly sequential").
2. **Step determinism.** Is each step an AST-allowlisted expression, compiled once per (`runbook_id`, `release_version`)? Steps with unallowlisted logic, or logic compiled per run → deviates (cited: glossary; executor-spec §5).
3. **Zero inference inside.** Does execution contain no LLM judgment — all inference outside, reaching the run-book only as step-changes? Inference inside execution → deviates (cited: glossary "Automaton"; executor-spec §2 "Not an agent").
4. **Steps invoke tools.** Does every step invoke a declared tool (dist-shipped, deterministic, idempotent, hermetic)? Steps with unbound actions, or actions outside the tool contract → deviates (cited: glossary; executor-spec §8).
5. **Pinned to a shipped release.** Does the candidate declare `release_version`, with tools dist-shipped and release-pinned? Unpinned run-book or tools → deviates (cited: glossary; executor-spec §4, §8).
6. **One run-book per `AutomatonRun`.** Does the candidate run as a single run-book per `AutomatonRun` — no multi-run-book runs, no run-book addressee on the CLI? Violations → deviates (cited: glossary; executor-spec §4).
7. **Exercise declared (DR-CMD-009 pattern).** Does the candidate cite at least one executed run (run id, transcript, or replay ref) exercising the steps? Absent → deviates (cited: DR-CMD-009, by pattern). Presence checked only — run *quality* is disposition's judgment (G5), never the validator's.
8. **Trigger declared (DR-CMD-009 pattern).** Does the candidate state when it applies and name the non-trigger cases where it does not? Absent → deviates (cited: DR-CMD-009, by pattern).
9. **Output format specified (DR-CMD-009 pattern).** Is the run's record shape defined (event-log schema or result envelope cited), not left to per-run invention? Absent → deviates (cited: DR-CMD-009, by pattern).
10. **Failure routing at G1 precision (DR-CMD-009 pattern, adapted).** Is per-step failure behavior named with its consequence (`abort | skip | retry:<n>`, per executor-spec §6), precise enough that a run could observably violate it? A policy no failure could trigger is decoration → deviates (cited: DR-CMD-009, by pattern; executor-spec §6). This is the run-book analog of the playbook's kill gates.

Dimensions 7–10 are declaration-presence checks on the DR-CMD-009 regime: the validator checks that the declaration exists and is cited, never whether the cited evidence is good.

## 5. Overall verdict `[judgment]`

- **conforms**: every applicable dimension conforms (undefined-against dimensions recorded, not penalized).
- **deviates (cited)**: one or more dimensions deviate; each cited.
- **not evaluable against the definition**: the §3 second branch — run-book-adjacent, shape incomplete.

## 6. Report `[mechanical format, judgment content]`

Byte-exact template. Refused matters get no report (§2, §3); the admission line therefore shows only the admitted outcomes.

```text
/eval-rb report
Candidate: <matter> -> <resolved source> @ <commit> [(working tree[, clean|modified]) | inline]
Admission: <admitted: <reason> | not evaluable: <reason>>

Findings:
1. Sequential steps: <conforms | deviates: <clause> | undefined-against: <reason>> — <one-line reason>
2. Step determinism: <...> — <one-line reason>
3. Zero inference: <...> — <one-line reason>
4. Tool invocation: <...> — <one-line reason>
5. Release pinning: <...> — <one-line reason>
6. One run-book per run: <...> — <one-line reason>
7. Exercise declared: <...> — <one-line reason>
8. Trigger declared: <...> — <one-line reason>
9. Output format: <...> — <one-line reason>
10. Failure routing: <...> — <one-line reason>

Overall: <conforms | deviates (cited) | not evaluable against the definition>
```

Pre-delivery checklist: admission line present; every dimension carries a finding; every deviates cites its clause; no bare verdicts; deviations reported, never repaired.

## 7. Worked example

2026-09-20: executed in-chat by the ambient agent — `/eval-rb` applied to its own contract (`doc/slash-commands/eval-rb.md`: Check dimensions + Admission + Output). Admission: run-book-adjacent non-run-book — the contract validates run-books but is a judgment-stepped ambient-agent procedure by declared design (Boundaries 1, 4: ambient layer only, evaluation is not decision); sequentiality alone does not pass the §3 threshold — → overall verdict **not evaluable against the definition**. Per-dimension: 1 deviates (the routine is sequential — parse → resolve → admit → validate → report — but its steps are judgment operations, not AST-allowlisted tool-invoking expressions); 2 deviates (steps are `[judgment]`, not compiled expressions); 3 deviates (the routine requires inference by design); 4 deviates (no tool invocation); 5 deviates (no `release_version`); 6 undefined-against (no `AutomatonRun` by design); 7 conforms (this run is cited); 8 conforms (Trigger + non-trigger cases declared in the contract); 9 conforms (byte-exact template in §6); 10 conforms (refusal paths named with exact texts).

## Glossary

- **candidate** — the run-book candidate under validation: CANDIDATE-SRC resolved (§2).
- **matter** — the text supplied to `/eval-rb` in chat.
- **admission** — the §3 gate: verifies the matter is actually a run-book candidate; verifies, never classifies.
- **dimension** — one of the ten check dimensions (§4.1–§4.10).
- **conforms / deviates / undefined-against** — the finding scale (§4, §5). Deviates always cites its normative clause; undefined-against states its reason.
- **normative clause** — the cited requirement: glossary "Run-book", the RunBook entity (`schema.py`), `doc/automaton-executor-spec.md`, or a ratified DecisionRecord (e.g., DR-CMD-009, by pattern).
- **comparability threshold** — the §3 bar: a procedure claiming the run-book form (automaton-plane, sequential, tool-invoking, zero-inference, release-pinned). Below it, redirect. Sequentiality alone does not pass.
- **declaration-presence** — the DR-CMD-009 check regime, applied by pattern: the validator checks that a declaration exists and is cited, never its quality.
