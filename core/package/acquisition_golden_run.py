"""Golden run for the acquisition contract (DR-CMD-053).

Acceptances (spec §Acceptances):
  1. The accretion path is absent (not a git repo) -> acquisition
     refuses before drive start (fail fast, initiation's duty, D3).
  2. The path resolves but the handle's dsys.repo-id does not match
     the manifest identity -> refuse at resolution (fail fast, D2);
     and a drive started without acquisition against a mismatched
     handle still fails closed at the D3 per-write check (the
     backstop remains).
  3. The manifest records no accretion_repo.identity (accretion
     disabled) -> the drive refuses before starting.
  4. Resolution success -> the drive proceeds under the verified
     handle; the acquisition record rides the drive record (the
     transcript envelope); replay re-derives the path; the resolved
     path does not enter event payloads (R1).
  5. D1 precedence: flag > config > default.

Plus the R3 discharge: I-27 fires on every broken conjunct and is
clean on the authorized tuple — the predicate, not the procedure.
And the post-hoc rule: a drive handed a violated acquisition record
is refused (invalid).

Returns {'violations': [...], 'refusals': [...], 'ok': bool}.
Refusals are the expected-loud cases behaving correctly; violations
are unexpected failures (any assertion firing fails the run).
"""
from __future__ import annotations

import json

from .updater import (
    AcquisitionRecord,
    AcquisitionRefused,
    DriveInitiation,
    World,
    acquire_handle,
    i25_identity_binding,
    i27_authorized_acquisition,
    mint_repo_identity,
    path_hash,
    production_drive,
    replay,
)
from .updater_golden_run import _events_of, build_updater_state
from .drive_contract_golden_run import FLOW_ID, FULL_PATH

IDLE = "urm-idle"


def _world() -> World:
    return World(feed_version="0.1.1", installed_version="0.1.0",
                 updater_policy="auto")


