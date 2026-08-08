import requests
import config
import json
import hashlib
from logging_setup import get_logger
from http_util import post_with_retry

logger = get_logger("wave_client")

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
        logger.info("Creating Wave transaction (%s) on %s: %s on %s...",
                    anchor_direction, anchor_account_id or "Default", description, date_str)

        if not line_items:
            logger.warning("No line items provided for '%s' on %s. Skipping.", description, date_str)
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

        # Deterministic fallback external id. Previously this used
        # datetime.now(), which changed every run and defeated idempotency —
        # re-running a day posted duplicate transactions. If no external id is
        # supplied, derive one from the transaction's content so identical
        # re-posts carry an identical id. Callers should still pass an explicit
        # external_id (see idempotency.deterministic_external_id).
        if not external_id:
            _material = json.dumps(
                {
                    "date": date_str,
                    "description": description,
                    "amount": fmt_amount,
                    "anchor": anchor_account_id,
                    "direction": anchor_direction,
                    "lines": sorted(
                        (l["accountId"], l["balance"], l["amount"]) for l in gql_lines
                    ),
                },
                sort_keys=True,
            )
            external_id = "SQ_" + hashlib.sha256(_material.encode("utf-8")).hexdigest()[:24]

        variables = {
            "input": {
                "businessId": self.business_id,
                "externalId": external_id,
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
        
        response = post_with_retry(self.url, json={"query": mutation, "variables": variables}, headers=self.headers)


        if response.status_code == 200:
            res_data = response.json()
            if 'errors' in res_data:
                 logger.error("GraphQL error posting '%s' (%s): %s",
                              description, external_id, res_data['errors'])
                 return None

            result = res_data['data']['moneyTransactionCreate']
            if result['didSucceed']:
                tx_id = result['transaction']['id']
                logger.info("Wave transaction created: %s (external_id=%s)", tx_id, external_id)
                return tx_id
            else:
                logger.error("Wave rejected transaction '%s' (%s): %s",
                             description, external_id, result['inputErrors'])
                return None
        else:
            logger.error("Wave HTTP request failed (%s) for '%s': %s",
                         response.status_code, external_id, response.text)
            return None
