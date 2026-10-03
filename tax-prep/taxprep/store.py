"""JSONL document store.

Layout under <data_dir>/:
    documents.jsonl        one JSON object per line (upsert by doc_id)
    ocr/<doc_id>.txt       extracted / sidecar OCR text per document
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Document


class DocumentStore:
    def __init__(self, data_dir: str | Path = "data") -> None:
        self.data_dir = Path(data_dir)
        self.ocr_dir = self.data_dir / "ocr"
        self.db_path = self.data_dir / "documents.jsonl"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.ocr_dir.mkdir(parents=True, exist_ok=True)
        self._docs: dict[str, Document] = {}
        self._load()

    # -- persistence -------------------------------------------------
    def _load(self) -> None:
        if not self.db_path.exists():
            return
        for line in self.db_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            doc = Document.from_dict(json.loads(line))
            self._docs[doc.doc_id] = doc

    def _save(self) -> None:
        with self.db_path.open("w", encoding="utf-8") as fh:
            for doc in self._docs.values():
                fh.write(json.dumps(doc.to_dict()) + "\n")

    # -- OCR text ----------------------------------------------------
    def save_ocr(self, doc_id: str, text: str) -> str:
        """Persist OCR text; returns the ocr_text_ref stored on the Document."""
        ref = f"ocr/{doc_id}.txt"
        (self.ocr_dir / f"{doc_id}.txt").write_text(text, encoding="utf-8")
        return ref

    def load_ocr(self, doc_id: str) -> str:
        return (self.ocr_dir / f"{doc_id}.txt").read_text(encoding="utf-8")

    # -- CRUD --------------------------------------------------------
    def upsert(self, doc: Document) -> None:
        self._docs[doc.doc_id] = doc
        self._save()

    def get(self, doc_id: str) -> Document | None:
        return self._docs.get(doc_id)

    def list(self, year: int | None = None, form: str | None = None) -> list[Document]:
        docs = list(self._docs.values())
        if year is not None:
            docs = [d for d in docs if d.tax_year == year]
        if form is not None:
            docs = [d for d in docs if d.form_type == form]
        return sorted(docs, key=lambda d: (d.tax_year or 0, d.form_type, d.doc_id))

    def counts(self) -> dict[tuple[int | None, str], int]:
        out: dict[tuple[int | None, str], int] = {}
        for d in self._docs.values():
            key = (d.tax_year, d.form_type)
            out[key] = out.get(key, 0) + 1
        return out

    def needs_review(self) -> list[Document]:
        return [d for d in self._docs.values() if d.status == "needs_review"]

    def __len__(self) -> int:
        return len(self._docs)
