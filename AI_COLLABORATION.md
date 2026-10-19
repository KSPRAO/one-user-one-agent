# AI collaboration log

AI assistance was used to interpret the assignment, scaffold the deterministic Python implementation, review edge cases, and draft documentation. The implementation was kept offline: no viewer-level synthetic data was sent to a hosted model or external service.

## Corrections made during review

1. **Rejected served-vs-unserved as causal evidence.** The historical pilot is recomputed from randomized treatment and holdout assignments, regardless of whether a treatment user received an intervention.
2. **Added persistent active-goal semantics.** A viewer's active goal keeps its original start time and deadline until the goal-specific success condition is met or it expires; it is not replaced on every app open.
3. **Tightened outcome attribution.** G03 checks a later IST calendar day; G04/G05 require a non-trial purchase; G07/G08 constrain title IDs; G09 requires plays on three distinct IST days; goals with incomplete observation windows are inconclusive.
4. **Added data-quality audit and requirement traceability.** Duplicate IDs, duplicate profile rows, content variants, stale triggers, and randomized-arm counts are recorded in generated reports.
5. **Used a deterministic provider boundary rather than an external LLM.** Injected model-fault records are captured and the rule-based fallback remains available without an API key or network dependency.
6. **Implemented offline push and WhatsApp actions.** Added approved WhatsApp templates, pricing-backed trial messaging, title-backed push copy, consent/opt-out checks, quiet-hour deferral, shared daily caps, and independent action verification. No external provider is contacted.

## Verification performed

- Ran `python -m unittest discover -s tests -v`; all thirteen tests passed, including messaging consent, quiet-hour deferral, holdout protection, shared push/WhatsApp frequency caps, and replay coverage for both channels.
- Ran the end-to-end replay and supplied outcome simulator using a fixed seed.
- Checked simulator policy diagnostics and generated latency, data-quality, outcome, and impact reports.

AI-generated suggestions were treated as proposals, not evidence. The candidate should personally review this code, run the commands in `README.md` on their machine, and be prepared to explain and defend the design decisions in the technical discussion.
