"""Harness-side inference-service channel (Half 2).

A contained agent that needs inference prints prompt-request blocks to its
stdout (spec: doc/half2-inference-service-spec.md §1). The harness — outside
containment, where inference is allowed — accommodates each request by
invoking the `claude` CLI (spec §2), stages the response as an
inference-result event, and re-drives the agent, until the agent emits no
requests or a bound is hit.

Load-bearing separations (design: doc/half2-inference-service-design.md):
  - the agent NEVER invokes `claude` (containment refuses child processes);
    its only inference surface is the prompt-request text;
  - the harness never infers unasked: every `claude` invocation traces to a
    prompt-request the agent printed;
  - `claude`'s stdout is inert data: it is never scanned for prompt-request
    markers (only the contained agent's fresh stdout is parsed);
  - zero inference inside the contained agent (J0); the agent's transition
    stays a pure function of (event, inference_results).

Refusals are fail-closed and enumerated in spec §6.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any

from .author_contain import DEFAULT_TIMEOUT_S, run_contained

# ---------------------------------------------------------------------------
# Bounds (spec §8 — normative values)
# ---------------------------------------------------------------------------

INFER_KINDS = ("propose", "classify", "triage", "assess", "challenge", "goal")
MAX_PROMPT_BYTES = 65536
MAX_REQUESTS_PER_ROUND = 8
DEFAULT_MAX_ROUNDS = 3
DEFAULT_CLAUDE_TIMEOUT_S = 120


class ProtocolViolation(Exception):
    """Malformed prompt-request text (spec §1 V1..V7)."""


class ClaudeFailure(Exception):
    """The `claude` CLI failed, timed out, or is missing (spec §6 R4/R5)."""


@dataclass(frozen=True)
class PromptRequest:
    id: str
    kind: str
    prompt: str


_START_RE = re.compile(
    r'^@@prompt-request id="([A-Za-z0-9_-]{1,64})" kind="([A-Za-z0-9_]+)"$')
_END_LINE = "@@end"


def parse_prompt_requests(stdout: str) -> list[PromptRequest]:
    """Parse §1 prompt-request blocks from the contained agent's stdout.

    Text outside blocks is ignored (logs). Raises ProtocolViolation on any
    §1 violation — the caller refuses the round (fail-closed).
    """
    requests: list[PromptRequest] = []
    seen: set[str] = set()
    lines = stdout.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _START_RE.match(line)
        if line.startswith("@@prompt-request") and not m:
            raise ProtocolViolation(
                f"V3 malformed start line {i + 1}: {line[:80]!r}")
        if not m:
            i += 1
            continue
        rid, kind = m.group(1), m.group(2)
        if kind not in INFER_KINDS:
            raise ProtocolViolation(
                f"V2 unknown kind {kind!r} (request {rid!r})")
        body: list[str] = []
        j = i + 1
        closed = False
        while j < len(lines):
            if lines[j] == _END_LINE:
                closed = True
                break
            if lines[j].startswith("@@"):
                raise ProtocolViolation(
                    f"V6 reserved marker inside prompt body "
                    f"(request {rid!r}, line {j + 1})")
            body.append(lines[j])
            j += 1
        if not closed:
            raise ProtocolViolation(
                f"V1 dangling block: request {rid!r} has no @@end")
        prompt = "\n".join(body)
        if not prompt.strip():
            raise ProtocolViolation(f"V4 empty prompt (request {rid!r})")
        if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
            raise ProtocolViolation(
                f"V5 prompt exceeds {MAX_PROMPT_BYTES} bytes "
                f"(request {rid!r})")
        if rid not in seen:  # duplicate ids: first wins
            seen.add(rid)
            requests.append(PromptRequest(id=rid, kind=kind, prompt=prompt))
        i = j + 1
    if len(requests) > MAX_REQUESTS_PER_ROUND:
        raise ProtocolViolation(
            f"V7 {len(requests)} requests exceed max "
            f"{MAX_REQUESTS_PER_ROUND} per round")
    return requests


def claude_backing() -> str:
    """Identity string for the transcript: 'stub' or the binary path."""
    binpath = os.environ.get("CLAUDE_BIN", "claude")
    if os.path.basename(binpath) == "claude-stub":
        return "stub"
    return binpath


def invoke_claude(prompt: str, kind: str = "assess",
                  timeout_s: int = DEFAULT_CLAUDE_TIMEOUT_S) -> str:
    """Harness-side: run `claude --kind KIND PROMPT`; return stdout text.

    Raises ClaudeFailure on missing binary, non-zero exit, or timeout.
    The returned text is inert data (never parsed for prompt-requests).
    """
    if kind not in INFER_KINDS:
        raise ClaudeFailure(f"refusing to invoke claude: unknown kind {kind!r}")
    binpath = os.environ.get("CLAUDE_BIN", "claude")
    try:
        cp = subprocess.run(
            [binpath, "--kind", kind, prompt],
            capture_output=True, text=True, timeout=timeout_s)
    except FileNotFoundError:
        raise ClaudeFailure(f"claude binary not found: {binpath}")
    except subprocess.TimeoutExpired:
        raise ClaudeFailure(f"claude timed out after {timeout_s}s")
    if cp.returncode != 0:
        raise ClaudeFailure(
            f"claude exit={cp.returncode}: {cp.stderr[-500:]}")
    return cp.stdout


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def infer_loop(*, agent: str, event: dict[str, Any],
               max_rounds: int = DEFAULT_MAX_ROUNDS,
               claude_timeout_s: int = DEFAULT_CLAUDE_TIMEOUT_S,
               venv_dir: Any = None,
               keep_scratch: bool = True) -> dict[str, Any]:
    """Run the §3 inference loop. Returns the §5 transcript.

    outcome is 'complete' (agent_result adopted) or 'refused' (fail-closed;
    refusal_reasons set, no result adopted).
    """
    transcript: dict[str, Any] = {
        "agent": agent,
        "outcome": "refused",  # overwritten on completion
        "rounds": [],
        "claude": {"backing": claude_backing(),
                   "timeout_s": claude_timeout_s},
        "bounds": {"max_rounds": max_rounds,
                   "max_requests_per_round": MAX_REQUESTS_PER_ROUND,
                   "max_prompt_bytes": MAX_PROMPT_BYTES},
    }

    def refuse(reasons: list[str]) -> dict[str, Any]:
        transcript["refusal_reasons"] = reasons
        return transcript

    inference_results: list[dict[str, Any]] = []
    for r in range(1, max_rounds + 1):
        commission = {"mode": "infer", "agent": agent, "event": event,
                      "inference_results": inference_results}
        rec = run_contained(commission, timeout_s=DEFAULT_TIMEOUT_S,
                            venv_dir=venv_dir, keep_scratch=keep_scratch)
        if rec["outcome"] != "ok":
            return refuse([
                f"R6 contained agent {rec['outcome']}: "
                f"{rec.get('reason', rec.get('quarantine', 'no reason'))}"])
        stdout = rec["stdio"]["stdout"]
        try:
            reqs = parse_prompt_requests(stdout)
        except ProtocolViolation as e:
            return refuse([f"R1/R2/R3 prompt-request protocol: {e}"])
        round_rec: dict[str, Any] = {
            "round": r, "requests": [],
            "agent_stdout_sha256": _sha(stdout)}
        if not reqs:
            agent_result = (rec["result"] or {}).get("agent_result")
            transcript["rounds"].append(round_rec)
            transcript["outcome"] = "complete"
            transcript["result"] = agent_result
            return transcript
        if r == max_rounds:
            transcript["rounds"].append(round_rec)
            return refuse([
                f"R7 max rounds ({max_rounds}) reached with "
                f"{len(reqs)} request(s) still pending"])
        for q in reqs:
            prompt_sha = _sha(q.prompt)
            try:
                text = invoke_claude(q.prompt, q.kind,
                                     timeout_s=claude_timeout_s)
            except ClaudeFailure as e:
                transcript["rounds"].append(round_rec)
                return refuse([f"R4/R5 claude invocation failed: {e}"])
            inference_results.append({
                "request_id": q.id, "kind": q.kind,
                "prompt_sha256": prompt_sha,
                "text": text, "text_sha256": _sha(text)})
            round_rec["requests"].append({
                "request_id": q.id, "kind": q.kind,
                "prompt_sha256": prompt_sha,
                "response_sha256": _sha(text), "claude_exit": 0})
        transcript["rounds"].append(round_rec)
    return refuse([f"R7 max rounds ({max_rounds}) exhausted"])  # unreachable


__all__ = [
    "INFER_KINDS",
    "MAX_PROMPT_BYTES",
    "MAX_REQUESTS_PER_ROUND",
    "DEFAULT_MAX_ROUNDS",
    "DEFAULT_CLAUDE_TIMEOUT_S",
    "ProtocolViolation",
    "ClaudeFailure",
    "PromptRequest",
    "parse_prompt_requests",
    "claude_backing",
    "invoke_claude",
    "infer_loop",
]
