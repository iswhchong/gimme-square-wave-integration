import requests
import config
import json
from datetime import datetime

class WaveClient:
    def __init__(self):
        if not config.WAVE_ACCESS_TOKEN:
            raise ValueError("Wave Access Token is missing")
        if not config.WAVE_BUSINESS_ID:
            raise ValueError("Wave Business ID is missing")
            
        self.url = "https://gql.waveapps.com/graphql/public"
        self.headers = {
            "Authorization": f"Bearer {config.WAVE_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        self.business_id = config.WAVE_BUSINESS_ID

    def create_transaction(self, date_str, description, amount, line_items, external_id=None, anchor_direction="DEPOSIT", anchor_account_id=None):
        """
        Create a money transaction.
        :param anchor_direction: 'DEPOSIT' or 'WITHDRAWAL'. 
        :param anchor_account_id: ID of the anchor account. Defaults to Clearing Account if None.
        """
        # ... (logging)
        print(f"Creating Wave transaction ({anchor_direction}) on {anchor_account_id or 'Default'}: {description} on {date_str}...")
        
        if not line_items:
            print("No line items provided. Skipping.")
            return None

        # Determine Anchor Account from config (Clearing Account) if not provided
        if not anchor_account_id:
            anchor_account_id = config.ACCOUNT_MAPPING['clearing']
        
        # ... (mutation string remains same)
        mutation = """
        mutation ($input: MoneyTransactionCreateInput!) {
          moneyTransactionCreate(input: $input) {
            didSucceed
            inputErrors {
              code
              message
              path
            }
            transaction {
              id
            }
          }
        }
        """

        # Format amount to 2 decimals
        fmt_amount = "{:.2f}".format(float(amount))
        
        gql_lines = []
        for item in line_items:
            gql_lines.append({
                "accountId": item['account_id'],
                "amount": "{:.2f}".format(float(item['amount'])), 
                "balance": item['direction'] 
            })

        variables = {
            "input": {
                "businessId": self.business_id,
                "externalId": external_id or f"SQ_TX_{date_str.replace('-','')}_{int(datetime.now().timestamp())}",
                "date": date_str,
                "description": description,
                "anchor": {
                    "accountId": anchor_account_id,
                    "amount": fmt_amount,
                    "direction": anchor_direction # 'DEPOSIT' or 'WITHDRAWAL'
                },
                "lineItems": gql_lines
            }
        }
        
        response = requests.post(self.url, json={"query": mutation, "variables": variables}, headers=self.headers)

        
        if response.status_code == 200:
            res_data = response.json()
            if 'errors' in res_data:
                 print("GraphQL Error:", res_data['errors'])
                 return None
            
            result = res_data['data']['moneyTransactionCreate']
            if result['didSucceed']:
                print(f"Success! Transaction ID: {result['transaction']['id']}")
                return result['transaction']['id']
            else:
                print("Transaction Failed:", result['inputErrors'])
                return None
        else:
            print(f"HTTP Request Failed: {response.status_code} {response.text}")
            return None
