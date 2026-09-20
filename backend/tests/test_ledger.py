from fastapi.testclient import TestClient


def onboard(client: TestClient) -> tuple[dict[str, dict], dict[str, dict]]:
    response = client.post("/api/onboarding", json={})
    assert response.status_code == 200, response.text
    assets = {asset["symbol"]: asset for asset in client.get("/api/assets").json()}
    accounts = {account["name"]: account for account in client.get("/api/accounts").json()}
    return assets, accounts


def test_generic_draft_and_post_routes_are_not_public(client: TestClient) -> None:
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
    assert response.status_code == 404
    assert client.post("/api/events/not-a-public-draft/post").status_code == 404


def test_manual_events_enforce_account_asset_and_rate_invariants(client: TestClient) -> None:
    assets, accounts = onboard(client)
    income_category = next(
        category["id"]
        for category in client.get("/api/categories").json()
        if category["kind"] == "INCOME" and category["name"] == "Salary"
    )

    def post(payload: dict[str, str]) -> tuple[int, dict]:
        response = client.post("/api/events/manual", json=payload)
        return response.status_code, response.json()

    base = {
        "event_type": "SALARY",
        "occurred_at": "2026-08-01T00:00:00Z",
        "debit_account_id": accounts["Crypto Wallet"]["id"],
        "credit_account_id": accounts["Salary"]["id"],
        "asset_id": assets["USDT"]["id"],
        "quantity": "10",
        "book_amount_myr": "42.5",
        "category_id": income_category,
        "valuation_source": "receipt",
    }
    invalid_payloads = [
        {**base, "event_type": "TRANSFER"},
        {**base, "event_type": "EXPENSE", "debit_account_id": accounts["General Expense"]["id"]},
        {**base, "event_type": "ADJUSTMENT"},
        {**base, "debit_account_id": accounts["General Expense"]["id"]},
        {**base, "quantity": "0"},
        {**base, "book_amount_myr": "0"},
        {**base, "asset_id": assets["MYR"]["id"], "quantity": "10", "book_amount_myr": "9"},
        {**base, "valuation_rate": "100"},
    ]
    for payload in invalid_payloads:
        status, body = post(payload)
        assert status == 422, body
    assert client.get("/api/events").json() == []

    status, event = post(base)
    assert status == 201, event
    assert {entry["valuation_rate"] for entry in event["entries"]} == {"4.25"}
    assert {entry["valuation_source"] for entry in event["entries"]} == {"receipt"}

    status, body = post({**base, "occurred_at": "2026-08-02T00:00:00Z", "valuation_rate": "4.24"})
    assert status == 422
    assert "valuation_rate conflicts" in body["detail"]
    assert len(client.get("/api/events").json()) == 1


def test_salary_transfer_expense_and_reversal_reports(client: TestClient) -> None:
    assets, accounts = onboard(client)
    categories = {
        (category["kind"], category["name"]): category
        for category in client.get("/api/categories").json()
    }
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
            "category_id": categories[("INCOME", "Salary")]["id"],
            "valuation_rate": "4.25",
            "valuation_source": "manual receipt price",
        },
    )
    assert salary.status_code == 201, salary.text
    assert salary.json()["status"] == "POSTED"

    transfer = client.post(
        "/api/transfers",
        json={
            "occurred_at": "2026-08-02T12:00:00+08:00",
            "description": "ATM withdrawal",
            "source_account_id": accounts["Crypto Wallet"]["id"],
            "destination_account_id": accounts["Bank"]["id"],
        "asset_id": assets["USDT"]["id"],
        "sent_quantity": "100",
        "received_quantity": "100",
            "gain_loss_account_id": accounts["Realized Gain/Loss"]["id"],
        },
    )
    assert transfer.status_code == 201, transfer.text
    before_expense = client.get("/api/reports/income-expense").json()
    assert before_expense == {"income_myr": "4250", "expense_myr": "0", "net_income_myr": "4250"}

    expense = client.post(
        "/api/events/manual",
        json={
            "event_type": "EXPENSE",
            "occurred_at": "2026-08-03T12:00:00+08:00",
            "description": "Lunch",
            "category_id": categories[("EXPENSE", "Food")]["id"],
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
        "quantity": "900",
        "book_amount_myr": "3825",
    }


def test_event_search_filters_dates_and_pagination(client: TestClient) -> None:
    assets, accounts = onboard(client)
    categories = {
        category["name"]: category["id"]
        for category in client.get("/api/categories").json()
        if category["kind"] == "EXPENSE"
    }

    def manual_event(payload: dict[str, str]) -> dict:
        response = client.post("/api/events/manual", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    lunch = manual_event(
        {
            "event_type": "EXPENSE",
            "occurred_at": "2026-08-01T12:00:00+08:00",
            "description": "Lunch at cafe",
            "category_id": categories["Food"],
            "debit_account_id": accounts["General Expense"]["id"],
            "credit_account_id": accounts["Cash"]["id"],
            "asset_id": assets["MYR"]["id"],
            "quantity": "25.50",
            "book_amount_myr": "25.50",
        }
    )
    cloud = manual_event(
        {
            "event_type": "EXPENSE",
            "occurred_at": "2026-08-02T12:00:00+08:00",
            "description": "Cloud hosting",
            "category_id": categories["Subscription"],
            "debit_account_id": accounts["General Expense"]["id"],
            "credit_account_id": accounts["Cash"]["id"],
            "asset_id": assets["MYR"]["id"],
            "quantity": "55",
            "book_amount_myr": "55",
        }
    )
    transfer = manual_event(
        {
            "event_type": "ADJUSTMENT",
            "occurred_at": "2026-08-03T12:00:00+08:00",
            "description": "Move cash",
            "debit_account_id": accounts["Cash"]["id"],
            "credit_account_id": accounts["Bank"]["id"],
            "asset_id": assets["MYR"]["id"],
            "quantity": "100",
            "book_amount_myr": "100",
        }
    )

    response = client.get("/api/events/search", params={"q": "cloud"})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == cloud["id"]

    response = client.get(
        "/api/events/search",
        params={"event_type": "EXPENSE", "category_id": categories["Food"], "status": "POSTED"},
    )
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == lunch["id"]

    response = client.get("/api/events/search", params={"category_id": "uncategorized"})
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == transfer["id"]

    response = client.get(
        "/api/events/search",
        params={"from_date": "2026-08-02", "to_date": "2026-08-02"},
    )
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == cloud["id"]

    response = client.get("/api/events/search", params={"page": 2, "page_size": 1})
    assert response.json()["total"] == 3
    assert response.json()["page"] == 2
    assert response.json()["page_size"] == 1
    assert len(response.json()["items"]) == 1

    invalid = client.get(
        "/api/events/search",
        params={"from_date": "2026-08-03", "to_date": "2026-08-01"},
    )
    assert invalid.status_code == 422
    assert "from_date must be on or before to_date" in invalid.json()["detail"]

    assert isinstance(client.get("/api/events").json(), list)
