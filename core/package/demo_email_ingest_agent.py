"""Scratch simulation agent for the operator's email-ingestion example.

NOT part of the ratified build — hand-built 2026-09-26 for the manual
simulation of the Half 2 inference-service channel.

Pure function — zero inference inside. Round 1: mechanically validates and
sanitizes the email batch (V6: no prompt body line may begin with "@@"),
then emits one `classify` prompt-request per email (MATTER vs NOISE).
Round 2: mechanically maps verdicts to request ids and builds structured
matter records for MATTER verdicts; NOISE is discarded by rule.
"""

from __future__ import annotations

import hashlib
from typing import Any

MAX_EMAILS = 8  # spec §8: max 8 requests per round


def _matter_id(sender: str, subject: str) -> str:
    h = hashlib.sha256(f"{sender}\x00{subject}".encode("utf-8")).hexdigest()
    return "m-" + h[:12]


def _sanitize(text: str) -> str:
    """Mechanical V6 compliance: no line of a prompt body may start with @@."""
    out = []
    for line in text.splitlines():
        if line.startswith("@@"):
            line = "> " + line  # quote it; meaning preserved, marker gone
        out.append(line)
    return "\n".join(out)


def _email_key(i: int) -> str:
    return f"pr-{i + 1}"


def handle(event: dict[str, Any],
           inference_results: list[dict[str, Any]]) -> dict[str, Any]:
    emails = event.get("emails", [])
    if not isinstance(emails, list):
        return {"status": "crashed",
                "reason": "event.emails is not a list (mechanical refusal)"}
    batch = emails[:MAX_EMAILS]

    if not inference_results:
        # ---- Round 1: mechanical prep, then inference requests ----
        prepared = []
        for i, em in enumerate(batch):
            sender = str(em.get("from", ""))
            subject = str(em.get("subject", ""))
            body = _sanitize(str(em.get("body", "")))
            prepared.append({
                "request_id": _email_key(i),
                "matter_id": _matter_id(sender, subject),
                "from": sender, "subject": subject, "body": body,
            })
        for p in prepared:
            print(f'@@prompt-request id="{p["request_id"]}" kind="classify"')
            print("Classify this email as MATTER or NOISE.")
            print("MATTER = requests action, a decision, or records a "
                  "commitment. NOISE = everything else.")
            # NOTE (stub artifact): the deterministic claude-stub speaks a
            # fixed URGENT/ROUTINE vocabulary regardless of the prompt. The
            # agent therefore requests the stub's vocabulary and maps
            # URGENT->MATTER, ROUTINE->NOISE mechanically. Against the real
            # `claude` backing the prompt would ask for MATTER/NOISE
            # directly; the mechanism exercised here is identical.
            print("Reply with exactly one line:")
            print("verdict: URGENT")
            print("or:")
            print("verdict: ROUTINE")
            print()
            print(f"From: {p['from']}")
            print(f"Subject: {p['subject']}")
            print()
            print(p["body"])
            print("@@end", flush=True)
        return {"status": "awaiting_inference",
                "requests": [p["request_id"] for p in prepared],
                "prepared": len(prepared)}
    # ---- Round 2: mechanical verdict mapping + record building ----
    verdict_by_id: dict[str, str] = {}
    for r in inference_results:
        v = "UNKNOWN"
        for line in str(r.get("text", "")).splitlines():
            if line.strip().lower().startswith("verdict:"):
                v = line.split(":", 1)[1].strip().upper()
                break
        verdict_by_id[str(r.get("request_id"))] = v
    matters: list[dict[str, Any]] = []
    noise = 0
    unknown = 0
    for i, em in enumerate(batch):
        rid = _email_key(i)
        sender = str(em.get("from", ""))
        subject = str(em.get("subject", ""))
        v = verdict_by_id.get(rid, "UNKNOWN")
        if v == "URGENT":
            # stub vocabulary -> matter vocabulary (mechanical mapping;
            # see note in round 1: real backing would return MATTER/NOISE)
            matters.append({
                "matter_id": _matter_id(sender, subject),
                "from": sender,
                "subject": subject,
                "classification": "MATTER",
                "source": "email-ingest-sim",
            })
        elif v == "ROUTINE":
            noise += 1
        else:
            unknown += 1
    return {"status": "complete",
            "matters": matters,
            "matters_created": len(matters),
            "discarded_noise": noise,
            "unknown": unknown}
