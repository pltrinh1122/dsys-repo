"""Entry point: run the golden run and print the verification report."""
from .golden_run import run
from .schema import SystemState

if __name__ == "__main__":
    result = run()
    from .golden_run import build_state
    s: SystemState = build_state()
    counts = {k: len(v) for k, v in s.model_dump().items() if v}
    print("Dyad System Architecture — verification")
    print(f"entities : {sum(counts.values())} across {len(counts)} types")
    print(f"golden chain violations: {len(result['violations'])}")
    print("refusal cases:")
    for r in result["refusals"]:
        print(f"  - {r}")
    print("RESULT:", "PASS" if result["ok"] else "FAIL")
