"""Authoring-package contract — the inference/mechanical seam of "authoring".

Decomposition of the author-agent loop's Author/Stage steps (spec §3):

  INFERENCE process (ambient-side, wright-governed; J0 — not CLI-reachable):
    input:  commission record + wright profile + spec library
    work:   interpret brief -> assess existing artifacts (kind=assess) ->
            draft profile module: builder, ARCHETYPES, diagnostic_cases(),
            rationale prose (kind=propose) -> attest checklist G1-G6
    output: an AuthoringPackage (this module's contract)

  MECHANICAL process (harness-side; CLI: `stage-profile`):
    input:  an AuthoringPackage on disk
    work:   G1 commission exists + operator-attributed -> envelope
            validation -> stage bytes + hash-pinned manifest -> G2
            archetype gate (early) -> G4 rationale present -> G6
            diagnostic_cases present -> record authoring session ->
            stage build-request (J1-ii)
    output: staged records; fail-closed with reasons at every step

The inference itself is the ambient's and is never mechanized here:
this module only defines what the ambient must deliver and validates
the envelope mechanically. Content judgment (is the profile any good?)
belongs to the factory driver (gate -> bind -> compile -> verify ->
diagnose), which re-verifies everything and trusts nothing from the
stager. G3 (zero warnings), compile, verify, and diagnostics run there,
not in the stager.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_AGENT_NAME_RE = re.compile(r"[A-Za-z0-9_]+")


@dataclass(frozen=True)
class AuthoringPackage:
    """What the authoring inference must deliver for one agent.

    agent_name:      module stem; the module must define
                     `{agent_name}_profile()`, `ARCHETYPES`, and
                     `diagnostic_cases()`.
    profile_source:  the authored profile module, utf-8 python source.
    rationale:       staged prose recording judgment calls (G4).
    archetypes:      declared archetype names, e.g. ("staff", "office").
    commission_id:   the operator commission this authors under (G1).
    checklist:       the ambient's G1-G6 attestation; every item must be
                     True. Mechanically re-verifiable items (G1, G2, G4,
                     G6) are re-checked by the stager; the attestation is
                     still required so the ambient's judgment is on record.
    note:            free-form ambient note (optional).
    """
    agent_name: str
    profile_source: str
    rationale: str
    archetypes: tuple[str, ...]
    commission_id: str
    checklist: dict[str, bool] = field(default_factory=dict)
    note: str = ""


class PackageViolation(Exception):
    """The authoring package envelope is malformed (mechanical refusal)."""


# The governance checklist, in the ambient's attestation vocabulary.
CHECKLIST_ITEMS = (
    "G1 commission exists and is operator-attributed",
    "G2 declared archetypes conform (mechanical gate)",
    "G3 profile validates with zero warnings (mechanical)",
    "G4 rationale staged (judgment calls as prose)",
    "G5 stage-only: no deployment, no commit, no push",
    "G6 diagnostics authored alongside (J2)",
)


def validate_envelope(pkg: AuthoringPackage) -> dict[str, Any]:
    """Mechanically validate the package envelope. Returns a summary.

    Raises PackageViolation with reasons. Checks shape only: field
    presence, name well-formedness, non-empty source/rationale,
    archetype names known, commission id present, checklist complete.
    Semantic checks (does the gate pass? does it verify?) belong to
    the stager (G2 early) and the factory driver.
    """
    from .factory_archetypes import ARCHETYPES as KNOWN

    reasons: list[str] = []
    if not isinstance(pkg.agent_name, str) or \
            not _AGENT_NAME_RE.fullmatch(pkg.agent_name):
        reasons.append(f"bad agent_name {pkg.agent_name!r}")
    if not pkg.profile_source or not pkg.profile_source.strip():
        reasons.append("empty profile_source")
    elif "def " not in pkg.profile_source:
        reasons.append("profile_source defines no functions")
    if not pkg.rationale or not pkg.rationale.strip():
        reasons.append("empty rationale (G4)")
    if not pkg.archetypes:
        reasons.append("no archetypes declared (G2)")
    else:
        unknown = [a for a in pkg.archetypes if a not in KNOWN]
        if unknown:
            reasons.append(f"unknown archetypes {unknown}; "
                           f"known: {sorted(KNOWN)}")
    if not pkg.commission_id or not str(pkg.commission_id).strip():
        reasons.append("missing commission_id (G1)")
    missing = [k for k in CHECKLIST_ITEMS if not pkg.checklist.get(k, False)]
    if missing:
        reasons.append(f"checklist unattested: {missing}")
    if reasons:
        raise PackageViolation("; ".join(reasons))
    return {
        "agent": pkg.agent_name,
        "archetypes": list(pkg.archetypes),
        "commission_id": pkg.commission_id,
        "source_chars": len(pkg.profile_source),
        "rationale_chars": len(pkg.rationale),
        "checklist": "6/6 attested",
    }


__all__ = [
    "AuthoringPackage",
    "PackageViolation",
    "CHECKLIST_ITEMS",
    "validate_envelope",
]
