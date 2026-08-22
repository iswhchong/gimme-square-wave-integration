import os
from dotenv import load_dotenv

load_dotenv()

# Authentication
SQUARE_ACCESS_TOKEN = os.getenv("SQUARE_ACCESS_TOKEN")
SQUARE_LOCATION_ID = os.getenv("SQUARE_LOCATION_ID")
WAVE_ACCESS_TOKEN = os.getenv("WAVE_ACCESS_TOKEN")
WAVE_BUSINESS_ID = os.getenv("WAVE_BUSINESS_ID")

# Wave's built-in "Uncategorized Income" account. Used as the single, easy-to-spot
# suspense/placeholder for every "needs re-pointing to a transfer" line — the
# payout transfer, the daily cash transfer, and credit-card payments all land here
# so they're trivial to find and follow up in the Wave portal.
UNCATEGORIZED_INCOME_ID = "QWNjb3VudDoxOTMzNjkxNDI3MDA3NTUwMjU2O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA=="

# Account Mapping (Wave Account IDs)
# Account Mapping (Wave Account IDs)
ACCOUNT_MAPPING = {
    # Liability/Tax Accounts
    "tax": "QWNjb3VudDoyMDQzMzM1NDgyMTI0ODUwMDY5O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",    # GST
    "tips": "QWNjb3VudDoyMzAwNTM1MDM0MDY4NjUyMTQ5O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",   # Sales - Tips
    
    # Asset Accounts (Tenders & Clearing)
    "clearing": "QWNjb3VudDoyMDgyMDk4MzkxODg5NzkzODg4O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==", # Square - Account Receivable (Initial Post)
    "cash": "QWNjb3VudDoyMDgyMDk3NDAzMDgyNjI1NzYyO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",     # Cash Register (Target for Cash Transfer)
    
    # Other Liabilities
    "gift_card": "QWNjb3VudDoyMDgyMDk2Mzk4MDg1NDQ0MjQzO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==", # Liability - Gimme Gift Card
    
    # Placeholder for the daily cash-transfer workaround. Now points to
    # Uncategorized Income (was Tee Time) so it's easy to spot and re-point to
    # "Transfer from Square - Account Receivable" in Wave.
    "transfer_suspense": UNCATEGORIZED_INCOME_ID,  # Uncategorized Income (placeholder)
    # Real Tee Time (Sales) account — kept for reference; no longer the transfer placeholder.
    "tee_time": "QWNjb3VudDoyMDgyMTAxODMxMDAwOTY5NTIzO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==", # Tee Time (Sales) - ...523
    
    # Expenses/Contra
    "discounts_default": "QWNjb3VudDoyMDgyMTAyNDgxMDg0NTM1MTk5O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==", # Discount for Friends and Family (Default)
}

# INCOME MAPPING (Square Category -> Wave Account ID)
ITEM_CATEGORY_MAPPING = {
    "Drinks": "QWNjb3VudDoxOTMzNjkxNDI3MDgzMDQ3NzMwO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==", 
    "Memberships": "QWNjb3VudDoyMDgyMTAxMzA3MTQwNzg4NDExO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",
    "No Discount Items": "WAVE_ACCOUNT_ID_DEFAULT",
    "Food & Snack": "QWNjb3VudDoyMDg1MzkzOTg0MDkxMzc4MzQxO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",
    "Club Rentals": "QWNjb3VudDoyMDgyMTAzMjA4NjExNzI5ODMyO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",
    "Alcohol": "QWNjb3VudDoyMTA4Mjg3NDQ2NDkwODYyNTU2O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",
    "Accessories": "QWNjb3VudDoyMTUzNTE4MjA5MjcyMTczMzUyO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",
    "Lessons": "QWNjb3VudDoyMDgyMTAxODMxMDAwOTY5NTIzO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",
    "Winter Hourly Rates": "QWNjb3VudDoyMDgyMTAxODMxMDAwOTY5NTIzO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",
    "Summer Hourly Rates": "QWNjb3VudDoyMDgyMTAxODMxMDAwOTY5NTIzO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",
    "Uncategorized": "QWNjb3VudDoyMDgyMTAxODMxMDAwOTY5NTIzO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA=="
}

