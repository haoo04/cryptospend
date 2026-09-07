from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.recurring_expenses import advance_due_on


def onboard(client: TestClient) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
    assert client.post("/api/onboarding", json={}).status_code == 200
    assets = {item["symbol"]: item for item in client.get("/api/assets").json()}
    accounts = {item["name"]: item for item in client.get("/api/accounts").json()}
    categories = {
        item["name"]: item for item in client.get("/api/categories?kind=EXPENSE").json()
    }
    return assets, accounts, categories


def recurring_payload(
    assets: dict[str, dict], accounts: dict[str, dict], categories: dict[str, dict], **overrides: object
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Rent",
        "amount_myr": "1800.50",
        "frequency": "MONTHLY",
        "first_due_on": "2026-09-01",
        "asset_id": assets["MYR"]["id"],
        "funding_account_id": accounts["Bank"]["id"],
        "expense_account_id": accounts["General Expense"]["id"],
        "category_id": categories["Subscription"]["id"],
    }
    payload.update(overrides)
    return payload


def test_frequency_boundaries_preserve_calendar_anchor() -> None:
    assert advance_due_on("WEEKLY", date(2026, 12, 29), date(2026, 12, 29)) == date(2027, 1, 5)
    assert advance_due_on("MONTHLY", date(2027, 1, 31), date(2027, 1, 31)) == date(2027, 2, 28)
    assert advance_due_on("MONTHLY", date(2027, 2, 28), date(2027, 1, 31)) == date(2027, 3, 31)
    assert advance_due_on("MONTHLY", date(2028, 1, 31), date(2028, 1, 31)) == date(2028, 2, 29)
    assert advance_due_on("YEARLY", date(2028, 2, 29), date(2028, 2, 29)) == date(2029, 2, 28)
    assert advance_due_on("YEARLY", date(2031, 2, 28), date(2028, 2, 29)) == date(2032, 2, 29)


def test_recurring_expense_list_summary_and_validation(client: TestClient) -> None:
    assets, accounts, categories = onboard(client)
    created = []
    for frequency, amount, due_on in (
        ("WEEKLY", "10", "2026-09-08"),
        ("MONTHLY", "100", "2026-10-01"),
        ("YEARLY", "12", "2027-01-01"),
    ):
        response = client.post(
            "/api/recurring-expenses",
            json=recurring_payload(
                assets,
                accounts,
                categories,
                name=frequency,
                amount_myr=amount,
                frequency=frequency,
                first_due_on=due_on,
            ),
        )
        assert response.status_code == 201, response.text
        created.append(response.json())

    body = client.get("/api/recurring-expenses").json()
    assert body["summary"] == {
        "active_count": 3,
        "overdue_count": 0,
        "weekly_total_myr": "10",
        "monthly_total_myr": "100",
        "yearly_total_myr": "12",
        "annualized_myr": "1732",
    }
    assert [item["frequency"] for item in body["items"]] == ["WEEKLY", "MONTHLY", "YEARLY"]
    assert created[0]["annualized_amount_myr"] == "520"

    invalid_asset = client.post(
        "/api/recurring-expenses",
        json=recurring_payload(assets, accounts, categories, asset_id=assets["USDT"]["id"]),
    )
    assert invalid_asset.status_code == 422
    invalid_account = client.post(
        "/api/recurring-expenses",
        json=recurring_payload(
            assets,
            accounts,
            categories,
            funding_account_id=accounts["Salary"]["id"],
        ),
    )
    assert invalid_account.status_code == 422
    invalid_category = client.post(
        "/api/recurring-expenses",
        json=recurring_payload(
            assets,
            accounts,
            categories,
            category_id=next(
                item["id"]
                for item in client.get("/api/categories?include_inactive=true").json()
                if item["kind"] == "INCOME"
            ),
        ),
    )
    assert invalid_category.status_code == 422


