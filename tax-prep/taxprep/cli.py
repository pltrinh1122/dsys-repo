"""CLI: taxprep ingest|list|show|review|carryforward|mcp"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from .ingest import ingest_dir
from .models import FORM_TYPES
from .review import DEFAULT_PORT, serve_forever
from .store import DocumentStore

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _store(data_dir: str | None) -> DocumentStore:
    return DocumentStore(data_dir or str(DEFAULT_DATA_DIR))


def cmd_ingest(args: argparse.Namespace) -> int:
    store = _store(args.data_dir)
    docs = ingest_dir(args.input_dir, store)

    # summary table: counts by form_type x year
    counts = store.counts()
    years = sorted({y for (y, _f) in counts}, key=lambda v: (v is None, v))
    forms = sorted({f for (_y, f) in counts})

    def ylab(y):
        return str(y) if y is not None else "????"

    header = ["form \\ year"] + [ylab(y) for y in years] + ["total"]
    rows = []
    for f in forms:
        row = [f] + [str(counts.get((y, f), 0)) for y in years]
        row.append(str(sum(counts.get((y, f), 0) for y in years)))
        rows.append(row)
    widths = [max(len(r[i]) for r in [header] + rows) for i in range(len(header))]

    print(f"Ingested {len(docs)} document(s) from {args.input_dir}")
    print(" | ".join(h.ljust(w) for h, w in zip(header, widths)))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(" | ".join(c.ljust(w) for c, w in zip(row, widths)))

    need = store.needs_review()
    print(f"\n{len(need)} document(s) need review:")
    for d in need:
        print(f"  {d.doc_id}  [{d.form_type} {ylab(d.tax_year)}]  {d.source_path}")
    print(f"\nStore: {store.db_path} ({len(store)} records)")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    store = _store(args.data_dir)
    docs = store.list(year=args.year, form=args.form)
    if not docs:
        print("No documents match.")
        return 0
    print(f"{'doc_id':36} {'year':6} {'form':22} {'status':13} fields")
    for d in docs:
        year = str(d.tax_year) if d.tax_year else "????"
        print(f"{d.doc_id:36} {year:6} {d.form_type:22} {d.status:13} {len(d.fields)}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    store = _store(args.data_dir)
    doc = store.get(args.doc_id)
    if doc is None:
        # allow prefix match
        matches = [d for d in store.list() if d.doc_id.startswith(args.doc_id)]
        if len(matches) == 1:
            doc = matches[0]
        elif matches:
            print(f"Ambiguous prefix; {len(matches)} matches:")
            for m in matches:
                print(f"  {m.doc_id}")
            return 1
        else:
            print(f"No document: {args.doc_id}")
            return 1
    print(f"doc_id:      {doc.doc_id}")
    print(f"form_type:   {doc.form_type}")
    print(f"tax_year:    {doc.tax_year}")
    print(f"status:      {doc.status}")
    print(f"source:      {doc.source_path}")
    print(f"ocr_text:    {doc.ocr_text_ref}")
    print("fields:")
    for code, f in doc.fields.items():
        val = f.get("value")
        if isinstance(val, list) and len(val) > 5:
            val = f"<{len(val)} items>"
        print(f"  {code:28} = {val!r}  [{f.get('confidence')}]")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    store = _store(args.data_dir)
    serve_forever(store, port=args.port)
    return 0


def cmd_carryforward(args: argparse.Namespace) -> int:
    from .carryforward import compute_chain, from_store

    store = _store(args.data_dir)
    years = [args.year] if args.year is not None else [2023, 2024, 2025, 2026]
    yearly: dict[int, dict] = {}
    lot_notes: list[str] = []
    for y in years:
        r = from_store(store, y)  # raises on unvalidated 1099-Bs
        yearly[y] = {"st_current": r["st_current"], "lt_current": r["lt_current"]}
        lot_notes.append(
            f"{y}: {r['lots_included']} lot(s) in, {r['lots_excluded']} excluded"
        )
        for w in r["warnings"]:
            lot_notes.append(f"  ! {y}: {w}")
    result = compute_chain(
        yearly,
        {y: args.filing_status for y in years},
        prior_carryover={"st": Decimal(args.prior_st), "lt": Decimal(args.prior_lt)},
    )
    print(f"filing status: {args.filing_status} (all years; "
          "use the Python API for per-year statuses)")
    print(f"prior carryover into {years[0]}: "
          f"ST {_fmt(args.prior_st)}, LT {_fmt(args.prior_lt)}")
    print()
    print(result["table"])
    print()
    print("lots: " + "; ".join(lot_notes))
    if result["warnings"]:
        print("\nwarnings:")
        for w in result["warnings"]:
            print(f"  ! {w}")
    return 0


def _fmt(raw: str) -> str:
    d = Decimal(raw)
    s = f"${abs(d):,.2f}"
    return f"({s})" if d < 0 else s


def cmd_mcp(args: argparse.Namespace) -> int:
    import os
    if getattr(args, "data_dir", None):
        os.environ["TAXPREP_DATA_DIR"] = args.data_dir
    from .mcp_server import mcp
    mcp.run()  # stdio transport only -- never network
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="taxprep", description="Transcribe tax documents into structured digital form (local-only).")
    p.add_argument("--data-dir", default=None, help="data directory (default: ./data)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="ingest PDFs / OCR text files from a directory")
    pi.add_argument("input_dir", help="directory to walk for .pdf / .txt files")
    pi.set_defaults(func=cmd_ingest)

    pl = sub.add_parser("list", help="list ingested documents")
    pl.add_argument("--year", type=int, default=None)
    pl.add_argument("--form", default=None, choices=FORM_TYPES)
    pl.set_defaults(func=cmd_list)

    ps = sub.add_parser("show", help="show one document's extracted fields")
    ps.add_argument("doc_id", help="doc_id (prefix ok if unambiguous)")
    ps.set_defaults(func=cmd_show)

    pr = sub.add_parser("review", help="serve the visual validation UI (localhost only)")
    pr.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help=f"port to listen on (default {DEFAULT_PORT})")
    pr.set_defaults(func=cmd_review)

    pc = sub.add_parser("carryforward",
                        help="capital-loss carryforward chain 2023-2026 from validated 1099-Bs")
    pc.add_argument("--year", type=int, default=None,
                    help="compute a single year only (default: chain 2023-2026)")
    pc.add_argument("--filing-status", default="single",
                    help="filing status for all years, e.g. single|mfj|mfs|hoh (default single)")
    pc.add_argument("--prior-st", default="0",
                    help="2022 ST loss carryover into the first year (default 0)")
    pc.add_argument("--prior-lt", default="0",
                    help="2022 LT loss carryover into the first year (default 0)")
    pc.set_defaults(func=cmd_carryforward)

    pm = sub.add_parser("mcp", help="run the local MCP server over stdio (no network)")
    # SUPPRESS so `taxprep --data-dir D mcp` (parent flag) isn't clobbered.
    pm.add_argument("--data-dir", default=argparse.SUPPRESS,
                    help="data directory (default: ./data or TAXPREP_DATA_DIR)")
    pm.set_defaults(func=cmd_mcp)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
