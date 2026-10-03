"""CLI: taxprep ingest|list|show|review|carryforward|mcp|verify|bus|config|relevance|gaps"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

from . import bus as bus_mod
from . import config as taxprep_config
from .ingest import ingest_dir
from .models import FORM_TYPES
from .review import DEFAULT_PORT, serve_forever
from .store import DocumentStore

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Blind-orchestrator mode: when TAXPREP_BLIND=1, commands that would print
# field values redact them (box_code + confidence + has_value only).
# The MCP tool boundary is the primary PII guarantee; this is defense in
# depth for the workstation session's shell.
BLIND = os.environ.get("TAXPREP_BLIND") == "1"


def _store(data_dir: str | None) -> DocumentStore:
    return DocumentStore(taxprep_config.resolve("data_dir", cli_value=data_dir))


def cmd_ingest(args: argparse.Namespace) -> int:
    input_dir = args.input_dir or taxprep_config.resolve("source_dir")
    if not input_dir:
        print("error: no input directory: pass one or run "
              "`taxprep config set source_dir <dir>` once", file=sys.stderr)
        return 2
    store = _store(args.data_dir)
    docs = ingest_dir(input_dir, store)

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

    print(f"Ingested {len(docs)} document(s) from {input_dir}")
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
    if BLIND:
        print("fields:      [redacted: TAXPREP_BLIND=1]")
        for code, f in doc.fields.items():
            v = f.get("value") if isinstance(f, dict) else None
            has = v is not None and v != ""
            print(f"  {code:28}  has_value={has!s:5}  [{f.get('confidence') if isinstance(f, dict) else '?'}]")
        return 0
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


def cmd_verify(args: argparse.Namespace) -> int:
    from .verify import verify_all

    store = _store(args.data_dir)
    result = verify_all(store, args.year)
    print(f"verify_all{' year=' + str(args.year) if args.year else ''}: "
          f"{'PASS' if result['passed'] else 'FAIL'}")
    for name, r in result["checks"].items():
        status = "PASS" if r.get("passed") else "FAIL"
        detail = ", ".join(
            f"{k}={v}" for k, v in r.items()
            if k not in ("passed",) and not k.endswith("_ids")
            and isinstance(v, (int, str, bool)))
        ids = [v for k, v in r.items()
               if k.endswith("_ids") and isinstance(v, list) and v]
        line = f"  {name:32} {status:4}  {detail}"
        print(line)
        for idlist in ids:
            for i in idlist:
                print(f"    - {i}")
    return 0 if result["passed"] else 1


# -- message bus -------------------------------------------------------


def cmd_bus_publish(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError as exc:
        print(f"error: --payload is not valid JSON: {exc}", file=sys.stderr)
        return 2
    try:
        path = bus_mod.publish(
            args.topic, args.type, payload,
            correlation_id=args.correlation_id,
            bus_dir=args.bus_dir,
            store_dir=args.store_dir,
            tuning_path=args.tuning,
        )
    except (ValueError, TypeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(path)
    print("Broadcasting = commit + push the dsys-store repo (not the code "
          "repo); listeners pick it up on their next pull.")
    return 0


def cmd_bus_listen(args: argparse.Namespace) -> int:
    tuning = bus_mod.load_tuning(args.tuning)
    topics = list(args.topic) or bus_mod.subscribed_topics(
        tuning, bus_dir=args.bus_dir, store_dir=args.store_dir)
    if not topics:
        print("no topics to listen on: `taxprep bus tune --topic <t>` "
              "or publish first", file=sys.stderr)
        return 1
    exclude = None if args.include_own else (tuning["session"]["id"] or None)
    try:
        bus_dir = bus_mod.resolve_bus_dir(args.bus_dir, store_dir=args.store_dir)
        repo = bus_mod.resolve_pull_target(args.bus_dir, store_dir=args.store_dir)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if repo is None:
        print("warning: bus dir is not inside a git repo; "
              "reading local messages only", file=sys.stderr)
    interval = int(tuning["tuning"].get("poll_interval_seconds", 30))
    timeout = args.timeout
    once = args.once
    start = time.monotonic()
    while True:
        for i, topic in enumerate(topics):
            try:
                result = bus_mod.poll_once(
                    topic, repo or bus_dir, bus_dir=bus_dir,
                    do_pull=repo is not None and i == 0,  # one pull per pass
                    exclude_from=exclude, tuning_path=args.tuning)
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            for msg in result:
                print(json.dumps(msg))
            for w in result.warnings:
                print(f"warning: {w}", file=sys.stderr)
        sys.stdout.flush()
        if once or (time.monotonic() - start) >= timeout:
            return 0
        time.sleep(min(interval, max(1, timeout - (time.monotonic() - start))))


def cmd_bus_topics(args: argparse.Namespace) -> int:
    for t in bus_mod.topics(bus_dir=args.bus_dir):
        print(t)
    return 0


def cmd_bus_tune(args: argparse.Namespace) -> int:
    if args.off:
        tuning = bus_mod.unsubscribe(args.topic, args.tuning)
        print(f"tuned out of {args.topic}")
    else:
        tuning = bus_mod.subscribe(args.topic, args.tuning)
        print(f"tuned into {args.topic}")
    print("subscribed topics: " +
          ", ".join(tuning["tuning"]["topics"]))
    return 0


def cmd_bus_whoami(args: argparse.Namespace) -> int:
    tuning = bus_mod.load_tuning(args.tuning)
    sid = tuning["session"]["id"] or "(not set -- generated on first publish)"
    print(f"session_id:  {sid}")
    print("subscribed:  " +
          ", ".join(bus_mod.subscribed_topics(
              tuning, bus_dir=args.bus_dir, store_dir=args.store_dir)))
    try:
        store = bus_mod.resolve_store_dir(args.store_dir)
        bus_dir = bus_mod.resolve_bus_dir(args.bus_dir, store_dir=args.store_dir)
    except (ValueError, FileNotFoundError) as exc:
        print(f"store_dir:   (unresolved: {exc})")
        return 0
    print(f"store_dir:   {store}  (dsys-store checkout)")
    print(f"bus_dir:     {bus_dir}")
    print(f"tuning:      {bus_mod.default_tuning_path() if args.tuning is None else args.tuning}")
    print(f"cursor:      {bus_mod.default_cursor_path()}")
    return 0
    print("(tuning and cursor are local-only; never committed)")
    return 0


# -- local config --------------------------------------------------------


def cmd_config_set(args: argparse.Namespace) -> int:
    try:
        path = taxprep_config.set_value(args.key, args.value)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"{args.key} = {args.value}  (in {path})")
    print("(machine-local; never committed)")
    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    path = taxprep_config.default_config_path()
    print(f"config file: {path}  "
          f"({'present' if path.is_file() else 'missing -- defaults apply'})")
    for key in ("source_dir", "data_dir", "scope_years", "store_dir"):
        print(f"{key:12} = {taxprep_config.resolve(key)}")
    print("(machine-local; never committed)")
    return 0


# -- relevance + gaps ----------------------------------------------------


def cmd_relevance(args: argparse.Namespace) -> int:
    from .relevance import assess_relevance, summarize

    store = _store(args.data_dir)
    scope = taxprep_config.resolve("scope_years")
    docs = store.list(year=args.year) if args.year is not None else None
    verdicts = assess_relevance(store, scope, docs=docs, persist=True)
    s = summarize(verdicts)
    print(f"relevance{' year=' + str(args.year) if args.year else ''} "
          f"(scope {scope}): {s['n_docs']} assessed, verdicts persisted")
    for v, n in s["counts"].items():
        print(f"  {v:12} {n}")
    for label, entries in (("needs_human", s["needs_human"]),
                           ("irrelevant", s["irrelevant"])):
        if entries:
            print(f"\n{label}:")
            for e in entries:
                print(f"  {e['doc_id']:36} {','.join(e['reasons'])}")
    return 0


def cmd_gaps(args: argparse.Namespace) -> int:
    from .gaps import analyze_gaps

    store = _store(args.data_dir)
    scope = taxprep_config.resolve("scope_years")
    result = analyze_gaps(store, scope, year=args.year)
    years = [str(args.year)] if args.year is not None else sorted(
        k for k in result if k != "report_path")
    for y in years:
        g = result[y]
        print(f"{y}: expected={','.join(g['expected_forms']) or '-'} "
              f"missing={','.join(g['missing_forms']) or '-'} "
              f"transcript_payers={g['n_transcript_payers']} "
              f"document_payers={g['n_document_payers']} "
              f"docs={g['n_docs']}"
              + ("" if g["has_transcript"]
                 else "  [no transcript parsed -- no ground truth]"))
    print(f"\nper-payer report (operator's eyes only): {result['report_path']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="taxprep", description="Transcribe tax documents into structured digital form (local-only).")
    p.add_argument("--data-dir", default=None, help="data directory (default: ./data)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="ingest PDFs / OCR text files from a directory")
    pi.add_argument("input_dir", nargs="?", default=None,
                    help="directory to walk (default: configured source_dir)")
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

    pv = sub.add_parser("verify", help="run mechanical verification checks (PII-free output)")
    pv.add_argument("--year", type=int, default=None,
                    help="restrict per-year checks to one year (default: all years)")
    pv.set_defaults(func=cmd_verify)

    pb = sub.add_parser("bus", help="broadcast message bus for sessions (accretes to dsys-store)")
    pb.add_argument("--bus-dir", default=None,
                    help="bus directory (default: <dsys-store>/bus or TAXPREP_BUS_DIR)")
    pb.add_argument("--store-dir", default=None,
                    help="dsys-store checkout (default: TAXPREP_STORE_DIR, config, or ~/workspace/dsys-store)")
    pb.add_argument("--tuning", default=None,
                    help="tuning file (default: ~/.config/taxprep/bus.toml)")
    bsub = pb.add_subparsers(dest="bus_cmd", required=True)

    bpub = bsub.add_parser("publish", help="publish one message (broadcast = commit + push)")
    bpub.add_argument("--topic", required=True)
    bpub.add_argument("--type", required=True, help="message type, e.g. code-landed")
    bpub.add_argument("--payload", required=True, help="JSON object (shapes only -- PII refused)")
    bpub.add_argument("--correlation-id", default=None)
    bpub.set_defaults(func=cmd_bus_publish)

    blis = bsub.add_parser("listen", help="poll subscribed topics (own broadcasts excluded)")
    blis.add_argument("--topic", action="append", default=[],
                      help="topic to listen on (repeatable; default: subscribed topics)")
    blis.add_argument("--timeout", type=float, default=300,
                      help="seconds to listen (default 300)")
    blis.add_argument("--once", action="store_true",
                      help="single pass, then exit")
    blis.add_argument("--include-own", action="store_true",
                      help="do NOT filter out this session's own broadcasts")
    blis.set_defaults(func=cmd_bus_listen)

    btop = bsub.add_parser("topics", help="list topics in the bus dir")
    btop.set_defaults(func=cmd_bus_topics)

    btun = bsub.add_parser("tune", help="tune into/out of a topic (local-only)")
    btun.add_argument("--topic", required=True)
    btun.add_argument("--off", action="store_true",
                      help="tune out instead of in")
    btun.set_defaults(func=cmd_bus_tune)

    bwho = bsub.add_parser("whoami", help="show this session's bus identity and tuning")
    bwho.set_defaults(func=cmd_bus_whoami)

    pcfg = sub.add_parser("config", help="machine-local workstation config (never committed)")
    csub = pcfg.add_subparsers(dest="config_cmd", required=True)
    cset = csub.add_parser("set", help="set one key: source_dir | data_dir | scope_years | store_dir")
    cset.add_argument("key")
    cset.add_argument("value")
    cset.set_defaults(func=cmd_config_set)
    cshow = csub.add_parser("show", help="show resolved config values")
    cshow.set_defaults(func=cmd_config_show)

    prl = sub.add_parser("relevance", help="triage docs: relevant | irrelevant | needs_human (labels only)")
    prl.add_argument("--year", type=int, default=None)
    prl.set_defaults(func=cmd_relevance)

    pgp = sub.add_parser("gaps", help="transcript-vs-ingested gap analysis (PII-free shape + local report)")
    pgp.add_argument("--year", type=int, default=None)
    pgp.set_defaults(func=cmd_gaps)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
