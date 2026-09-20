import importlib.util

import pytest
from fastapi.testclient import TestClient


def onboard(client: TestClient) -> tuple[dict[str, dict], dict[str, dict], dict[tuple[str, str], dict]]:
    assert client.post("/api/onboarding", json={}).status_code == 200
    assets = {asset["symbol"]: asset for asset in client.get("/api/assets").json()}
    accounts = {account["name"]: account for account in client.get("/api/accounts").json()}
    categories = {
        (category["kind"], category["name"]): category
        for category in client.get("/api/categories").json()
    }
    return assets, accounts, categories


def manual_event(
    client: TestClient,
    *,
    event_type: str,
    occurred_at: str,
    debit_account_id: str,
    credit_account_id: str,
    asset_id: str,
    quantity: str,
    amount: str,
    category_id: str | None = None,
) -> dict:
    payload = {
        "event_type": event_type,
        "occurred_at": occurred_at,
        "debit_account_id": debit_account_id,
        "credit_account_id": credit_account_id,
        "asset_id": asset_id,
        "quantity": quantity,
        "book_amount_myr": amount,
        "valuation_source": "test valuation",
    }
    if category_id is not None:
        payload["category_id"] = category_id
    response = client.post("/api/events/manual", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_category_management_and_event_reclassification(client: TestClient) -> None:
    assets, accounts, categories = onboard(client)
    duplicate = client.post("/api/categories", json={"name": "  food  ", "kind": "EXPENSE"})
    assert duplicate.status_code == 409
    same_name_other_kind = client.post("/api/categories", json={"name": "Food", "kind": "INCOME"})
    assert same_name_other_kind.status_code == 201

    salary = manual_event(
        client,
        event_type="SALARY",
        occurred_at="2026-08-01T00:00:00Z",
        debit_account_id=accounts["Crypto Wallet"]["id"],
        credit_account_id=accounts["Salary"]["id"],
        asset_id=assets["USDT"]["id"],
        quantity="100",
        amount="425",
        category_id=categories[("INCOME", "Salary")]["id"],
    )
    missing = client.post(
        "/api/events/manual",
        json={
            "event_type": "EXPENSE",
            "occurred_at": "2026-08-02T00:00:00Z",
            "debit_account_id": accounts["General Expense"]["id"],
            "credit_account_id": accounts["Cash"]["id"],
            "asset_id": assets["MYR"]["id"],
            "quantity": "10",
            "book_amount_myr": "10",
        },
    )
    assert missing.status_code == 422
    mismatch = client.post(
        "/api/events/manual",
        json={
            "event_type": "EXPENSE",
            "occurred_at": "2026-08-02T00:00:00Z",
            "debit_account_id": accounts["General Expense"]["id"],
            "credit_account_id": accounts["Cash"]["id"],
            "asset_id": assets["MYR"]["id"],
            "quantity": "10",
            "book_amount_myr": "10",
            "category_id": categories[("INCOME", "Salary")]["id"],
        },
    )
    assert mismatch.status_code == 422

    expense = manual_event(
        client,
        event_type="EXPENSE",
        occurred_at="2026-08-02T00:00:00Z",
        debit_account_id=accounts["General Expense"]["id"],
        credit_account_id=accounts["Cash"]["id"],
        asset_id=assets["MYR"]["id"],
        quantity="10",
        amount="10",
        category_id=categories[("EXPENSE", "Food")]["id"],
    )
    before_entries = expense["entries"]
    food_id = categories[("EXPENSE", "Food")]["id"]
    disabled = client.patch(
        f"/api/categories/{food_id}",
        json={"active": False},
    )
    assert disabled.status_code == 200
    inactive = client.post(
        "/api/events/manual",
        json={
            "event_type": "EXPENSE",
            "occurred_at": "2026-08-03T00:00:00Z",
            "debit_account_id": accounts["General Expense"]["id"],
            "credit_account_id": accounts["Cash"]["id"],
            "asset_id": assets["MYR"]["id"],
            "quantity": "11",
            "book_amount_myr": "11",
            "category_id": food_id,
        },
    )
    assert inactive.status_code == 422

    grocery_id = categories[("EXPENSE", "Grocery")]["id"]
    reclassified = client.patch(f"/api/events/{expense['id']}/category", json={"category_id": grocery_id})
    assert reclassified.status_code == 200, reclassified.text
    assert reclassified.json()["category"] == "Grocery"
    assert reclassified.json()["entries"] == before_entries
    renamed = client.patch(f"/api/categories/{grocery_id}", json={"name": "Household"})
    assert renamed.status_code == 200
    assert client.get(f"/api/events/{expense['id']}").json()["category"] == "Household"
    assert client.get(f"/api/events/{salary['id']}").json()["category"] == "Salary"


def test_analytics_uses_timezone_buckets_and_uncategorized_rows(client: TestClient) -> None:
    assets, accounts, categories = onboard(client)
    salary = categories[("INCOME", "Salary")]["id"]
    food = categories[("EXPENSE", "Food")]["id"]
    manual_event(
        client,
        event_type="SALARY",
        occurred_at="2026-07-31T16:30:00Z",
        debit_account_id=accounts["Crypto Wallet"]["id"],
        credit_account_id=accounts["Salary"]["id"],
        asset_id=assets["USDT"]["id"],
        quantity="100",
        amount="425",
        category_id=salary,
    )
    manual_event(
        client,
        event_type="EXPENSE",
        occurred_at="2026-08-15T04:00:00Z",
        debit_account_id=accounts["General Expense"]["id"],
        credit_account_id=accounts["Cash"]["id"],
        asset_id=assets["MYR"]["id"],
        quantity="25",
        amount="25",
        category_id=food,
    )
    manual_event(
        client,
        event_type="ADJUSTMENT",
        occurred_at="2026-08-20T04:00:00Z",
        debit_account_id=accounts["General Expense"]["id"],
        credit_account_id=accounts["Cash"]["id"],
        asset_id=assets["MYR"]["id"],
        quantity="5",
        amount="5",
    )
    manual_event(
        client,
        event_type="EXPENSE",
        occurred_at="2026-08-31T16:30:00Z",
        debit_account_id=accounts["General Expense"]["id"],
        credit_account_id=accounts["Cash"]["id"],
        asset_id=assets["MYR"]["id"],
        quantity="10",
        amount="10",
        category_id=food,
    )

    month = client.get("/api/reports/analytics?period=month&anchor=2026-08-15")
    assert month.status_code == 200, month.text
    body = month.json()
    assert body["period_start"] == "2026-07-31T16:00:00+00:00"
    assert body["period_end"] == "2026-08-31T16:00:00+00:00"
    assert body["bucket_unit"] == "day"
    assert body["summary"] == {"income_myr": "425", "expense_myr": "30", "net_income_myr": "395"}
    assert len(body["timeline"]) == 31
    assert body["timeline"][0]["income_myr"] == "425"
    assert body["timeline"][0]["expense_myr"] == "0"
    assert body["expense_categories"] == [
        {"category_id": food, "name": "Food", "amount_myr": "25"},
        {"category_id": None, "name": "Uncategorized", "amount_myr": "5"},
    ]
    assert len(client.get("/api/reports/analytics?period=day&anchor=2026-08-15").json()["timeline"]) == 24
    assert client.get("/api/reports/analytics?period=year&anchor=2026-08-15").json()["bucket_unit"] == "month"
    assert len(client.get("/api/reports/analytics?period=all").json()["timeline"]) == 1


@pytest.mark.skipif(importlib.util.find_spec("multipart") is None, reason="python-multipart is not installed")
def test_receipt_upload_replace_download_and_delete(client: TestClient) -> None:
    assets, accounts, categories = onboard(client)
    event = manual_event(
        client,
        event_type="SALARY",
        occurred_at="2026-08-01T00:00:00Z",
        debit_account_id=accounts["Crypto Wallet"]["id"],
        credit_account_id=accounts["Salary"]["id"],
        asset_id=assets["USDT"]["id"],
        quantity="100",
        amount="425",
        category_id=categories[("INCOME", "Salary")]["id"],
    )
    jpeg = b"\xff\xd8\xff\xe0receipt"
    uploaded = client.put(
        f"/api/events/{event['id']}/receipt",
        files={"file": ("receipt.jpg", jpeg, "image/jpeg")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["byte_size"] == len(jpeg)
    detail = client.get(f"/api/events/{event['id']}").json()
    assert detail["receipt"]["original_filename"] == "receipt.jpg"
    assert "data" not in detail["receipt"]
    downloaded = client.get(f"/api/events/{event['id']}/receipt")
    assert downloaded.status_code == 200
    assert downloaded.content == jpeg
    assert downloaded.headers["content-type"] == "image/jpeg"
    assert downloaded.headers["x-content-type-options"] == "nosniff"

    png = b"\x89PNG\r\n\x1a\nreplacement"
    replaced = client.put(
        f"/api/events/{event['id']}/receipt",
        files={"file": ("replacement.png", png, "image/png")},
    )
    assert replaced.status_code == 200
    assert client.get(f"/api/events/{event['id']}/receipt").content == png
    assert client.delete(f"/api/events/{event['id']}/receipt").status_code == 204
    assert client.get(f"/api/events/{event['id']}/receipt").status_code == 404
