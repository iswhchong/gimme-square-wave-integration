import requests
import config
import json
import datetime

def fetch_recent_transactions():
    print("\n--- Fetching Recent Wave Transactions (MoneyTransactions) ---")
    if not config.WAVE_ACCESS_TOKEN or not config.WAVE_BUSINESS_ID:
        print("Missing Credentials")
        return

    url = "https://gql.waveapps.com/graphql/public"
    headers = {
        "Authorization": f"Bearer {config.WAVE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Account-based Query
    query = """
    query ($accountId: ID!) {
      account(id: $accountId) {
        transactions(page: 1, pageSize: 20) {
          edges {
            node {
              id
              date
              description
              items {
                account { name }
                amount { value direction }
              }
            }
          }
        }
      }
    }
    """
    
    # Use the Sales Account ID from config
    sales_acct_id = config.ACCOUNT_MAPPING['sales']
    
    transactions = []
    response = requests.post(url, json={"query": query, "variables": {"accountId": sales_acct_id}}, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        if 'errors' in data:
            print("GraphQL Errors:", json.dumps(data['errors'], indent=2))
        else:
            edges = data['data']['business']['moneyTransactions']['edges']
            for edge in edges:
                transactions.append(edge['node'])
            print(f"Successfully fetched {len(transactions)} transactions.")
    else:
        print(f"HTTP Error: {response.status_code}")
        print(response.text)

    # Analyze specifically for "Sales - " pattern
    print(f"\nFiltering for 'Sales -'...")
    
    examples = {
        "square": [],
        "cash": [],
        "gift": []
    }
    
    for t in transactions:
        desc = t['description'] or ""
        if "Sales" in desc:
            if "Square" in desc:
                examples["square"].append(t)
            elif "Cash" in desc:
                examples["cash"].append(t)
            elif "Gift" in desc:
                examples["gift"].append(t)

    # Output details
    for key, tx_list in examples.items():
        print(f"\n=== Pattern: {key.upper()} (Found {len(tx_list)}) ===")
        if tx_list:
            example = tx_list[0] 
            print(f"Description: {example['description']}")
            print(f"Date: {example['date']}")
            print("Splits/Lines:")
            for item in example['items']:
                acct_name = item['account']['name']
                acct_type = item['account']['type']['name']
                amt = item['amount']['value']
                direction = item['amount']['direction']
                print(f"  - Account: {acct_name} ({acct_type}) | Amount: {amt} {direction}")

if __name__ == "__main__":
    fetch_recent_transactions()
