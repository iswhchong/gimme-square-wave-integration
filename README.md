# Gimme Square Wave Integration

An integration utility to synchronize sales and transaction data from **Square** to **Wave Accounting**, and export transactional reporting to **Google Sheets**.

---

## Features

1. **Daily Financial Journal Entries**:
   - Fetches completed daily orders from Square.
   - Aggregates sales by Category mapping.
   - Computes Net Sales, Gross Sales, Discounts, Tips, and Taxes.
   - Automatically posts matching daily journal entries and cash/gift card clearing transfers to Wave Accounting.

2. **Google Sheets Reporting Export**:
   - Dumps transactional line items and order summaries directly into a Google Sheet.
   - Separates data into two main worksheets: `transactions` (order-level) and `items` (item-level).

---

## Setup & Installation

### 1. Clone the repository
```bash
git clone https://github.com/iswhchong/gimme-square-wave-integration.git
cd gimme-square-wave-integration
```

### 2. Set up virtual environment and install dependencies
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure credentials
Create a `.env` file in the root directory:
```env
SQUARE_ACCESS_TOKEN=your_square_access_token
SQUARE_LOCATION_ID=your_square_location_id
WAVE_ACCESS_TOKEN=your_wave_access_token
WAVE_BUSINESS_ID=your_wave_business_id
```

For Google Sheets exporting, place your Google service account credentials JSON file in the root directory and name it `service_account.json`.

---

## Usage

### Syncing Square to Wave Accounting

`main.py` follows a **prepare → approve → post** workflow so a human reviews every
day's figures before anything hits the live books. Nothing posts to Wave without
an explicit, recorded approval.

1. **Prepare** — fetch, aggregate, validate, and write a reviewable *approval
   artifact* (JSON) plus a reconciliation summary. Posts nothing. This is also
   the default action if no mode flag is given.
   ```bash
   python main.py --date 2026-05-23 --prepare
   # -> logs/approval_20260523.json  (approved: false)
   ```

2. **Approve** — after eyeballing the summary against Square, approve the
   artifact. This records who approved it and when, and binds the approval to the
   exact figures (an artifact edited afterward is refused).
   ```bash
   python main.py --approve --approval-file logs/approval_20260523.json --approver kent
   ```

3. **Post** — post the exact payloads from the approved artifact to Wave. Refused
   unless the artifact is approved and its integrity fingerprint still matches.
   Idempotent: re-running skips anything already posted (see the ledger).
   ```bash
   python main.py --post --approval-file logs/approval_20260523.json
   ```

Other options:

- **Dry run** (quick preview, no artifact, no post):
  ```bash
  python main.py --date 2026-05-23 --dry-run
  ```
- **Only one payload type** (`sales_journal` or `transfer`) when posting:
  ```bash
  python main.py --post --approval-file logs/approval_20260523.json --type sales_journal
  ```
- **Supersede changed figures** (a day already posted whose amounts changed, e.g.
  a late refund) — re-prepare/approve, then:
  ```bash
  python main.py --post --approval-file logs/approval_20260523.json --replace
  ```
- **Legacy one-shot** (fetch → prepare → post in a single step, bypassing the
  approval gate — logged loudly; use only when you know what you're doing):
  ```bash
  python main.py --date 2026-05-23 --force-oneshot
  ```

Every run writes a timestamped log to `logs/run_YYYYMMDD_HHMMSS.log`, and every
posting is appended to the audit ledger `logs/posted_ledger.jsonl` (traceable
back to the Square order ids that fed it).

### Exporting Square Transactions to Google Sheets
Use `square_to_sheets.py` to extract and sync transactions to your Google Sheet:

- **Export single date**:
  ```bash
  python square_to_sheets.py --date 2026-05-16
  ```

- **Export date range**:
  ```bash
  python square_to_sheets.py --date 2026-05-16 --end-date 2026-05-22
  ```
