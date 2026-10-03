"""taxprep — Phase 1: transcribe tax documents into structured digital form.

Local-only. Works exclusively with synthetic fixture documents in this
phase; no real PII, no network calls.
"""

from .models import Document, FORM_TYPES, STATUSES

__all__ = ["Document", "FORM_TYPES", "STATUSES"]
