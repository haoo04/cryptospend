from decimal import Decimal

from fastapi.testclient import TestClient


def setup_ledger(client: TestClient) -> tuple[dict[str, dict], dict[str, dict]]:
    assert client.post("/api/onboarding", json={}).status_code == 200
    assets = {asset["symbol"]: asset for asset in client.get("/api/assets").json()}
    accounts = {account["name"]: account for account in client.get("/api/accounts").json()}
    return assets, accounts


def acquire(
    client: TestClient,
    *,
    event_type: str,
    account_id: str,
    contra_account_id: str,
    asset_id: str,
    quantity: str,
    value_myr: str,
    occurred_at: str,
) -> dict:
    category_id = None
    if event_type in {"SALARY", "INCOME"}:
        category_id = next(
            category["id"]
            for category in client.get("/api/categories").json()
            if category["kind"] == "INCOME" and category["name"] == "Salary"
        )
    elif event_type == "EXPENSE":
        category_id = next(
            category["id"]
            for category in client.get("/api/categories").json()
            if category["kind"] == "EXPENSE" and category["name"] == "Food"
        )
    payload = {
        "event_type": event_type,
        "occurred_at": occurred_at,
        "description": f"Acquire {quantity}",
        "debit_account_id": account_id,
        "credit_account_id": contra_account_id,
        "asset_id": asset_id,
        "quantity": quantity,
        "book_amount_myr": value_myr,
    }
    if category_id:
        payload["category_id"] = category_id
    response = client.post(
        "/api/events/manual",
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_hata_sale_tracks_gross_fee_net_fifo_and_reversal(client: TestClient) -> None:
    assets, accounts = setup_ledger(client)
    acquire(
        client,
        event_type="OPENING_BALANCE",
        account_id=accounts["Crypto Wallet"]["id"],
        contra_account_id=accounts["Opening Balances"]["id"],
        asset_id=assets["ETH"]["id"],
        quantity="0.25",
        value_myr="4000",
        occurred_at="2026-08-01T00:00:00Z",
    )
    trade = client.post(
        "/api/trades",
        json={
            "occurred_at": "2026-08-10T02:00:00Z",
            "account_id": accounts["Crypto Wallet"]["id"],
            "sell_asset_id": assets["ETH"]["id"],
            "sell_quantity": "0.25",
            "buy_asset_id": assets["MYR"]["id"],
            "buy_quantity": "4241.50",
            "execution_rate": "17000",
            "gross_value_myr": "4250",
            "description": "Hata ETH/MYR sale",
            "gain_loss_account_id": accounts["Realized Gain/Loss"]["id"],
            "fee": {
                "component_type": "TRADING_FEE",
                "asset_id": assets["MYR"]["id"],
                "amount": "8.50",
                "value_myr": "8.50",
                "accounting_treatment": "REDUCE_PROCEEDS",
                "included_in_funding_amount": True,
                "expense_account_id": accounts["Trading Fees"]["id"],
            },
        },
    )
    assert trade.status_code == 201, trade.text
    body = trade.json()
    assert body["status"] == "POSTED"
    assert body["transaction_value_myr"] == "4250"
    assert body["fees"][0]["value_myr"] == "8.5"
    debit = sum(
        (Decimal(entry["book_amount_myr"]) for entry in body["entries"] if entry["direction"] == "DEBIT"),
        Decimal(),
    )
    credit = sum(
        (Decimal(entry["book_amount_myr"]) for entry in body["entries"] if entry["direction"] == "CREDIT"),
        Decimal(),
    )
    assert debit == credit == Decimal("4250")

    fee_report = client.get("/api/reports/fees").json()
    assert fee_report == {
        "total_myr": "8.5",
        "components": [{"component_type": "TRADING_FEE", "value_myr": "8.5"}],
    }
    portfolio = {position["symbol"]: position for position in client.get("/api/reports/portfolio").json()}
    assert portfolio["ETH"]["quantity"] == "0"
    assert portfolio["ETH"]["realized_gain_loss_myr"] == "250"
    assert portfolio["MYR"]["quantity"] == "4241.5"
    assert portfolio["MYR"]["cost_basis_myr"] == "4241.5"

    reversal = client.post(f"/api/events/{body['id']}/reverse", json={"reason": "test correction"})
    assert reversal.status_code == 201, reversal.text
    assert client.get("/api/reports/fees").json()["total_myr"] == "0"
    portfolio = {position["symbol"]: position for position in client.get("/api/reports/portfolio").json()}
    assert portfolio["ETH"]["quantity"] == "0.25"
    assert portfolio["ETH"]["cost_basis_myr"] == "4000"
    assert portfolio["ETH"]["realized_gain_loss_myr"] == "0"
    assert portfolio["ETH"]["market_rate_myr"] == "17000"
    assert portfolio["ETH"]["market_value_myr"] == "4250"
    assert portfolio["ETH"]["unrealized_gain_loss_myr"] == "250"


def test_myr_to_usdt_trade_validates_rate_direction_and_gross_value(client: TestClient) -> None:
    assets, accounts = setup_ledger(client)
    acquire(
        client,
        event_type="OPENING_BALANCE",
        account_id=accounts["Crypto Wallet"]["id"],
        contra_account_id=accounts["Opening Balances"]["id"],
        asset_id=assets["MYR"]["id"],
        quantity="8400",
        value_myr="8400",
        occurred_at="2026-08-01T00:00:00Z",
    )
    payload = {
        "occurred_at": "2026-08-10T02:00:00Z",
        "account_id": accounts["Crypto Wallet"]["id"],
        "sell_asset_id": assets["MYR"]["id"],
        "sell_quantity": "2800",
        "buy_asset_id": assets["USDT"]["id"],
        "buy_quantity": "690.000172500043125011",
        "execution_rate": "0.246428633035729687503928571429",
        "gross_value_myr": "2800",
        "gain_loss_account_id": accounts["Realized Gain/Loss"]["id"],
    }

    reversed_rate = client.post("/api/trades", json={**payload, "execution_rate": "4.05797"})
    assert reversed_rate.status_code == 422
    assert "USDT per MYR" in reversed_rate.json()["detail"]

    wrong_gross = client.post("/api/trades", json={**payload, "gross_value_myr": "690"})
    assert wrong_gross.status_code == 422
    assert "gross_value_myr must be 2800" in wrong_gross.json()["detail"]

    trade = client.post("/api/trades", json=payload)
    assert trade.status_code == 201, trade.text
    body = trade.json()
    assert body["transaction_value_myr"] == "2800"
    assert any(
        entry["asset_symbol"] == "USDT" and entry["quantity"] == "690.000172500043125011"
        for entry in body["entries"]
    )


def test_transfer_preserves_lots_and_only_fee_reduces_global_quantity(client: TestClient) -> None:
    assets, accounts = setup_ledger(client)
    hata = client.post(
        "/api/accounts", json={"name": "Hata", "account_type": "ASSET", "provider": "HATA"}
    ).json()
    acquire(
        client,
        event_type="SALARY",
        account_id=accounts["Crypto Wallet"]["id"],
        contra_account_id=accounts["Salary"]["id"],
        asset_id=assets["USDT"]["id"],
        quantity="1000",
        value_myr="4250",
        occurred_at="2026-08-01T00:00:00Z",
    )
    acquire(
        client,
        event_type="OPENING_BALANCE",
        account_id=accounts["Crypto Wallet"]["id"],
        contra_account_id=accounts["Opening Balances"]["id"],
        asset_id=assets["ETH"]["id"],
        quantity="0.001",
        value_myr="10",
        occurred_at="2026-08-01T00:01:00Z",
    )
    response = client.post(
        "/api/transfers",
        json={
            "occurred_at": "2026-08-02T00:00:00Z",
            "source_account_id": accounts["Crypto Wallet"]["id"],
            "destination_account_id": hata["id"],
            "asset_id": assets["USDT"]["id"],
            "sent_quantity": "1000",
            "received_quantity": "1000",
            "network": "Ethereum",
            "tx_hash": "0xabc",
            "gain_loss_account_id": accounts["Realized Gain/Loss"]["id"],
            "fee": {
                "component_type": "NETWORK_FEE",
                "asset_id": assets["ETH"]["id"],
                "amount": "0.0003",
                "value_myr": "3",
                "accounting_treatment": "EXPENSED",
                "expense_account_id": accounts["Network Fees"]["id"],
            },
        },
    )
    assert response.status_code == 201, response.text
    account_rows = {account["name"]: account for account in client.get("/api/accounts").json()}
    hata_usdt = next(balance for balance in account_rows["Hata"]["balances"] if balance["asset_symbol"] == "USDT")
    wallet_eth = next(
        balance for balance in account_rows["Crypto Wallet"]["balances"] if balance["asset_symbol"] == "ETH"
    )
    assert hata_usdt["quantity"] == "1000"
    assert hata_usdt["book_amount_myr"] == "4250"
    assert wallet_eth["quantity"] == "0.0007"
    assert wallet_eth["book_amount_myr"] == "7"
    destination_lot = next(
        lot
        for lot in client.get(f"/api/cost-lots?asset_id={assets['USDT']['id']}").json()
        if lot["account_id"] == hata["id"]
    )
    assert destination_lot["remaining_quantity"] == "1000"
    assert destination_lot["remaining_basis_myr"] == "4250"

    reversal = client.post(f"/api/events/{response.json()['id']}/reverse", json={"reason": "wrong destination"})
    assert reversal.status_code == 201, reversal.text
    account_rows = {account["name"]: account for account in client.get("/api/accounts").json()}
    wallet_usdt = next(
        balance for balance in account_rows["Crypto Wallet"]["balances"] if balance["asset_symbol"] == "USDT"
    )
    assert wallet_usdt["quantity"] == "1000"


def test_fifo_uses_oldest_lots_and_rejects_shortage(client: TestClient) -> None:
    assets, accounts = setup_ledger(client)
    for quantity, value, timestamp in [
        ("100", "425", "2026-08-01T00:00:00Z"),
        ("100", "450", "2026-08-02T00:00:00Z"),
    ]:
        acquire(
            client,
            event_type="SALARY",
            account_id=accounts["Crypto Wallet"]["id"],
            contra_account_id=accounts["Salary"]["id"],
            asset_id=assets["USDT"]["id"],
            quantity=quantity,
            value_myr=value,
            occurred_at=timestamp,
        )
    trade = client.post(
        "/api/trades",
        json={
            "occurred_at": "2026-08-03T00:00:00Z",
            "account_id": accounts["Crypto Wallet"]["id"],
            "sell_asset_id": assets["USDT"]["id"],
            "sell_quantity": "150",
            "buy_asset_id": assets["BTC"]["id"],
            "buy_quantity": "0.002",
            "execution_rate": "0.000013333333333333",
            "gross_value_myr": "900",
            "gain_loss_account_id": accounts["Realized Gain/Loss"]["id"],
        },
    )
    assert trade.status_code == 201, trade.text
    usdt_lots = client.get(f"/api/cost-lots?asset_id={assets['USDT']['id']}").json()
    assert [lot["remaining_quantity"] for lot in usdt_lots] == ["0", "50"]
    assert [lot["remaining_basis_myr"] for lot in usdt_lots] == ["0", "225"]
    portfolio = {position["symbol"]: position for position in client.get("/api/reports/portfolio").json()}
    assert portfolio["USDT"]["realized_gain_loss_myr"] == "250"

    rejected = client.post(
        "/api/trades",
        json={
            "occurred_at": "2026-08-04T00:00:00Z",
            "account_id": accounts["Crypto Wallet"]["id"],
            "sell_asset_id": assets["USDT"]["id"],
            "sell_quantity": "51",
            "buy_asset_id": assets["ETH"]["id"],
            "buy_quantity": "1",
            "execution_rate": "0.01",
            "gross_value_myr": "300",
            "gain_loss_account_id": accounts["Realized Gain/Loss"]["id"],
        },
    )
    assert rejected.status_code == 409
    assert "insufficient FIFO quantity" in rejected.json()["detail"]
