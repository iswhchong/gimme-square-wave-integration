import requests
import json
import base64
import config

def fetch():
    # Construct ID
    # User ID: 2438369449691108092
    raw_id = f"Business:{config.WAVE_BUSINESS_ID};Transaction:2438369449691108092"
    encoded_id = base64.b64encode(raw_id.encode('utf-8')).decode('utf-8')
    print(f"Constructed ID: {encoded_id}")
    
    query = """
    query ($id: ID!) {
      node(id: $id) {
        ... on MoneyTransaction {
          id
          date
          description
          amount { value }
          anchor {
            accountId
            account { name }
            amount { value }
            direction
          }
          lineItems {
            accountId
            account { name }
            amount { value }
            balance
            direction
          }
        }
      }
    }
    """
    
    url = "https://gql.waveapps.com/graphql/public"
    headers = {
        "Authorization": f"Bearer {config.WAVE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    res = requests.post(url, json={"query": query, "variables": {"id": encoded_id}}, headers=headers)
    if res.status_code != 200:
        print(res.text)
        return

    data = res.json()
    print(json.dumps(data, indent=2))

if __name__ == "__main__":
    fetch()
