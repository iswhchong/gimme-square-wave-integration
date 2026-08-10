# Workstream 3 — Credit-card (CIBC) spending → Wave

**Goal:** post business CIBC Credit Card charges into Wave from a downloaded
statement CSV — categorized to expense accounts, anchored on the CIBC Credit Card
liability — replacing the manual entry. Reuses the Phase 1 stack (idempotency
ledger, prepare→approve→post gate, logging, exit codes).

## Input
A CIBC statement CSV (no header): `date, merchant, charge, payment, card-last4`.
Three sub-cards all belong to the one CIBC Credit Card account.

## Row handling (one Wave money transaction each)
- **Charge** → anchor CIBC Credit Card *Withdrawal*; one expense line *Increase*.
- **Refund** (merchant credit) → anchor *Deposit*; expense line *Decrease*.
- **Card payment** ("PRE-AUTHORIZED PAYMENT") → anchor *Deposit*; a line to
  **Uncategorized Income** as a placeholder Kent re-points to "Transfer from Cash
  on Hand" (Wave's API can't create the bank→card transfer).

GST is posted **gross** (no per-transaction split), by decision.

## Categorization (derived from 186 historical Wave postings)
Keyword rules (config.CC_MERCHANT_RULES) auto-map: alcohol (liquor/brewing/
distilling/…), subscriptions (Spotify/Canva/Telsco/Wave-Payroll/Wix/Ask Benny/
Amazon Prime), advertising (Facebook/Best Version Media), Zoom→Telephone-Wireless,
Telus→Computer-Internet, Taobao→Golf Supplies, Best Buy→Office, WCB→Insurance,
Callingwood/ProServe/Food Permit→Business Licenses. Everything else (Costco/
Wholesale/Amazon/Temu/Dollar Tree/Home Depot/restaurants/unknowns) →
**Uncategorized Expense** for Kent to split manually.

## Idempotency
Per-row deterministic id `CC_<hash(date|merchant|amount|kind|occurrence)>` (the CSV
has no transaction id); identical rows in a file get distinct, stable ids.

## Files
cibc_statement.py (parse), cc_processor.py (rules + payloads), creditcard.py
(entrypoint: dry-run/prepare/approve/post/force-oneshot), config.CC_ACCOUNTS +
CC_MERCHANT_RULES, tests/test_creditcard.py. Run per statement (not daily).

## Pending
Create "Uncategorized Expense" + "Uncategorized Income" in Wave and set their ids
in config.CC_ACCOUNTS (currently TODO placeholders; the tool refuses to post until
set). Then dry-run the sample, review, post one statement, reconcile.
