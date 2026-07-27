"""Integration tests for custom date-range reporting (spec:
custom-report-date-range/spec.md — custom interval succeeds, single-day
boundary succeeds, invalid interval rejected). Window contract (design.md):
half-open [start 00:00 app tz, (end+1) 00:00 app tz), app tz = Colombia
(UTC-5). DB columns are naive UTC, so seed datetimes are naive UTC.
"""

import uuid
from datetime import datetime

import pytest

from models.member import Member
from models.sale import SalesTransaction


def _utc(y, mo, d, h, mi=0, s=0):
    """Naive UTC datetime (the form the DB stores for naive timestamp columns)."""
    return datetime(y, mo, d, h, mi, s)


@pytest.fixture
def member_with_sales(db_session):
    """Seed one member + transactions. Window: Colombia 2026-01-10..20
    -> [2026-01-10 05:00 UTC, 2026-01-21 05:00 UTC) (half-open)."""
    member = Member(
        first_name="Range",
        last_name="Tester",
        email=f"range-{uuid.uuid4().hex[:8]}@example.com",
        phone="555-0100",
        status="active",
    )
    db_session.add(member)
    db_session.flush()

    seed = [
        # inside window
        ("in-1", _utc(2026, 1, 10, 12, 0, 0), 100, "cash"),
        ("in-2", _utc(2026, 1, 15, 0, 0, 0), 250, "card"),
        ("in-3", _utc(2026, 1, 20, 4, 30, 0), 75, "transfer"),  # Jan19 23:30 col
        # before window
        ("out-before", _utc(2026, 1, 9, 12, 0, 0), 999, "cash"),
        # at/after the half-open end bound -> excluded
        ("out-at-end", _utc(2026, 1, 21, 5, 0, 0), 888, "card"),
        ("out-after", _utc(2026, 1, 21, 6, 0, 0), 777, "cash"),
    ]
    created = {}
    for label, dt, amount, method in seed:
        tx = SalesTransaction(
            member_id=member.id,
            amount=amount,
            payment_method=method,
            invoice_number=f"INV-TEST-{label}-{uuid.uuid4().hex[:6]}",
            transaction_date=dt,
        )
        db_session.add(tx)
        created[label] = tx
    db_session.flush()
    db_session.commit()
    return {"member": member, "tx": created}


class TestReportSummaryDateRange:
    def test_reversed_range_returns_422(self, auth_client, member_with_sales):
        resp = auth_client.get(
            "/api/sales/report/summary",
            params={"start_date": "2026-01-20", "end_date": "2026-01-10"},
        )
        assert resp.status_code == 422

    def test_malformed_date_returns_422(self, auth_client, member_with_sales):
        resp = auth_client.get(
            "/api/sales/report/summary",
            params={"start_date": "not-a-date", "end_date": "2026-01-20"},
        )
        assert resp.status_code == 422

    def test_partial_range_returns_422(self, auth_client, member_with_sales):
        # Exactly one of start/end is an incomplete interval.
        resp = auth_client.get(
            "/api/sales/report/summary",
            params={"start_date": "2026-01-10"},
        )
        assert resp.status_code == 422

    def test_valid_window_excludes_outside_transactions(
        self, auth_client, member_with_sales
    ):
        resp = auth_client.get(
            "/api/sales/report/summary",
            params={"start_date": "2026-01-10", "end_date": "2026-01-20"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # in-1(100) + in-2(250) + in-3(75) = 425; out-* excluded
        assert body["total_transactions"] == 3
        assert float(body["total_revenue"]) == 425.0

    def test_single_day_window_includes_that_day(self, auth_client, member_with_sales):
        # Colombia 2026-01-15 -> [2026-01-15 05:00, 2026-01-16 05:00) UTC.
        # in-2 (2026-01-15 00:00 UTC) is BEFORE 05:00 UTC -> excluded. 0 in window.
        resp = auth_client.get(
            "/api/sales/report/summary",
            params={"start_date": "2026-01-15", "end_date": "2026-01-15"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_transactions"] == 0
        assert float(body["total_revenue"]) == 0.0

    def test_single_day_window_includes_midday_transaction(
        self, db_session, auth_client
    ):
        # Separate seed: a transaction clearly inside a single Colombia day.
        m = Member(
            first_name="Mid",
            last_name="Day",
            email=f"mid-{uuid.uuid4().hex[:8]}@example.com",
            phone="555-0100",
            status="active",
        )
        db_session.add(m)
        db_session.flush()
        # 2026-02-03 15:00 UTC == 2026-02-03 10:00 Colombia -> inside Feb 3.
        db_session.add(
            SalesTransaction(
                member_id=m.id,
                amount=300,
                payment_method="card",
                invoice_number=f"INV-MID-{uuid.uuid4().hex[:6]}",
                transaction_date=_utc(2026, 2, 3, 15, 0, 0),
            )
        )
        db_session.commit()
        resp = auth_client.get(
            "/api/sales/report/summary",
            params={"start_date": "2026-02-03", "end_date": "2026-02-03"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_transactions"] == 1
        assert float(body["total_revenue"]) == 300.0

    def test_presets_without_dates_still_work(self, auth_client, member_with_sales):
        # Backward compatibility: no dates -> no window filter, 200.
        resp = auth_client.get("/api/sales/report/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_transactions"] >= 6


class TestDashboardDateRange:
    def test_reversed_range_returns_422(self, auth_client, member_with_sales):
        resp = auth_client.get(
            "/api/sales/dashboard",
            params={"start_date": "2026-01-20", "end_date": "2026-01-10"},
        )
        assert resp.status_code == 422

    def test_partial_range_returns_422(self, auth_client, member_with_sales):
        resp = auth_client.get(
            "/api/sales/dashboard",
            params={"end_date": "2026-01-20"},
        )
        assert resp.status_code == 422

    def test_dashboard_and_summary_totals_agree_for_same_window(
        self, auth_client, member_with_sales
    ):
        params = {"start_date": "2026-01-10", "end_date": "2026-01-20"}
        dash = auth_client.get("/api/sales/dashboard", params=params)
        summ = auth_client.get("/api/sales/report/summary", params=params)
        assert dash.status_code == 200
        assert summ.status_code == 200

        dash_revenue = sum(p["amount"] for p in dash.json()["revenue_trend"])
        summary_revenue = float(summ.json()["total_revenue"])
        # Spec: "their shared totals MUST agree"
        assert dash_revenue == summary_revenue
        assert dash_revenue == 425.0

    def test_dashboard_window_excludes_outside(self, auth_client, member_with_sales):
        resp = auth_client.get(
            "/api/sales/dashboard",
            params={"start_date": "2026-01-10", "end_date": "2026-01-20"},
        )
        assert resp.status_code == 200
        total = sum(p["amount"] for p in resp.json()["revenue_trend"])
        assert total == 425.0

    def test_dashboard_presets_still_work(self, auth_client, member_with_sales):
        resp = auth_client.get("/api/sales/dashboard", params={"days": 30})
        assert resp.status_code == 200
        assert isinstance(resp.json()["revenue_trend"], list)
