# Implementation: `/eval-meta` execution procedure

**Status: DRAFT** — proposed 2026-09-20. Implements
`doc/eval-meta-design.md` (DRAFT). Not evaluated, not
disposed.

## 0. Execution model

`/eval-meta` is executed by the ambient agent in the
invoking chat session. "Execution" means the agent
performs this procedure: parse, scope, the five checks,
and the two-section report. Steps marked **[mechanical]**
are exact commands. Steps marked **[judgment]** require
the agent's reasoning, reported with reasons, never bare
verdicts. The agent never writes to the accretion repo,
the instance tree, or any record store during execution.

## 1. Parse the invocation **[mechanical]**

Input line: `/eval-meta {matter}`.

1. Empty matter → refuse back with the usage line, no
   report:
   `usage: /eval-meta {claim}  |  /eval-meta {claim} :: {citations}`
2. Form B iff the matter contains a `::` delimiter or a
   trailing `Evidence:` / `Citations:` list. Otherwise
   Form A.
3. CLAIM = text before the delimiter, trimmed.
   CITATIONS = the list after it, one per line or
   comma-separated, trimmed.

## 2. Step 0 — scope determination **[judgment]**

Ask: does the claim's truth depend on instance state
(installed tree, accreted history, runtime behavior)?
State the answer with one reason.

- No → D3–D5 are N/A in the report (reason recorded);
  continue with checks 1–2 and adversarial reasoning.
- Yes → full pipeline.

## 3. Check 1 — falsifiability **[judgment]**

Admissible iff some observable state could refute the
claim. Test the four defects: tautological (true by
definition), vague (terms without referents),
normative-unoperationalized ("should" with no observable
criterion), untestable-in-principle (no observation could
bear on it).

On failure → refuse back, no report. Exact text:

> Refused back for reframing: the claim is <defect>.
> To reframe, supply <the missing operationalization>.

## 4. Check 2 — logical coherence **[judgment]** (Form B only)

On the cited evidence *as cited* — face value, no repo
touched. Verdict per sub-check, one line each:

- relevance — does it bear on the claim's truth
  conditions?
- non-circularity — it must not restate or assume the
  claim;
- internal consistency — the cited set must not
  contradict itself;
- sufficiency-in-form — *if* the cited evidence were
  true, would it move the needle, or is there a
  non-sequitur gap?

On failure → produce the report: D2 = fail (gap named),
D3–D5 = not-run, synthesis = refusal. Exact synthesis
text:

> Refused back: the cited evidence is incoherent
> (<the gap>). Reframe and resubmit.

## 5. Check 3 — grounding **[mechanical]**

Bind the instance. Default is the operator's instance;
the operator may qualify another instance home in the
invocation (multi-instance grammar is otherwise open —
G6).

```sh
H=<instance home>   # e.g. /tmp/evaltest
A=$(python3 -c "import json;print(json.load(open('$H/var/manifest.json'))['accretion']['path'])")
A=${A:-/var/daccretion/$(basename "$H")}   # manifest > default
G="git --git-dir=$A/.git"  # read-only handle
```

The manifest is read from the live tree as a *locator*
only, never as evidence; it records the resolved
accretion path (flags > config > default per the
installer spec).

Precondition: `$G rev-parse HEAD` succeeds. If not →
D3 = unevaluable (`accretion repo absent at <A>`), D4 =
N/A, D5 = unevaluable; skip to the report. Live-tree
observations may be noted in the synthesis, labeled as
observations, never as grounding.

Read-only verbs only: `show`, `cat-file -p`, `log`,
`ls-tree`, `rev-parse`. Nothing that writes, ever.

Per citation, resolve (`<path>` is relative to the
install home, e.g. `etc/config.yaml`):

- `<path>@<commit>` → `$G show <commit>:<path>`;
  pin = `<commit>:<path>`.
- `<path>` (unpinned) → `$G show HEAD:<path>`;
  pin = `HEAD:<path>`, flagged unpinned (declared
  trust).
- 40-hex SHA → `$G cat-file -p <sha>`;
  pin = `blob:<sha>`.
- record ID, label, or anything else → ungrounded:
  `non-file citation grammar open (G6)`.

A failing command → ungrounded with the reason (no such
path, no such commit, ambiguous SHA). Record per
citation the grounded bytes (or content hash + excerpt
for the report) or the ungrounded reason.

## 6. Check 4 — consistency **[mechanical + judgment]**

For each grounded citation, compare what the citation
*claimed* (quoted text, asserted values) against the
grounded bytes:

- exact quote present? asserted value equal? First
  divergence recorded as the diff.
- mismatch → `inconsistent: <diff>`.
- excerpt-risk **[judgment]**: the quote is accurate but
  reading the surrounding ~20 lines reverses its
  apparent meaning → flag `excerpt-risk`.

