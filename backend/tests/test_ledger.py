from fastapi.testclient import TestClient


def onboard(client: TestClient) -> tuple[dict[str, dict], dict[str, dict]]:
    response = client.post("/api/onboarding", json={})
    assert response.status_code == 200, response.text
    assets = {asset["symbol"]: asset for asset in client.get("/api/assets").json()}
    accounts = {account["name"]: account for account in client.get("/api/accounts").json()}
    return assets, accounts


def test_unbalanced_draft_cannot_be_posted(client: TestClient) -> None:
    assets, accounts = onboard(client)
    response = client.post(
        "/api/events/drafts",
        json={
            "event_type": "SALARY",
            "occurred_at": "2026-08-01T08:00:00+08:00",
            "entries": [
                {
                    "account_id": accounts["Crypto Wallet"]["id"],
                    "asset_id": assets["USDT"]["id"],
                    "direction": "DEBIT",
                    "quantity": "1000",
                    "book_amount_myr": "4250",
                },
                {
                    "account_id": accounts["Salary"]["id"],
                    "asset_id": assets["USDT"]["id"],
                    "direction": "CREDIT",
                    "quantity": "1000",
                    "book_amount_myr": "4249.99",
                },
            ],
        },
    )
    assert response.status_code == 201
    event_id = response.json()["id"]
    rejected = client.post(f"/api/events/{event_id}/post")
    assert rejected.status_code == 422
    assert "not balanced" in rejected.json()["detail"]


def test_salary_transfer_expense_and_reversal_reports(client: TestClient) -> None:
    assets, accounts = onboard(client)
    salary = client.post(
        "/api/events/manual",
        json={
            "event_type": "SALARY",
            "occurred_at": "2026-08-01T08:00:00+08:00",
            "description": "August salary",
            "debit_account_id": accounts["Crypto Wallet"]["id"],
            "credit_account_id": accounts["Salary"]["id"],
            "asset_id": assets["USDT"]["id"],
            "quantity": "1000.00000000",
            "book_amount_myr": "4250",
            "valuation_rate": "4.25",
            "valuation_source": "manual receipt price",
        },
    )
    assert salary.status_code == 201, salary.text
    assert salary.json()["status"] == "POSTED"

    transfer = client.post(
        "/api/events/manual",
        json={
            "event_type": "TRANSFER",
            "occurred_at": "2026-08-02T12:00:00+08:00",
            "description": "ATM withdrawal",
            "debit_account_id": accounts["Cash"]["id"],
            "credit_account_id": accounts["Bank"]["id"],
            "asset_id": assets["MYR"]["id"],
            "quantity": "100",
            "book_amount_myr": "100",
        },
    )
    assert transfer.status_code == 201
    before_expense = client.get("/api/reports/income-expense").json()
    assert before_expense == {"income_myr": "4250", "expense_myr": "0", "net_income_myr": "4250"}

    expense = client.post(
        "/api/events/manual",
        json={
            "event_type": "EXPENSE",
            "occurred_at": "2026-08-03T12:00:00+08:00",
            "description": "Lunch",
            "category": "Food",
            "debit_account_id": accounts["General Expense"]["id"],
            "credit_account_id": accounts["Cash"]["id"],
            "asset_id": assets["MYR"]["id"],
            "quantity": "25.50",
            "book_amount_myr": "25.50",
        },
    )
    assert expense.status_code == 201
    report = client.get("/api/reports/income-expense").json()
    assert report == {"income_myr": "4250", "expense_myr": "25.5", "net_income_myr": "4224.5"}

    reversal = client.post(f"/api/events/{expense.json()['id']}/reverse", json={"reason": "duplicate receipt"})
    assert reversal.status_code == 201, reversal.text
    assert reversal.json()["reverses_event_id"] == expense.json()["id"]
    assert client.get(f"/api/events/{expense.json()['id']}").json()["status"] == "REVERSED"
    report = client.get("/api/reports/income-expense").json()
    assert report["expense_myr"] == "0"
    assert client.post(f"/api/events/{expense.json()['id']}/reverse", json={"reason": "again"}).status_code == 409

    wallet = next(account for account in client.get("/api/accounts").json() if account["name"] == "Crypto Wallet")
    usdt = next(balance for balance in wallet["balances"] if balance["asset_symbol"] == "USDT")
    assert usdt == {
        "asset_id": assets["USDT"]["id"],
        "asset_symbol": "USDT",
        "quantity": "1000",
        "book_amount_myr": "4250",
    }
