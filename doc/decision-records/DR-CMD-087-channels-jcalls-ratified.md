# DR-CMD-087 — author-agent channels: J-CH1 / J-CH2 ratified

- **Status:** ratified
- **Date:** 2026-09-26 ~14:48 PDT
- **Matter:** disposition of the two judgment calls left open by
  DR-CMD-085 (author-agent channels, spec'd and built). Peter rendered
  "ratify to adopt as recommended".

## Disposition

- **J-CH1 RATIFIED as recommended — principal-afferent topology:**
  staged commission queue canonical; the CLI is a thin ingress adapter
  over the *same* admission gate (`admit_commission`); CLI-direct
  invocation bypassing the queue is refused. Rationale (as built): two
  ingress paths would break the boundary — the channels are the
  containment boundary's I/O, and the boundary holds only if every
  crossing passes one gate. Refused ingress stays audit-visible
  (`channel-admission` log, AP-E3).
- **J-CH2 RATIFIED as recommended — vocabulary ADOPTED:** the channel
  codes AP-A1..A4 / AP-E1..E4 (principal) and AW-A1..A4 / AW-E1..E3
  (world), and the name "afferent–efferent triad", are adopted as the
  standing vocabulary. This **disposes the open vocabulary item from
  DR-CMD-069** — proposed there, provisionally used through DR-CMD-085,
  now adopted. Mechanics remain name-independent (enums; display names
  in the single `CHANNEL_NAMES` table; pinned by golden-run case H9).

## Resulting channel architecture (ratified)

- **One ingress gate.** `admit_commission(...)` in
  `core/package/author_channels.py` validates mechanically against the
  agent's D6 (principal must map to a bound source — the wright binds
  OPERATOR only), requires non-empty brief/acceptance/disposition, kind
  ∈ {AP-A2 standing, AP-A3 one-shot}, unique commission_id.
  Refuse-with-reasons; every admission and refused admission logged.
- **Queue canonical.** `pending_commissions(...)` is the read side;
  the driver works the queue. The wright's standing commission rides
  AP-A2; task commissions ride AP-A3.
- **CLI as adapter, not endpoint.**
  `python -m core.package.author_channels
  <commission|drive|report|pending>` — invokes harness functions over
  the same admission, prints records; exit codes 0 ok / 2 usage /
  4 governance refusal. Anti-relay clause stands (J0): never converses,
  cannot reach the authoring inference (ambient-side).
- **Principal-efferent (AP-E2).** `read_results(commission_id)` —
  staged verdicts + diagnostics as the return payload; a refused
  verdict is a complete result; only missing/malformed records refuse.
- **World channels spec'd but UNBOUND for the wright** (J-H
  discipline): `world_ingress` refuses citing D7 (no world_target,
  fail_closed); `world_egress` refuses citing D5 (write_scope empty,
  staff stage-only). Every refused attempt logged (`channel-refusal`).
  Handling is a future field-agent matter.

## Status updates

- `doc/d1-d7-author-channels-spec.md`: DRAFT → RATIFIED (DR-CMD-087).
- DR-CMD-085: built → ratified-under-087.

## Notes

- Sibling containment build (DR-CMD-086, Peter's "ratify: C" —
  `venv` + subprocess discipline) is in flight; the channels are its
  I/O by design — the container decision changes the host, not the
  channels.
- Next free identifier: DR-CMD-088. DR-CMD-059 remains reserved for
  the Product Vision Board Definition of Done.
- Nothing committed, nothing pushed; commit and push remain separate
  authorities.
