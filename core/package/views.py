"""DR-5/A2: read-only verification views computed from SystemState ground
truth. A view is a pure function — no stored state, no agent discretion.
The verification view is the single definition of "the open disclosure
queue" shared by the drain-duty validators and operator audit. Its
independence is presentation-independence (not authorship-independence):
it audits written->disposed, never detected->written."""
from __future__ import annotations

from dataclasses import dataclass

from .schema import (
    DisclosureKind,
    DisclosureStatus,
    DispositionMode,
    DispositionStatus,
    SystemState,
)

_KIND_RANK = {
    DisclosureKind.CONFLICT: 0,
    DisclosureKind.ERROR: 1,
    DisclosureKind.UNCERTAINTY: 2,
}


@dataclass(frozen=True)
class DisclosureViewRow:
    """One open disclosure as the operator audits it."""
    id: str
    kind: DisclosureKind
    text: str
    seq: int
    triage_in_flight: bool  # cited by a PROPOSED triage disposition (CTA out, unanswered)


def verification_view(s: SystemState) -> list[DisclosureViewRow]:
    """DR-5/A2: every OPEN disclosure, kind-then-seq ordered. Completeness is
    by construction: the only filter is status == OPEN."""
    in_flight = {
        d.disclosure_ref
        for d in s.dispositions.values()
        if d.mode == DispositionMode.TRIAGE
        and d.disclosure_ref
        and d.status == DispositionStatus.PROPOSED
    }
    rows = [
        DisclosureViewRow(
            id=d.id,
            kind=d.kind,
            text=d.text,
            seq=d.seq,
            triage_in_flight=d.id in in_flight,
        )
        for d in s.disclosures.values()
        if d.status == DisclosureStatus.OPEN
    ]
    rows.sort(key=lambda r: (_KIND_RANK[r.kind], r.seq))
    return rows
