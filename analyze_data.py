import pandas as pd
import os

file_path = 'data/master_square_transactions_2026.xlsx'

try:
    df = pd.read_excel(file_path)
    print("Columns:")
    print(df.columns.tolist())
    print("\nFirst 5 rows:")
    print(df.head().to_string())
    print("\nData Types:")
    print(df.dtypes)
except Exception as e:
    print(f"Error reading file: {e}")