def test_record_skip_stale_requests_and_reversal(client: TestClient) -> None:
    assets, accounts, categories = onboard(client)
    due_on = (date.fromisoformat(client.get("/api/recurring-expenses").json()["as_of"]) - timedelta(days=2)).isoformat()
    created = client.post(
        "/api/recurring-expenses",
        json=recurring_payload(assets, accounts, categories, amount_myr="25", first_due_on=due_on),
    )
    assert created.status_code == 201, created.text
    expense_id = created.json()["id"]
    before = client.get("/api/reports/summary").json()

    recorded = client.post(
        f"/api/recurring-expenses/{expense_id}/record",
        json={"due_on": due_on, "occurred_at": "2026-09-06T09:30:00+08:00"},
    )
    assert recorded.status_code == 201, recorded.text
    body = recorded.json()
    assert body["occurrence"]["action"] == "RECORDED"
    assert body["occurrence"]["event_status"] == "POSTED"
    event = client.get(f"/api/events/{body['occurrence']['event_id']}").json()
    assert event["source"] == "RECURRING_EXPENSE"
    assert event["external_id"] == f"recurring-expense:{expense_id}:{due_on}"
    assert event["description"] == "Rent"
    assert all(entry["asset_id"] == assets["MYR"]["id"] for entry in event["entries"])
    assert client.get("/api/reports/summary").json()["expense_myr"] != before["expense_myr"]
    assert client.post(
        f"/api/recurring-expenses/{expense_id}/record",
        json={"due_on": due_on, "occurred_at": "2026-09-06T09:30:00+08:00"},
    ).status_code == 409

    reversed_event = client.post(
        f"/api/events/{body['occurrence']['event_id']}/reverse", json={"reason": "entered in error"}
    )
    assert reversed_event.status_code == 201, reversed_event.text
    history = client.get(f"/api/recurring-expenses/{expense_id}/occurrences").json()
    assert history[0]["event_status"] == "REVERSED"
    next_due = body["recurring_expense"]["next_due_on"]

    weekly = client.post(
        "/api/recurring-expenses",
        json=recurring_payload(
            assets,
            accounts,
            categories,
            name="Weekly skip",
            frequency="WEEKLY",
            first_due_on=due_on,
            amount_myr="7",
        ),
    )
    assert weekly.status_code == 201, weekly.text
    weekly_id = weekly.json()["id"]
    skipped = client.post(
        f"/api/recurring-expenses/{weekly_id}/skip",
        json={"due_on": due_on, "reason": "holiday"},
    )
    assert skipped.status_code == 201, skipped.text
    assert skipped.json()["occurrence"]["event_id"] is None
    assert skipped.json()["occurrence"]["skip_reason"] == "holiday"
    assert date.fromisoformat(skipped.json()["recurring_expense"]["next_due_on"]) == (
        date.fromisoformat(due_on) + timedelta(days=7)
    )

    listed = client.get("/api/recurring-expenses").json()
    assert next(item for item in listed["items"] if item["id"] == expense_id)["next_due_on"] == next_due


def test_pause_resume_and_schedule_reset(client: TestClient) -> None:
    assets, accounts, categories = onboard(client)
    created = client.post("/api/recurring-expenses", json=recurring_payload(assets, accounts, categories))
    assert created.status_code == 201, created.text
    expense_id = created.json()["id"]
    paused = client.patch(f"/api/recurring-expenses/{expense_id}", json={"active": False})
    assert paused.status_code == 200
    assert paused.json()["due_status"] == "PAUSED"
    assert client.get("/api/recurring-expenses").json()["summary"]["active_count"] == 0
    assert client.get("/api/recurring-expenses?include_inactive=true").json()["items"][0]["active"] is False

    record_while_paused = client.post(
        f"/api/recurring-expenses/{expense_id}/record",
        json={"due_on": "2026-09-01", "occurred_at": "2026-09-01T00:00:00+08:00"},
    )
    assert record_while_paused.status_code == 409
    resumed = client.patch(f"/api/recurring-expenses/{expense_id}", json={"active": True})
    assert resumed.status_code == 200

    invalid_schedule = client.patch(f"/api/recurring-expenses/{expense_id}", json={"frequency": "YEARLY"})
    assert invalid_schedule.status_code == 422
    reset = client.patch(
        f"/api/recurring-expenses/{expense_id}",
        json={"frequency": "YEARLY", "next_due_on": "2027-01-15"},
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["anchor_on"] == "2027-01-15"
    assert reset.json()["next_due_on"] == "2027-01-15"
