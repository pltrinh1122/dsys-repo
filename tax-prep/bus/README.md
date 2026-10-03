# Message bus

Broadcast channel for collaborating sessions. Publishing writes one JSON
file per message under `<topic>/`; **broadcasting = commit + push**;
listening = `git pull` + read.

- Topics: `tax-prep.build` (architect → workstation: code landed),
  `tax-prep.ops` (workstation → architect/human: run reports),
  `tax-prep.review` (human → all: decisions). Free-form beyond these.
- Every message carries a unique broadcaster session-id (`from`); listeners
  tune OUT their own broadcasts.
- Listener state (subscriptions, session id, per-topic cursors) lives in
  `~/.config/taxprep/` on each machine — **never committed here**.
- This repo is public: payloads are shapes only (ids, counts, statuses).
  The bus client refuses SSN/EIN patterns outright.

See `../COLLABORATION.md` ("The bus replaces hand-carried prompts").
