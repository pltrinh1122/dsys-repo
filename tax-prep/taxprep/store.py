"""Thin shim: DocumentStore is now the medallion-backed MedallionStore.

`from taxprep.store import DocumentStore` keeps working unchanged.
The JSONL + fcntl lock-file implementation is superseded by SQLite
(taxprep/mstore.py); see medallion_schema.sql for the DDL.
"""

from .mstore import DocumentStore, MedallionStore

__all__ = ["DocumentStore", "MedallionStore"]