## 7. Check 5 — coherence **[judgment]**

Over the grounded-and-consistent evidence: `supports` /
`refutes` / `neutral`, with reasons. Decompose partial
claims into surviving and refuted-or-ungrounded parts.
No grounded evidence → `unevaluable` (gaps named).

## 8. Report **[mechanical format, judgment content]**

```text
/eval-meta report
Claim: <text>
(Admitted as falsifiable.)

1. Synthesis
Verdict: <confirmed | refuted | decomposed | unevaluable>
<compressed reasoning: what the dimensions jointly establish>

2. Dimension assessment
D2 - claim<->cited-evidence coherence:
  <pass | fail: <gap> | N/A: <reason> | not-run>
D3 - grounding:
  - <citation> -> grounded @ <pin> | ungrounded: <reason>
D4 - consistency:
  - <citation> -> consistent | inconsistent: <diff> | excerpt-risk: <note>
D5 - grounded-evidence<->claim coherence:
  <supports | refutes | neutral | unevaluable>: <reasons>
```

## 9. Worked example

Test-drive 2026-09-20 (scratch instance `/tmp/evaltest`,
accretion `/tmp/evaltest-accretion`; §10). Invocation:

```text
/eval-meta the scratch instance was installed with accretion
enabled and the manifest records it
:: var/manifest.json@HEAD contains accretion.enabled=true;
   etc/config.yaml@HEAD contains accretion.path=/tmp/evaltest-accretion
```

Report (abridged):

```text
/eval-meta report
Claim: the scratch instance was installed with accretion enabled
  and the manifest records it
(Admitted as falsifiable.)

1. Synthesis
Verdict: confirmed
Both citations ground to the install commit; the manifest's
accretion block matches the cited values exactly. No gaps.

2. Dimension assessment
D2 - claim<->cited-evidence coherence: pass
D3 - grounding:
  - var/manifest.json@HEAD -> grounded @ 912a474:var/manifest.json
  - etc/config.yaml@HEAD -> grounded @ 912a474:etc/config.yaml
D4 - consistency:
  - var/manifest.json@HEAD -> consistent
  - etc/config.yaml@HEAD -> consistent
D5 - grounded-evidence<->claim coherence: supports: the manifest
  records accretion.enabled=true and the config records the
  matching path.
```

## 10. Test-drive record

2026-09-20: scratch install (`--home /tmp/evaltest
--profile base --accretion-path /tmp/evaltest-accretion`)
succeeded; accretion repo initialized with the install
commit. The worked example in §9 was executed for real:
parse, scope (Yes — instance state), check 1 (admissible:
a manifest without the accretion block would refute it),
check 2 (pass), check 3 (both citations grounded via
`git --git-dir=.../.git show`), check 4 (cited strings
present in grounded bytes — the `contains` assertions
hold), check 5 (supports). Mismatch probe (claim: config
sets the accretion path explicitly; citation:
`etc/config.yaml@HEAD` contains an uncommented
accretion.path line): D3 grounded, D4 inconsistent
(the accretion block is commented out), D5 refutes →
verdict refuted. Form A probe ("the accretion repo
holds exactly the install commit") grounded via
`git log --oneline | wc -l` → 1 → confirmed. Gap path
verified against the live instance (`~/dsys-inst`, no
accretion repo): D3 = unevaluable with the reason named,
no live-tree content presented as grounding. Scratch
trees removed after the run.

## Glossary

Self-containment rule: every acronym and specialized term
used in this document is defined here. Citations point to
the official definition; the inline definition stands
alone.

- **accretion repo** — the git repository at the
  accretion path (separate git dir `<path>/.git`,
  work-tree = install home) holding the install's
  accreted state.
- **ambient agent** — the agent executing in the chat
  session (this procedure's executor).
- **declared trust** — properties that are
  author-declared rather than mechanically enforced
  (e.g. unpinned citations resolving to HEAD).
- **D2–D5** — the four report dimensions (§8).
- **DRAFT** — proposed; not evaluated, not disposed.
- **Form A / Form B** — bare `{claim}` / `{claim} ::
  {citations}` (§1).
- **G6** — gate 6 of the decision-making playbook: the
  open-questions slot (deferred items, revisit
  triggers).
- **mechanical / judgment** — step markers: exact
  commands vs agent reasoning reported with reasons
  (§0).
- **N/A** — not applicable, always with the reason.
- **not-run** — dimension not executed because an
  earlier dimension stopped the pipeline.
- **refuse back** — explicit refusal with usage,
  reframing instruction, or redirect — never silent.
- **step 0** — scope determination (§2).
- **unevaluable** — finding: admissible claim,
  insufficient grounded evidence; gaps named.
