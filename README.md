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
Use `main.py` to calculate and post daily summaries to Wave:

- **Dry Run (Calculate only, do not post)**:
  ```bash
  python main.py --date 2026-05-23 --dry-run
  ```

- **Post Daily Sales to Wave**:
  ```bash
  python main.py --date 2026-05-23
  ```

- **Post Specific Transaction Types (e.g. `sales_journal` or `transfer`)**:
  ```bash
  python main.py --date 2026-05-23 --type sales_journal
  ```

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
