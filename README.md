# One User, One Agent — STAGE take-home

A reproducible, deterministic Python implementation of the STAGE “One User, One Agent” assignment. It uses only Python's standard library and the supplied synthetic data pack; no API key, hosted model, or external service is required. The deterministic planner is an intentional reliability/privacy trade-off, not a claim that a live LLM has been integrated.

## Requirements

- Python 3.9 or later
- No third-party packages
- Disk space for generated JSONL outputs and per-viewer state files

## Run the complete replay

From the repository root:

```bash
python run_replay.py
```

Use another deterministic simulator seed:

```bash
python run_replay.py --seed evaluator-seed
```

Run tests:

```bash
python -m unittest discover -s tests -v
```

The replay command processes triggers and control events, creates decisions/actions/per-viewer state, audits data quality, runs the supplied 14-day simulator, judges outcomes, and writes latency, impact, and final reports into `sample_run/`. Push and WhatsApp actions are simulated only; no external provider or real recipient is contacted.

## Repository map

- `data/`: historical events, profile snapshot, catalogue, episodes
- `config/`: goal rules, intervention constraints, pricing, messaging policy
- `replay/`: randomized arms, triggers, live/control events, model faults
- `pilot/`: historical randomized pilot assignment/outcomes and supplied summary
- `simulator/`: supplied outcome simulator
- `src/agent.py`: viewer facts, goal planning, home-page and messaging action selection, independent checks, replay state
- `src/reporting.py`: goal outcome judgment and randomized intention-to-treat impact report
- `src/data_audit.py`: reproducible pack-quality audit
- `tests/`: regression tests for idempotency, holdout, stale triggers, conflicts, active goals, faults, rule correction, and page constraints
- `sample_run/`: generated evidence, including decisions/actions/outcomes, viewer state, latency/data-quality/impact/final reports
- `REQUIREMENTS_TRACEABILITY.md`: assignment checklist mapped to implementation and limitations
- `SUBMISSION_CHECKLIST.md`: final packaging, documentation, and evidence checklist

## Design summary

1. Deduplicate historical events by `event_id`; process replay triggers idempotently.
2. Resolve duplicate profiles by latest `updated_at`; use server receipt time for event ordering; let newer purchase/lapse and opt-out events override stale snapshots.
3. Use the trigger's `app_dialect` as the current display dialect; retain profile conflicts in the decision.
4. Select one measurable goal, preserve the viewer's active goal until success/expiry, and skip goals without measurable success signals.
5. Choose a personalized home page, a policy-verified push/WhatsApp action, or an explicit `NONE` decision. Messaging is generated in offline replay/mock mode; no real messages are sent.
6. Independently verify holdout, dialect, availability, withdrawn titles, row size and duplicate `content_slug` before publishing.
7. Apply replay control events, including goal-rule corrections, only to still-open goals.
8. Judge outcomes only from matching signals in the goal window. If the simulator observation window does not cover the full deadline, label the result inconclusive.
9. Reanalyse the historical pilot by randomized treatment-vs-holdout assignment, regardless of whether a treatment user was served.

## Interpretation of results

- The replay is a deterministic engineering check, not a causal experiment; use the historical randomized pilot for the causal comparison.
- `decided_in_ms` measures local offline decision computation, not network/API latency.
- The source data is synthetic but is treated as private input; this project does not upload it anywhere.
- Read `KNOWN_LIMITATIONS.md` and `REQUIREMENTS_TRACEABILITY.md` before submission.

## Data-pack privacy note

The assignment's messaging policy says to treat the supplied pack as personal data and not upload it to services that retain or train on submitted content. Keep the supplied `data/`, `config/`, `replay/`, `pilot/`, and generated `sample_run/` directories local unless STAGE explicitly authorizes a destination. These paths are ignored by `.gitignore`. To run locally, place the supplied pack directories at the repository root first. A source-only checkout will not run until the authorized pack is supplied locally. Do not publish viewer-level events, profiles, replay inputs, per-viewer state, or generated event logs in a public repository.
