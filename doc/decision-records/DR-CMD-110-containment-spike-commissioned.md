# DR-CMD-110 — Build-path containment: design spike commissioned

- Status: adopted
- Date: 2026-09-27
- Selector: Peter (rendered "Commission a containment design spike",
  ~20:52 PDT)

## Matter

Build-path containment — the known gap from DR-CMD-101's honest
boundaries: `drive_build` executes authored module bytes in-process
during VALIDATE→VERIFY.

Already containing it: RECEIVE hash-pins the bytes (tampered bytes
refuse before anything executes), so only commissioned bytes ever run;
deterministic replay; commission scoping. Not contained: commissioned
bytes run with the ambient's full process privileges — a buggy builder
corrupts the ambient process; hostile bytes via a compromised
commission chain do worse.

## Disposition

Peter selected "Commission a containment design spike" over "Accept the
gap as bounded" — the gap is not accepted; it is scoped for design.

## Consequences

A containment design spike is commissioned — **design only, no build**.
It must:

- State the threat model precisely: what "commissioned bytes" means,
  what a compromised commission chain can reach, and which failure
  classes are in scope (buggy builder vs hostile bytes).
- Work within the constraints: deterministic byte-equal replay
  preserved; zero inference; fail-closed; the path stays drivable via
  `drive_build`; builds are infrequent, so subprocess overhead is
  acceptable.
- Return a design document for Peter's disposition **before anything is
  built**. Nothing about the build path changes under this record.

Out of scope: the wright-invocation half (ambient-side labor). The
spike's boundary is the build-request → `drive_build` path, RECEIVE
through STAGE.

## Identifier discipline

- DR-CMD-059 remains earmarked for the PVB Definition of Done — **not
  consumed**.
- Next free identifier: DR-CMD-111.

## State

**No commit, no push.** This record commissions the design only; the
spike returns a design doc for Peter's disposition.
