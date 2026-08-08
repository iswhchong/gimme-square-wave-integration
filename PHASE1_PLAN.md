# Phase 1 — Harden Square Sales → Wave

> **Status (2026-08-08):** W1 idempotency done (PR #1). W2 structured logging &
> audit done. W3 robustness/retries + rounding-fudge fix done. W4
> prepare-then-approve gate done. W5 testing runs alongside each PR (31 offline
> tests green). Remaining: Kent's live dry-run → single real day → reconcile in Wave.

**Goal:** make the existing daily sales pipeline robust, idempotent, logged, and safe to
re-run — satisfying the charter's core principles (*prepare-then-approve*, *idempotent &
auditable*, *reconciliation-first*) before we automate anything new.

**Scope of this phase:** only the existing `main.py` sales-journal + clearing-transfer flow.
No new data sources (payouts, cards, timesheets, tips) — those are later phases.

---

## Guiding principle for every change

The pipeline handles real money and posts to live books. So every change in this phase must
be provable *without* touching live Wave data first: we validate against captured Square data
and `--dry-run` output, and only then post to Wave. Nothing in Phase 1 should make a
first-time real posting riskier than it is today.

---

## Workstream 1 — Idempotency (highest priority)

**Problem today.** `wave_client.create_transaction` builds `externalId` as
`SQ_TX_<date>_<datetime.now() timestamp>` when no explicit id is passed. Because the timestamp
changes every run, re-running a day posts *new* duplicate transactions instead of being caught
as already-posted. This directly violates "re-runs never double-post."

**Approach.**
1. Replace the timestamp-based id with a **deterministic external id per (day, payload type)**.
   The daily sales journal is an *aggregate* of all of a day's orders, so there is no single
   Square order id to key on — the stable key is the day + payload role + location, e.g.
   - sales journal → `SQ_SALESJOURNAL_<locationId>_<YYYYMMDD>`
   - cash transfer → `SQ_TRANSFER_CASH_<locationId>_<YYYYMMDD>`
   - gift-card transfer → `SQ_TRANSFER_GC_<locationId>_<YYYYMMDD>`
2. **Before posting, query Wave** for an existing transaction with that external id.
   - Not found → post as normal.
   - Found and amounts unchanged → skip, log "already posted".
   - Found and amounts changed (e.g. a late refund altered the day) → do **not** silently
     double-post. Surface it for the human (see Workstream 4). Decide policy: safest default
     is *flag and skip*, with an explicit `--replace` flag to delete+recreate.

**Open discovery item (must confirm before building):** does Wave's `moneyTransactionCreate`
enforce uniqueness on `externalId` server-side, or do we need to query first? This changes
whether idempotency is enforced by Wave or by us. I'll verify against the Wave GraphQL schema.

**Definition of done:** running the same date twice produces exactly one set of Wave
transactions, and the second run reports "already posted" for each.

---

## Workstream 2 — Structured logging & audit trail

**Problem today.** Output is `print()` statements to the console — fine for interactive use,
useless for after-the-fact audit of an automated run.

**Approach.**
- Add real logging (Python `logging`) with levels, writing both to console and a dated log file
  (e.g. `logs/run_YYYYMMDD_HHMMSS.log`).
- For every posting, log a structured audit record: date, payload type, external id, amount,
  the Square order ids that fed the aggregate, the Wave transaction id returned, and the
  outcome (posted / skipped / failed).
- Keep an append-only run ledger (JSONL) so every automated action is traceable to its Square
  source — the charter's "every automated entry is traceable to a Square source ID."

**Definition of done:** after any run, there is a durable record of exactly what was posted,
from what source data, with what result.

---

## Workstream 3 — Robustness & correctness hardening

**Problem today.** Several places assume the happy path: `requests` calls without timeouts or
retries, partial failures in the middle of a multi-payload post can leave a day half-posted,
and the rounding-adjustment logic silently edits the largest sales line.

**Approach.**
- Add timeouts + bounded retry/backoff to Square and Wave HTTP calls; fail loudly on
  non-transient errors.
- Make a day's post **all-or-nothing where possible**: validate every payload first, then post;
  if a later payload fails, log clearly which succeeded so recovery is a clean re-run (safe now
  that Workstream 1 makes re-runs idempotent).
- Turn the silent rounding fudge (`Adjusting largest sales item`) into a logged, bounded
  adjustment — flag if the discrepancy exceeds a small threshold (e.g. > $0.05) instead of
  absorbing it blindly.
- Add input validation: empty day, no tenders, negative net day (full-refund day), and the
  "Uncategorized" fallback should all be handled explicitly and logged, not guessed.

---

## Workstream 4 — Formalize the approval gate

**Problem today.** The only gate is `--dry-run`. The charter wants *prepare-then-approve* until
the pipeline is trusted.

**Approach.**
- Make the default workflow: **prepare → write a human-readable summary → require explicit
  approval → post.** Concretely, a `--prepare` step emits the summary + the exact payloads;
  posting requires a separate confirmed step (a flag or a saved approved artifact).
- The summary should be reconciliation-friendly: totals by category, tenders, tax, tips, and
  the resulting Wave entries, so a human can eyeball it against Square before approving.

---

## Workstream 5 — Testing approach (no live money)

- Capture a few **real Square API responses** for representative days (a normal day, a day with
  refunds, a full-refund day, a gift-card day) as fixtures — using existing `fetch_*`/`analyze_*`
  helpers or a dump script.
- Write unit tests for `processor.aggregate_daily_orders` and `prepare_wave_transactions` against
  those fixtures so the accounting math is pinned down and regressions are caught.
- Add a `wave_client` test that asserts payload shape and the new deterministic external id,
  using a mocked HTTP layer — **no calls to live Wave** in tests.
- Only after tests pass: run `--dry-run` against a live day, eyeball, then post one real day and
  reconcile in Wave.

---

## Suggested order of work

1. Confirm the Wave `externalId` uniqueness behaviour (discovery).
2. Build the fixture set + tests for the current behaviour (lock in today's math before changing it).
3. Idempotency (Workstream 1).
4. Logging/audit (Workstream 2).
5. Robustness (Workstream 3).
6. Approval gate (Workstream 4).
7. Live dry-run → single real day → reconcile.

Each becomes its own small, reviewable pull request rather than one big change.
