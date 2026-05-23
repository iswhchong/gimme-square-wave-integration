import gspread
from oauth2client.service_account import ServiceAccountCredentials
import config

KEY_FILE = "service_account.json"
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def test_create():
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(KEY_FILE, SCOPE)
        client = gspread.authorize(creds)
        
        # 1. Create new sheet
        sh_name = "SquareExport_Test_Automated"
        print(f"Creating new spreadsheet: {sh_name}...")
        sh = client.create(sh_name)
        print(f"Success! Sheet ID: {sh.id}")
        
        # 2. Add tabs "Transactions" and "Items"
        print("Adding tabs...")
        sh.add_worksheet(title="Transactions", rows=100, cols=20)
        sh.add_worksheet(title="Items", rows=100, cols=20)
        
        # 3. Share with user (if email known) or print instructions
        print("\n**SUCCESS**: Service Account is working and can create sheets.")
        print(f"Please open this sheet: {sh.url}")
        print("Since I created it, I have full access.")
        print("You can verify the export works on this sheet first.")
        
        return sh.id
        
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    test_create()
