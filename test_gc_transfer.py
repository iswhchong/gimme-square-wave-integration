import config
from wave_client import WaveClient
import os
from dotenv import load_dotenv

load_dotenv()

def run():
    wv = WaveClient()
    
    # Data for Jan 12 Gift Card
    date = "2026-01-12"
    amount = "72.45"
    desc = "Sales - Jan 12 - Gift Card"
    
    # Account IDs
    ar_id = config.ACCOUNT_MAPPING['clearing'] # ...388 (Asset)
    gc_id = config.ACCOUNT_MAPPING['gift_card'] # ...243 (Liability)
    
    # Logic:
    # We want to Credit AR (Decrease Asset) and Debit Gift Card (Decrease Liability).
    # Wave "Anchor" on Liability?
    # If Anchor = Liability.
    # We want to Decrease it (Debit). So Anchor Direction = WITHDRAWAL?
    # (Withdrawal usually means money leaving the account. For Liability, that's a Debit).
    
    print(f"Attempting Gift Card Transfer for ${amount}")
    print(f"Anchor: Liability ({gc_id}) -> WITHDRAWAL")
    print(f"Line: AR ({ar_id}) -> DECREASE")
    
    try:
        wv.create_transaction(
            date_str=date,
            description=desc,
            amount=float(amount),
            anchor_account_id=gc_id,
            anchor_direction="WITHDRAWAL",
            line_items=[{
                "account_id": ar_id,
                "amount": float(amount),
                "direction": "DECREASE" 
            }]
        )
        print("SUCCESS! Gift Card Transfer posted.")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    run()
