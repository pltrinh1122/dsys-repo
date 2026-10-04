"""CLI: taxprep ingest|list|show|review|carryforward|mcp|verify|bus|config|relevance|gaps|pipeline|relevance-override|validation-queue|exclude|exclusions|sync|ingest-csv"""

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
from . import lifecycle
from .ingest import ingest_dir
from .models import FORM_TYPES
from .review import DEFAULT_PORT, add_token_argument, serve_forever
from .store import DocumentStore

# N1: data_dir has no package default. It is REQUIRED -- set once via
# `taxprep config set data_dir <path>` (or TAXPREP_DATA_DIR / --data-dir);
# config.resolve("data_dir") fails closed naming that command, and
# refuses paths inside site-packages.

# Blind-orchestrator mode: when TAXPREP_BLIND=1, commands that would print
# field values redact them (box_code + confidence + has_value only).
# The MCP tool boundary is the primary PII guarantee; this is defense in
# depth for the workstation session's shell.
BLIND = os.environ.get("TAXPREP_BLIND") == "1"


def _store(data_dir: str | None) -> DocumentStore:
    try:
        return DocumentStore(taxprep_config.resolve("data_dir", cli_value=data_dir))
    except ValueError as exc:
        # N1 fail-closed: no usable data dir configured.
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)


def _resolve_doc(store: DocumentStore, doc_id: str):
    """Resolve a doc_id (prefix ok if unambiguous); None + message if not."""
    doc = store.get(doc_id)
    if doc is not None:
        return doc
    matches = [d for d in store.list() if d.doc_id.startswith(doc_id)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        print(f"Ambiguous prefix; {len(matches)} matches:")
        for m in matches:
            print(f"  {m.doc_id}")
    else:
        print(f"No document: {doc_id}")
    return None


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
    # R6 per-run accounting (reason codes; file names hidden in blind mode)
    rep = docs.summary()
    print(f"files seen: {rep['files_seen']}, ingested: {rep['ingested']}, "
          f"skipped: {len(rep['skipped'])}, errored: {len(rep['errored'])}")
    for entry in rep["skipped"]:
        suffix = "" if BLIND else f"  {entry['file']}"
        print(f"  skipped [{entry['reason_code']}]" + suffix)
    for entry in rep["errored"]:
        suffix = "" if BLIND else f"  {entry['file']}"
        print(f"  errored [{entry['reason_code']}]" + suffix)
    print(" | ".join(h.ljust(w) for h, w in zip(header, widths)))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(" | ".join(c.ljust(w) for c, w in zip(row, widths)))

    need = store.needs_review()
    print(f"\n{len(need)} document(s) need review:")
    for d in need:
        # R8: blind mode drops source_path -- local paths can leak usernames.
        suffix = "" if BLIND else f"  {d.source_path}"
        print(f"  {d.doc_id}  [{d.form_type} {ylab(d.tax_year)}]{suffix}")
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
    doc = _resolve_doc(store, args.doc_id)
    if doc is None:
        return 1
    if args.meta:
        # R21a: metadata-only output -- the same scrubbed shape the MCP
        # boundary uses. Opaque owner ids cross; names never do.
        from .mcp_server import _scrub_doc
        print(json.dumps(_scrub_doc(doc.to_dict()), indent=2,
                         sort_keys=True))
        return 0
    print(f"doc_id:      {doc.doc_id}")
    print(f"form_type:   {doc.form_type}")
    print(f"tax_year:    {doc.tax_year}")
    print(f"status:      {doc.status}")
    # R21a: owner is opaque metadata -- shown in both modes.
    owner_line = f"owner:       {doc.owner_person_id or '(unassigned)'}"
    if doc.owner_suggestion and not doc.owner_person_id:
        owner_line += (f"  [suggestion pending: {doc.owner_suggestion} "
                       f"({doc.owner_suggestion_basis}) -- Operator disposes]")
    print(owner_line)
    if BLIND:
        # R8: reuse the MCP scrub helper -- transcript field codes embed
        # payer names ("payer1.ACME CORP.1"); they must be redacted here
        # too. (Local import: keeps FastMCP out of every CLI invocation.)
        from .mcp_server import _scrub_code

        print("fields:      [redacted: TAXPREP_BLIND=1]")
        for code, f in doc.fields.items():
            v = f.get("value") if isinstance(f, dict) else None
            has = v is not None and v != ""
            print(f"  {_scrub_code(code):28}  has_value={has!s:5}  [{f.get('confidence') if isinstance(f, dict) else '?'}]")
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


# -- R21a: per-person scoping ------------------------------------------

def cmd_person_register(args: argparse.Namespace) -> int:
    from . import persons
    store = _store(args.data_dir)
    try:
        pid = persons.register_person(store.data_dir, args.name)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"registered {pid}")
    return 0