# DISCOUNT MAPPING (Square Discount Name -> Wave Account ID)
# Square Catalog Discounts found:
# - Friend and Family Discount
# - 20% OFF Premium Membership Rate
# - 10% OFF Premium Membership Rate
DISCOUNT_MAPPING = {
    "Friends and Family": "QWNjb3VudDoyMDgyMTAyNzgxNzk5MzU0Nzg3O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",
    
    # Map both 10% and 20% membership discounts to the 'Gimme Membership' account
    "Gimme Membership": "QWNjb3VudDoyMDgyMTAyNDgxMDg0NTM1MTk5O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",
    "20% OFF Premium Membership Rate": "QWNjb3VudDoyMDgyMTAyNDgxMDg0NTM1MTk5O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",
    "10% OFF Premium Membership Rate": "QWNjb3VudDoyMDgyMTAyNDgxMDg0NTM1MTk5O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",
    "50% Off to Staff": "QWNjb3VudDoyMDgyMTAyNDgxMDg0NTM1MTk5O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",
    
    "Default": "QWNjb3VudDoyMDgyMTAyNzgxNzk5MzU0Nzg3O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA=="
}


# Mapping Logic Configuration
# If true, all discounts are aggregated to the 'discounts' account above.
AGGREGATE_DISCOUNTS = True

# Largest acceptable double-entry gap (in dollars) between Square's reported
# total collected and the sum of the computed credit lines. Gaps at or below
# this are absorbed into the largest sales line as a rounding artifact (and
# logged); larger gaps raise a ReconciliationError instead of being fudged.
ROUNDING_TOLERANCE = 0.05


# --- Workstream 2: Square Payouts -> Wave -----------------------------------
# Wave's API cannot create the "Transfer from <bank>" split a payout needs
# (bank-to-bank transfers aren't in moneyTransactionCreate). So the payout posts
# the transfer amount to a SUSPENSE account instead; Kent then re-points that one
# line to "Transfer from Square - Account Receivable" (and fixes the actual date)
# in Wave. Everything else (fees + GST) posts correctly and needs no adjustment.
PAYOUT_ACCOUNTS = {
    # Bank account the payout cash lands in (asset, anchor / Deposit).
    "bank": "QWNjb3VudDoyNTk4ODc3MzYzMDA5ODAyNjcwO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Wealthsimple
    # SUSPENSE placeholder for the "Transfer from Square - A/R" line (Kent edits
    # this to the real transfer). Uncategorized Income, so it's easy to spot and
    # follow up in Wave (shared with the daily cash transfer + card payments).
    "suspense": UNCATEGORIZED_INCOME_ID,  # Uncategorized Income — placeholder only
    # Credit-card processing fee (expense, GST-exclusive).
    "cc_fee": "QWNjb3VudDoyMDgyMTA3NDI1NzU3OTA5ODQ5O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Square Transaction Fee
    # Gift-card processing fee, NET of GST (expense).
    "gift_card_fee": "QWNjb3VudDoyMjUwMjI4MzcwNzkwOTk0NTE5O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Square - Gift Card Fee
    # Recoverable GST (Input Tax Credit) on the gift-card fee (asset).
    "itc": "QWNjb3VudDoxOTMzNjkxNDI2NzcyNjY5MjIwO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Taxes Recoverable/Refundable
}


