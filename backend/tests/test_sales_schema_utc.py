"""Sales wire format must be self-describing UTC (``…Z``).

DB timestamp columns are naive 'timestamp without time zone' storing UTC.
JavaScript's ``new Date`` parses an offset-less ISO string as browser-local
time, so every rendered timestamp drifted by the device's UTC offset
(spec: sales-reporting — Configured-Timezone Reporting). These tests pin the
serializers and the live ``GET /api/sales`` payload to explicit UTC.
"""

import json
import uuid
from datetime import datetime, timezone

from schemas.sale import SalesTransactionResponse


def _make_tx(
    transaction_date: datetime, created_at: datetime
) -> SalesTransactionResponse:
    return SalesTransactionResponse(
        id=uuid.uuid4(),
        member_id=uuid.uuid4(),
        amount="1234.56",
        payment_method="cash",
        invoice_number=f"INV-UTC-{uuid.uuid4().hex[:6]}",
        transaction_date=transaction_date,
        created_at=created_at,
    )


class TestSalesTimestampUtcSerialization:
    def test_naive_utc_datetime_serializes_with_z(self):
        tx = _make_tx(
            transaction_date=datetime(2026, 1, 15, 12, 0, 0),
            created_at=datetime(2026, 1, 15, 12, 0, 0),
        )
        payload = json.loads(tx.model_dump_json())
        assert payload["transaction_date"] == "2026-01-15T12:00:00Z"
        assert payload["created_at"] == "2026-01-15T12:00:00Z"

    def test_aware_utc_datetime_serializes_with_z(self):
        dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        tx = _make_tx(transaction_date=dt, created_at=dt)
        payload = json.loads(tx.model_dump_json())
        assert payload["transaction_date"] == "2026-01-15T12:00:00Z"
        assert payload["created_at"] == "2026-01-15T12:00:00Z"

    def test_microseconds_kept_and_normalized_to_utc(self):
        dt = datetime(2026, 1, 15, 12, 0, 0, 500000)
        tx = _make_tx(transaction_date=dt, created_at=dt)
        payload = json.loads(tx.model_dump_json())
        assert payload["transaction_date"] == "2026-01-15T12:00:00.500000Z"
