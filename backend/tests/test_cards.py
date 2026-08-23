from fastapi.testclient import TestClient


def setup_card_ledger(client: TestClient) -> tuple[dict[str, dict], dict[str, dict]]:
    assert client.post("/api/onboarding", json={}).status_code == 200
    assets = {asset["symbol"]: asset for asset in client.get("/api/assets").json()}
    accounts = {account["name"]: account for account in client.get("/api/accounts").json()}
    salary = client.post(
        "/api/events/manual",
        json={
            "event_type": "SALARY",
            "occurred_at": "2026-08-01T00:00:00Z",
            "description": "Card funding salary",
            "debit_account_id": accounts["Crypto Wallet"]["id"],
            "credit_account_id": accounts["Salary"]["id"],
            "asset_id": assets["USDT"]["id"],
            "quantity": "100",
            "book_amount_myr": "425",
            "valuation_rate": "4.25",
            "valuation_source": "receipt execution",
        },
    )
    assert salary.status_code == 201, salary.text
    return assets, accounts


def authorize(client: TestClient, assets: dict[str, dict], accounts: dict[str, dict], external_id: str) -> dict:
    response = client.post(
        "/api/cards/authorizations",
        json={
            "provider": "Bybit",
            "provider_account_id": "card-main",
            "external_id": external_id,
            "card_account_id": accounts["Crypto Wallet"]["id"],
            "merchant_name": "Dinner",
            "merchant_country": "MY",
            "merchant_asset_id": assets["MYR"]["id"],
            "merchant_amount": "100",
            "billing_asset_id": assets["USD"]["id"],
            "billing_amount": "23.70",
            "merchant_value_myr": "100",
            "hold_account_id": accounts["Crypto Wallet"]["id"],
            "hold_asset_id": assets["USDT"]["id"],
            "hold_amount": "23.96",
            "hold_value_myr": "101.83",
            "authorized_at": "2026-08-05T12:00:00Z",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def settle(
    client: TestClient, assets: dict[str, dict], accounts: dict[str, dict], authorization_id: str
) -> dict:
    response = client.post(
        "/api/cards/settlements",
        json={
            "authorization_id": authorization_id,
            "provider": "Bybit",
            "provider_account_id": "card-main",
            "external_id": "settlement-1",
            "card_account_id": accounts["Crypto Wallet"]["id"],
            "merchant_name": "Dinner",
            "merchant_country": "MY",
            "merchant_asset_id": assets["MYR"]["id"],
            "merchant_amount": "100",
            "billing_asset_id": assets["USD"]["id"],
            "billing_amount": "23.70",
            "merchant_value_myr": "100",
            "reference_fx_rate": "4.25",
            "expense_account_id": accounts["General Expense"]["id"],
            "gain_loss_account_id": accounts["Realized Gain/Loss"]["id"],
            "funding_legs": [
                {
                    "account_id": accounts["Crypto Wallet"]["id"],
                    "asset_id": assets["USDT"]["id"],
                    "quantity": "23.96",
                    "transaction_value_myr": "100.89",
                    "reference_value_myr": "101.83",
                    "actual_conversion_rate": "4.21076794657763",
                }
            ],
            "fees": [
                {
                    "component_type": "CRYPTO_CONVERSION_FEE",
                    "asset_id": assets["USDT"]["id"],
                    "amount": "0.21",
                    "value_myr": "0.89",
                    "accounting_treatment": "EXPENSED",
                    "included_in_funding_amount": True,
                    "expense_account_id": accounts["Trading Fees"]["id"],
                }
            ],
            "settled_at": "2026-08-06T12:00:00Z",
            "final_capture": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_authorization_hold_changes_available_not_book_balance(client: TestClient) -> None:
    assets, accounts = setup_card_ledger(client)
    authorization = authorize(client, assets, accounts, "authorization-reverse")
    wallet = next(account for account in client.get("/api/accounts").json() if account["name"] == "Crypto Wallet")
    book = next(balance for balance in wallet["balances"] if balance["asset_symbol"] == "USDT")
    available = next(balance for balance in wallet["available_balances"] if balance["asset_symbol"] == "USDT")
    assert book["quantity"] == "100"
    assert available["quantity"] == "76.04"
    assert client.get("/api/reports/income-expense").json()["expense_myr"] == "0"

    reversed_card = client.post(f"/api/cards/{authorization['id']}/reverse-authorization")
    assert reversed_card.status_code == 200, reversed_card.text
    assert reversed_card.json()["status"] == "REVERSED"
    wallet = next(account for account in client.get("/api/accounts").json() if account["name"] == "Crypto Wallet")
    available = next(balance for balance in wallet["available_balances"] if balance["asset_symbol"] == "USDT")
    assert available["quantity"] == "100"
    assert len(client.get("/api/events").json()) == 1


def test_settlement_refund_and_credited_cashback_are_independent(client: TestClient) -> None:
    assets, accounts = setup_card_ledger(client)
    authorization = authorize(client, assets, accounts, "authorization-settle")
    settlement = settle(client, assets, accounts, authorization["id"])
    cards = {card["id"]: card for card in client.get("/api/cards").json()}
    assert cards[authorization["id"]]["status"] == "SETTLED"
    assert cards[authorization["id"]]["hold"]["status"] == "RELEASED"

    costs = client.get("/api/reports/card-costs").json()
    assert len(costs) == 1
    cost = costs[0]
    assert cost["merchant_value_myr"] == "100"
    assert cost["funding_value_myr"] == "101.83"
    assert cost["separate_fee_value_myr"] == "0"
    assert cost["gross_economic_cost_myr"] == "101.83"
    assert cost["total_leakage_myr"] == "1.83"
    assert cost["fx_deviation_myr"] == "0.725"
    assert cost["conversion_deviation_myr"] == "0.215"
    assert cost["net_economic_cost_myr"] == "101.83"
    assert cost["fees"] == [
        {
            "component_type": "CRYPTO_CONVERSION_FEE",
            "value_myr": "0.89",
            "included_in_funding_amount": True,
        }
    ]

    pending = client.post(
        f"/api/cards/{settlement['id']}/rewards",
        json={
            "reward_type": "CASHBACK",
            "account_id": accounts["Crypto Wallet"]["id"],
            "asset_id": assets["USDT"]["id"],
            "amount": "1",
            "earned_at": "2026-08-06T12:00:00Z",
        },
    )
    assert pending.status_code == 201, pending.text
    assert client.get("/api/reports/card-costs").json()[0]["net_economic_cost_myr"] == "101.83"
    credited = client.post(
        f"/api/rewards/{pending.json()['id']}/credit",
        json={
            "income_account_id": accounts["Other Income"]["id"],
            "value_myr": "4.25",
            "valuation_rate": "4.25",
            "valuation_source": "credited price",
            "credited_at": "2026-08-07T00:00:00Z",
        },
    )
    assert credited.status_code == 200, credited.text
    assert client.get("/api/reports/card-costs").json()[0]["net_economic_cost_myr"] == "97.58"

    refund = client.post(
        f"/api/cards/{settlement['id']}/refunds",
        json={
            "external_id": "refund-1",
            "refund_value_myr": "40",
            "expense_account_id": accounts["General Expense"]["id"],
            "refund_legs": [
                {
                    "account_id": accounts["Crypto Wallet"]["id"],
                    "asset_id": assets["USD"]["id"],
                    "quantity": "9.4",
                    "transaction_value_myr": "40",
                    "reference_value_myr": "39.95",
                }
            ],
            "refunded_at": "2026-08-08T00:00:00Z",
            "full_refund": False,
        },
    )
    assert refund.status_code == 201, refund.text
    cost = client.get("/api/reports/card-costs").json()[0]
    assert cost["status"] == "PARTIALLY_REFUNDED"
    assert cost["refunded_value_myr"] == "39.95"
    assert cost["credited_cashback_value_myr"] == "4.25"
    assert cost["net_economic_cost_myr"] == "57.63"
    usd_lots = client.get(f"/api/cost-lots?asset_id={assets['USD']['id']}").json()
    assert any(lot["remaining_quantity"] == "9.4" and lot["remaining_basis_myr"] == "40" for lot in usd_lots)


def test_separate_fee_is_added_once_to_economic_cost(client: TestClient) -> None:
    assets, accounts = setup_card_ledger(client)
    opening = client.post(
        "/api/events/manual",
        json={
            "event_type": "OPENING_BALANCE",
            "occurred_at": "2026-08-01T00:01:00Z",
            "debit_account_id": accounts["Crypto Wallet"]["id"],
            "credit_account_id": accounts["Opening Balances"]["id"],
            "asset_id": assets["MYR"]["id"],
            "quantity": "10",
            "book_amount_myr": "10",
        },
    )
    assert opening.status_code == 201
    response = client.post(
        "/api/cards/settlements",
        json={
            "provider": "Bitget",
            "provider_account_id": "card-two",
            "external_id": "settlement-separate-fee",
            "card_account_id": accounts["Crypto Wallet"]["id"],
            "merchant_name": "Groceries",
            "merchant_asset_id": assets["MYR"]["id"],
            "merchant_amount": "100",
            "billing_asset_id": assets["MYR"]["id"],
            "billing_amount": "100",
            "merchant_value_myr": "100",
            "expense_account_id": accounts["General Expense"]["id"],
            "gain_loss_account_id": accounts["Realized Gain/Loss"]["id"],
            "funding_legs": [
                {
                    "account_id": accounts["Crypto Wallet"]["id"],
                    "asset_id": assets["USDT"]["id"],
                    "quantity": "23.529411764705882353",
                    "transaction_value_myr": "100",
                    "reference_value_myr": "100",
                }
            ],
            "fees": [
                {
                    "component_type": "CARD_FEE",
                    "asset_id": assets["MYR"]["id"],
                    "amount": "2",
                    "value_myr": "2",
                    "accounting_treatment": "EXPENSED",
                    "included_in_funding_amount": False,
                    "expense_account_id": accounts["Trading Fees"]["id"],
                    "funding_account_id": accounts["Crypto Wallet"]["id"],
                }
            ],
            "settled_at": "2026-08-09T00:00:00Z",
        },
    )
    assert response.status_code == 201, response.text
    cost = client.get("/api/reports/card-costs").json()[0]
    assert cost["funding_value_myr"] == "100"
    assert cost["separate_fee_value_myr"] == "2"
    assert cost["gross_economic_cost_myr"] == "102"
    assert cost["total_leakage_myr"] == "2"
    assert client.get("/api/reports/fees").json()["total_myr"] == "2"
