# DR-CMD-085 — author-agent channels: spec'd and built

- **Status:** ratified-under-087 (2026-09-26 ~14:48 PDT; J-CH1 and J-CH2 ratified as recommended)
- **Date:** 2026-09-26 ~14:44 PDT
- **Matter:** Half 1b of the containment matter — afferent/efferent
  channels for the author-agent (wright), designed AS the containment
  boundary's I/O: the only paths in and out. (Half 1a — the host
  container, `venv` vs docker vs `venv`+subprocess-discipline — is a
  pending /pb-decide sibling; the boundary's I/O is designed so the
  container decision changes the host, not the channels.)

## J-calls (for Peter)

- **J-CH1 — principal-afferent topology: staged commission queue
  canonical; CLI as thin ingress adapter over the same admission.**
  Refused alternative: CLI-direct invocation bypassing staging (two
  ingress paths, different auditability — breaks "channels as the
  containment boundary"). The CLI invokes harness machinery; it does
  not relay chat to a separate endpoint (falsified relay topology;
  J0 stands).
- **J-CH2 — vocabulary: AP-A1..A4 / AP-E1..E4 (principal) and
  AW-A1..A4 / AW-E1..E3 (world) codes plus the "afferent–efferent
  triad" name, used PROVISIONALLY** (proposed since DR-CMD-069,
  undisposed). Adoption / amend / rename is Peter's call. Mechanics
  are name-independent: channel kinds are enums; display names live
  in exactly one table (`CHANNEL_NAMES`) — a rename relabels the
  table only (pinned by golden-run case H9).

## What was built (new files only; nothing committed/pushed)

- `core/package/author_channels.py` — the boundary module. Sibling
  to `author_agent.py`; that module's core untouched.
  - Provisional vocabulary: `PrincipalAfferent`, `PrincipalEfferent`,
    `WorldAfferent`, `WorldEfferent` enums + `CHANNEL_NAMES` table.
  - `admit_commission(...)`: the single ingress gate — validates
    against the agent's D6 mechanically (principal must map to a bound
    source; wright binds OPERATOR only), brief/acceptance/disposition
    non-empty, kind ∈ {AP-A3 one-shot, AP-A2 standing}, commission_id
    unique. Every admission AND every refused admission is logged
    (`kind: "channel-admission"`) — refused ingress is audit-visible
    (AP-E3). Refuse-with-reasons, never silent.
  - `pending_commissions(...)`: queue read side — commissions with no
    authoring session.
  - `read_results(commission_id)` (AP-E2): staged verdicts +
    diagnostics as the return payload. A refused verdict is a
    *complete* result; only missing/malformed records refuse, with
    reasons listing what exists.
  - `world_ingress` / `world_egress`: specified but UNBOUND for the
    wright — refuse citing D7 (no world_target; fail_closed) and D5
    (write_scope empty; staff stage-only) respectively (J-H
    discipline). Profile-driven gates; every refused attempt logged
    (`kind: "channel-refusal"`). A profile that *would* admit still
    refuses: handling is a future field-agent matter.
  - CLI `main(argv)` (`python -m core.package.author_channels
    <commission|drive|report|pending>`): invokes harness functions,
    prints records. Anti-relay clause: never converses, cannot reach
    the authoring inference (ambient-side, J0). Exit codes: 0 ok,
    2 usage, 4 governance refusal.
- `core/package/author_channels_golden_run.py` — H1–H9 battery.
- `doc/d1-d7-author-channels-spec.md` — self-contained spec with
  Glossary (status DRAFT pending J-CH1/J-CH2).

## Verification (exact counts)

- Channels golden run: **11/11 green** (H1 queue admission, H2 CLI
  ingress through same admission, H3 six malformed commissions
  refused + CLI exit 4, H4 full loop → verified/all_green, H5/H5b
  verdict-less and unknown-commission reports refused, H6/H6b world
  ingress refuses citing D7 + logged, H7 world egress refuses citing
  D5, H8 byte-identity across two loops, H9 rename-independence).
  Two consecutive battery runs byte-identical.
- CLI smoke-tested read-only against the live root: `pending` → [],
  `report --commission commission-001` → both verdicts verified,
  diagnostics green. No writes to live evidence.
- Existing suites all green, factory tree untouched: factory golden
  run **183 passed / 0 violations / 4 expected refusals** (baseline
  held exactly); agent-behavior 0 violations; author-agent loop 6/6;
  archetype self-test ok (six conform, negative refused, unknown
  rejected); set-002 both verified; bridge, updater, drive contract,
  acquisition, PVB workflow, scenario sim, playbook green.

## Notes

- The wright's standing commission (Peter's instruction, DR-CMD-084)
  rides AP-A2; task commissions ride AP-A3. AP-A1/AP-A4 and AP-E4 are
  vocabulary-complete but unbound (no case has needed them).
- D4 trace/log is the witness, not a party (recorded position).
- Next free identifier: DR-CMD-086. DR-CMD-059 remains reserved for
  the PVB Definition of Done. Branch `main`; nothing committed,
  nothing pushed.
