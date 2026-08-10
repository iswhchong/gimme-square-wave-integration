"""
Fetch ALL Wave accounts (paginated) and write wave_accounts.json.

fetch_metadata.py only requested page 1, so accounts beyond Wave's page-size cap
were dropped. This walks every page via pageInfo, so nothing is missed. Output
shape matches what the rest of the tooling expects: {data:{business:{accounts:
{edges:[...]}}}}.
"""

import json

import requests

import config

URL = "https://gql.waveapps.com/graphql/public"
QUERY = """
query ($businessId: ID!, $page: Int!, $pageSize: Int!) {
  business(id: $businessId) {
    accounts(page: $page, pageSize: $pageSize) {
      pageInfo { currentPage totalPages totalCount }
      edges {
        node {
          id
          name
          description
          type { name normalBalanceType value }
          subtype { name value }
        }
      }
    }
  }
}
"""


def main():
    if not config.WAVE_ACCESS_TOKEN or not config.WAVE_BUSINESS_ID:
        raise SystemExit("Missing WAVE_ACCESS_TOKEN / WAVE_BUSINESS_ID (.env).")
    headers = {"Authorization": f"Bearer {config.WAVE_ACCESS_TOKEN}",
               "Content-Type": "application/json"}

    all_edges, page, page_size = [], 1, 100
    while True:
        variables = {"businessId": config.WAVE_BUSINESS_ID, "page": page, "pageSize": page_size}
        resp = requests.post(URL, json={"query": QUERY, "variables": variables},
                             headers=headers, timeout=30)
        if resp.status_code != 200:
            raise SystemExit(f"HTTP {resp.status_code}: {resp.text}")
        data = resp.json()
        if "errors" in data:
            raise SystemExit(f"GraphQL errors: {json.dumps(data['errors'], indent=2)}")
        conn = data["data"]["business"]["accounts"]
        all_edges.extend(conn["edges"])
        pi = conn["pageInfo"]
        print(f"page {pi['currentPage']}/{pi['totalPages']}  (total accounts: {pi['totalCount']})")
        if pi["currentPage"] >= pi["totalPages"]:
            break
        page += 1

    out = {"data": {"business": {"accounts": {"edges": all_edges}}}}
    with open("wave_accounts.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {len(all_edges)} accounts -> wave_accounts.json")

    # Highlight the two we're after.
    for edge in all_edges:
        n = edge["node"]["name"]
        if "unmapped" in n.lower():
            print(f"  {n} (ID: {edge['node']['id']})")


if __name__ == "__main__":
    main()
