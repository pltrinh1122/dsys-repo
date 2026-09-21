# Design: `/sc-author` — slash-command triplet completion

**Status:** active — created 2026-09-20 per operator direction. Design reasoning for the `/sc-author` triplet-completion routine. The normative procedure is `doc/sc-author-implementation.md`; the operator-facing contract is `doc/slash-commands/sc-author.md`. Per the standing principle, provenance and reasoning live here, not in the implementation doc.

## 1. What `/sc-author` is

`/sc-author` codifies the routine exercised 2026-09-20 to complete the `/eval-rb` and `/pb-extend` triplets: given a slash command (existing or proposed), produce its contract, implementation, and design artifacts on the DR-CMD-006 / DR-CMD-010 schema, staged as DRAFTs for disposition. It is an **authoring instrument**: it completes structure. Substance — the normative procedure, the dimensions, the conditionals, the report shape — comes from the matter's normative source, never from the author. This is the standing "do not invent mechanisms" constraint operationalized as a procedure: where substance is missing, the draft carries explicit `GAP:` flags; where the matter cannot be framed, the command refuses back rather than staging half-invented machinery.

The authority chain is three links, each owned by a different act: the agent **authors** (this command), the operator **disposes** (ratify / refuse / reframe the staged DRAFTs), and only disposition **deploys**. `/sc-author` never performs the second or third link — and it never ratifies its own output, which would be self-disposition voiding proposer≠disposer. This mirrors the family's existing separations: evaluation≠decision (`/eval-*`), authoring≠deploying (here).

## 2. The two matter forms — design rationale

`/sc-author` accepts an existing `/name` or a new-command proposal because triplet completion has two real cases, and tonight exercised both halves: `/eval-rb` needed authoring from a ratified pattern plus a contract's declared dimensions; `/pb-decide` and `/pb-extend` needed remediation of existing contracts (Family, Description, S2 trigger grammar — the same three gaps twice, which is why §4 of the implementation names the remediation pattern explicitly). The inventory step (§2) exists so the command never re-authors what exists and never misses what doesn't: each triplet member and each schema edge is checked present/absent before any writing.

The new-proposal form demands four elements — name, family, one-line purpose, normative source — because those are exactly the inputs the authoring steps consume: the name locates the files, the family selects the contract's authority posture and section treatment, the purpose becomes the Description, and the normative source is operationalized into the implementation body. A proposal missing any of them is refused back naming the missing piece; this is the same input-shaping the family's triggers already do (bare invocations refused, vague matters reframed).

## 3. Why the output is always DRAFT

The staged artifacts are DRAFTs not because they are unfinished but because **only the operator's disposition deploys**. A chat response is not authority, and an agent-authored file is not a deployed command — the DRAFT header is the file-level enforcement of that principle. This is also why the staging report carries the `/eval-sc` verification result *reported, not repaired*: deviations in the staged triplet are the operator's disposition input. An author that silently repaired its own output against the evaluator would be disposing by stealth.

## 4. Relation to the anticipated verification harness — name provenance

The name `sc-author` was anticipated earlier (M5; DR-CMD-007 G6) as a **verification** harness with a corresponding automaton — the machinery for extensive, especially Python-driven, mechanical verification/validation that does not belong inside a slash command. This command is the **authoring** instrument: a chat-session judgment routine that completes prose triplets. Related stem, distinct functions. The verification harness remains future work — a legitimate expansion matter for `/pb-extend` when the operator wants it — and this command's contract does not claim it. The collision is recorded here so the two are never confused: authoring triplets (this command, now) vs mechanically verifying them (harness, later).

## 5. Character of the routine

`/sc-author` is a judgment routine in the ambient layer: parse, inventory, author, verify, stage. It performs no extensive execution — no Python-driven machinery — so it respects the M5 layer boundary by construction; the heavy verification it invokes (`/eval-sc` on the staged contract) is itself a chat-session procedure. Deterministic replay holds in the weak sense: same matter bytes, same normative source → same staged artifacts, modulo the judgment content, which is why every authored finding carries its reasons. The routine is sequential by design; it does not claim the run-book form.

