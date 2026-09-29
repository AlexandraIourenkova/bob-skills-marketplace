# Probe fixtures

Hand-built from the same documented shapes as `../documented/` (IBM API Hub and IBM client code). They were not captured from a live watsonx Orchestrate instance. The probe tests also reuse the files in `../documented/`.

- `run-events.json`: GET runs/{run_id}/events answered as a JSON array of RunEvents that replays the tool steps. The spec calls the route a JSON array; the Hub prose calls it SSE. No IBM client reads it, so this shape is one of the two the probe must recognise.
- `thread-messages-thinking-only.json`: a turn whose step history holds only a `thinking` step. The steps are visible and no tool was called, so the probe reports "inconclusive, no tool called" rather than "tool metadata missing".

All ids, hosts and names are fake.