# --- Workstream 3: CIBC Credit-card spending -> Wave -------------------------
# Posts business card charges as expenses, anchored on the CIBC Credit Card
# liability. Posts cleanly via API (credit-card = valid anchor, expenses = valid
# lines). GST is posted GROSS (no per-transaction split). Charges Kent can't map
# by merchant land in "Uncategorized Expense" for him to split; card payments land
# in "Uncategorized Income" for him to re-point to "Transfer from Cash on Hand".
CC_ACCOUNTS = {
    "card": "QWNjb3VudDoyMjA1MzI1NTAwOTM3NzIwNjgwO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # CIBC Credit Card (liability, anchor)
    "alcohol": "QWNjb3VudDoyMzAwOTUwOTIxNTE0ODk4MDIxO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Inventory Expense - Alcohol
    "subscription": "QWNjb3VudDoyMDgwMzExNTQyNjk1MzgzMTk4O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Subscription Expense
    "advertising": "QWNjb3VudDoxOTMzNjkxNDI3OTcyMjQwMjIyO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Advertising & Promotion
    "telephone_wireless": "QWNjb3VudDoxOTMzNjkxNDI3NTc3OTc1NjI2O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Telephone - Wireless (Zoom)
    "computer_internet": "QWNjb3VudDoxOTMzNjkxNDI3NDM1MzY5Mjg0O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Computer - Internet (Telus)
    "golf_supplies": "QWNjb3VudDoyMzAwNjgzNDM0Mzk5NDIxMzQ0O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Golf Supplies (Taobao)
    "office_supplies": "QWNjb3VudDoxOTMzNjkxNDI3Njg3MDI3NTM2O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Office Supplies (Best Buy)
    "insurance": "QWNjb3VudDoyMDQ0MTMxMzg5NTI3MzQ3ODc1O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Insurance Expense (WCB)
    "business_licenses": "QWNjb3VudDoxOTMzNjkxNDI3NjUzNDczMTAyO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Business Licenses & Permits
    # Wave's built-in Uncategorized accounts (ambiguous charges / card-payment placeholder).
    "uncategorized_expense": "QWNjb3VudDoxOTMzNjkxNDI3MTUwMTU2NTk4O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Uncategorized Expense
    "uncategorized_income": UNCATEGORIZED_INCOME_ID,   # Uncategorized Income
}

# Merchant keyword -> account key. First match wins (put specifics first). Matched
# case-insensitively against the raw CIBC merchant text. Anything unmatched falls
# back to 'uncategorized_expense'. Derived from 186 historical Wave postings.
CC_MERCHANT_RULES = [
    # Alcohol (liquor / breweries / distilleries)
    ("LIQUOR", "alcohol"), ("BREWING", "alcohol"), ("DISTILL", "alcohol"),
    ("SEA CHANGE", "alcohol"), ("ALLEY KAT", "alcohol"), ("SHIDDY", "alcohol"),
    ("MALTS & GRAIN", "alcohol"), ("MALT & GRAIN", "alcohol"), ("SYC BREW", "alcohol"),
    ("HENNESSY", "alcohol"), ("HENESSY", "alcohol"), ("SOJU", "alcohol"), ("SAPPORO", "alcohol"),
    # Subscriptions / software
    ("SPOTIFY", "subscription"), ("SPORTIFY", "subscription"), ("CANVA", "subscription"),
    ("TELSCO", "subscription"), ("WAVE - PAYROLL", "subscription"), ("WAVE-PAYROLL", "subscription"),
    ("PAYROLL FEE", "subscription"), ("WIX", "subscription"), ("ASK BENNY", "subscription"),
    ("AMAZON PRIME", "subscription"), ("AMZN PRIME", "subscription"),
    ("PRIME MEMBERSHIP", "subscription"), ("AMAZON CHANNEL", "subscription"),
    # Advertising
    ("FACEBK", "advertising"), ("FACEBOOK", "advertising"), ("BEST VERSION MEDIA", "advertising"),
    # Utilities / comms
    ("ZOOM", "telephone_wireless"), ("TELUS", "computer_internet"),
    # Golf / office / insurance / licenses
    ("TAOBAO", "golf_supplies"), ("BEST BUY", "office_supplies"), ("WCB", "insurance"),
    ("CALLINGWOOD REGISTRIES", "business_licenses"), ("PROSERVE", "business_licenses"),
    ("FOOD PERMIT", "business_licenses"),
]

# A col-4 (money-in) row is a CARD PAYMENT (not a merchant refund) if its
# description contains any of these.
CC_PAYMENT_KEYWORDS = ["PRE-AUTHORIZED PAYMENT", "PRE-AUTH PAYMENT", "THANK YOU"]
