import pandas as pd

def inspect_excel():
    file_path = "c:/Users/iswhc/workspace/gimme-square-wave-integration/data/master_square_transactions_2026.xlsx"
    try:
        # Read sheet names
        xl = pd.ExcelFile(file_path)
        print(f"Sheet names: {xl.sheet_names}")
        
        # Read Transactions headers
        if "Transactions" in xl.sheet_names:
            df_tx = pd.read_excel(file_path, sheet_name="Transactions", nrows=0)
            print("\n--- Transactions Headers ---")
            for col in df_tx.columns:
                print(col)
                
        # Read Items headers
        if "Items" in xl.sheet_names:
            df_items = pd.read_excel(file_path, sheet_name="Items", nrows=0)
            print("\n--- Items Headers ---")
            for col in df_items.columns:
                print(col)

    except Exception as e:
        print(f"Error reading Excel: {e}")

if __name__ == "__main__":
    inspect_excel()
