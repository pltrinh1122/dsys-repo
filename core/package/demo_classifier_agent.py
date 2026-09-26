"""Hand-built demo agent for the Half 2 inference-service channel.

Pure function — zero inference inside. Round 1: emits a `classify`
prompt-request asking for the principal message to be classified.
Round 2: reads the verdict from the harness-fulfilled inference result
and returns it.

Production agents using this channel MUST sanitize prompt bodies: no body
line may begin with "@@" (spec §1 V6). This demo's event text is fixed and
safe; the obligation is the agent author's, not the parser's.
"""

from __future__ import annotations

from typing import Any


def handle(event: dict[str, Any],
           inference_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not inference_results:
        text = event.get("text", "")
        print('@@prompt-request id="pr-1" kind="classify"')
        print("Classify the following principal message as ROUTINE or URGENT.")
        print("Reply with exactly one line: verdict: ROUTINE")
        print("or: verdict: URGENT")
        print()
        print(text)
        print("@@end", flush=True)
        return {"status": "awaiting_inference", "requests": ["pr-1"]}
    verdict = "UNKNOWN"
    for line in inference_results[0].get("text", "").splitlines():
        if line.strip().lower().startswith("verdict:"):
            verdict = line.split(":", 1)[1].strip().upper()
            break
    return {"status": "complete", "verdict": verdict,
            "rounds_used": len(inference_results) + 1}