def cmd_owner_set(args: argparse.Namespace) -> int:
    from . import persons
    store = _store(args.data_dir)
    doc = _resolve_doc(store, args.doc_id)
    if doc is None:
        return 1
    try:
        res = persons.assign_owner(store, doc.doc_id, args.person_id)
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    prev = f" (was {res['previous']})" if res["previous"] else ""
    acc = " [accepted suggestion]" if res["accepted_suggestion"] else ""
    print(f"{res['doc_id']}: owner = {res['owner_person_id']}{prev}{acc}")
    return 0


def cmd_owner_suggest(args: argparse.Namespace) -> int:
    from . import persons
    store = _store(args.data_dir)
    doc = _resolve_doc(store, args.doc_id)
    if doc is None:
        return 1
    try:
        res = persons.suggest_owner_for_doc(store, doc.doc_id)
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if res is None:
        print(f"{doc.doc_id}: no suggestion (no recipient text matched a "
              "registered person)")
        return 0
    print(f"{doc.doc_id}: suggested owner {res['owner_suggestion']} "
          f"({res['basis']}) -- UN-DISPOSED: the Operator assigns it with "
          "`taxprep owner set`")
    return 0


def cmd_scope_apply(args: argparse.Namespace) -> int:
    from . import persons
    store = _store(args.data_dir)
    in_scope = {p.strip() for p in args.in_scope.split(",") if p.strip()}
    if not in_scope:
        print("error: --in-scope needs at least one person id",
              file=sys.stderr)
        return 1
    try:
        applied = persons.apply_scope_filter(store, in_scope)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for r in applied:
        print(f"excluded {r['doc_id']} (owner {r['owner_person_id']}: "
              "out-of-scope-person)")
    print(f"{len(applied)} document(s) excluded; in scope: "
          f"{', '.join(sorted(in_scope))}")
    return 0


def cmd_return_assign(args: argparse.Namespace) -> int:
    from . import persons
    store = _store(args.data_dir)
    doc = _resolve_doc(store, args.doc_id)
    if doc is None:
        return 1
    try:
        res = persons.record_return_assignment(
            store, doc.doc_id, args.person_id, args.assignment)
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{res['doc_id']}: {res['person_id']} -> {res['assignment']} "
          f"(decision {res['decision_seq']})")
    return 0


# -- R21b: 1040-X column-A builder --------------------------------------

def cmd_column_a(args: argparse.Namespace) -> int:
    from . import column_a
    store = _store(args.data_dir)
    result = column_a.build_column_a(store, args.year)
    cov = result["coverage"]
    print(f"1040-X column A -- tax year {args.year} "
          f"({cov['n_present']} present, {cov['n_missing']} MISSING, "
          f"{cov['n_conflict']} CONFLICT; {cov['n_source_docs']} source docs)")
    for e in result["lines"]:
        if BLIND:
            val = "[redacted: TAXPREP_BLIND=1]" if e["value"] else "-"
        else:
            val = e["value"] if e["value"] is not None else "-"
        src = e["source"] or "-"
        flag = "" if e["status"] == "present" else f"  [{e['status']}]"
        print(f"  {e['line']:4} {e['label']:52} {val:>14}  {src}{flag}")
        for alt in e["also_seen"]:
            mark = "agrees" if alt.get("agrees") else "DIFFERS"
            print(f"         also seen: {alt['source']} {alt['source_doc_id']} "
                  f"= {alt['value']} ({mark})")
    for c in result["conflicts_raised"]:
        print(f"CONFLICT raised for {c['line']}: {c['conflict_id']} "
              f"(transcript {c['transcript_doc']} vs original "
              f"{c['original_doc']}) -- Operator disposes")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    store = _store(args.data_dir)
    serve_forever(store, port=args.port, token=args.token)
    return 0


