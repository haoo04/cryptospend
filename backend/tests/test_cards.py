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
            "category_id": next(
                category["id"]
                for category in client.get("/api/categories").json()
                if category["kind"] == "INCOME" and category["name"] == "Salary"
            ),
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


def settlement_payload(
    client: TestClient, assets: dict[str, dict], accounts: dict[str, dict], authorization_id: str
) -> dict:
    expense_category_id = next(
        category["id"]
        for category in client.get("/api/categories").json()
        if category["kind"] == "EXPENSE" and category["name"] == "Food"
    )
    return {
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
        "category_id": expense_category_id,
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
    }


def settle(
    client: TestClient,
    assets: dict[str, dict],
    accounts: dict[str, dict],
    authorization_id: str,
    overrides: dict | None = None,
) -> dict:
    payload = settlement_payload(client, assets, accounts, authorization_id)
    payload.update(overrides or {})
    response = client.post("/api/cards/settlements", json=payload)
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


def test_linked_settlement_validates_identity_and_final_capture_before_side_effects(client: TestClient) -> None:
    assets, accounts = setup_card_ledger(client)
    authorization = authorize(client, assets, accounts, "authorization-integrity")
    before_events = client.get("/api/events").json()

    mismatch_payload = settlement_payload(client, assets, accounts, authorization["id"])
    mismatch_payload["merchant_name"] = "Different merchant"
    mismatch = client.post("/api/cards/settlements", json=mismatch_payload)
    assert mismatch.status_code == 409
    assert "merchant_name" in mismatch.json()["detail"]

    cards = client.get("/api/cards").json()
    assert len(cards) == 1
    assert next(card for card in cards if card["id"] == authorization["id"])["status"] == "AUTHORIZED"
    assert client.get("/api/events").json() == before_events

    not_final_payload = settlement_payload(client, assets, accounts, authorization["id"])
    not_final_payload.update({"external_id": "settlement-not-final", "final_capture": False})
    not_final = client.post("/api/cards/settlements", json=not_final_payload)
    assert not_final.status_code == 409
    assert "final capture" in not_final.json()["detail"]
    assert client.get("/api/events").json() == before_events

    settlement = settle(client, assets, accounts, authorization["id"])
    duplicate_payload = settlement_payload(client, assets, accounts, authorization["id"])
    duplicate_payload["external_id"] = "settlement-duplicate"
    duplicate = client.post("/api/cards/settlements", json=duplicate_payload)
    assert duplicate.status_code == 409
    assert "cannot accept" in duplicate.json()["detail"]
    assert len([card for card in client.get("/api/cards").json() if card["transaction_type"] == "PURCHASE"]) == 1
    assert settlement["status"] == "SETTLED"


def test_settlement_refund_and_credited_cashback_are_independent(client: TestClient) -> None:
    assets, accounts = setup_card_ledger(client)
    authorization = authorize(client, assets, accounts, "authorization-settle")
    settlement = settle(client, assets, accounts, authorization["id"])
    cards = {card["id"]: card for card in client.get("/api/cards").json()}
    assert cards[authorization["id"]]["status"] == "SETTLED"
    assert cards[authorization["id"]]["hold"]["status"] == "RELEASED"
    assert settlement["provider_account_id"] == "card-main"
    assert settlement["card_account_id"] == accounts["Crypto Wallet"]["id"]
    assert settlement["merchant_country"] == "MY"
    assert settlement["expense_account_id"] == accounts["General Expense"]["id"]
    assert settlement["refunded_value_myr"] == "0"
    assert settlement["refundable_remaining_myr"] == "100"

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
            "category_id": next(
                category["id"]
                for category in client.get("/api/categories").json()
                if category["kind"] == "INCOME" and category["name"] == "Cashback"
            ),
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
        },
    )
    assert refund.status_code == 201, refund.text
    purchase = next(card for card in client.get("/api/cards").json() if card["id"] == settlement["id"])
    assert purchase["status"] == "PARTIALLY_REFUNDED"
    assert purchase["refunded_value_myr"] == "40"
    assert purchase["refundable_remaining_myr"] == "60"
    cost = client.get("/api/reports/card-costs").json()[0]
    assert cost["status"] == "PARTIALLY_REFUNDED"
    assert cost["refunded_value_myr"] == "39.95"
    assert cost["credited_cashback_value_myr"] == "4.25"
    assert cost["net_economic_cost_myr"] == "57.63"
    usd_lots = client.get(f"/api/cost-lots?asset_id={assets['USD']['id']}").json()
    assert any(lot["remaining_quantity"] == "9.4" and lot["remaining_basis_myr"] == "40" for lot in usd_lots)


