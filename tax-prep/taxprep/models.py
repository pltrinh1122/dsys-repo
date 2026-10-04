"""Data model for Phase 1 document records.

A Document is one ingested source (a PDF, a .txt sidecar, an image
converted to PDF, or one CSV row) with its classification, extracted
fields, review status, and text provenance.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

FORM_TYPES = [
    "W-2",
    "1099-B",
    "1099-INT",
    "1099-DIV",
    "1099-NEC",
    "1099-R",
    "1099-MISC",
    "1098",
    "1040",
    "1040-X",
    "SCHEDULE_D",
    "WAGE_INCOME_TRANSCRIPT",
    "RETURN_TRANSCRIPT",
    "ACCOUNT_TRANSCRIPT",
    "RECORD_OF_ACCOUNT",
    "UNKNOWN",
]

STATUSES = (
    # R13 lifecycle states (taxprep/lifecycle.py owns the transition
    # table). R1 legacy spellings retained verbatim for back-compat.
    "discovered",
    "selected",
    "unselected",
    "transcribed",
    "needs_review",
    "validated",
    "rereview",
    "errored",
    "excluded",
    "MULTI_FORM",
    "BLOCKED",
    "ORPHANED",
)

RELEVANCE_VERDICTS = ("unassessed", "relevant", "irrelevant", "needs_human")


@dataclass
class Document:
    doc_id: str
    tax_year: int | None
    form_type: str
    source_path: str
    ocr_text_ref: str
    fields: dict = field(default_factory=dict)
    status: str = "needs_review"
    validated_at: str | None = None
    relevance: str = "unassessed"
    # R1: for documents split out of a multi-form file — the 1-based page
    # range the section came from (e.g. "3-5", or "3" for a single page)
    # and the id the unsplit source file would have had.
    page_range: str | None = None
    parent_doc_id: str | None = None
    # R4: stable identity — full sha256 of the SOURCE BYTES (the doc_id is
    # its 16-hex prefix; no filename component anywhere).
    source_sha256: str | None = None
    # R4: machine reason accompanying the current status, e.g.
    # ORPHANED -> "source_missing", BLOCKED -> "encrypted"/"needs-ocr".
    status_reason: str | None = None
    # R4: re-ingest disagreed with Operator-validated values -- the
    # validated values were kept and the doc needs Operator re-review.
    re_review: bool = False
    # R5: text provenance -- operational metadata, not taxpayer data, so
    # these cross the MCP boundary as non-PII keys.
    # R15: text_source names WHICH text was actually used:
    #   "native" | "sidecar:<relpath>" | "form-field" |
    #   "ocr:<engine>/<mode>" | "broker-csv" | "error" | "blocked"
    text_source: str | None = None
    reason_code: str | None = None
    ocr_engine: str | None = None
    engine_version: str | None = None
    ocr_mode: str | None = None          # skip-text | redo-ocr | force-ocr
    attempts: list = field(default_factory=list)
    mean_confidence: float | None = None
    # X1: encryption provenance -- "owner-only" when the PDF carried only
    # an owner password (empty user password unlocked it), None otherwise.
    # Operational metadata, not taxpayer data -- crosses the MCP boundary
    # alongside text_source/ocr_engine (blind-orchestrator safe).
    encryption: str | None = None
    # R21a: per-person scoping. owner_person_id is an opaque "person-N" id
    # from the store's person registry (taxprep/persons.py), assigned by
    # the OPERATOR ONLY -- the system never infers it silently.
    # owner_suggestion is a system-derived suggestion (derivation basis in
    # owner_suggestion_basis); it is shown to the Operator and NEVER
    # auto-applied. A suggestion is "un-disposed" exactly while
    # owner_person_id is None; the Operator's assignment (which may accept
    # or override the suggestion) consumes it. Both are operational
    # metadata -- opaque ids cross the MCP boundary; names never do.
    owner_person_id: str | None = None
    owner_suggestion: str | None = None
    owner_suggestion_basis: str | None = None

    def __post_init__(self) -> None:
        if self.form_type not in FORM_TYPES:
            raise ValueError(f"unknown form_type: {self.form_type!r}")
        if self.status not in STATUSES:
            raise ValueError(f"unknown status: {self.status!r}")
        if self.relevance not in RELEVANCE_VERDICTS:
            raise ValueError(f"unknown relevance: {self.relevance!r}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Document":
        return cls(
            doc_id=d["doc_id"],
            tax_year=d.get("tax_year"),
            form_type=d.get("form_type", "UNKNOWN"),
            source_path=d.get("source_path", ""),
            ocr_text_ref=d.get("ocr_text_ref", ""),
            fields=d.get("fields", {}),
            status=d.get("status", "needs_review"),
            validated_at=d.get("validated_at"),
            relevance=d.get("relevance", "unassessed"),
            page_range=d.get("page_range"),
            parent_doc_id=d.get("parent_doc_id"),
            source_sha256=d.get("source_sha256"),
            status_reason=d.get("status_reason"),
            re_review=d.get("re_review", False),
            text_source=d.get("text_source"),
            reason_code=d.get("reason_code"),
            ocr_engine=d.get("ocr_engine"),
            engine_version=d.get("engine_version"),
            ocr_mode=d.get("ocr_mode"),
            attempts=d.get("attempts") or [],
            mean_confidence=d.get("mean_confidence"),
            encryption=d.get("encryption"),
            owner_person_id=d.get("owner_person_id"),
            owner_suggestion=d.get("owner_suggestion"),
            owner_suggestion_basis=d.get("owner_suggestion_basis"),
        )
