"""Data model for Phase 1 document records.

A Document is one ingested source file (a PDF, or a .txt OCR sidecar)
with its classification, extracted fields, and review status.
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
    "UNKNOWN",
]

STATUSES = ("transcribed", "needs_review", "validated")

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
        )