## 6. Boundaries (retained)

From the contract: ambient layer only — never installed, never on the dsys CLI tree, never invokable by the automaton executor; authoring is not disposition and not deployment — no ratification, no DecisionRecords, no push, and never of its own output; substance from the matter — gaps flagged (`GAP:`), never invented, never silently bridged; writes only the staged triplet files — normative sources, runtime, installed trees, and live state untouched.

## 7. Provenance

Authoring notes (durable):

- 2026-09-20 (creation): built per operator direction ("create new slash command '/sc-author {matter}' that completes the required design, contract and implementation triplet artifacts. the triplet artifacts would need operator disposition before it can be deployed and used."). Created complete — the creation order is the disposition; no DRAFT phase, no DecisionRecord for the creation act (same practice as the remediation acts).
- 2026-09-20 (creation): the `sc-*` family declared with `/sc-author` as first member, following DR-CMD-001's namespace-first family argument (`pb-*`, `eval-*` precedents).
- 2026-09-20 (creation): the rehearsal/governed-style regime question does not arise — `/sc-author`'s own procedure is created active, not draft-gated; only its *output* is DRAFT-for-disposition.
- 2026-09-20 (creation): name provenance recorded in §4 — the anticipated verification harness (M5, DR-CMD-007 G6) is a distinct future instrument; this command is the authoring one.

## G6 / open

- The verification-harness half of the `sc-author` name (M5's anticipated harness + automaton for extensive mechanical verification): still future, still un-designed. If the operator wants it, it is a `/pb-extend` expansion matter.
- Whether `/sc-author` should ever *update* the standing exemplar's 11-section set (as opposed to applying it): currently no — it applies the set; changing the set is a family matter for `/pb-decide`, not an authoring judgment.
- Worked executions: none yet — the first `/sc-author` run will exercise §§2–8 against a real matter.
- `/eval-meta` on "'/sc-author' validates completion by checking for existence of target's triplet" (2026-09-20, verdict *decomposed*) named one small gap: §7 step 2's absent-file failure path is unspecified (DR-CMD-019, ratified O2: record and defer). Analysis: the case is behaviorally covered upstream — §2's inventory records implementation/design present/absent for existing matters, and §§4–6 author whatever the inventory found absent, so §7's greps run over in-hand texts (authored drafts, or files read at §2). No procedure change. Revisit trigger: the first real `/sc-author` run — if it surfaces ambiguity in §7's grep target, add the one-line clarification then (O1's text stands ready).
- The `sc-*` family's future membership: unknown. A second member (if any) would test whether the family declaration holds.

## Glossary

- **triplet** — the three artifacts: contract (`doc/slash-commands/<name>.md`), implementation (`doc/<name>-implementation.md`), design (`doc/<name>-design.md`).
- **authoring** — completing the triplet's structure from the matter's substance; the agent's act.
- **disposition** — the operator's act on staged DRAFTs (ratify / refuse / reframe); only disposition deploys.
- **deployment** — a staged command becoming usable as an instrument; follows disposition, never precedes it.
- **inventory** — the §2 check of which triplet members and schema edges exist (present/absent) before authoring.
- **exemplar set** — the 11-section contract anatomy from the standing exemplar.
- **normative source** — the procedure or spec the matter command binds or operationalizes; the substance `/sc-author` never invents.
- **`GAP:`** — explicit flag in a staged draft for under-specified procedure substance.
- **self-disposition** — the forbidden act: `/sc-author` ratifying its own output, voiding proposer≠disposer.
- **verification harness** — the anticipated (M5, DR-CMD-007 G6) future instrument for extensive mechanical verification; distinct from this authoring command.
