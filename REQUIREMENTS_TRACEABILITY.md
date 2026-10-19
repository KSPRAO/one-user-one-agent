# Assignment requirements traceability

This matrix describes the implemented baseline and where it can be inspected. It is intentionally candid: it does not claim production-scale guarantees that a single-process offline replay cannot prove.

| Requirement | Implementation / evidence | Status |
|---|---|---|
| One agent owns one active goal per viewer | `src/agent.py` maintains active goal state and reuses it until success/expiry; `sample_run/viewer_state/` | Implemented in replay process |
| Facts with provenance/freshness and conflict resolution | Decision `evidence`, `dialect.conflicts`, and per-viewer `facts`; latest profile `updated_at`, event-based subscription/opt-out overrides | Implemented; fact store is compact rather than a full event-sourced database |
| Measurable eligible goal and deadline | `ViewerAgent.goal`; G10 is rejected because it has no success event; G07/G08 have target-title constraints | Implemented for the supplied goal rules, with assumptions documented |
| Intervention or explicit no-action | Home-page, push, WhatsApp action or `NONE` with reason in `decisions.jsonl` | Implemented in offline replay/mock mode; no live provider calls |
| Home-page dialect, availability, row limits, slug uniqueness | `page()` plus independent checks in `process()`; simulator independently validates pages | Implemented for published rows; simulator is the second validation layer |
| Consent, quiet hours and one message/day | Independent message verifier, IST deferral to 08:00, opt-out override and combined push/WhatsApp daily cap | Implemented for generated actions and tested in replay; real provider delivery is not implemented |
| Holdout users get no actions | Gate before action creation; `tests/test_agent.py` | Implemented |
| Duplicate and stale trigger handling | Event ID idempotency and 10-minute staleness gate; tests | Implemented for supplied replay semantics |
| Fault handling | Supplied model faults are recorded; deterministic no-model path avoids external provider failure; tests | Implemented as deterministic fallback, not a live LLM integration |
| Corrected goal rules | Replay control event updates only still-open matching goals; regression test | Implemented for supplied correction event |
| Outcome judgments | `src/reporting.py` uses goal windows and goal-specific success conditions; incomplete observation windows are inconclusive | Implemented for supported goal conditions |
| Randomized impact analysis | `pilot/pilot_outcomes.csv`, treatment vs holdout, difference and 95% Wald CI | Implemented; small-sample Wald CI has known limitations |
| Data quality audit | `src/data_audit.py`, `sample_run/data_quality_report.md/json` | Implemented |
| Latency budget | `sample_run/latency_report.json` measures local decision computation | Local compute only; does not measure a networked service's end-to-end latency |
| Runnable command and no API key | `python run_replay.py`; Python standard library only | Implemented |
| Scale to 1,000+ simultaneous events / production durability | Single-process offline replay and JSON state files | Not production-grade; documented in `KNOWN_LIMITATIONS.md` |

## Required manual submission check

Run the commands in `README.md` from a fresh clone after placing the authorized assignment pack in the repository root. Inspect the generated reports. Do not commit the supplied data/config/replay/pilot pack or generated viewer-level outputs to a public repository unless STAGE explicitly authorizes it. Update `AI_COLLABORATION.md` if you personally make additional corrections before submission.
