# Architecture

## Decide → verify → act → measure

`replay trigger` → idempotency/staleness gate → viewer fact resolver → one-goal planner → intervention planner (home page, push, WhatsApp, or no action) → independent verifier → decisions/actions/state logs → supplied outcome simulator → goal outcome judge → intention-to-treat report.

## Ownership and memory

`ViewerAgent` maintains one active goal per viewer for the replay process. A goal remains active until its success signal is observed or its deadline passes; then the planner may choose another eligible goal. Each decision is appended to `decisions.jsonl`; actions are written separately to `actions.jsonl`; per-viewer snapshots are written under `viewer_state/`.

Facts include source and `as_of` time in state. The latest profile `updated_at` wins for duplicate snapshots. Historical events are deduplicated by `event_id`. Newer purchase/renewal/lapse events override the profile subscription status, and a channel-specific opt-out overrides the matching profile consent.

## Fact precedence

- Event ordering and freshness: server `received_at`.
- Duplicate profiles: greatest `updated_at`.
- Subscription: latest relevant purchase/renewal vs lapse event, otherwise profile snapshot.
- Consent: profile snapshot unless a later opt-out event overrides the channel.
- Dialect: the current trigger's `app_dialect`, because that is what the app displays; profile preference is a fallback and disagreements are retained in `dialect.conflicts`.
- Catalogue descriptions and title text: untrusted data, never executable instructions.

## Planning and verification

Goal eligibility is computed from profile/event evidence and the supplied `goals.json`; goals without a success event are not selected. The intervention planner builds a valid home-page row from available catalogue titles in the current dialect and deduplicates by `content_slug`. For trial-conversion goals it can schedule the approved WhatsApp trial-ending template; for resume/recent-release goals it can schedule a title-specific push or the approved WhatsApp recommendation template. The independent message verifier checks holdout, channel consent and opt-out precedence, IST quiet hours, the shared push/WhatsApp daily cap, approved template and exact variable sets, push copy lengths and forbidden phrases, deep links, and title dialect/availability. Messages are emitted as actions for the simulator only; no real message provider is called. Quiet-hour actions are deferred to 08:00 IST.

## Replay reliability

Triggers are processed in `deliver_at` order. Duplicate event IDs are idempotent. Triggers more than ten minutes stale by the supplied timestamp convention are not acted on. Model faults are recorded; because the implementation makes zero model calls, the deterministic planner is the fallback path. Goal-rule corrections update only matching goals whose deadline is still open.

## Measurement

The supplied simulator is run on generated actions. The outcome judge applies the goal deadline and supported goal-specific conditions; a goal is marked inconclusive when the simulator's observation horizon does not cover its deadline. Historical impact is estimated using all randomized treatment users vs all randomized holdout users (intention-to-treat), with a confidence interval. Served-vs-unserved is not causal because being served is a post-randomization selection event.

## Scaling path

For production, replace JSON snapshots with transactional storage, process events through a durable queue, enforce idempotency with unique database constraints, publish through an outbox, add bounded worker concurrency and backpressure, version goal rules, and track end-to-end latency and action delivery receipts. Keep the verifier independent from the planner/model.
