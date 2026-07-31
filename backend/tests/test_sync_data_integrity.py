"""
Sync data-integrity tests (WS-8).

- Financial records are immutable via sync: sales_transactions allows INSERT
  only (business-logic.sales-{delete,update}-integrity, CWE-840).
- sales INSERT is validated: server-generated invoice number + non-negative
  amount (input-validation.sales-insert-validation, CWE-20/840).
- A member deleted via sync gets a durable audit row AND CV-template
  invalidation (stale-resource.member-delete-audit-invalidation, CWE-672/778).
"""

import uuid
from unittest.mock import AsyncMock

from models.audit_log import AuditLog
from models.sale import SalesTransaction


def _push(client, headers, *ops):
    return client.post(
        "/api/sync/push", headers=headers, json={"operations": list(ops)}
    ).json()


class TestSalesImmutability:
    def test_sales_update_rejected(self, client, auth_headers):
        r = _push(
            client,
            auth_headers,
            {
                "table": "sales_transactions",
                "operation": "UPDATE",
                "id": str(uuid.uuid4()),
                "data": {"amount": 999},
            },
        )
        assert r["results"][0]["status"] == "error"
        assert "immutable" in r["results"][0]["error"]

    def test_sales_delete_rejected(self, client, auth_headers):
        r = _push(
            client,
            auth_headers,
            {
                "table": "sales_transactions",
                "operation": "DELETE",
                "id": str(uuid.uuid4()),
            },
        )
        assert r["results"][0]["status"] == "error"
        assert "immutable" in r["results"][0]["error"]


class TestSalesInsertValidation:
    def test_negative_amount_rejected(self, client, auth_headers, sample_member):
        r = _push(
            client,
            auth_headers,
            {
                "table": "sales_transactions",
                "operation": "INSERT",
                "data": {
                    "member_id": str(sample_member.id),
                    "amount": -50,
                    "payment_method": "cash",
                },
            },
        )
        assert r["results"][0]["status"] == "error"
        assert "non-negative amount" in r["results"][0]["error"]

    def test_insert_generates_invoice_number(
        self, client, auth_headers, db_session, sample_member
    ):
        before = db_session.query(SalesTransaction).count()
        r = _push(
            client,
            auth_headers,
            {
                "table": "sales_transactions",
                "operation": "INSERT",
                "data": {
                    "member_id": str(sample_member.id),
                    "amount": 100,
                    "payment_method": "cash",
                    # invoice_number intentionally omitted -> server generates
                },
            },
        )
        assert r["results"][0]["status"] == "success", r
        after = db_session.query(SalesTransaction).count()
        assert after == before + 1
        # The server generated an invoice number for the new row.
        new_tx = (
            db_session.query(SalesTransaction)
            .order_by(SalesTransaction.created_at.desc())
            .first()
        )
        assert new_tx.invoice_number and new_tx.invoice_number.startswith("SYNC-")


class TestMemberDeleteAuditAndInvalidation:
    def test_member_delete_audits_and_invalidates_cv(
        self, client, auth_headers, db_session, sample_member, monkeypatch
    ):
        mock_notify = AsyncMock()
        monkeypatch.setattr("api.sync.notify_cv_invalidation", mock_notify)

        member_id = str(sample_member.id)
        r = _push(
            client,
            auth_headers,
            {"table": "members", "operation": "DELETE", "id": member_id},
        )
        assert r["results"][0]["status"] == "success", r

        # CV template invalidation was triggered for this member.
        mock_notify.assert_awaited_once_with(member_id)

        # A durable audit row was committed in the same transaction.
        db_session.expire_all()
        audit = (
            db_session.query(AuditLog)
            .filter_by(action="member_delete", resource_id=member_id)
            .first()
        )
        assert audit is not None, "member_delete audit row missing"
