"""Stubborn demo agent for the Half 2 golden battery: requests inference
every round, unconditionally. Used to prove the max-rounds bound (R7)."""


def handle(event, inference_results):
    n = len(inference_results) + 1
    print(f'@@prompt-request id="pr-{n}" kind="assess"')
    print(f"Round {n}: assess whether round {n + 1} will be needed.")
    print("@@end", flush=True)
    return {"status": "awaiting_inference", "round": n}
