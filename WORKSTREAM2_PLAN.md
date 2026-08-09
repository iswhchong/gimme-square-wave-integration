# Workstream 2 — Square Payouts → Wave

> **Status (2026-08-09):** POSTS VIA API using a SUSPENSE account. Wave's API
> can't create the "Transfer from <bank>" split, so the transfer amount posts to
> config.PAYOUT_ACCOUNTS['suspense'] (default Tee Time); Kent re-points that one
> line to "Transfer from Square - Account Receivable" and sets the actual date in
> Wave. Fees + GST post correctly (no adjustment). Modes: dry-run/prepare/approve/
> post/force-oneshot; per-payout id SQ_PAYOUT_<id>; run-daily.ps1 step 2 posts
> yesterday via force-oneshot. Verified: all 33 real payouts balance; 42 tests
> passing. LIVE: dry-run then post Jul 13, confirm Wave accepts + directions, then
> re-point the suspense line.

**Goal:** automatically record each Square **payout** (Square → bank transfer) in
Wave, clearing the "Square – Account Receivable" balance that daily sales build
up, booking Square's processing fees as an expense, and reconciling each payout's
entries against its stated amount — replacing the current manual process.

**Reuses everything Phase 1 built:** deterministic idempotent posting + append-only
ledger, structured logging/audit, HTTP timeouts/retries, validation, the
prepare→approve→post gate, and process exit codes. This is a new data source, not
a rewrite.

---

## Where payouts fit in the books

Phase 1 posts card takings into **Square – Account Receivable** (config `clearing`)
— "money Square owes us but hasn't sent." That balance only grows. A **payout** is
the event that drains it: Square sweeps the net (gross card sales − refunds − Square
fees) to the bank.

So each payout should, in Wave:
- **increase Bank** by the net amount that actually arrived (`amount_money`),
- **book Square fees** to a processing-fees **expense** account,
- **decrease Square – A/R (clearing)** by the gross released,

with `net + fees = gross` so it balances. The exact Wave `balance`
(INCREASE/DECREASE) directions and whether an asset anchor workaround is needed
will be confirmed against Wave with a `--dry-run` first, exactly as we did for the
Phase 1 transfers — not assumed.

---

## Date & title (per Kent, 2026-08-09)

- Wave transaction **title**: `"<Date> - Square Transfer"`.
- `<Date>` = the **Square transfer date** (when Square initiated the payout,
  `payout.created_at` in America/Edmonton), **not** the bank settlement date.
- The actual cash-settlement date in the bank may differ (e.g. Square transfer
  Aug 5, settles Aug 6). **Kent adjusts the "actual" date manually in Wave.** Our
  job is only to get the **Square transfer date** right.
- Wave transaction `date` field = the Square transfer date too (Kent edits it if
  he wants it on the settlement date).
- Date format in the title: assumed `"MMM D"` (e.g. `"Aug 5 - Square Transfer"`)
  to match the Phase 1 descriptions — **please confirm this matches your existing
  manual entries** (e.g. is it "Aug 5", "Aug 05", or "2026-08-05"?). Trivial to change.

---

## Data model (Square Payouts API)

- `GET /v2/payouts` — list payouts for the location in a date range
  (`begin_time`/`end_time` on `created_at`), paginated by `cursor`. Fields we use:
  `id`, `status` (SENT/PAID/FAILED), `amount_money` (net to bank), `created_at`
  (transfer date), `arrival_date` (expected settlement — informational only),
  `destination`, `version`.
- `GET /v2/payouts/{id}/payout-entries` — the itemized entries that make up the
  payout, paginated. Types include `CHARGE`, `REFUND`, `FEE`, `DEPOSIT_FEE`
  (and possibly `DISPUTE`/`ADJUSTMENT`). Each has `gross_amount_money`,
  `fee_amount_money`, `net_amount_money`, and `type_*_details` linking to the
  payment/refund id.
- We compute per payout: `gross = Σ entry.gross`, `fees = Σ entry.fee`,
  `net = Σ entry.net`, and **assert `net == amount_money`** (the reconciliation
  totals check). The `type_*_details` payment ids are what let us later tie
  entries back to Phase-1-posted sales (deeper reconciliation, if wanted).

---

## Idempotency

Unlike daily sales (an aggregate with no single source id), each payout has a
stable unique `id`. So:
- external id = `SQ_PAYOUT_<payout_id>` (deterministic, one per payout).
- Same ledger (`logs/posted_ledger.jsonl`), same content-hash "changed since post"
  guard, same `--replace` semantics as Phase 1.

---

## Reconciliation depth (default: record + totals check)

For each payout: post the Wave transfer and verify the entries reconcile
(`Σ net == amount_money`, and `gross = net + fees`); log/flag any mismatch and
refuse to post a payout that doesn't reconcile (a ReconciliationError, same as the
sales rounding guard). Full entry-to-sale matching is a later option, not this pass.

---

## Edge cases to handle explicitly

- **FAILED payouts** — do not post; log and skip (money never moved).
- **Net-debit payout** (`amount_money` ≤ 0, fees/refunds exceed sales) — post as a
  bank **withdrawal**; flag for review.
- **Entry types beyond CHARGE/REFUND/FEE** (DISPUTE, ADJUSTMENT, DEPOSIT_FEE) —
  fold into the gross/fees math correctly; log any unrecognized type instead of
  silently dropping it.
- **Empty range / no payouts** — benign, exit 0 (like a no-orders day).
- **A payout still SENT (not yet PAID)** — decide whether to post on SENT or wait
  for PAID; default: post on SENT (Square rarely reverses), flag if it later FAILS.

---

## Config needed from Kent (Wave account IDs)

- **Bank account** the payouts land in (Wave asset account id).
- **Square processing fees** expense account (Wave account id). If one doesn't
  exist yet, create it in Wave.
- Confirm the **clearing** account (`config.ACCOUNT_MAPPING['clearing']`,
  "Square – Account Receivable") is the right one to draw down.

---

## Sub-workstreams (each its own reviewable commit)

1. **Capture + fixtures** — `fetch_payouts.py` (done, for Kent to run) → real
   payout+entries JSON → sanitized fixtures.
2. **Payout client** — `PayoutClient` (list payouts + entries, timeouts/retries,
   Edmonton day boundaries), mirroring `square_client.py`.
3. **Payout processor** — map a payout(+entries) → a Wave payload
   (bank/clearing/fees), with the totals reconciliation.
4. **Entrypoint** — `payouts.py` (or extend `main.py`) supporting
   list/dry-run/prepare/approve/post + force-oneshot, reusing the gate, ledger,
   logging, and exit codes; extend `run-daily.ps1` to also sweep payouts.
5. **Tests** — offline, against captured fixtures (normal, refund day, fee-only,
   failed, net-debit).
6. **Live validation** — dry-run a real payout, then prepare/approve/post one,
   reconcile in Wave.

---

## What I need from Kent to proceed past step 1

1. Run `fetch_payouts.py` (see below) for ~1–2 weeks and send back the JSON dump
   (review/sanitize first — it contains amounts and a masked destination).
2. The two Wave account ids (bank, fees expense) above.
3. Confirm the title date format.

With the dump in hand I'll build steps 2–5 against the real API shapes and deliver
them the same way as Phase 1.
