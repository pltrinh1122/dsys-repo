"""Canonical pipeline stage registry + the `pipeline run` driver.

The eight stages are the single source of truth for the pipeline order
(CLI, docs, and accounting reference these names, never a private copy).
GAP_ANALYSIS rides alongside as kind=analysis -- it uses transcripts,
is not a gate, and never runs inside `pipeline run`.

Corrected order (adopted falsification fix): RELEVANCE runs BEFORE
REVIEW. It needs only tax_year/form_type/OCR hash -- all available
post-extraction -- so the mechanical triage lands before the human
ever looks at the queue, and the queue can hide irrelevants from the
start. The human stage REVIEW then sees only what might matter.

kind ∈ {"mechanical", "human", "analysis"}:
    mechanical -- `pipeline run` executes these against the real
        functions, in order, failing fast with the stage's reason code.
    human      -- `pipeline run` NEVER executes these. They print as
        OPERATOR STEP markers and are skipped.
    analysis   -- not a gate; reported alongside the pipeline.

Blind-orchestrator: every runner prints stage names, counts, doc_ids,
and reason codes only -- never field values, OCR text, names, paths,
or dollar amounts. The CARRYFORWARD runner prints lots-in/warnings
counts; the full PII-bearing report stays operator-local.
"""

from __future__ import annotations

from decimal import Decimal

STAGES = [
    {
        "name": "INGESTION",
        "title": "Ingestion",
        "description": (
            "Intake a directory of PDFs / OCR text files (recursive): "
            "native text, sidecar, or OCR routing; per-file accounting "
            "(R6 IngestReport). CLASSIFICATION and EXTRACTION execute "
            "inside this stage; they are named separately because the "
            "registry is the accounting contract, not because they "
            "have their own entry points."
        ),
        "kind": "mechanical",
    },
    {
        "name": "CLASSIFICATION",
        "title": "Classification",
        "description": (
            "Form-type assignment per page/section (R1): every document "
            "gets a form_type from the classifier. Runs inside INGESTION; "
            "the runner reports the form x year inventory."
        ),
        "kind": "mechanical",
    },
    {
        "name": "EXTRACTION",
        "title": "Extraction",
        "description": (
            "Box-level field extraction / transcript parsing per "
            "classified document. Runs inside INGESTION; the runner "
            "reports field-row counts."
        ),
        "kind": "mechanical",
    },
    {
        "name": "RELEVANCE",
        "title": "Relevance triage",
        "description": (
            "assess_relevance: deterministic metadata-only verdicts "
            "(relevant | irrelevant | needs_human) persisted as labels. "
            "Needs only tax_year/form_type/OCR hash -- available "
            "post-extraction, hence before REVIEW. A validated document "
            "is relevant by definition (validated_by_operator); the "
            "mechanical rules never demote it."
        ),
        "kind": "mechanical",
    },
    {
        "name": "REVIEW",
        "title": "Human review",
        "description": (
            "The operator reviews each document against source evidence "
            "in the localhost UI (`taxprep review`). Human-only: "
            "`pipeline run` never executes it."
        ),
        "kind": "human",
    },
    {
        "name": "VALIDATION",
        "title": "Validation",
        "description": (
            "Apply the operator's recorded corrections and flip "
            "documents to validated (review.apply_validation). In "
            "`pipeline run` this is a checkpoint: the corrections are "
            "the human's work, so the runner reports the queue depth and "
            "skips with an OPERATOR STEP marker when review is outstanding."
        ),
        "kind": "mechanical",
    },
    {
        "name": "VERIFICATION",
        "title": "Mechanical verification",
        "description": (
            "verify_all gates: completeness, no_silent_drops, validation "
            "gate, 1099-B lot integrity, transcript reconciliation, "
            "carryforward-readiness. Fail fast with the failing check's "
            "reason codes."
        ),
        "kind": "mechanical",
    },
    {
        "name": "CARRYFORWARD",
        "title": "Carryforward chain",
        "description": (
            "Capital-loss carryforward chain (IRS Schedule D worksheet, "
            "Decimal-exact) from validated 1099-B lots only. Prints "
            "counts/warnings; the full report is operator-local."
        ),
        "kind": "mechanical",
    },
]

GAP_ANALYSIS = {
    "name": "GAP_ANALYSIS",
    "title": "Gap analysis",
    "description": (
        "Transcript-vs-ingested gap analysis (gaps.analyze_gaps): "
        "expected vs missing forms per year from the IRS wage & income "
        "transcript. Uses transcripts; analysis, not a gate -- it rides "
        "alongside the pipeline and never blocks it."
    ),
    "kind": "analysis",
}

# The run sequence is exactly the eight canonical stages, in order.
# GAP_ANALYSIS is deliberately excluded: it is not a gate.
RUN_SEQUENCE = [s["name"] for s in STAGES]

_VALID_KINDS = ("mechanical", "human", "analysis")


def registry() -> list[dict]:
    """The full ordered registry: the eight canonical stages, then
    GAP_ANALYSIS riding alongside. Each entry is
    {name, title, description, kind}."""
    return list(STAGES) + [dict(GAP_ANALYSIS)]


