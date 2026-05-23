import gspread
from oauth2client.service_account import ServiceAccountCredentials

KEY_FILE = "service_account.json"
SHEET_ID = "1iQAF7kblDt9TdQMG1vPC5kfDnvCIdfiacRdnSSX4qWI"
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

try:
    creds = ServiceAccountCredentials.from_json_keyfile_name(KEY_FILE, SCOPE)
    client = gspread.authorize(creds)
    sh = client.open_by_key(SHEET_ID)
    
    ws_tx = sh.worksheet("transactions")
    print("--- Transactions Headers ---")
    headers = ws_tx.row_values(1)
    with open("headers_dump.txt", "w") as f:
        for i, h in enumerate(headers):
            line = f"Col {chr(65+i)}: '{h}'"
            print(line)
            f.write(line + "\n")

except Exception as e:
    print(e)
