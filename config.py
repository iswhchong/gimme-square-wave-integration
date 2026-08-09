import os
from dotenv import load_dotenv

load_dotenv()

# Authentication
SQUARE_ACCESS_TOKEN = os.getenv("SQUARE_ACCESS_TOKEN")
SQUARE_LOCATION_ID = os.getenv("SQUARE_LOCATION_ID")
WAVE_ACCESS_TOKEN = os.getenv("WAVE_ACCESS_TOKEN")
WAVE_BUSINESS_ID = os.getenv("WAVE_BUSINESS_ID")

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
    
    # Placeholder for Transfer Workaround
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
    "bank": "QWNjb3VudDoxOTMzNjkxNDI2NjM4NDUxNDg4O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Cash on Hand
    # SUSPENSE placeholder for the "Transfer from Square - A/R" line (Kent edits
    # this to the real transfer). Defaults to Tee Time (income), the same
    # placeholder Phase 1 uses for its transfer workaround. Change freely.
    "suspense": ACCOUNT_MAPPING["tee_time"],  # Tee Time (income) — placeholder only
    # Credit-card processing fee (expense, GST-exclusive).
    "cc_fee": "QWNjb3VudDoyMDgyMTA3NDI1NzU3OTA5ODQ5O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Square Transaction Fee
    # Gift-card processing fee, NET of GST (expense).
    "gift_card_fee": "QWNjb3VudDoyMjUwMjI4MzcwNzkwOTk0NTE5O0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Square - Gift Card Fee
    # Recoverable GST (Input Tax Credit) on the gift-card fee (asset).
    "itc": "QWNjb3VudDoxOTMzNjkxNDI2NzcyNjY5MjIwO0J1c2luZXNzOmI4YzZhMjZjLTYxZTYtNGU5OS05M2Q3LTA4ZDk4OWE4M2U3ZA==",  # Taxes Recoverable/Refundable
}