def check_registry() -> None:
    """Structural sanity of the registry (called by the test suite)."""
    kinds = {s["kind"] for s in registry()}
    assert kinds <= set(_VALID_KINDS), kinds
    names = [s["name"] for s in registry()]
    assert len(names) == len(set(names)), "duplicate stage names"
    assert RUN_SEQUENCE == names[:8], "run sequence must be the 8 stages in order"


def slice_sequence(from_stage: str | None = None,
                   to_stage: str | None = None) -> list[dict]:
    """The inclusive [--from, --to] slice of RUN_SEQUENCE (stage dicts).

    Names are matched case-insensitively; None means the sequence edge.
    Raises ValueError on an unknown name or a reversed slice.
    """
    names = RUN_SEQUENCE
    lo = 0 if from_stage is None else _stage_index(from_stage)
    hi = len(names) - 1 if to_stage is None else _stage_index(to_stage)
    if lo > hi:
        raise ValueError(
            f"--from {from_stage} comes after --to {to_stage} in the pipeline")
    return [STAGES[i] for i in range(lo, hi + 1)]


def _stage_index(name: str) -> int:
    upper = name.strip().upper()
    if upper not in RUN_SEQUENCE:
        raise ValueError(
            f"unknown stage {name!r}; expected one of {', '.join(RUN_SEQUENCE)}")
    return RUN_SEQUENCE.index(upper)


class PipelineError(Exception):
    """A mechanical stage refused to run or failed its gate.

    ``stage`` is the stage name; ``reason`` is a stable reason code
    (plus detail where the failing check names it).
    """

    def __init__(self, stage: str, reason: str):
        self.stage = stage
        self.reason = reason
        super().__init__(f"pipeline stage {stage} failed: {reason}")


# -- runners -----------------------------------------------------------

def _scoped(store, year: int | None) -> list:
    """Store docs, optionally restricted to one tax year."""
    return store.list(year=year) if year is not None else store.list()


def _review_queue(store, year: int | None) -> list:
    """Docs awaiting human validation -- the same definition as the
    review UI queue (review.queue_html): transcribed or needs_review."""
    return [d for d in _scoped(store, year)
            if d.status in ("transcribed", "needs_review")]


def _r_ingestion(store, ctx: dict) -> dict:
    from .ingest import ingest_dir

    input_dir = ctx.get("input_dir")
    if not input_dir:
        raise PipelineError(
            "INGESTION",
            "no_input_dir: pass a directory or run "
            "`taxprep config set source_dir <dir>` once")
    out = ctx["out"]
    report = ingest_dir(input_dir, store)
    rep = report.summary()
    # R6 per-run accounting (reason codes only -- never file names).
    out(f"   files seen: {rep['files_seen']}, ingested: {rep['ingested']}, "
        f"skipped: {len(rep['skipped'])}, errored: {len(rep['errored'])}")
    for entry in rep["skipped"]:
        out(f"     skipped [{entry['reason_code']}]")
    for entry in rep["errored"]:
        out(f"     errored [{entry['reason_code']}]")
    return rep


def _r_classification(store, ctx: dict) -> dict:
    out = ctx["out"]
    docs = _scoped(store, ctx.get("year"))
    by_form: dict[str, int] = {}
    for d in docs:
        by_form[d.form_type] = by_form.get(d.form_type, 0) + 1
    for form in sorted(by_form):
        out(f"   {form:24} {by_form[form]}")
    unknown = by_form.get("UNKNOWN", 0)
    if unknown:
        out(f"   !! {unknown} unclassified (UNKNOWN) document(s) -- "
            "needs human classification")
    return {"n_docs": len(docs), "by_form": by_form, "unknown": unknown}


def _r_extraction(store, ctx: dict) -> dict:
    out = ctx["out"]
    docs = _scoped(store, ctx.get("year"))

    def n_rows(d) -> int:
        return sum(1 for code, f in d.fields.items()
                   if isinstance(f, dict) and not code.startswith("__"))

    n_fields = sum(n_rows(d) for d in docs)
    n_with = sum(1 for d in docs if n_rows(d))
    out(f"   {len(docs)} document(s), {n_with} with extracted fields, "
        f"{n_fields} field rows total")
    return {"n_docs": len(docs), "docs_with_fields": n_with,
            "n_fields": n_fields}


def _r_relevance(store, ctx: dict) -> dict:
    from .relevance import assess_relevance, summarize

    out = ctx["out"]
    scope = ctx["scope_years"]
    year = ctx.get("year")
    docs = None if year is None else store.list(year=year)
    verdicts = assess_relevance(store, scope, docs=docs, persist=True)
    s = summarize(verdicts)
    out(f"   assessed {s['n_docs']}: " + ", ".join(
        f"{v}={s['counts'][v]}" for v in ("relevant", "irrelevant",
                                          "needs_human")))
    for label, entries in (("needs_human", s["needs_human"]),
                           ("irrelevant", s["irrelevant"])):
        for e in entries:
            out(f"     [{label}] {e['doc_id']}  {','.join(e['reasons'])}")
    return s


