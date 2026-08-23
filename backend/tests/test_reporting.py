from fastapi.testclient import TestClient


def setup_ledger(client: TestClient) -> tuple[dict[str, dict], dict[str, dict]]:
    assert client.post("/api/onboarding", json={}).status_code == 200
    assets = {asset["symbol"]: asset for asset in client.get("/api/assets").json()}
    accounts = {account["name"]: account for account in client.get("/api/accounts").json()}
    return assets, accounts


def manual_event(
    client: TestClient,
    *,
    event_type: str,
    occurred_at: str,
    debit_account_id: str,
    credit_account_id: str,
    asset_id: str,
    quantity: str,
    value_myr: str,
    description: str,
    valuation_rate: str | None = None,
) -> dict:
    response = client.post(
        "/api/events/manual",
        json={
            "event_type": event_type,
            "occurred_at": occurred_at,
            "debit_account_id": debit_account_id,
            "credit_account_id": credit_account_id,
            "asset_id": asset_id,
            "quantity": quantity,
            "book_amount_myr": value_myr,
            "description": description,
            "valuation_rate": valuation_rate,
            "valuation_source": "Payroll receipt" if valuation_rate else None,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_timezone_month_report_as_of_portfolio_and_immutable_snapshot(client: TestClient) -> None:
    assets, accounts = setup_ledger(client)
    manual_event(
        client,
        event_type="SALARY",
        occurred_at="2026-07-31T16:30:00Z",
        debit_account_id=accounts["Crypto Wallet"]["id"],
        credit_account_id=accounts["Salary"]["id"],
        asset_id=assets["USDT"]["id"],
        quantity="100",
        value_myr="425",
        description="August salary after midnight in Kuala Lumpur",
        valuation_rate="4.25",
    )
    manual_event(
        client,
        event_type="EXPENSE",
        occurred_at="2026-08-15T04:00:00Z",
        debit_account_id=accounts["General Expense"]["id"],
        credit_account_id=accounts["Cash"]["id"],
        asset_id=assets["MYR"]["id"],
        quantity="25",
        value_myr="25",
        description="Cash lunch",
    )
    manual_event(
        client,
        event_type="EXPENSE",
        occurred_at="2026-08-31T16:30:00Z",
        debit_account_id=accounts["General Expense"]["id"],
        credit_account_id=accounts["Bank"]["id"],
        asset_id=assets["MYR"]["id"],
        quantity="10",
        value_myr="10",
        description="September bank expense in Kuala Lumpur",
    )

    report = client.get("/api/reports/monthly?month=2026-08")
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["period_start"] == "2026-07-31T16:00:00+00:00"
    assert body["period_end"] == "2026-08-31T16:00:00+00:00"
    assert body["summary"] == {
        "net_worth_myr": "400",
        "income_myr": "425",
        "expense_myr": "25",
        "gross_spending_myr": "25",
        "net_spending_myr": "25",
    }
    assert body["channels"] == [
        {
            "channel_type": "CASH",
            "gross_spending_myr": "25",
            "refunds_myr": "0",
            "cashback_myr": "0",
            "net_spending_myr": "25",
            "source": "Posted ledger entries",
            "calculation_method": "gross expense - refunds - credited cashback",
            "confidence": "EXACT",
        }
    ]

    before_salary = client.get("/api/reports/portfolio?as_of=2026-07-31T16:00:00Z").json()
    assert before_salary == []
    at_month_end = {
        position["symbol"]: position
        for position in client.get("/api/reports/portfolio?as_of=2026-08-31T16:00:00Z").json()
    }
    assert at_month_end["USDT"]["quantity"] == "100"
    assert at_month_end["USDT"]["cost_basis_myr"] == "425"
    assert at_month_end["USDT"]["market_rate_source"] == "Payroll receipt"
    assert at_month_end["USDT"]["market_rate_confidence"] == "EXACT"

    snapshot = client.post("/api/reports/monthly-snapshots?month=2026-08")
    assert snapshot.status_code == 201, snapshot.text
    saved = snapshot.json()
    assert len(saved["checksum"]) == 64
    assert saved["report"] == body
    detail = client.get(f"/api/reports/monthly-snapshots/{saved['id']}").json()
    assert detail["report"] == body
    assert client.get("/api/reports/monthly-snapshots").json()[0]["id"] == saved["id"]


def test_journey_allocations_historical_portfolio_and_overallocation(client: TestClient) -> None:
    assets, accounts = setup_ledger(client)
    salary = manual_event(
        client,
        event_type="SALARY",
        occurred_at="2026-08-01T00:00:00Z",
        debit_account_id=accounts["Crypto Wallet"]["id"],
        credit_account_id=accounts["Salary"]["id"],
        asset_id=assets["USDT"]["id"],
        quantity="100",
        value_myr="425",
        description="Allocated salary",
        valuation_rate="4.25",
    )
    trade_response = client.post(
        "/api/trades",
        json={
            "occurred_at": "2026-08-02T00:00:00Z",
            "account_id": accounts["Crypto Wallet"]["id"],
            "sell_asset_id": assets["USDT"]["id"],
            "sell_quantity": "100",
            "buy_asset_id": assets["MYR"]["id"],
            "buy_quantity": "416.5",
            "execution_rate": "4.25",
            "gross_value_myr": "425",
            "description": "Hata salary sale",
            "gain_loss_account_id": accounts["Realized Gain/Loss"]["id"],
            "fee": {
                "component_type": "TRADING_FEE",
                "asset_id": assets["MYR"]["id"],
                "amount": "8.5",
                "value_myr": "8.5",
                "accounting_treatment": "REDUCE_PROCEEDS",
                "included_in_funding_amount": True,
                "expense_account_id": accounts["Trading Fees"]["id"],
            },
        },
    )
    assert trade_response.status_code == 201, trade_response.text
    trade = trade_response.json()

    journey_response = client.post(
        "/api/journeys",
        json={
            "name": "Salary to Hata MYR",
            "journey_type": "WITHDRAWAL",
            "status": "COMPLETED",
            "allocation_method": "Manual exact event allocation",
            "confidence": "EXACT",
        },
    )
    assert journey_response.status_code == 201, journey_response.text
    journey_id = journey_response.json()["id"]
    first_link = client.post(
        f"/api/journeys/{journey_id}/events",
        json={
            "event_id": salary["id"],
            "relation_type": "SOURCE",
            "sequence": 1,
            "allocations": [
                {
                    "asset_id": assets["USDT"]["id"],
                    "allocation_role": "INPUT",
                    "quantity": "100",
                    "value_myr": "425",
                    "source": "Payroll receipt and posted salary event",
                    "confidence": "EXACT",
                }
            ],
        },
    )
    assert first_link.status_code == 201, first_link.text
    final_link = client.post(
        f"/api/journeys/{journey_id}/events",
        json={
            "event_id": trade["id"],
            "relation_type": "DESTINATION",
            "sequence": 2,
            "allocations": [
                {
                    "asset_id": assets["MYR"]["id"],
                    "allocation_role": "OUTPUT",
                    "quantity": "416.5",
                    "value_myr": "416.5",
                    "source": "Hata fill",
                    "confidence": "EXACT",
                },
                {
                    "asset_id": assets["MYR"]["id"],
                    "allocation_role": "COST",
                    "quantity": "8.5",
                    "value_myr": "8.5",
                    "source": "Hata fee statement",
                    "confidence": "EXACT",
                },
            ],
        },
    )
    assert final_link.status_code == 201, final_link.text
    report = final_link.json()
    assert report["gross_input_myr"] == "425"
    assert report["net_output_myr"] == "416.5"
    assert report["explicit_cost_myr"] == "8.5"
    assert report["derived_deviation_myr"] == "0"
    assert report["total_path_cost_myr"] == "8.5"
    assert report["source"] == "Manual journey allocations over posted ledger events"
    assert report["confidence"] == "EXACT"
    leakage = client.get(
        "/api/reports/fee-leakage?start=2026-08-01T00:00:00Z&end=2026-08-03T00:00:00Z"
    ).json()
    assert leakage["explicit_myr"] == "8.5"
    assert leakage["derived_myr"] == "0"
    assert leakage["total_leakage_myr"] == "8.5"
    assert leakage["components"][0]["source_kind"] == "EXPLICIT"
    assert leakage["components"][0]["confidence"] == "EXACT"

    before_trade = {
        position["symbol"]: position
        for position in client.get("/api/reports/portfolio?as_of=2026-08-02T00:00:00Z").json()
    }
    assert before_trade["USDT"]["quantity"] == "100"
    assert before_trade["USDT"]["cost_basis_myr"] == "425"
    after_trade = {
        position["symbol"]: position
        for position in client.get("/api/reports/portfolio?as_of=2026-08-03T00:00:00Z").json()
    }
    assert after_trade["USDT"]["quantity"] == "0"
    assert after_trade["MYR"]["quantity"] == "416.5"

    another = client.post(
        "/api/journeys",
        json={
            "name": "Overallocated route",
            "journey_type": "WITHDRAWAL",
            "allocation_method": "Manual",
            "confidence": "EXACT",
        },
    ).json()
    rejected = client.post(
        f"/api/journeys/{another['id']}/events",
        json={
            "event_id": salary["id"],
            "allocations": [
                {
                    "asset_id": assets["USDT"]["id"],
                    "allocation_role": "INPUT",
                    "quantity": "1",
                    "value_myr": "4.25",
                    "source": "Unsupported duplicate attribution",
                    "confidence": "EXACT",
                }
            ],
        },
    )
    assert rejected.status_code == 409
    assert "exceeds the event quantity" in rejected.json()["detail"]

    assert client.post(f"/api/events/{trade['id']}/reverse", json={"reason": "corrected fill"}).status_code == 201
    historical = client.get(
        f"/api/reports/journeys/{journey_id}?as_of=2026-08-03T00:00:00Z"
    ).json()
    assert historical["net_output_myr"] == "416.5"
    current = client.get(f"/api/reports/journeys/{journey_id}").json()
    assert current["net_output_myr"] == "0"
    assert current["confidence"] == "MISSING_INPUT"


def test_channel_comparison_fixes_conditions_and_labels_simulation(client: TestClient) -> None:
    response = client.post(
        "/api/reports/channel-comparison",
        json={
            "amount_myr": "100",
            "compared_at": "2026-08-20T12:00:00+08:00",
            "reference_rate": "4.25",
            "reference_source": "Market midpoint at comparison time",
            "cashback_eligible": True,
            "paths": [
                {
                    "name": "Bank withdrawal",
                    "path_type": "WITHDRAWAL",
                    "mode": "ACTUAL",
                    "explicit_cost_myr": "1",
                    "derived_deviation_myr": "0.5",
                    "cashback_myr": "0",
                    "source": "Bank and exchange statements",
                    "confidence": "EXACT",
                },
                {
                    "name": "Alternative exchange",
                    "path_type": "WITHDRAWAL",
                    "mode": "SIMULATED",
                    "explicit_cost_myr": "0.5",
                    "derived_deviation_myr": "0.25",
                    "cashback_myr": "1",
                    "source": "Published fee schedule and reference rate",
                    "confidence": "ESTIMATED",
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    comparison = response.json()
    assert comparison["fixed_conditions"] == {
        "amount_myr": "100",
        "compared_at": "2026-08-20T04:00:00+00:00",
        "reference_rate": "4.25",
        "reference_source": "Market midpoint at comparison time",
        "cashback_eligible": True,
    }
    assert comparison["paths"][0]["effective_cost_myr"] == "1.5"
    assert comparison["paths"][0]["is_lowest_cost"] is False
    assert comparison["paths"][1]["effective_cost_myr"] == "-0.25"
    assert comparison["paths"][1]["cost_rate_percent"] == "-0.25"
    assert comparison["paths"][1]["mode"] == "SIMULATED"
    assert comparison["paths"][1]["confidence"] == "ESTIMATED"
    assert comparison["paths"][1]["is_lowest_cost"] is True
