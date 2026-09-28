# DR-CMD-105 — /pb-decide next-best-action: O1 banked, O2 taken up

- Status: adopted
- Date: 2026-09-27
- Selector: Peter (rendered "proceed as recommended", ~19:00 PDT)

## Matter

The single next action best advancing the work. Context: tranche 1 landed
(`tool-register-artifact` built and verified, DR-CMD-103), `registrar_clerk`
registered (10 exemplars, DR-CMD-104), DR-CMD-102..104 plus the tool and
registration edits uncommitted, tranche 2 conditional, DR registry structure
undisposed.

## The /pb-decide (condensed)

- **O1 — bank changes. Adopt (now).** Everything since `a10a4f6` lived only
  in the working tree; exposed work compounds silently. Two minutes, zero
  design risk.
- **O2 — design the DR registry as a contracted structure. Adopt as its own
  design matter**, with the G3 condition explicit: the registry structure is
  tranche 2's precondition (i), but its value is gated on tranche 2's
  condition (ii) — demonstrated operational need for the DR channel itself.
  Designing the store without the channel's need proven is half a bridge.
- **O3 — factory close-out (Item 9 + Item 10). Defer.** Queued; sequencing
  only, no dependency either way.
- **O4 — wright runtime. Defer (G5 speculative).** Ambient labor closes the
  loop today at zero marginal cost; a wright runtime reopens the embody
  problem. Revisit trigger: hand-driven authoring becomes the bottleneck.
- **G6 note:** the push to origin is Peter's separate explicit call (device
  flow) — flagged, not recommended by the playbook.

## Disposition

Peter's selection: "proceed as recommended" — O1 adopted+executed, O2
adopted as its own matter, O3/O4 deferred.

## Consequences

- **O1 executed:** committed locally as `98bfe6d` ("Tool-channel tranche 1 +
  registrar_clerk registration (DR-CMD-102..104)") on `build/half1`. Working
  tree clean. No push — separate authority required; origin/main untouched.
- **O2 taken up:** the DR-registry-structure design is commissioned as a
  design spike — design only, no build authorized. The spike carries the G3
  condition explicitly: it assesses whether tranche 2's DR channel collapses
  into `tool-register-artifact` and whether condition (ii) operational need
  is met, before any channel is built.
- **O3/O4 queued** per the revisit/sequencing terms above.

Next free identifier: DR-CMD-106 (DR-CMD-059 still reserved for PVB DoD).