def run() -> dict:
    violations: list[str] = []
    refusals: list[str] = []

    # 1. (A-R2-1) absent path -> acquisition refuses before drive
    # start (fail fast, initiation's duty). Refusal is not failure:
    # the drive never starts — no events, nothing surfaced.
    s1 = build_updater_state("fr-a1")
    w1 = _world()
    try:
        acquire_handle(manifest_identity=w1.manifest_repo_identity,
                       config_path="/var/daccretion/dsys-inst",
                       git_available=False,  # <path>/.git is not valid
                       repo_identity=w1.accretion_repo_id)
        raise AssertionError("an absent path must refuse")
    except AcquisitionRefused as e:
        refusals.append(f"absent accretion path refused: {e}")
    assert len(s1.flow_transition_events) == 0, \
        "the refused drive started nothing"
    assert w1.surfaced == [], "refusal surfaces nothing (nothing failed)"

    # 2. (A-R2-2) wrong identity at resolution -> fail fast. And the
    # D3 backstop: a drive started without acquisition against a
    # mismatched handle still fails closed at the per-write check —
    # the backstop remains (D2).
    s2 = build_updater_state("fr-a2")
    w2 = _world()
    try:
        acquire_handle(manifest_identity=w2.manifest_repo_identity,
                       config_path="/var/daccretion/dsys-inst",
                       repo_identity="00000000-0000-0000-0000-000000000000")
        raise AssertionError("identity mismatch must refuse at "
                             "resolution")
    except AcquisitionRefused as e:
        assert "fail fast" in str(e) or "does not match" in str(e), \
            f"the refusal must name the mismatch: {e}"
        refusals.append(f"wrong identity refused at resolution "
                        f"(fail fast): {e}")
    assert len(s2.flow_transition_events) == 0, \
        "the fail-fast drive started nothing"
    # The backstop: no acquisition, mismatched handle -> D3 aborts the
    # drive mid-flight (failed, not refused-before-start).
    s2b = build_updater_state("fr-a2b")
    w2b = _world()
    w2b.accretion_repo_id = "00000000-0000-0000-0000-000000000000"
    rec2b = production_drive(s2b, w2b, DriveInitiation(), "fr-a2b")
    assert rec2b["state"] == "failed", \
        f"the D3 backstop must fail the drive: {rec2b}"
    assert rec2b["path"][-2:] == ["urm-committing", "urm-failed"], \
        "the D3 check aborts the drive"
    assert "acquisition" not in rec2b["initiation"], \
        "no acquisition ran for the backstop case"
    refusals.append("the D3 per-write check remains the backstop: a "
                    "drive without acquisition fails closed")

    # 3. (A-R2-3) the manifest records no accretion_repo.identity
    # (accretion disabled — the installer's "never fails the install"
    # leaves this possible) -> the drive refuses before starting.
    s3 = build_updater_state("fr-a3")
    w3 = _world()
    try:
        acquire_handle(manifest_identity=None,  # accretion disabled
                       config_path="/var/daccretion/dsys-inst",
                       repo_identity=w3.accretion_repo_id)
        raise AssertionError("disabled accretion must refuse")
    except AcquisitionRefused as e:
        assert "accretion_repo.identity" in str(e), \
            f"the refusal must name the missing identity: {e}"
        refusals.append(f"disabled accretion refused: {e}")
    assert len(s3.flow_transition_events) == 0, \
        "the refused drive started nothing"

    # 4. (A-R2-4) resolution success -> the drive proceeds under the
    # verified handle; the acquisition record rides the drive record
    # (the transcript envelope, R1); replay re-derives the path; the
    # resolved path does not enter event payloads.
    s4 = build_updater_state("fr-a4")
    w4 = _world()
    acq4 = acquire_handle(manifest_identity=w4.manifest_repo_identity,
                          config_path="/var/daccretion/dsys-inst",
                          repo_identity=w4.accretion_repo_id,
                          git_available=w4.git_available)
    assert i27_authorized_acquisition(acq4) == [], \
        "I-27 must be clean on the authorized acquisition"
    # The fail-fast check is the I-25 predicate applied at resolution:
    # the same verdict the D3 check would produce per write.
    assert i25_identity_binding(acq4.manifest_identity,
                                acq4.repo_identity,
                                acq4.git_available) == [], \
        "fail fast is the I-25 predicate, applied earlier"
    rec4 = production_drive(s4, w4, DriveInitiation(), "fr-a4",
                            acquisition=acq4)
    assert rec4["state"] == "done", f"the drive must complete: {rec4}"
    assert rec4["path"] == FULL_PATH, f"unexpected path: {rec4['path']}"
    env4 = rec4["initiation"]["acquisition"]
    assert env4["resolved_identity"] == w4.manifest_repo_identity, \
        "the envelope carries the resolved identity"
    assert env4["path_source"] == "config" and \
        env4["path"] == "/var/daccretion/dsys-inst"
    events4 = _events_of(s4, "fr-a4")
    for e in events4:
        assert "/var/daccretion/dsys-inst" not in e.payload, \
            f"the resolved path must not enter event payloads: {e.id}"
    path_r = replay(events4,
                    [t for t in s4.flow_transitions.values()
                     if t.flow_id == FLOW_ID], IDLE)
    assert path_hash(path_r) == path_hash(rec4["path"]), \
        "replay must re-derive the drive's path"
    refusals.append("resolution success: the drive completed under the "
                    "verified handle; the acquisition record rides the "
                    "envelope; replay re-derived the path (R1)")

    # 5. (D1) precedence: flag > config > default. The K3 edge: every
    # source is operator-owned config; the mechanic never invents a
    # path.
    ident5 = mint_repo_identity()
    r5a = acquire_handle(manifest_identity=ident5, repo_identity=ident5,
                         flag_path="/flag/path",
                         config_path="/config/path",
                         default_path="/default/path")
    assert (r5a.path, r5a.path_source) == ("/flag/path", "flag"), \
        "the flag wins under the config contract"
    r5b = acquire_handle(manifest_identity=ident5, repo_identity=ident5,
                         config_path="/config/path",
                         default_path="/default/path")
    assert (r5b.path, r5b.path_source) == ("/config/path", "config"), \
        "the config wins over the default"
    r5c = acquire_handle(manifest_identity=ident5, repo_identity=ident5,
                         default_path="/default/path")
    assert (r5c.path, r5c.path_source) == ("/default/path", "default"), \
        "the default rule resolves when nothing overrides it"
    refusals.append("D1 precedence pinned: flag > config > default")

    # 6. Post-hoc: a drive handed a violated acquisition record is
    # refused — invalid. (Fresh instances per case: no
    # non-validating copies.)
    s6 = build_updater_state("fr-a6")
    w6 = _world()
    violated6 = AcquisitionRecord(path_source="config",
                                  path="/var/daccretion/dsys-inst",
                                  git_available=True,
                                  manifest_identity=w6
                                  .manifest_repo_identity,
                                  repo_identity="00000000-0000-0000-0000-"
                                  "000000000000",
                                  at_initiation=True)
    try:
        production_drive(s6, w6, DriveInitiation(), "fr-a6",
                         acquisition=violated6)
        raise AssertionError("a violated acquisition record must "
                             "refuse the drive")
    except AcquisitionRefused as e:
        refusals.append(f"post-hoc violated acquisition refused: {e}")
    assert len(s6.flow_transition_events) == 0, \
        "the refused drive started nothing"

    # 7. (R3) I-27 fires on every broken conjunct and is clean on the
    # authorized tuple — the predicate, not the procedure.
    ident7 = mint_repo_identity()
    good7 = AcquisitionRecord(path_source="config",
                              path="/var/daccretion/dsys-inst",
                              git_available=True,
                              manifest_identity=ident7,
                              repo_identity=ident7,
                              at_initiation=True)
    assert i27_authorized_acquisition(good7) == []
    cases7 = [
        (AcquisitionRecord(path_source="cron", path="/x",
                           manifest_identity=ident7,
                           repo_identity=ident7),
         "unknown path source"),
        (AcquisitionRecord(path_source="config", path=None,
                           manifest_identity=ident7,
                           repo_identity=ident7),
         "no accretion path resolvable"),
        (AcquisitionRecord(path_source="config", path="/x",
                           git_available=False,
                           manifest_identity=ident7,
                           repo_identity=ident7),
         "not a git repo"),
        (AcquisitionRecord(path_source="config", path="/x",
                           manifest_identity=None,
                           repo_identity=ident7),
         "no accretion_repo.identity"),
        (AcquisitionRecord(path_source="config", path="/x",
                           manifest_identity=ident7,
                           repo_identity=None),
         "no dsys.repo-id"),
        (AcquisitionRecord(path_source="config", path="/x",
                           manifest_identity=ident7,
                           repo_identity="00000000-0000-0000-0000-"
                           "000000000000"),
         "does not match"),
        (AcquisitionRecord(path_source="config", path="/x",
                           manifest_identity=ident7,
                           repo_identity=ident7,
                           at_initiation=False),
         "at initiation"),
    ]
    for rec7, needle in cases7:
        bad7 = i27_authorized_acquisition(rec7)
        assert any(needle in x for x in bad7), \
            f"I-27 must fire on {needle!r}: {bad7}"
    refusals.append("I-27 fired on every broken conjunct; clean on the "
                    "authorized tuple")

    return {"violations": violations, "refusals": refusals, "ok": True}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