def _r_validation(store, ctx: dict) -> dict:
    out = ctx["out"]
    queue = _review_queue(store, ctx.get("year"))
    if queue:
        # The corrections are the human's work (review UI); the runner
        # cannot apply them. Checkpoint only, then the VERIFICATION
        # gate fails fast on the validation_gate check if still pending.
        out(f"   OPERATOR STEP: {len(queue)} document(s) await human "
            "validation (`taxprep review`) -- nothing to apply mechanically")
        return {"status": "deferred", "awaiting": len(queue),
                "marker": "operator-step"}
    year = ctx.get("year")
    n = sum(1 for d in _scoped(store, year) if d.status == "validated")
    out(f"   review queue empty -- {n} validated document(s), "
        "nothing to apply")
    return {"status": "ok", "validated": n}


def _r_verification(store, ctx: dict) -> dict:
    from .verify import verify_all

    out = ctx["out"]
    year = ctx.get("year")
    result = verify_all(store, year)
    failed: list[str] = []
    for name, r in result["checks"].items():
        status = "PASS" if r.get("passed") else "FAIL"
        out(f"   {name:36} {status}")
        if not r.get("passed"):
            failed.append(name)
            for key, v in r.items():
                if key.endswith("_ids") and isinstance(v, list) and v:
                    for i in v:
                        out(f"       - {i}")
    if not result["passed"]:
        raise PipelineError(
            "VERIFICATION", "checks_failed:" + ",".join(failed))
    return {"passed": True, "n_checks": len(result["checks"])}


def _r_carryforward(store, ctx: dict) -> dict:
    from .carryforward import compute_chain, from_store

    out = ctx["out"]
    scope = ctx["scope_years"]
    year = ctx.get("year")
    years = [year] if year is not None else sorted(set(scope))
    if not years:
        raise PipelineError("CARRYFORWARD", "no_years_in_scope")
    yearly: dict[int, dict] = {}
    for y in years:
        try:
            r = from_store(store, y)
        except (ValueError, TypeError) as exc:
            raise PipelineError(
                "CARRYFORWARD", f"refused:{type(exc).__name__}:{y}")
        yearly[y] = {"st_current": r["st_current"],
                     "lt_current": r["lt_current"]}
        out(f"   {y}: {r['lots_included']} lot(s) in, "
            f"{r['lots_excluded']} excluded, {len(r['warnings'])} warning(s)")
    # Filing status: single for all years, matching `taxprep carryforward`
    # defaults. Per-year statuses are the operator's call via the CLI.
    result = compute_chain(
        yearly,
        {y: "single" for y in years},
        prior_carryover={"st": Decimal("0"), "lt": Decimal("0")},
    )
    out(f"   chained {len(years)} year(s); "
        f"{len(result['warnings'])} chain warning(s)")
    return {"years": years, "n_warnings": len(result["warnings"]),
            "status": "ok"}


_RUNNERS = {
    "INGESTION": _r_ingestion,
    "CLASSIFICATION": _r_classification,
    "EXTRACTION": _r_extraction,
    "RELEVANCE": _r_relevance,
    # REVIEW is kind=human: never executed, OPERATOR STEP marker only.
    "VALIDATION": _r_validation,
    "VERIFICATION": _r_verification,
    "CARRYFORWARD": _r_carryforward,
}


# -- driver ------------------------------------------------------------

def run_pipeline(store, *, input_dir: str | None, scope_years: list[int],
                 year: int | None = None,
                 from_stage: str | None = None,
                 to_stage: str | None = None,
                 out=print) -> dict:
    """Run the mechanical stages of the pipeline in the corrected order.

    Returns {"ok", "failed_stage", "stages": [{name, status, ...}]}.
    Fails fast: the first failing stage stops the run (no later stage
    executes). Human stages (REVIEW) print OPERATOR STEP markers and are
    SKIPPED, never executed. GAP_ANALYSIS is not part of the sequence.
    """
    total = len(STAGES)
    ctx = {"input_dir": input_dir, "scope_years": scope_years,
           "year": year, "out": out}
    stages = slice_sequence(from_stage, to_stage)
    results: list[dict] = []
    for s in stages:
        idx = RUN_SEQUENCE.index(s["name"]) + 1
        out(f"── STAGE {idx}/{total}: {s['name']} ──")
        if s["kind"] == "human":
            out(f"   OPERATOR STEP: {s['title']} is human work -- "
                "skipped, never executed")
            results.append({"name": s["name"], "status": "skipped",
                            "marker": "operator-step"})
            continue
        try:
            summary = _RUNNERS[s["name"]](store, ctx)
        except PipelineError as exc:
            out(f"   FAILED [{exc.stage}] reason: {exc.reason}")
            results.append({"name": s["name"], "status": "failed",
                            "reason": exc.reason})
            return {"ok": False, "failed_stage": s["name"],
                    "stages": results}
        results.append({"name": s["name"], "status": "ok",
                        "summary": summary})
    return {"ok": True, "failed_stage": None, "stages": results}
