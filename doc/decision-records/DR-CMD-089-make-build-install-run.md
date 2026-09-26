# DR-CMD-089 — author-agent tree adopts GNU Make for build/install/run

- **Status:** ratified
- **Date:** 2026-09-26 ~15:25 PDT
- **Matter:** Best "make" system for the author-agent tree's build/install/run
  framework. Framed falsifiably: "The author-agent tree's build/install/run
  framework should be GNU Make targets, not bespoke shell scripts." Separator: Peter.

## Disposition

Peter rendered "O1: GNU Make" (~15:25 PDT 2026-09-26) on the /pb-decide
matter framed ~15:24 PDT. The make-system matter is now **ratified as decided**;
implementation of the Makefile follows under this record.

## Dialectic trail

- **Thesis (O1):** GNU Make. Makefile with `install`, `run`, `clean`
  targets; the empty-cwd flow becomes `git clone`, `make install`,
  `make run` — the standard interface every LLM agent already knows.
  Peter's standing gate ("the runner must not execute unless the
  installer has executed") becomes a native make dependency / check
  (the `run` target refuses without `install-receipt.json`).
- **Antithesis (O3, steelmanned):** keep the bespoke
  `install-author-agent.sh` v2 + `run-author-agent.sh` v2. Genuinely
  tested — three full green runs plus a passing gate test — and zero
  churn; make's tab/`$$` authoring quirks are real costs, not strawmen.
  Killed not by testing but by the matter's own terms: an invented
  framework against the standard interface.
- **Separator:** Peter (operator default).

## Options with gate trails

- **O1 — GNU Make.** G1 pass (concrete: Makefile, `install`/`run`/`clean`
  targets); G2 pass (universal LLM familiarity — the matter's stated
  criterion; preinstalled on macOS/Linux); G3 pass (no standing decision
  constrains this — the v2 scripts were committed but unratified and
  unpushed); G4 pass (changes the tree interface and the operator's
  commands); G5 pass (checkable: `make install && make run` from an
  empty directory). **ADOPTED.**
- **O2 — just (justfile).** G1 pass; **KILLED at G2** — not preinstalled
  anywhere, contradicting the "most familiar" criterion; installing
  `just` in order to run the installer is a bootstrap paradox.
- **O3 — keep bespoke scripts v2.** G1–G5 pass (tested, green 3x plus a
  gate test). **Killed by the matter's criterion**: invented framework
  and hand-rolled gate where `make` carries the idiom natively.
- **O4 — decide nothing.** Recorded explicitly, per STOP: the v2 scripts
  would stay local and unpushed. Not recommended; not selected.

## Consequences

- `install-author-agent.sh` and `run-author-agent.sh` retire from the
  tree (kept in git history); their logic migrates into Makefile targets
  plus `scripts/` helpers, with the make interface primary.
- Local commit `3e46b50` ("installer+runner v2: install receipt gate;
  empty-cwd flow") is **superseded** — held locally, never pushed.
- `build/half1` stays at `9a5f522` on origin until the Makefile commit
  pushes; the push flow (device flow, remote-head verification, token
  destruction) is unchanged.
- The install-receipt concept survives as the make-native gate
  (`run` requires the receipt the `install` target writes).

## Uncertainties (G6)

- Exact target set beyond `install` / `run` / `clean` (e.g. `verify`,
  `test` aliases) — implementer's call.
- Whether recipe bodies stay shell-in-Makefile or move to `scripts/`
  helpers — implementer's call; the make interface stays primary.
- Bootstrap remains `git clone` of the public `build/half1` branch —
  no bespoke fetcher script.

Next free identifier: DR-CMD-090 (DR-CMD-059 still reserved for PVB DoD).
