import requests
import config
import json
import os

def fetch_wave_accounts():
    print("\n--- Fetching Wave Accounts ---")
    if not config.WAVE_ACCESS_TOKEN or not config.WAVE_BUSINESS_ID:
        print("Skipping Wave: Missing WAVE_ACCESS_TOKEN or WAVE_BUSINESS_ID in config.py")
        return

    url = "https://gql.waveapps.com/graphql/public"
    headers = {
        "Authorization": f"Bearer {config.WAVE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # GraphQL query to get all accounts
    query = """
    query ($businessId: ID!) {
      business(id: $businessId) {
        id
        name
        accounts(page: 1, pageSize: 200) {
          edges {
            node {
              id
              name
              description
              type {
                name
                normalBalanceType
                value
              }
              subtype {
                name
                value
              }
            }
          }
        }
      }
    }
    """
    
    response = requests.post(url, json={"query": query, "variables": {"businessId": config.WAVE_BUSINESS_ID}}, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if 'errors' in data:
            print("GraphQL Errors:", data['errors'])
        else:
            accounts = data['data']['business']['accounts']['edges']
            print(f"Found {len(accounts)} accounts. Saving to 'wave_accounts.json'.")
            
            # Save to file for easy inspection
            with open("wave_accounts.json", "w") as f:
                json.dump(data, f, indent=2)
                
            # Print distinct listing for mapping
            print("\nPotential Mapping Candidates:")
            for edge in accounts:
                node = edge['node']
                acct_type = node['type']['name']
                acct_subtype = node['subtype']['name'] if node.get('subtype') else ""
                print(f"[{acct_type} - {acct_subtype}] {node['name']} (ID: {node['id']})")

    else:
        print(f"Failed to fetch Wave accounts: {response.text}")

def fetch_square_catalog():
    print("\n--- Fetching Square Catalog (Items/Categories/Taxes/Discounts) ---")
    if not config.SQUARE_ACCESS_TOKEN:
        print("Skipping Square: Missing SQUARE_ACCESS_TOKEN in config.py")
        return

    url = "https://connect.squareup.com/v2/catalog/list"
    headers = {
        "Authorization": f"Bearer {config.SQUARE_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "Square-Version": "2024-01-18"
    }
    
    # Fetch wider range of objects for mapping
    params = {
        "types": "TAX,DISCOUNT,CATEGORY,ITEM"
    }

    objects = []
    cursor = None
    
    while True:
        if cursor:
             params['cursor'] = cursor
             
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            batch_objects = data.get('objects', [])
            objects.extend(batch_objects)
            
            cursor = data.get('cursor')
            if not cursor:
                break
        else:
            print(f"Failed to fetch Square catalog: {response.text}")
            return

    print(f"Total catalog items found: {len(objects)}")
    
    # Save to file
    with open("square_catalog_full.json", "w") as f:
        json.dump({"objects": objects}, f, indent=2)

    # Print summary for user
    print("\n--- Categories ---")
    category_counts = {}
    for obj in objects:
        if obj['type'] == 'CATEGORY':
            name = obj['category_data']['name']
            print(f"[CATEGORY] {name} (ID: {obj['id']})")
            
    print("\n--- Taxes/Discounts ---")
    for obj in objects:
        if obj['type'] == 'TAX':
                print(f"[TAX] {obj['tax_data']['name']} (ID: {obj['id']})")
        elif obj['type'] == 'DISCOUNT':
                print(f"[DISCOUNT] {obj['discount_data']['name']} (ID: {obj['id']})")

if __name__ == "__main__":
    fetch_wave_accounts()
    fetch_square_catalog()
