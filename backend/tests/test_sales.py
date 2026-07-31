"""Tests for sales API endpoints."""

import pytest


def test_list_sales_unauthenticated(client):
    response = client.get("/api/sales")
    assert response.status_code == 401


def test_dashboard_authenticated(auth_client):
    response = auth_client.get("/api/sales/dashboard")
    assert response.status_code == 200


def test_report_summary_authenticated(auth_client):
    """Route should be reachable (not shadowed by /{transaction_id})."""
    response = auth_client.get("/api/sales/report/summary")
    assert response.status_code == 200


def test_transactions_wire_timestamps_are_explicit_utc(auth_client, db_session):
    """transaction_date/created_at must carry a Z suffix on the wire so JS
    `new Date()` resolves the instant as UTC instead of browser-local time."""
    import uuid as _uuid

    from datetime import datetime

    from models.member import Member
    from models.sale import SalesTransaction

    member = Member(
        first_name="Utc",
        last_name="Wire",
        email=f"utc-{_uuid.uuid4().hex[:8]}@example.com",
        phone="555-0199",
        status="active",
    )
    db_session.add(member)
    db_session.flush()
    db_session.add(
        SalesTransaction(
            member_id=member.id,
            amount=120.5,
            payment_method="card",
            invoice_number=f"INV-UTC-{_uuid.uuid4().hex[:8]}",
            transaction_date=datetime(2026, 1, 15, 12, 0, 0),
        )
    )
    db_session.commit()

    response = auth_client.get("/api/sales")
    assert response.status_code == 200
    body = response.json()
    txs = body.get("transactions", [])
    assert txs, "expected at least one seeded transaction"
    sample = next(t for t in txs if str(t["invoice_number"]).startswith("INV-UTC-"))
    assert sample["transaction_date"].endswith("Z")
    assert sample["created_at"].endswith("Z")