def cmd_carryforward(args: argparse.Namespace) -> int:
    from .carryforward import compute_chain
    from . import gold

    store = _store(args.data_dir)
    years = [args.year] if args.year is not None else [2023, 2024, 2025, 2026]
    yearly: dict[int, dict] = {}
    lot_notes: list[str] = []
    params = {"filing_status": args.filing_status,
              "prior_st": str(args.prior_st), "prior_lt": str(args.prior_lt)}
    for y in years:
        try:
            # W4 (Arc B): every gold computation runs through the gate.
            # GoldRefused carries structured reason codes -- loud, never
            # silent. Exit 3 marks a gate refusal (distinct from 1/2).
            r = gold.gated_carryforward(store, y, params=params)
        except gold.GoldRefused as exc:
            print(f"gold refused for {y}: {len(exc.reason_codes)} blocker(s)",
                  file=sys.stderr)
            for rc in exc.reason_codes:
                who = (rc.get("doc_id") or rc.get("group_id")
                       or rc.get("conflict_id") or "")
                print(f"  [{rc['code']}] {who} {rc.get('detail', '')}".rstrip(),
                      file=sys.stderr)
            print("resolve each blocker (or record an Operator decision "
                  "disposing it), then retry", file=sys.stderr)
            return 3
        except ValueError as exc:
            # The carryforward's own R3 guard, post-gate: still loud.
            print(f"carryforward failed for {y}: {exc}", file=sys.stderr)
            return 1
        yearly[y] = {"st_current": r["st_current"], "lt_current": r["lt_current"]}
        lot_notes.append(
            f"{y}: {r['lots_included']} lot(s) in, {r['lots_excluded']} excluded"
        )
        g = r.get("gold", {})
        if g.get("input_digest"):
            lot_notes.append(
                f"{y}: gold input_digest {g['input_digest'][:16]}… "
                f"output_digest {g['output_digest'][:16]}…"
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
    try:
        # N1 fail-closed with a clean CLI error (not a FastMCP traceback).
        taxprep_config.resolve("data_dir")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
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
    wait_first = args.wait_first  # N3: block until first delivery, then exit
    delivered = 0
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
                delivered += 1
            for w in result.warnings:
                print(f"warning: {w}", file=sys.stderr)
        sys.stdout.flush()
        if wait_first and delivered:
            return 0
        if once or (time.monotonic() - start) >= timeout:
            return 0
        time.sleep(min(interval, max(1, timeout - (time.monotonic() - start))))


def cmd_bus_topics(args: argparse.Namespace) -> int:
    for t in bus_mod.topics(bus_dir=args.bus_dir):
        print(t)
    return 0


def cmd_bus_tune(args: argparse.Namespace) -> int:
    # N3: tuning into a topic on top of the default "*" expands it to an
    # explicit list -- say so, instead of a silent no-op.
    was_star = bus_mod.load_tuning(args.tuning)["tuning"]["topics"] == ["*"]
    if args.off:
        tuning = bus_mod.unsubscribe(args.topic, args.tuning)
        print(f"tuned out of {args.topic}")
    else:
        tuning = bus_mod.subscribe(args.topic, args.tuning)
        print(f"tuned into {args.topic}")
        if was_star:
            print("note: '*' expanded to the explicit topic list above -- "
                  "a later `tune --topic <t> --off` now narrows it")
    print("subscribed topics: " +
          ", ".join(tuning["tuning"]["topics"]))
    return 0


def cmd_bus_whoami(args: argparse.Namespace) -> int:
    import tomllib

    tuning = bus_mod.load_tuning(args.tuning)
    # N3: TAXPREP_SESSION_ID is the ROLE, not the id -- show both
    # distinctly. The generated id (<role>-<6 hex>) lives in the tuning
    # file; a bare role-shaped value there is not an id.
    role = os.environ.get("TAXPREP_SESSION_ID") or "(not set)"
    tp = Path(args.tuning) if args.tuning else bus_mod.default_tuning_path()
    file_id = ""
    if tp.is_file():
        try:
            with tp.open("rb") as fh:
                raw = tomllib.load(fh)
            if isinstance(raw, dict):
                file_id = str(raw.get("session", {}).get("id", "") or "")
        except (OSError, tomllib.TOMLDecodeError):
            file_id = ""
    if file_id and bus_mod._SESSION_ID_RE.match(file_id):
        sid_line = file_id
    elif file_id:
        sid_line = (f"{file_id}  (not a generated id -- a fresh "
                    "<role>-<6 hex> id is minted on first publish)")
    else:
        sid_line = "(not generated yet -- minted on first publish)"
    print(f"role:        {role}  (TAXPREP_SESSION_ID: the role, not the id)")
    print(f"session_id:  {sid_line}")
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
        try:
            value = taxprep_config.resolve(key)
        except ValueError as exc:
            # N1: data_dir is required; show the setup hint, not a traceback.
            value = f"(unset: {exc})"
        print(f"{key:12} = {value}")
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


# -- G: pipeline stages + relevance override + validation queue -------


def cmd_pipeline_stages(args: argparse.Namespace) -> int:
    from .pipeline import registry

    for s in registry():
        alongside = "  [rides alongside -- analysis, not a gate]" \
            if s["kind"] == "analysis" else ""
        print(f"{s['name']:16} [{s['kind']:10}] {s['title']}{alongside}")
        print(f"    {s['description']}")
    return 0


def cmd_pipeline_run(args: argparse.Namespace) -> int:
    from .pipeline import run_pipeline, slice_sequence

    store = _store(args.data_dir)  # N1 fail-closed
    input_dir = args.input_dir or taxprep_config.resolve("source_dir")
    scope = taxprep_config.resolve("scope_years")
    try:
        stages = slice_sequence(args.from_stage, args.to_stage)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if input_dir is None and any(s["name"] == "INGESTION" for s in stages):
        print("error: no input directory: pass one or run "
              "`taxprep config set source_dir <dir>` once", file=sys.stderr)
        return 2
    result = run_pipeline(
        store, input_dir=input_dir, scope_years=scope, year=args.year,
        from_stage=args.from_stage, to_stage=args.to_stage)
    print()
    done = sum(1 for r in result["stages"] if r["status"] == "ok")
    skipped = sum(1 for r in result["stages"] if r["status"] == "skipped")
    if result["ok"]:
        print(f"pipeline: OK ({done} ran, {skipped} operator-step skipped)")
        return 0
    print(f"pipeline: FAILED at {result['failed_stage']} "
          f"({done} ran before the failure)")
    return 1


def cmd_relevance_override(args: argparse.Namespace) -> int:
    from .relevance import relevance_override

    store = _store(args.data_dir)
    doc_id = _resolve_doc_id(store, args.doc_id)
    try:
        out = relevance_override(store, doc_id, args.verdict, args.reason)
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    rec = out["record"]
    print(f"override recorded: {rec['doc_id']} -> {rec['verdict']} "
          f"(reason: {rec['reason']}, ts: {rec['ts']})")
    print(f"applied verdict: {out['applied_verdict']}")
    if out["suppressed"]:
        print("note: suppressed -- the document is validated, so "
              "validated_by_operator dominates (stays relevant)")
    return 0


def cmd_validation_queue(args: argparse.Namespace) -> int:
    store = _store(args.data_dir)
    docs = [d for d in store.list(year=args.year, form=args.form)
            if d.status in lifecycle.UNVALIDATED_EXTRACTED]
    hidden = [d for d in docs if d.relevance == "irrelevant"]
    if not args.include_irrelevant:
        docs = [d for d in docs if d.relevance != "irrelevant"]
    if not docs:
        print("validation queue empty.")
    else:
        print(f"{'doc_id':36} {'year':6} {'form':22} {'status':13} relevance")
        for d in sorted(docs, key=lambda d: d.doc_id):
            year = str(d.tax_year) if d.tax_year else "????"
            print(f"{d.doc_id:36} {year:6} {d.form_type:22} "
                  f"{d.status:13} {d.relevance}")
    if hidden and not args.include_irrelevant:
        print(f"\n{len(hidden)} irrelevant document(s) hidden "
              "(--include-irrelevant to list; `taxprep relevance-override` "
              "to restore)")
    return 0


# -- R4/R6/R7: sync, exclusions, broker CSV (wave-2 workstream F) --------


def _resolve_doc_id(store: DocumentStore, doc_id: str):
    """Exact doc_id, else unique prefix match (like cmd_show)."""
    doc = store.get(doc_id)
    if doc is not None:
        return doc.doc_id
    matches = [d for d in store.list() if d.doc_id.startswith(doc_id)]
    if len(matches) == 1:
        return matches[0].doc_id
    if matches:
        print(f"Ambiguous prefix; {len(matches)} matches.", file=sys.stderr)
        raise SystemExit(1)
    print(f"No document: {doc_id}", file=sys.stderr)
    raise SystemExit(1)


def cmd_sync(args: argparse.Namespace) -> int:
    from .ingest import sync as sync_store

    input_dir = args.input_dir or taxprep_config.resolve("source_dir")
    if not input_dir:
        print("error: no input directory: pass one or run "
              "`taxprep config set source_dir <dir>` once", file=sys.stderr)
        return 2
    store = _store(args.data_dir)
    result = sync_store(input_dir, store)
    print(f"sync {input_dir}: files_seen={result['files_seen']} "
          f"ingested={result['ingested']} "
          f"skipped={len(result['skipped'])} "
          f"errored={len(result['errored'])}")
    for entry in result["skipped"]:
        suffix = "" if BLIND else f"  {entry['file']}"
        print(f"  skipped [{entry['reason_code']}]" + suffix)
    for entry in result["errored"]:
        suffix = "" if BLIND else f"  {entry['file']}"
        print(f"  errored [{entry['reason_code']}]" + suffix)
    if result["orphaned"]:
        print(f"{len(result['orphaned'])} document(s) ORPHANED "
              "(source missing):")
        for doc_id in result["orphaned"]:
            print(f"  {doc_id}")
    else:
        print("no orphaned documents")
    return 0


def cmd_exclude(args: argparse.Namespace) -> int:
    from . import exclusions as excl_mod
    from . import silver as silver_mod

    store = _store(args.data_dir)
    doc_id = _resolve_doc_id(store, args.doc_id)
    try:
        rec = excl_mod.record_exclusion(store.data_dir, doc_id, args.reason)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    doc = store.get(doc_id)
    # R13: the exclusion also moves the doc through the lifecycle
    # (any non-terminal --exclude(operator)--> excluded). Terminal
    # docs keep the file record; the transition refusal is loud.
    if doc is not None:
        with store.txn():
            res = lifecycle.transition(
                doc, lifecycle.EXCLUDE, actor=lifecycle.OPERATOR,
                event_input=lifecycle.ExcludeInput(reason=args.reason),
                store=store)
            if not res.ok:
                print(f"warning: lifecycle exclude refused "
                      f"({res.reason_code}); doc stays {doc.status}",
                      file=sys.stderr)
            elif not res.noop:
                bronze_hash = silver_mod.bronze_hash_for_doc(store, doc)
                if bronze_hash is None:
                    store.upsert(doc)
                else:
                    silver_mod.persist_silver_doc(
                        store, doc,
                        silver_mod.derivation_for_doc(store, doc.doc_id),
                        bronze_hash)
    # Medallion record (Arc B): the exclusion also lands in the append-only
    # decision log so gold's input digest and audit trail see the same
    # disposal. Best-effort -- the file record above is authoritative.
    log_decision = getattr(store, "log_decision", None)
    if callable(log_decision):
        from datetime import datetime, timezone
        try:
            log_decision(actor="operator", kind="exclude", doc_id=doc_id,
                         payload={"doc_id": doc_id, "reason": args.reason,
                                  "ts": datetime.now(timezone.utc).isoformat()})
        except Exception:
            pass
    print(f"excluded {rec['doc_id']} (recorded {rec['recorded_at']})")
    return 0


def cmd_exclusions(args: argparse.Namespace) -> int:
    from . import exclusions as excl_mod

    store = _store(args.data_dir)
    recs = excl_mod.list_exclusions(store.data_dir)
    if not recs:
        print("no exclusions recorded")
        return 0
    for r in recs:
        # Operator free text stays local: redacted in blind mode.
        reason = "[redacted: TAXPREP_BLIND=1]" if BLIND else r["reason"]
        print(f"{r['doc_id']}: {reason} (recorded {r['recorded_at']})")
    return 0


def cmd_ingest_csv(args: argparse.Namespace) -> int:
    from .brokercsv import ingest_csv

    store = _store(args.data_dir)
    try:
        docs = ingest_csv(args.file, args.broker, args.year, store)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"ingested {len(docs)} lot(s) from broker CSV "
          f"(broker={args.broker}, year={args.year})")
    for d in docs:
        codes = sorted(d.fields)
        print(f"  {d.doc_id}  [{d.form_type} {d.tax_year}] "
              f"{len(codes)} fields: {','.join(codes)}")
    print("status needs_review: validate with `taxprep review` before "
          "carryforward will consume these lots")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="taxprep", description="Transcribe tax documents into structured digital form (local-only).")
    p.add_argument("--data-dir", default=None,
                   help="data directory (default: TAXPREP_DATA_DIR or config "
                        "data_dir; required -- set once via "
                        "`taxprep config set data_dir <path>`")
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
    ps.add_argument("--meta", action="store_true",
                    help="R21a: print PII-free metadata only (MCP-scrubbed "
                         "shape; opaque owner ids, never names)")
    ps.set_defaults(func=cmd_show)

    pr = sub.add_parser("review", help="serve the visual validation UI (localhost only)")
    pr.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help=f"port to listen on (default {DEFAULT_PORT})")
    add_token_argument(pr)  # R10: optional per-run auth token
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
                    help="data directory (TAXPREP_DATA_DIR or config data_dir "
                         "otherwise; required)")
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
    blis.add_argument("--wait-first", action="store_true",
                      help="block until the first delivery, then exit "
                           "(wakes a background process; --timeout still bounds it)")
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

    # -- G: canonical pipeline stages + relevance override + queue --------

    ppl = sub.add_parser("pipeline", help="canonical pipeline stages (registry + run)")
    psub = ppl.add_subparsers(dest="pipeline_cmd", required=True)

    pst = psub.add_parser("stages", help="list the canonical stage sequence")
    pst.set_defaults(func=cmd_pipeline_stages)

    prun = psub.add_parser("run", help="run the mechanical stages in the corrected order")
    prun.add_argument("input_dir", nargs="?", default=None,
                      help="directory to ingest (default: configured source_dir; "
                           "needed only when the slice includes INGESTION)")
    prun.add_argument("--from", dest="from_stage", default=None, metavar="STAGE",
                      help="first stage to run (default: INGESTION)")
    prun.add_argument("--to", dest="to_stage", default=None, metavar="STAGE",
                      help="last stage to run, inclusive (default: CARRYFORWARD)")
    prun.add_argument("--year", type=int, default=None,
                      help="restrict per-year reporting/checks to one year")
    prun.set_defaults(func=cmd_pipeline_run)

    pro = sub.add_parser("relevance-override",
                         help="record an explicit Operator override of a "
                              "document's relevance verdict")
    pro.add_argument("doc_id", help="doc_id (prefix ok if unambiguous)")
    pro.add_argument("verdict", choices=["relevant", "irrelevant",
                                        "needs_human"])
    pro.add_argument("--reason", required=True,
                     help="why this verdict (required; recorded in the "
                          "audit trail)")
    pro.set_defaults(func=cmd_relevance_override)

    pvq = sub.add_parser("validation-queue",
                         help="list the human validation queue (irrelevants "
                              "excluded by default)")
    pvq.add_argument("--year", type=int, default=None)
    pvq.add_argument("--form", default=None, choices=FORM_TYPES)
    pvq.add_argument("--include-irrelevant", action="store_true",
                     help="also list documents with relevance verdict "
                          "irrelevant")
    pvq.set_defaults(func=cmd_validation_queue)

    # -- R4/R6/R7: sync, exclusions, broker CSV (additive; wave-2 workstream F)

    psy = sub.add_parser("sync", help="re-ingest a source dir (idempotent); "
                                      "mark documents whose source is missing ORPHANED")
    psy.add_argument("input_dir", nargs="?", default=None,
                     help="directory to walk (default: configured source_dir)")
    psy.set_defaults(func=cmd_sync)

    pex = sub.add_parser("exclude", help="record an Operator exclusion for a "
                                         "document (carryforward guard)")
    pex.add_argument("doc_id", help="doc_id (prefix ok if unambiguous)")
    pex.add_argument("--reason", required=True,
                     help="why this document is excluded (required)")
    pex.set_defaults(func=cmd_exclude)

    pexl = sub.add_parser("exclusions", help="list recorded exclusions")
    pexl.set_defaults(func=cmd_exclusions)

    pcs = sub.add_parser("ingest-csv", help="ingest a broker CSV into 1099-B "
                                            "lot records")
    pcs.add_argument("--broker", required=True,
                     help="broker name (see brokercsv.BROKER_MAPS)")
    pcs.add_argument("--file", required=True, help="CSV file to ingest")
    pcs.add_argument("--year", type=int, required=True, help="tax year")
    pcs.set_defaults(func=cmd_ingest_csv)

    # -- R21a: per-person scoping ---------------------------------------

    pper = sub.add_parser("person", help="R21a: person registry (opaque ids)")
    ppersub = pper.add_subparsers(dest="person_cmd", required=True)
    ppreg = ppersub.add_parser("register", help="register a person by name "
                                               "(local only; returns "
                                               "person-N)")
    ppreg.add_argument("name", help="person's name (PII: local registry only)")
    ppreg.set_defaults(func=cmd_person_register)

    pown = sub.add_parser("owner", help="R21a: assign / suggest document owners")
    pownsub = pown.add_subparsers(dest="owner_cmd", required=True)
    poset = pownsub.add_parser("set", help="Operator assigns a document's "
                                          "owner (disposes any suggestion)")
    poset.add_argument("doc_id", help="doc_id (prefix ok if unambiguous)")
    poset.add_argument("person_id", help="opaque person id (person-N)")
    poset.set_defaults(func=cmd_owner_set)
    posug = pownsub.add_parser("suggest", help="derive an owner suggestion "
                                              "from recipient text "
                                              "(shown, never auto-applied)")
    posug.add_argument("doc_id", help="doc_id (prefix ok if unambiguous)")
    posug.set_defaults(func=cmd_owner_suggest)

    psc = sub.add_parser("scope", help="R21a: apply the Operator's person scope")
    pscsub = psc.add_subparsers(dest="scope_cmd", required=True)
    pscap = pscsub.add_parser("apply", help="exclude out-of-scope-owned docs "
                                            "with reason out-of-scope-person")
    pscap.add_argument("--in-scope", required=True,
                       help="comma-separated opaque person ids in scope")
    pscap.set_defaults(func=cmd_scope_apply)

    pret = sub.add_parser("return", help="R21a: record return assignments")
    pretsub = pret.add_subparsers(dest="return_cmd", required=True)
    pra = pretsub.add_parser("assign", help="Operator decision: which return "
                                            "this person's documents feed")
    pra.add_argument("doc_id", help="doc_id (prefix ok if unambiguous)")
    pra.add_argument("person_id", help="opaque person id (person-N)")
    pra.add_argument("assignment", choices=["joint", "own", "election"],
                     help="joint = the joint return; own = the person's own "
                          "return; election = per-election")
    pra.set_defaults(func=cmd_return_assign)

    # -- R21b: 1040-X column-A builder ----------------------------------

    pca = sub.add_parser("column-a", help="R21b: build 1040-X column-A lines "
                                          "for a tax year (read-model)")
    pca.add_argument("--year", type=int, required=True, help="tax year")
    pca.set_defaults(func=cmd_column_a)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