def test_refund_limit_status_and_reversal_are_server_derived(client: TestClient) -> None:
    assets, accounts = setup_card_ledger(client)
    purchase = settle(client, assets, accounts, authorize(client, assets, accounts, "authorization-refunds")["id"])

    def refund_payload(external_id: str, transaction_value: str, reference_value: str) -> dict:
        return {
            "external_id": external_id,
            "refund_legs": [
                {
                    "account_id": accounts["Crypto Wallet"]["id"],
                    "asset_id": assets["USD"]["id"],
                    "quantity": transaction_value,
                    "transaction_value_myr": transaction_value,
                    "reference_value_myr": reference_value,
                }
            ],
            "refunded_at": "2026-08-08T00:00:00Z",
        }

    first = client.post(
        f"/api/cards/{purchase['id']}/refunds", json=refund_payload("refund-first", "40", "39.95")
    )
    assert first.status_code == 201, first.text
    before_overage_events = client.get("/api/events").json()
    overage = client.post(
        f"/api/cards/{purchase['id']}/refunds", json=refund_payload("refund-overage", "61", "60.95")
    )
    assert overage.status_code == 409
    assert "exceeds" in overage.json()["detail"]
    assert client.get("/api/events").json() == before_overage_events

    second = client.post(
        f"/api/cards/{purchase['id']}/refunds", json=refund_payload("refund-second", "60", "59.95")
    )
    assert second.status_code == 201, second.text
    refunded = next(card for card in client.get("/api/cards").json() if card["id"] == purchase["id"])
    assert refunded["status"] == "REFUNDED"
    assert refunded["refunded_value_myr"] == "100"
    assert refunded["refundable_remaining_myr"] == "0"

    reverse_second = client.post(
        f"/api/events/{second.json()['event_id']}/reverse", json={"reason": "second refund correction"}
    )
    assert reverse_second.status_code == 201, reverse_second.text
    partial = next(card for card in client.get("/api/cards").json() if card["id"] == purchase["id"])
    assert partial["status"] == "PARTIALLY_REFUNDED"
    assert partial["refunded_value_myr"] == "40"
    assert partial["refundable_remaining_myr"] == "60"

    reverse_first = client.post(
        f"/api/events/{first.json()['event_id']}/reverse", json={"reason": "first refund correction"}
    )
    assert reverse_first.status_code == 201, reverse_first.text
    restored = next(card for card in client.get("/api/cards").json() if card["id"] == purchase["id"])
    assert restored["status"] == "SETTLED"
    assert restored["refunded_value_myr"] == "0"
    assert restored["refundable_remaining_myr"] == "100"


def test_reward_rate_is_derived_and_legacy_mismatch_is_rejected(client: TestClient) -> None:
    assets, accounts = setup_card_ledger(client)
    purchase = settle(client, assets, accounts, authorize(client, assets, accounts, "authorization-reward")["id"])
    pending = client.post(
        f"/api/cards/{purchase['id']}/rewards",
        json={
            "reward_type": "CASHBACK",
            "account_id": accounts["Crypto Wallet"]["id"],
            "asset_id": assets["USDT"]["id"],
            "amount": "1",
            "earned_at": "2026-08-06T12:00:00Z",
        },
    )
    assert pending.status_code == 201, pending.text
    reward_id = pending.json()["id"]
    before_events = client.get("/api/events").json()
    mismatch = client.post(
        f"/api/rewards/{reward_id}/credit",
        json={
            "income_account_id": accounts["Other Income"]["id"],
            "value_myr": "4.25",
            "valuation_rate": "100",
            "valuation_source": "credited price",
            "credited_at": "2026-08-07T00:00:00Z",
        },
    )
    assert mismatch.status_code == 422
    assert "valuation_rate" in mismatch.json()["detail"]
    assert client.get("/api/events").json() == before_events

    credited = client.post(
        f"/api/rewards/{reward_id}/credit",
        json={
            "income_account_id": accounts["Other Income"]["id"],
            "category_id": next(
                category["id"]
                for category in client.get("/api/categories").json()
                if category["kind"] == "INCOME" and category["name"] == "Cashback"
            ),
            "value_myr": "4.25",
            "valuation_source": "credited price",
            "credited_at": "2026-08-07T00:00:00Z",
        },
    )
    assert credited.status_code == 200, credited.text
    reward_event = next(event for event in client.get("/api/events").json() if event["event_type"] == "REWARD")
    assert {entry["valuation_rate"] for entry in reward_event["entries"]} == {"4.25"}


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
            "category_id": next(
                category["id"]
                for category in client.get("/api/categories").json()
                if category["kind"] == "EXPENSE" and category["name"] == "Food"
            ),
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
