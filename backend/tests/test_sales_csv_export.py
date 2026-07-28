"""Integration tests for server-side CSV report export.

Spec: sales-reporting/spec.md — "Server-Side CSV Report Export".
- custom-range CSV uses the SAME half-open configured-timezone window as the
  on-screen report, so its row count matches /sales/report/summary exactly
- reversed range -> 422 (no export query executed)
- preset `days` works
- non-staff -> 403
- filename matches the documented convention
- CSV body starts with the Excel-friendly UTF-8 BOM
"""

import csv
import io
import uuid
from datetime import datetime

import pytest

from core.database import get_redis
from core.security import create_access_token
from models.member import Member
from models.sale import SalesTransaction
from models.user import User
from services.timezone import CACHE_KEY


def _utc(y, mo, d, h, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s)


@pytest.fixture(autouse=True)
def _isolate_tz_cache():
    """Cold tz cache around each test (settings may change across tests)."""
    get_redis().delete(CACHE_KEY)
    yield
    get_redis().delete(CACHE_KEY)


@pytest.fixture
def non_staff_user(db_session):
    """A user whose role is neither admin nor staff -> require_staff 403."""
    suffix = uuid.uuid4().hex[:8]
    from core.security import get_password_hash

    user = User(
        username=f"outsider-{suffix}",
        email=f"outsider-{suffix}@example.com",
        password_hash=get_password_hash("secret123"),
        role="member",  # not admin/staff
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def non_staff_client(client, non_staff_user):
    token = create_access_token(data={"sub": str(non_staff_user.id)})
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture
def sales_in_window(db_session):
    """Seed one member + transactions in the Bogota 2026-01-10..20 window."""
    member = Member(
        first_name="Csv",
        last_name="Tester",
        email=f"csv-{uuid.uuid4().hex[:8]}@example.com",
        phone="555-0100",
        status="active",
    )
    db_session.add(member)
    db_session.flush()

    seed = [
        ("in-1", _utc(2026, 1, 10, 12, 0, 0), 100, "cash"),
        ("in-2", _utc(2026, 1, 15, 0, 0, 0), 250, "card"),
        ("in-3", _utc(2026, 1, 20, 4, 30, 0), 75, "transfer"),
        ("out-before", _utc(2026, 1, 9, 12, 0, 0), 999, "cash"),
        ("out-at-end", _utc(2026, 1, 21, 5, 0, 0), 888, "card"),
    ]
    for label, dt, amount, method in seed:
        db_session.add(
            SalesTransaction(
                member_id=member.id,
                amount=amount,
                payment_method=method,
                invoice_number=f"INV-CSV-{label}-{uuid.uuid4().hex[:6]}",
                transaction_date=dt,
            )
        )
    db_session.commit()
    return member


class TestCsvExportAuth:
    def test_unauthenticated_returns_401(self, client, sales_in_window):
        resp = client.get(
            "/api/sales/report/export",
            params={"start_date": "2026-01-10", "end_date": "2026-01-20"},
        )
        assert resp.status_code == 401

    def test_non_staff_returns_403(self, non_staff_client, sales_in_window):
        resp = non_staff_client.get(
            "/api/sales/report/export",
            params={"start_date": "2026-01-10", "end_date": "2026-01-20"},
        )
        assert resp.status_code == 403


class TestCsvExportWindow:
    def test_custom_range_csv_row_count_matches_summary(
        self, auth_client, sales_in_window
    ):
        params = {"start_date": "2026-01-10", "end_date": "2026-01-20"}
        summary = auth_client.get("/api/sales/report/summary", params=params).json()
        # 3 transactions inside the Bogota window (in-1, in-2, in-3).
        assert summary["total_transactions"] == 3

        resp = auth_client.get("/api/sales/report/export", params=params)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")

        body = resp.text
        assert body.startswith("\ufeff")  # UTF-8 BOM for Excel

        rows = list(csv.reader(io.StringIO(body.lstrip("\ufeff"))))
        assert len(rows) >= 2  # header + at least one data row
        header = rows[0]
        # Row count (excluding header) matches the on-screen summary count.
        assert len(rows) - 1 == summary["total_transactions"] == 3
        # Header documents the columns (transaction_date rendered in configured tz).
        assert any("date" in h.lower() for h in header)

    def test_reversed_range_returns_422(self, auth_client, sales_in_window):
        resp = auth_client.get(
            "/api/sales/report/export",
            params={"start_date": "2026-01-20", "end_date": "2026-01-10"},
        )
        assert resp.status_code == 422

    def test_partial_range_returns_422(self, auth_client, sales_in_window):
        resp = auth_client.get(
            "/api/sales/report/export",
            params={"start_date": "2026-01-10"},
        )
        assert resp.status_code == 422

    def test_preset_days_works(self, auth_client, sales_in_window):
        # Preset path: no dates -> days=365 default covers the seeded 2026 data
        # when 'now' is mocked/real; just assert a valid CSV comes back.
        resp = auth_client.get("/api/sales/report/export", params={"days": 365})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")

    def test_filename_matches_convention(self, auth_client, sales_in_window):
        import re

        resp = auth_client.get(
            "/api/sales/report/export",
            params={"start_date": "2026-01-10", "end_date": "2026-01-20"},
        )
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        match = re.search(r'filename="([^"]+)"', cd)
        assert match, f"no filename in Content-Disposition: {cd!r}"
        fname = match.group(1)
        assert re.match(r"^sales_report_.+\.csv$", fname), fname
